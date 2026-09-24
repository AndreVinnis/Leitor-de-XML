import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import (
    ArquivoLote,
    Lote,
    Nota,
    SituacaoNota,
    StatusProcessamento,
    TipoNota,
    Usuario,
)

router = APIRouter()

LIMITE_DOWNLOAD_NOTAS = 500


def _filtrar_notas(
    db: Session,
    cliente_caso_id: int | None,
    status: str | None,
    tipo: str | None,
    q: str | None,
    data_inicio: date | None,
    data_fim: date | None,
    situacao: str | None = None,
):
    """Query base (Nota + status do ArquivoLote) com os filtros da tela Notas Fiscais."""
    query = db.query(Nota, ArquivoLote.status).outerjoin(
        ArquivoLote, ArquivoLote.nota_id == Nota.id
    )
    if cliente_caso_id is not None:
        query = query.filter(Nota.cliente_caso_id == cliente_caso_id)
    if status is not None:
        query = query.filter(ArquivoLote.status == StatusProcessamento(status))
    if tipo is not None:
        query = query.filter(Nota.tipo == TipoNota(tipo))
    if situacao is not None:
        query = query.filter(Nota.situacao == SituacaoNota(situacao))
    if q is not None:
        termo = f"%{q}%"
        query = query.filter(
            or_(
                Nota.numero.ilike(termo),
                Nota.chave_acesso.ilike(termo),
                Nota.emitente_nome.ilike(termo),
            )
        )
    if data_inicio is not None:
        query = query.filter(Nota.data_emissao >= data_inicio)
    if data_fim is not None:
        # data_emissao é DateTime e costuma ter hora (não só a meia-noite
        # do dia); comparar com "<=" contra a date pura excluiria o
        # próprio dia final. Soma 1 dia e usa "<" para incluir o dia
        # inteiro.
        query = query.filter(Nota.data_emissao < data_fim + timedelta(days=1))
    return query


@router.get("")
async def listar_notas(
    cliente_caso_id: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    q: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
    limit: int = 50,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Alimenta o dashboard ("Notas recentes") e a tela Notas Fiscais: numero,
    tipo, emitente_nome, destinatario_nome, data_emissao, valor_total, a
    situacao (autorizada/cancelada, ver app/models/models.py::Nota) e o
    status de processamento (que vive em ArquivoLote, não em Nota).
    """
    db: Session = SessionLocal()
    try:
        query = _filtrar_notas(db, cliente_caso_id, status, tipo, q, data_inicio, data_fim, situacao)

        total = query.count()
        resultados = query.order_by(Nota.criado_em.desc()).offset(offset).limit(limit).all()

        itens = [
            {
                "id": nota.id,
                "numero": nota.numero,
                "tipo": nota.tipo.value if nota.tipo is not None else None,
                "emitente_nome": nota.emitente_nome,
                "destinatario_nome": nota.destinatario_nome,
                "data_emissao": nota.data_emissao,
                # Decimal serializado como string, não float: é dinheiro e o
                # frontend não deve receber ponto flutuante nesse campo.
                "valor_total": str(nota.valor_total) if nota.valor_total is not None else None,
                "situacao": nota.situacao.value if nota.situacao is not None else None,
                "status": status_arquivo.value if status_arquivo is not None else None,
            }
            for nota, status_arquivo in resultados
        ]
        return {"itens": itens, "total": total}
    finally:
        db.close()


@router.get("/ids")
async def listar_ids_notas(
    cliente_caso_id: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    q: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    situacao: str | None = None,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Ids das notas que batem com os filtros de GET "" (sem paginação), para o
    "selecionar todas" da tela Notas Fiscais. Limitado a LIMITE_DOWNLOAD_NOTAS;
    `limitado` avisa quando o filtro tem mais notas que isso.
    """
    db: Session = SessionLocal()
    try:
        query = _filtrar_notas(db, cliente_caso_id, status, tipo, q, data_inicio, data_fim, situacao)
        total = query.count()
        resultados = query.order_by(Nota.criado_em.desc()).limit(LIMITE_DOWNLOAD_NOTAS).all()
        return {
            "ids": [nota.id for nota, _ in resultados],
            "total": total,
            "limitado": total > LIMITE_DOWNLOAD_NOTAS,
        }
    finally:
        db.close()


class DownloadNotasEntrada(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=LIMITE_DOWNLOAD_NOTAS)


def _caminho_xml_seguro(arquivo_origem: str | None) -> Path | None:
    """
    Resolve o caminho do XML e só o aceita se estiver dentro de UPLOAD_DIR e
    existir -- nunca serve um caminho arbitrário do disco.
    """
    from app.api.routes_upload import UPLOAD_DIR

    if not arquivo_origem:
        return None
    caminho = Path(arquivo_origem).resolve()
    if not caminho.is_relative_to(UPLOAD_DIR.resolve()) or not caminho.is_file():
        return None
    return caminho


@router.post("/download")
async def baixar_notas(
    entrada: DownloadNotasEntrada, usuario: Usuario = Depends(usuario_atual_ativo)
):
    """
    Devolve o XML original das notas pedidas: o próprio XML se for uma só,
    ou um ZIP se forem várias. Arquivos ausentes em disco são pulados e
    contados no header X-Arquivos-Ausentes.
    """
    ids = list(dict.fromkeys(entrada.ids))
    db: Session = SessionLocal()
    try:
        notas = db.query(Nota).filter(Nota.id.in_(ids)).all()
        caminhos = [(n, _caminho_xml_seguro(n.arquivo_origem)) for n in notas]
    finally:
        db.close()

    disponiveis = [(n, c) for n, c in caminhos if c is not None]
    ausentes = len(ids) - len(disponiveis)
    if not disponiveis:
        raise HTTPException(status_code=404, detail="Nenhum XML encontrado para as notas pedidas.")

    cabecalhos = {"X-Arquivos-Ausentes": str(ausentes)}
    if len(disponiveis) == 1:
        _, caminho = disponiveis[0]
        cabecalhos["Content-Disposition"] = f'attachment; filename="{caminho.name}"'
        return Response(content=caminho.read_bytes(), media_type="application/xml", headers=cabecalhos)

    buffer = io.BytesIO()
    usados: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nota, caminho in disponiveis:
            nome = caminho.name
            if nome in usados:
                nome = f"{caminho.stem}_{nota.id}{caminho.suffix}"
            usados.add(nome)
            zf.write(caminho, arcname=nome)
    cabecalhos["Content-Disposition"] = 'attachment; filename="notas_fiscais.zip"'
    return Response(content=buffer.getvalue(), media_type="application/zip", headers=cabecalhos)


@router.get("/lotes")
async def listar_lotes_com_erro(
    cliente_caso_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Alimenta a tela "Lotes com erro" (a partir do card Erros do Dashboard):
    só lotes com pelo menos um ArquivoLote em ERRO, com quem fez o upload e
    quando -- dado que já existe em Lote.criado_por_usuario_id/criado_em,
    mas nenhum endpoint expunha até agora (ver app/models/models.py).
    """
    db: Session = SessionLocal()
    try:
        erros_por_lote = (
            db.query(
                ArquivoLote.lote_id.label("lote_id"),
                func.count(ArquivoLote.id).label("arquivos_com_erro"),
            )
            .filter(ArquivoLote.status == StatusProcessamento.ERRO)
            .group_by(ArquivoLote.lote_id)
            .subquery()
        )

        query = (
            db.query(Lote, Usuario.nome, erros_por_lote.c.arquivos_com_erro)
            .join(erros_por_lote, erros_por_lote.c.lote_id == Lote.id)
            .outerjoin(Usuario, Usuario.id == Lote.criado_por_usuario_id)
        )
        if cliente_caso_id is not None:
            query = query.filter(Lote.cliente_caso_id == cliente_caso_id)

        total = query.count()
        resultados = query.order_by(Lote.criado_em.desc()).offset(offset).limit(limit).all()

        itens = [
            {
                "id": lote.id,
                "criado_em": lote.criado_em,
                "usuario_nome": usuario_nome,
                "total_arquivos": lote.total_arquivos,
                "arquivos_com_erro": arquivos_com_erro,
            }
            for lote, usuario_nome, arquivos_com_erro in resultados
        ]
        return {"itens": itens, "total": total}
    finally:
        db.close()


@router.get("/lotes/{lote_id}")
async def progresso_lote(lote_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    """
    Progresso agregado de um lote de upload, substituindo a necessidade de
    N chamadas a GET /upload/{task_id}/status (uma por arquivo).
    """
    db: Session = SessionLocal()
    try:
        lote = db.get(Lote, lote_id)
        if lote is None:
            raise HTTPException(status_code=404, detail="Lote não encontrado.")

        arquivos = db.query(ArquivoLote).filter(ArquivoLote.lote_id == lote_id).all()
        concluidos = sum(1 for a in arquivos if a.status != StatusProcessamento.PENDENTE)
        com_erro = sum(1 for a in arquivos if a.status == StatusProcessamento.ERRO)

        return {
            "lote_id": lote_id,
            "total_arquivos": lote.total_arquivos,
            "concluidos": concluidos,
            "com_erro": com_erro,
            "arquivos": [
                {
                    "id": a.id,
                    "nome_arquivo": a.nome_arquivo,
                    "status": a.status.value if a.status is not None else None,
                    "motivo_erro": a.motivo_erro,
                    "nota_id": a.nota_id,
                }
                for a in arquivos
            ],
        }
    finally:
        db.close()


@router.get("/{nota_id}")
async def obter_nota(nota_id: int, usuario: Usuario = Depends(usuario_atual_ativo)):
    """Cabeçalho da nota (+ status e arquivo de origem, via ArquivoLote) e seus itens."""
    db: Session = SessionLocal()
    try:
        nota = db.get(Nota, nota_id)
        if nota is None:
            raise HTTPException(status_code=404, detail="Nota não encontrada.")

        arquivo_lote = (
            db.query(ArquivoLote).filter(ArquivoLote.nota_id == nota.id).one_or_none()
        )

        return {
            "id": nota.id,
            "chave_acesso": nota.chave_acesso,
            "tipo": nota.tipo.value,
            "numero": nota.numero,
            "serie": nota.serie,
            "data_emissao": nota.data_emissao,
            "emitente_cnpj": nota.emitente_cnpj,
            "emitente_nome": nota.emitente_nome,
            "destinatario_cnpj": nota.destinatario_cnpj,
            "destinatario_nome": nota.destinatario_nome,
            # Dinheiro: string decimal, nunca float -- mesma regra de listar_notas.
            "valor_total": str(nota.valor_total) if nota.valor_total is not None else None,
            "situacao": nota.situacao.value if nota.situacao is not None else None,
            "cancelada_em": nota.cancelada_em,
            "cliente_caso_id": nota.cliente_caso_id,
            "status": arquivo_lote.status.value if arquivo_lote is not None and arquivo_lote.status is not None else None,
            "arquivo_origem": arquivo_lote.nome_arquivo if arquivo_lote is not None else None,
            "itens": [
                {
                    "id": item.id,
                    "numero_item": item.numero_item,
                    "codigo_produto": item.codigo_produto,
                    "descricao_original": item.descricao_original,
                    "ncm": item.ncm,
                    "cfop": item.cfop,
                    "unidade": item.unidade,
                    "quantidade": str(item.quantidade) if item.quantidade is not None else None,
                    "valor_unitario": str(item.valor_unitario) if item.valor_unitario is not None else None,
                    "valor_total": str(item.valor_total) if item.valor_total is not None else None,
                    "produto_canonico_id": item.produto_canonico_id,
                    "produto_canonico_nome": (
                        item.produto_canonico.nome_canonico if item.produto_canonico is not None else None
                    ),
                }
                for item in nota.itens
            ],
        }
    finally:
        db.close()
