from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.consulta_nl_sql import gerar_sql
from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.core.sql_seguranca import SqlInseguro, validar_e_finalizar_sql
from app.models.models import LogAuditoria, ProdutoCanonico, Usuario

router = APIRouter()


@router.post("")
async def consultar(
    pergunta: str = Body(..., embed=True),
    cliente_caso_id: int = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Traduz `pergunta` (linguagem natural) em SQL somente leitura via IA
    (RF-005/RF-006), valida contra a whitelist de tabelas/colunas (RNF-003)
    e executa escopado por cliente_caso_id. Toda consulta -- bloqueada ou
    não -- fica registrada em log_auditoria (RF-010).
    """
    db: Session = SessionLocal()
    try:
        canonicos = (
            db.query(ProdutoCanonico)
            .filter(ProdutoCanonico.cliente_caso_id == cliente_caso_id)
            .all()
        )
        canonicos_existentes = [
            {"id": c.id, "nome_canonico": c.nome_canonico, "categoria": c.categoria}
            for c in canonicos
        ]

        sql_bruto = gerar_sql(pergunta, canonicos_existentes)

        try:
            sql_final = validar_e_finalizar_sql(sql_bruto)
        except SqlInseguro as erro:
            db.add(
                LogAuditoria(
                    usuario_id=usuario.id,
                    acao="consulta_ia",
                    pergunta_usuario=pergunta,
                    sql_gerado=sql_bruto,
                    resultado_resumo=f"Consulta bloqueada: {erro}",
                )
            )
            db.commit()
            raise HTTPException(status_code=422, detail=f"Consulta bloqueada: {erro}")

        resultado = db.execute(text(sql_final), {"cliente_caso_id": cliente_caso_id})
        colunas = list(resultado.keys())
        linhas = [list(linha) for linha in resultado.fetchall()]

        db.add(
            LogAuditoria(
                usuario_id=usuario.id,
                acao="consulta_ia",
                pergunta_usuario=pergunta,
                sql_gerado=sql_final,
                resultado_resumo=f"{len(linhas)} linha(s) retornada(s)",
            )
        )
        db.commit()

        return {
            "pergunta": pergunta,
            "sql_gerado": sql_final,
            "colunas": colunas,
            "linhas": linhas,
            "total_linhas": len(linhas),
        }
    finally:
        db.close()
