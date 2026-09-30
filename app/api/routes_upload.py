import shutil
import unicodedata
import uuid
from pathlib import Path, PureWindowsPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.validadores import validar_cnpj_obrigatorio
from app.models.models import ArquivoLote, Lote, StatusProcessamento, Usuario
from app.workers.tasks import processar_xml_nfe

router = APIRouter()

UPLOAD_DIR = Path("/tmp/nfe_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# 999 e não 1000: o Starlette tem um teto interno de 1000 arquivos por
# multipart (proteção contra DoS, embutida em request.form() e não
# configurável nesta rota porque ela é síncrona de propósito -- ver
# docstring de upload_notas). Em 1000 esse teto dispara primeiro e devolve
# um 400 genérico do Starlette em vez da mensagem 422 em PT-BR abaixo.
LIMITE_ARQUIVOS_POR_LOTE = 999

_TAMANHO_BLOCO_COPIA = 1024 * 1024


class _UploadRecusado(Exception):
    """Arquivo do lote recusado (nome ou tamanho) -- vira HTTPException
    depois de desfazer o que já foi gravado em disco e no banco."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _nome_arquivo_seguro(nome: str | None) -> str:
    """
    Reduz o nome enviado pelo cliente ao basename, sem diretório nenhum.

    O nome vem do Content-Disposition do multipart e o Starlette não o limpa:
    `../../code/app/main.py` ou `/etc/x` gravariam fora do diretório do lote
    (com `--reload` e o bind mount do compose, isso vira execução de código).
    PureWindowsPath primeiro porque ele entende tanto a barra invertida quanto `/`.
    """
    base = Path(PureWindowsPath(nome or "").name).name
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    base = base.replace('"', "").strip()
    if base in ("", ".", ".."):
        raise _UploadRecusado(422, "Nome de arquivo inválido no lote.")
    if not base.lower().endswith(".xml"):
        raise _UploadRecusado(422, f"Arquivo '{base}' não é XML (.xml).")
    return base


def _copiar_com_limite(origem, destino: Path, restante_lote: int) -> int:
    """Copia em blocos e para assim que passar do teto por arquivo ou do
    que ainda cabe no lote. Devolve os bytes gravados."""
    limite_arquivo = settings.upload_max_bytes_por_arquivo
    total = 0
    with destino.open("wb") as f:
        while bloco := origem.read(_TAMANHO_BLOCO_COPIA):
            total += len(bloco)
            if total > limite_arquivo:
                raise _UploadRecusado(
                    413,
                    f"Arquivo '{destino.name}' excede o máximo de "
                    f"{limite_arquivo // (1024 * 1024)} MB por arquivo.",
                )
            if total > restante_lote:
                raise _UploadRecusado(
                    413,
                    "Lote excede o máximo de "
                    f"{settings.upload_max_bytes_por_lote // (1024 * 1024)} MB. "
                    "Divida em lotes menores.",
                )
            f.write(bloco)
    return total


@router.post("/upload")
def upload_notas(
    cliente_caso_id: int = Form(...),
    cnpj_cliente: str = Form(...),
    arquivos: list[UploadFile] = File(...),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Recebe um lote de arquivos XML, salva em disco e enfileira o
    processamento de cada um via Celery. Responde imediatamente
    (não trava a API esperando mil+ XMLs serem processados).

    Persiste o Lote e um ArquivoLote por arquivo ANTES de enfileirar as
    tasks -- sem isso, os cards do dashboard e o badge de status por nota
    não têm fonte de dados (o estado do Celery é efêmero).

    Handler síncrono (não `async def`) de propósito: todo o corpo é I/O
    bloqueante (disco, banco, broker), e um `async def` bloqueante trava a
    única event loop do processo (`uvicorn` roda sem `--workers`) para todo
    mundo, não só para quem fez o upload. `def` faz o FastAPI rodar isso
    numa thread do threadpool automaticamente.
    """
    if len(arquivos) > LIMITE_ARQUIVOS_POR_LOTE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Lote excede o máximo de {LIMITE_ARQUIVOS_POR_LOTE} arquivos "
                "por upload. Divida em lotes menores."
            ),
        )

    try:
        cnpj_cliente = validar_cnpj_obrigatorio(cnpj_cliente)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    lote_id = str(uuid.uuid4())
    lote_dir = UPLOAD_DIR / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)

    db: Session = SessionLocal()
    try:
        lote = Lote(
            id=lote_id,
            cliente_caso_id=cliente_caso_id,
            cnpj_cliente=cnpj_cliente,
            total_arquivos=len(arquivos),
            criado_por_usuario_id=usuario.id,
        )
        db.add(lote)
        db.flush()  # garante lote.id disponível para a FK de arquivo_lote

        arquivos_lote = []
        nomes_usados: set[str] = set()
        restante_lote = settings.upload_max_bytes_por_lote
        raiz_lote = lote_dir.resolve()
        for arquivo in arquivos:
            nome = _nome_arquivo_seguro(arquivo.filename)
            # Mesmo nome duas vezes no lote: sem isto o segundo sobrescrevia
            # o primeiro em disco, e as duas notas apontariam para o mesmo XML.
            candidato, contador = nome, 1
            while candidato.lower() in nomes_usados:
                contador += 1
                candidato = f"{contador}_{nome}"
            nome = candidato
            nomes_usados.add(nome.lower())

            destino = lote_dir / nome
            # Defesa em profundidade: mesmo padrão de
            # routes_notas._caminho_xml_seguro.
            if not destino.resolve().is_relative_to(raiz_lote):
                raise _UploadRecusado(422, "Nome de arquivo inválido no lote.")
            restante_lote -= _copiar_com_limite(arquivo.file, destino, restante_lote)

            arquivo_lote = ArquivoLote(
                lote_id=lote.id,
                nome_arquivo=nome,
                status=StatusProcessamento.PENDENTE,
            )
            db.add(arquivo_lote)
            db.flush()  # garante arquivo_lote.id antes de enfileirar a task
            arquivos_lote.append((destino, arquivo_lote))

        db.commit()

        # Só enfileira depois que o lote inteiro está persistido -- assim, se
        # o processamento de um arquivo já começar a rodar, a linha
        # ArquivoLote que ele precisa atualizar já existe.
        task_ids = []
        for destino, arquivo_lote in arquivos_lote:
            task = processar_xml_nfe.delay(
                str(destino), cnpj_cliente, cliente_caso_id, arquivo_lote.id
            )
            arquivo_lote.task_id = task.id
            task_ids.append(task.id)
        db.commit()

        return {
            "status": "processando",
            "lote_id": lote.id,
            "total_arquivos": len(arquivos),
            "task_ids": task_ids,
        }
    except _UploadRecusado as exc:
        db.rollback()
        shutil.rmtree(lote_dir, ignore_errors=True)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        db.close()


@router.get("/upload/{task_id}/status")
async def status_processamento(task_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}
