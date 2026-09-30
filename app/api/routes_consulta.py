import re
from typing import NoReturn, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.consulta_nl_sql import FINALIDADES_VALIDAS, MAX_CONSULTAS, gerar_plano_consulta
from app.core import limite_taxa
from app.core.auth import usuario_atual_ativo
from app.core.database import SessionConsulta, SessionLocal
from app.core.resposta_consulta import RespostaInvalida, ResultadoSql, montar_resposta
from app.core.sql_seguranca import SqlInseguro, validar_e_finalizar_sql
from app.models.models import LogAuditoria, ProdutoCanonico, Usuario

router = APIRouter()

# Teto da pergunta: cada chamada vai inteira para o Claude, então o tamanho
# é custo direto (e superfície de prompt injection).
TAMANHO_MAXIMO_PERGUNTA = 1000

_REGEX_LIMIT_FINAL = re.compile(r"LIMIT\s+(\d+)\s*;?\s*$", re.IGNORECASE)


def _juntar_sqls(sqls: list[tuple[str, str]], resposta_modelo: Optional[str] = None) -> str:
    """Formata todos os SQLs (finalidade, sql) juntos, legíveis, para o único
    campo de auditoria existente (logs_auditoria.sql_gerado, TEXT). O modelo
    de frase-resposta entra como comentário -- é o único registro de qual
    trecho da frase final veio de marcador (valor do banco) e qual foi texto
    livre escrito pela IA (RNF-004: rastreabilidade jurídica)."""
    partes = [
        f"-- Consulta {indice} ({finalidade})\n{sql};"
        for indice, (finalidade, sql) in enumerate(sqls, start=1)
    ]
    if resposta_modelo:
        partes.append(f"-- Modelo de resposta: {resposta_modelo}")
    return "\n\n".join(partes)


def _limite_da_consulta(sql: str) -> Optional[int]:
    """Extrai o valor do LIMIT final (sempre presente após
    validar_e_finalizar_sql) para detectar se a consulta pode ter sido
    truncada -- o número de linhas devolvidas bateu exatamente no teto."""
    match = _REGEX_LIMIT_FINAL.search(sql)
    return int(match.group(1)) if match else None


@router.post(
    "",
    dependencies=[
        Depends(limite_taxa.consulta_por_minuto),
        Depends(limite_taxa.consulta_por_dia),
    ],
)
def consultar(
    pergunta: str = Body(..., embed=True, min_length=1, max_length=TAMANHO_MAXIMO_PERGUNTA),
    cliente_caso_id: int = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Traduz `pergunta` (linguagem natural) em um plano de até MAX_CONSULTAS
    SQLs somente leitura via IA (RF-005/RF-006), valida cada um contra a
    whitelist de tabelas/colunas (RNF-003) e executa escopado por
    cliente_caso_id. Quando a pergunta é objetiva, a IA também devolve um
    modelo de frase-resposta com marcadores; quem decide o valor que
    preenche cada marcador -- a partir do resultado já validado e executado
    -- é app/core/resposta_consulta.py, nunca a IA diretamente. Toda
    consulta -- bloqueada, com erro de execução, ou bem-sucedida -- fica
    registrada em log_auditoria (RF-010), com todos os SQLs (e o modelo de
    resposta, quando houver) juntos no mesmo campo `sql_gerado` já existente.
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

        plano = gerar_plano_consulta(pergunta, canonicos_existentes)

        def _bloquear(motivo: str, sqls: list[tuple[str, str]]) -> NoReturn:
            db.add(
                LogAuditoria(
                    usuario_id=usuario.id,
                    acao="consulta_ia",
                    pergunta_usuario=pergunta,
                    sql_gerado=_juntar_sqls(sqls, plano.resposta_modelo),
                    resultado_resumo=f"Consulta bloqueada: {motivo}",
                )
            )
            db.commit()
            raise HTTPException(status_code=422, detail=f"Consulta bloqueada: {motivo}")

        sqls_brutos = [(c.finalidade, c.sql) for c in plano.consultas]

        if not (1 <= len(plano.consultas) <= MAX_CONSULTAS):
            _bloquear(
                f"plano com {len(plano.consultas)} consulta(s), esperado entre 1 e {MAX_CONSULTAS}.",
                sqls_brutos,
            )

        finalidades = [c.finalidade for c in plano.consultas]
        if any(f not in FINALIDADES_VALIDAS for f in finalidades):
            _bloquear(f"finalidade de consulta desconhecida em {finalidades}.", sqls_brutos)
        if finalidades.count("fontes") > 1 or finalidades.count("listagem") > 1:
            _bloquear("plano com mais de uma consulta de fontes/listagem.", sqls_brutos)
        if "listagem" in finalidades and any(f in ("resposta", "fontes") for f in finalidades):
            _bloquear("plano mistura finalidade 'listagem' com 'resposta'/'fontes'.", sqls_brutos)

        tem_resposta = "resposta" in finalidades
        if tem_resposta and finalidades.count("fontes") != 1:
            _bloquear(
                "consulta de finalidade 'resposta' precisa vir acompanhada de "
                "exatamente uma consulta 'fontes'.",
                sqls_brutos,
            )
        if tem_resposta and not plano.resposta_modelo:
            _bloquear(
                "plano tem consulta de finalidade 'resposta' mas nenhum modelo de frase-resposta.",
                sqls_brutos,
            )
        if plano.resposta_modelo and not tem_resposta:
            _bloquear(
                "plano tem modelo de frase-resposta mas nenhuma consulta de finalidade 'resposta'.",
                sqls_brutos,
            )

        sqls_finais: list[tuple[str, str]] = []
        try:
            for consulta in plano.consultas:
                sqls_finais.append((consulta.finalidade, validar_e_finalizar_sql(consulta.sql)))
        except SqlInseguro as erro:
            _bloquear(str(erro), sqls_brutos)

        # O SQL gerado roda numa conexão própria (usuário só-SELECT em
        # produção -- ver app/core/database.py::SessionConsulta); canônicos e
        # LogAuditoria continuam na conexão principal.
        db_consulta: Session = SessionConsulta()
        try:
            resultados_por_indice: list[ResultadoSql] = []
            consultas_executadas = []
            for finalidade, sql_final in sqls_finais:
                resultado = db_consulta.execute(
                    text(sql_final), {"cliente_caso_id": cliente_caso_id}
                )
                colunas = list(resultado.keys())
                linhas = [list(linha) for linha in resultado.fetchall()]
                resultados_por_indice.append(
                    ResultadoSql(finalidade=finalidade, colunas=colunas, linhas=linhas)
                )
                limite = _limite_da_consulta(sql_final)
                truncado = limite is not None and len(linhas) >= limite
                consultas_executadas.append(
                    {
                        "finalidade": finalidade,
                        "sql": sql_final,
                        "colunas": colunas,
                        "linhas": linhas,
                        "total_linhas": len(linhas),
                        "truncado": truncado,
                    }
                )
        except SQLAlchemyError as erro:
            db_consulta.rollback()
            db.add(
                LogAuditoria(
                    usuario_id=usuario.id,
                    acao="consulta_ia",
                    pergunta_usuario=pergunta,
                    sql_gerado=_juntar_sqls(sqls_finais, plano.resposta_modelo),
                    resultado_resumo=f"Erro ao executar consulta gerada: {type(erro).__name__}.",
                )
            )
            db.commit()
            raise HTTPException(
                status_code=502,
                detail="Não foi possível executar a consulta gerada. Tente reformular a pergunta.",
            ) from erro
        finally:
            db_consulta.close()

        resposta_texto = None
        motivo_resposta_nula = None
        if plano.resposta_modelo:
            try:
                resposta_texto = montar_resposta(
                    plano.resposta_modelo, resultados_por_indice, pergunta, canonicos_existentes
                )
            except Exception as erro:
                # RespostaInvalida é o caminho esperado; qualquer outro bug de
                # formatação também degrada para "sem resposta" -- nunca
                # derruba a consulta inteira por causa da frase.
                motivo_resposta_nula = str(erro)

        # A tabela principal exibida é a de fontes/listagem; se só houver
        # consulta "resposta" (sem fontes/listagem), cai na primeira -- não
        # deveria acontecer, a validação estrutural acima já exige o par.
        indice_principal = next(
            (i for i, f in enumerate(finalidades) if f in ("fontes", "listagem")), 0
        )
        principal = consultas_executadas[indice_principal]

        resumo = (
            f'Resposta: "{resposta_texto}"'
            if resposta_texto
            else f"Resposta não montada: {motivo_resposta_nula}"
            if motivo_resposta_nula
            else "Sem modelo de resposta (consulta de listagem)"
        )
        resumo += f" | {len(sqls_finais)} consulta(s), {principal['total_linhas']} linha(s) nas fontes"
        if principal["truncado"]:
            resumo += " (fontes truncadas pelo LIMIT -- pode haver mais linhas)"

        db.add(
            LogAuditoria(
                usuario_id=usuario.id,
                acao="consulta_ia",
                pergunta_usuario=pergunta,
                sql_gerado=_juntar_sqls(sqls_finais, plano.resposta_modelo),
                resultado_resumo=resumo,
            )
        )
        db.commit()

        return {
            "pergunta": pergunta,
            "resposta": resposta_texto,
            "resposta_pretendida": bool(plano.resposta_modelo),
            "sql_gerado": _juntar_sqls(sqls_finais, plano.resposta_modelo),
            "consultas": consultas_executadas,
            "colunas": principal["colunas"],
            "linhas": principal["linhas"],
            "total_linhas": principal["total_linhas"],
            "fontes_truncadas": principal["truncado"],
        }
    finally:
        db.close()
