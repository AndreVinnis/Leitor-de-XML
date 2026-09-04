import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import ArquivoLote, Lote, StatusProcessamento, Usuario
from app.workers.tasks import processar_xml_nfe

router = APIRouter()

UPLOAD_DIR = Path("/tmp/nfe_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_notas(
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
    """
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
        for arquivo in arquivos:
            destino = lote_dir / arquivo.filename
            with destino.open("wb") as f:
                shutil.copyfileobj(arquivo.file, f)

            arquivo_lote = ArquivoLote(
                lote_id=lote.id,
                nome_arquivo=arquivo.filename,
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
    finally:
        db.close()


@router.get("/upload/{task_id}/status")
async def status_processamento(task_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}
