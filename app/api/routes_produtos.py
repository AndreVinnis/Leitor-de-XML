from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import (
    ItemNota,
    LogAuditoria,
    Nota,
    ProdutoCanonico,
    StatusRevisao,
    SugestaoNormalizacao,
    Usuario,
)
from app.workers.tasks import normalizar_produtos_pendentes

router = APIRouter()


@router.post("/normalizar")
async def disparar_normalizacao(
    cliente_caso_id: int = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Dispara, de forma assíncrona, a normalização por IA de todos os itens
    pendentes (sem produto_canonico e sem sugestão já criada) de um caso.
    """
    task = normalizar_produtos_pendentes.delay(cliente_caso_id)
    return {"status": "processando", "task_id": task.id}


@router.get("/normalizar/{task_id}/status")
async def status_normalizacao(task_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}


@router.get("/canonicos")
async def listar_canonicos(
    cliente_caso_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """Lista os produtos canônicos de um caso, para popular o filtro "Categoria" da tela."""
    db: Session = SessionLocal()
    try:
        canonicos = (
            db.query(ProdutoCanonico)
            .filter(ProdutoCanonico.cliente_caso_id == cliente_caso_id)
            .order_by(ProdutoCanonico.nome_canonico)
            .all()
        )
        return [
            {"id": c.id, "nome_canonico": c.nome_canonico, "categoria": c.categoria}
            for c in canonicos
        ]
    finally:
        db.close()


@router.get("/sugestoes")
async def listar_sugestoes(
    cliente_caso_id: int,
    status: str = "pendente",
    categoria: str | None = None,
    fornecedor: str | None = None,
    busca: str | None = None,
    limit: int = 50,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Lista sugestões de normalização (join com o item, a nota e o canônico
    sugerido) de um caso, para revisão humana. `status="todos"` remove o
    filtro por status; qualquer outro valor precisa bater com StatusRevisao.
    """
    db: Session = SessionLocal()
    try:
        query = (
            db.query(SugestaoNormalizacao, ItemNota, Nota, ProdutoCanonico)
            .join(ItemNota, ItemNota.id == SugestaoNormalizacao.item_nota_id)
            .join(Nota, Nota.id == ItemNota.nota_id)
            .join(
                ProdutoCanonico,
                ProdutoCanonico.id == SugestaoNormalizacao.produto_canonico_sugerido_id,
            )
            .filter(Nota.cliente_caso_id == cliente_caso_id)
        )

        if status != "todos":
            try:
                status_enum = StatusRevisao(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Status inválido: {status}")
            query = query.filter(SugestaoNormalizacao.status == status_enum)

        if categoria is not None:
            query = query.filter(ProdutoCanonico.categoria == categoria)
        if fornecedor is not None:
            query = query.filter(Nota.emitente_nome == fornecedor)
        if busca is not None:
            termo = f"%{busca}%"
            query = query.filter(
                or_(
                    ItemNota.descricao_original.ilike(termo),
                    ProdutoCanonico.nome_canonico.ilike(termo),
                )
            )

        total = query.count()
        resultados = (
            query.order_by(SugestaoNormalizacao.criado_em.desc(), SugestaoNormalizacao.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        itens = [
            {
                "id": sugestao.id,
                "item_nota_id": item.id,
                "descricao_original": item.descricao_original,
                "produto_canonico_sugerido_id": sugestao.produto_canonico_sugerido_id,
                "nome_canonico": canonico.nome_canonico,
                "categoria": canonico.categoria,
                "fornecedor": nota.emitente_nome,
                "confianca": float(sugestao.confianca),
                "status": sugestao.status.value,
                "criado_em": sugestao.criado_em,
            }
            for sugestao, item, nota, canonico in resultados
        ]
        return {"itens": itens, "total": total}
    finally:
        db.close()


def _revisar(db: Session, sugestao_id: int, usuario_id: int, confirmado: bool) -> dict:
    """
    Fluxo compartilhado por confirmar/rejeitar, unitário ou em lote: marca o
    status da sugestão, grava quem/quando revisou, propaga
    produto_canonico_id ao item quando confirmado, e registra o LogAuditoria
    correspondente. Não commita -- quem chama decide o momento (uma sugestão
    por vez ou um lote inteiro em uma única transação).
    """
    sugestao = db.get(SugestaoNormalizacao, sugestao_id)
    if sugestao is None:
        return {"status": "erro", "motivo": "sugestão não encontrada"}

    sugestao.status = StatusRevisao.CONFIRMADO if confirmado else StatusRevisao.REJEITADO
    sugestao.revisado_por_usuario_id = usuario_id
    sugestao.revisado_em = datetime.utcnow()

    item = db.get(ItemNota, sugestao.item_nota_id)

    if confirmado:
        item.produto_canonico_id = sugestao.produto_canonico_sugerido_id
        acao = "confirmacao_sugestao_normalizacao"
        resumo = (
            f"Sugestão {sugestao_id} confirmada: item '{item.descricao_original}' "
            f"-> produto canônico {item.produto_canonico_id}"
        )
    else:
        acao = "rejeicao_sugestao_normalizacao"
        resumo = f"Sugestão {sugestao_id} rejeitada"

    db.add(LogAuditoria(usuario_id=usuario_id, acao=acao, resultado_resumo=resumo))

    return {"status": "ok", "sugestao_id": sugestao_id}


@router.post("/sugestoes/lote/confirmar")
async def confirmar_sugestoes_lote(
    ids: list[int] = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultados = [_revisar(db, sugestao_id, usuario.id, confirmado=True) for sugestao_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()


@router.post("/sugestoes/lote/rejeitar")
async def rejeitar_sugestoes_lote(
    ids: list[int] = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultados = [_revisar(db, sugestao_id, usuario.id, confirmado=False) for sugestao_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/confirmar")
async def confirmar_sugestao(
    sugestao_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultado = _revisar(db, sugestao_id, usuario.id, confirmado=True)
        db.commit()
        return resultado
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/rejeitar")
async def rejeitar_sugestao(
    sugestao_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultado = _revisar(db, sugestao_id, usuario.id, confirmado=False)
        db.commit()
        return resultado
    finally:
        db.close()
