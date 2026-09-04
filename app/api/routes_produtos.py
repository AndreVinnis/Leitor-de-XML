from datetime import datetime

from fastapi import APIRouter, Body
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import ItemNota, Nota, StatusRevisao, SugestaoNormalizacao
from app.workers.tasks import normalizar_produtos_pendentes

router = APIRouter()


@router.post("/normalizar")
async def disparar_normalizacao(cliente_caso_id: int = Body(..., embed=True)):
    """
    Dispara, de forma assíncrona, a normalização por IA de todos os itens
    pendentes (sem produto_canonico e sem sugestão já criada) de um caso.
    """
    task = normalizar_produtos_pendentes.delay(cliente_caso_id)
    return {"status": "processando", "task_id": task.id}


@router.get("/normalizar/{task_id}/status")
async def status_normalizacao(task_id: str):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}


@router.get("/sugestoes")
async def listar_sugestoes(cliente_caso_id: int, status: str = "pendente"):
    """Lista sugestões de normalização (join com o item e a nota) de um caso, para revisão humana."""
    db: Session = SessionLocal()
    try:
        query = (
            db.query(SugestaoNormalizacao, ItemNota)
            .join(ItemNota, ItemNota.id == SugestaoNormalizacao.item_nota_id)
            .join(Nota, Nota.id == ItemNota.nota_id)
            .filter(SugestaoNormalizacao.status == StatusRevisao(status))
            .filter(Nota.cliente_caso_id == cliente_caso_id)
        )

        resultados = []
        for sugestao, item in query.all():
            resultados.append(
                {
                    "id": sugestao.id,
                    "item_nota_id": item.id,
                    "descricao_original": item.descricao_original,
                    "produto_canonico_sugerido_id": sugestao.produto_canonico_sugerido_id,
                    "confianca": float(sugestao.confianca),
                    "status": sugestao.status.value,
                    "criado_em": sugestao.criado_em,
                }
            )
        return resultados
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/confirmar")
async def confirmar_sugestao(sugestao_id: int, usuario_id: int = Body(..., embed=True)):
    db: Session = SessionLocal()
    try:
        sugestao = db.get(SugestaoNormalizacao, sugestao_id)
        if sugestao is None:
            return {"status": "erro", "motivo": "sugestão não encontrada"}

        sugestao.status = StatusRevisao.CONFIRMADO
        sugestao.revisado_por_usuario_id = usuario_id
        sugestao.revisado_em = datetime.utcnow()

        item = db.get(ItemNota, sugestao.item_nota_id)
        item.produto_canonico_id = sugestao.produto_canonico_sugerido_id

        db.commit()
        return {"status": "ok", "sugestao_id": sugestao_id}
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/rejeitar")
async def rejeitar_sugestao(sugestao_id: int, usuario_id: int = Body(..., embed=True)):
    db: Session = SessionLocal()
    try:
        sugestao = db.get(SugestaoNormalizacao, sugestao_id)
        if sugestao is None:
            return {"status": "erro", "motivo": "sugestão não encontrada"}

        sugestao.status = StatusRevisao.REJEITADO
        sugestao.revisado_por_usuario_id = usuario_id
        sugestao.revisado_em = datetime.utcnow()

        db.commit()
        return {"status": "ok", "sugestao_id": sugestao_id}
    finally:
        db.close()
