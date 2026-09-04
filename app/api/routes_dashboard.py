from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import ArquivoLote, Lote, StatusProcessamento, Usuario

router = APIRouter()


@router.get("/estatisticas")
async def estatisticas(
    cliente_caso_id: int | None = None,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Os 3 cards do dashboard (Figma), contados sobre ArquivoLote -- é lá que
    vive o status de processamento, não em Nota (ver app/models/models.py).
    """
    db: Session = SessionLocal()
    try:
        query = db.query(ArquivoLote).join(Lote, Lote.id == ArquivoLote.lote_id)
        if cliente_caso_id is not None:
            query = query.filter(Lote.cliente_caso_id == cliente_caso_id)

        notas_processadas = query.filter(ArquivoLote.status == StatusProcessamento.SUCESSO).count()
        pendentes = query.filter(ArquivoLote.status == StatusProcessamento.PENDENTE).count()
        erros = query.filter(ArquivoLote.status == StatusProcessamento.ERRO).count()

        return {
            "notas_processadas": notas_processadas,
            "pendentes": pendentes,
            "erros": erros,
        }
    finally:
        db.close()
