"""
Validação de segurança do SQL gerado por IA (app/ai/consulta_nl_sql.py) antes
de qualquer execução no banco -- ver RNF-003 em Documentação/Instruções do
projeto. Pura e testável sem Gemini/banco: só string in, string (ou exceção)
out.

Limitação conhecida: o RNF-003 também pede uma conexão de banco somente
leitura como camada extra de defesa. Essa validação já bloqueia comandos de
escrita antes de chegar no banco, mas criar um usuário MySQL com grant
SELECT-only é uma mudança de infra fora do escopo deste MVP -- vale fazer
antes de rodar com dado real de cliente em produção.
"""

import re

TABELAS_PERMITIDAS = {"notas", "itens_nota", "produtos_canonicos"}

PALAVRAS_PROIBIDAS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "EXEC",
    "EXECUTE",
    "CALL",
    "MERGE",
    "OUTFILE",
    "LOAD_FILE",
    "INFORMATION_SCHEMA",
    "PRAGMA",
]

_REGEX_PALAVRA_PROIBIDA = re.compile(
    r"\b(" + "|".join(PALAVRAS_PROIBIDAS) + r")\b", re.IGNORECASE
)
_REGEX_TABELA = re.compile(r"\b(?:FROM|JOIN)\s+([`\"\[]?)(\w+)\1", re.IGNORECASE)
_REGEX_LIMIT = re.compile(r"\bLIMIT\b", re.IGNORECASE)

LIMIT_PADRAO = 200


class SqlInseguro(ValueError):
    """Levantada quando o SQL gerado pela IA reprova na validação de segurança."""


def validar_e_finalizar_sql(sql: str) -> str:
    """
    Valida `sql` contra a whitelist de tabelas/colunas e a política de
    somente-leitura, e devolve a versão final (com LIMIT garantido) pronta
    para execução. Levanta SqlInseguro (fail-closed) em qualquer reprovação.
    """
    sql_limpo = sql.strip().rstrip(";").strip()

    if not sql_limpo:
        raise SqlInseguro("SQL vazio.")

    if ";" in sql_limpo:
        raise SqlInseguro("Apenas um único comando SQL é permitido.")

    if not re.match(r"^SELECT\b", sql_limpo, re.IGNORECASE):
        raise SqlInseguro("Apenas comandos SELECT são permitidos.")

    match_proibida = _REGEX_PALAVRA_PROIBIDA.search(sql_limpo)
    if match_proibida:
        raise SqlInseguro(f"Palavra-chave não permitida: {match_proibida.group(1)}")

    tabelas = {nome.lower() for _, nome in _REGEX_TABELA.findall(sql_limpo)}
    tabelas_fora_da_whitelist = tabelas - TABELAS_PERMITIDAS
    if tabelas_fora_da_whitelist:
        raise SqlInseguro(
            f"Tabela(s) não permitida(s): {', '.join(sorted(tabelas_fora_da_whitelist))}"
        )

    if ":cliente_caso_id" not in sql_limpo:
        raise SqlInseguro(
            "A consulta precisa filtrar por :cliente_caso_id para não vazar dados de outro caso."
        )

    if not _REGEX_LIMIT.search(sql_limpo):
        sql_limpo = f"{sql_limpo} LIMIT {LIMIT_PADRAO}"

    return sql_limpo
