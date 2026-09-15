from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import requer_administrador
from app.core.database import SessionLocal
from app.models.models import LogAuditoria, Usuario

router = APIRouter()


def _serializar(log: LogAuditoria, usuario_nome: str) -> dict:
    return {
        "id": log.id,
        "criado_em": log.criado_em,
        "usuario_nome": usuario_nome,
        "acao": log.acao,
        "resumo": log.resultado_resumo,
        "pergunta_usuario": log.pergunta_usuario,
        "sql_gerado": log.sql_gerado,
    }


@router.get("")
async def listar_logs_auditoria(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: Usuario = Depends(requer_administrador),
):
    """
    Lista os logs de auditoria (não escopado por caso -- logs_auditoria não
    tem cliente_caso_id, mesma lógica de RBAC global de routes_usuarios.py).
    Somente leitura: a tabela é populada por outras rotas, nunca por esta.
    """
    db: Session = SessionLocal()
    try:
        query = db.query(LogAuditoria, Usuario.nome).join(Usuario, Usuario.id == LogAuditoria.usuario_id)

        if data_inicio is not None:
            query = query.filter(LogAuditoria.criado_em >= data_inicio)
        if data_fim is not None:
            # criado_em é DateTime; soma 1 dia e usa "<" para incluir o dia inteiro
            query = query.filter(LogAuditoria.criado_em < data_fim + timedelta(days=1))

        total = query.count()
        resultados = query.order_by(LogAuditoria.criado_em.desc()).offset(offset).limit(limit).all()
        return {"itens": [_serializar(log, nome) for log, nome in resultados], "total": total}
    finally:
        db.close()
