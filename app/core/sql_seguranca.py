"""
Validação de segurança do SQL gerado por IA (app/ai/consulta_nl_sql.py) antes
de qualquer execução no banco -- ver RNF-003 em Documentação/Instruções do
projeto e Documentação/Segurança. Pura e testável sem IA/banco: só string in,
string (ou exceção) out.

A análise estrutural usa um parser SQL de verdade (sqlglot, dialeto MySQL),
não regex: a versão anterior só enxergava a tabela logo depois de FROM/JOIN,
e `FROM notas, usuarios` (join por vírgula) passava direto pela whitelist.
O SQL devolvido continua sendo a string original (sem re-emitir pelo
sqlglot), para o texto auditado em logs_auditoria ser exatamente o que rodou.

Esta validação é a primeira camada. A segunda é a conexão da consulta, que
usa um usuário MySQL só com SELECT nas três tabelas permitidas
(app/core/database.py::SessionConsulta, quando DATABASE_URL_CONSULTA está
configurada).

Limitação conhecida e aceita: a checagem de :cliente_caso_id é de presença,
não de semântica -- `... WHERE situacao = 'autorizada' OR cliente_caso_id =
:cliente_caso_id` passa e devolve dados de outros casos. Isso é coerente com
a decisão deliberada de não haver isolamento por caso entre usuários (ver
CLAUDE.md); o parâmetro existe para escopo de pergunta, não de acesso.
"""


import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.tokens import TokenType

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
    "INTO",
    "DUMPFILE",
    "HANDLER",
    "LOCK",
]

_REGEX_PALAVRA_PROIBIDA = re.compile(
    r"\b(" + "|".join(PALAVRAS_PROIBIDAS) + r")\b", re.IGNORECASE
)

# Funções que vazam informação do servidor ou servem para DoS/canal lateral
# (SLEEP/BENCHMARK). Checadas duas vezes: por regex no texto (com os
# literais mascarados) e pelo nome de cada função na árvore, que pega também
# a grafia entre crases (`sleep`(600)), invisível para a regex. O sqlglot
# normaliza algumas para nós próprios (DATABASE() vira CurrentSchema,
# VERSION() vira CurrentVersion), cobertos em _NOS_PROIBIDOS. Nenhuma dessas
# checagens é o controle de DoS de verdade: esse é o max_execution_time da
# conexão de consulta (app/core/database.py).
FUNCOES_PROIBIDAS = [
    "SLEEP",
    "BENCHMARK",
    "LOAD_FILE",
    "GET_LOCK",
    "RELEASE_LOCK",
    "IS_FREE_LOCK",
    "USER",
    "CURRENT_USER",
    "SESSION_USER",
    "SYSTEM_USER",
    "DATABASE",
    "SCHEMA",
    "VERSION",
    "CONNECTION_ID",
    # Esperas de replicação: podem segurar a conexão por tempo arbitrário.
    "WAIT_FOR_EXECUTED_GTID_SET",
    "WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS",
    "SOURCE_POS_WAIT",
    "MASTER_POS_WAIT",
]
_REGEX_FUNCAO_PROIBIDA = re.compile(
    r"\b(" + "|".join(FUNCOES_PROIBIDAS) + r")\s*\(", re.IGNORECASE
)
_NOS_PROIBIDOS = (exp.CurrentUser, exp.CurrentSchema, exp.CurrentVersion, exp.SessionParameter)

_TOKENS_LITERAL = {
    TokenType.STRING,
    TokenType.NATIONAL_STRING,
    TokenType.RAW_STRING,
    TokenType.BIT_STRING,
    TokenType.HEX_STRING,
    TokenType.BYTE_STRING,
    TokenType.UNICODE_STRING,
    TokenType.HEREDOC_STRING,
}

LIMIT_PADRAO = 200


class SqlInseguro(ValueError):
    """Levantada quando o SQL gerado pela IA reprova na validação de segurança."""


def _mascarar_literais(sql: str) -> str:
    """
    Troca o conteúdo de cada literal de texto por espaços, mantendo as
    posições. As checagens por texto (comentário, `@`, palavras e funções
    proibidas, placeholder) rodam sobre esta versão: sem isso, uma busca
    legítima como `LIKE '%#80%'` (lixa nº 80) era recusada como comentário, e
    um `':cliente_caso_id'` entre aspas contaria como filtro. O tokenizer do
    sqlglot trata o escape com barra invertida igual ao MySQL (sql_mode sem
    NO_BACKSLASH_ESCAPES).
    """
    try:
        tokens = sqlglot.tokenize(sql, read="mysql")
    except SqlglotError as exc:
        raise SqlInseguro("SQL não reconhecido pelo validador.") from exc
    caracteres = list(sql)
    for token in tokens:
        if token.token_type in _TOKENS_LITERAL:
            for posicao in range(token.start, token.end + 1):
                caracteres[posicao] = " "
    return "".join(caracteres)


def validar_e_finalizar_sql(sql: str) -> str:
    """
    Valida `sql` contra a whitelist de tabelas/colunas e a política de
    somente-leitura, e devolve a versão final (com LIMIT garantido) pronta
    para execução. Levanta SqlInseguro (fail-closed) em qualquer reprovação.
    """
    sql_limpo = sql.strip().rstrip(";").strip()

    if not sql_limpo:
        raise SqlInseguro("SQL vazio.")

    # Todas as checagens por texto olham a versão com literais mascarados;
    # o parse e a string devolvida continuam sendo a original.
    texto = _mascarar_literais(sql_limpo)

    if ";" in texto:
        raise SqlInseguro("Apenas um único comando SQL é permitido.")

    if not re.match(r"^SELECT\b", texto, re.IGNORECASE):
        raise SqlInseguro("Apenas comandos SELECT são permitidos.")

    match_proibida = _REGEX_PALAVRA_PROIBIDA.search(texto)
    if match_proibida:
        raise SqlInseguro(f"Palavra-chave não permitida: {match_proibida.group(1)}")

    # Comentário não tem uso legítimo aqui e já serviu de bypass: o
    # placeholder dentro de `-- :cliente_caso_id` passava na checagem de
    # presença e ainda comentava o LIMIT acrescentado em seguida.
    if "--" in texto or "#" in texto or "/*" in texto:
        raise SqlInseguro("Comentários não são permitidos no SQL.")

    # `@` cobre variáveis de sessão/sistema (@@version, @@datadir) e
    # variáveis de usuário (@x := ...).
    if "@" in texto:
        raise SqlInseguro("Variáveis (@) não são permitidas no SQL.")

    match_funcao = _REGEX_FUNCAO_PROIBIDA.search(texto)
    if match_funcao:
        raise SqlInseguro(f"Função não permitida: {match_funcao.group(1).upper()}")

    try:
        arvores = sqlglot.parse(sql_limpo, read="mysql")
    except SqlglotError as exc:
        raise SqlInseguro("SQL não reconhecido pelo validador.") from exc

    if len(arvores) != 1 or arvores[0] is None:
        raise SqlInseguro("Apenas um único comando SQL é permitido.")
    arvore = arvores[0]
    if not isinstance(arvore, (exp.Select, exp.Union)):
        raise SqlInseguro("Apenas comandos SELECT são permitidos.")

    if any(True for _ in arvore.find_all(*_NOS_PROIBIDOS)):
        raise SqlInseguro("Função ou variável de sistema não permitida.")

    for funcao in arvore.find_all(exp.Anonymous):
        if funcao.name.upper() in FUNCOES_PROIBIDAS:
            raise SqlInseguro(f"Função não permitida: {funcao.name.upper()}")

    # FOR SHARE / FOR UPDATE: leitura com trava, sem uso numa consulta de
    # relatório (FOR UPDATE já cai em UPDATE acima; FOR SHARE, não).
    if any(select.args.get("locks") for select in arvore.find_all(exp.Select)):
        raise SqlInseguro("Leitura com trava (FOR SHARE/FOR UPDATE) não é permitida.")

    # Toda tabela da árvore -- FROM, JOIN, join por vírgula, subquery,
    # UNION -- precisa estar na whitelist. (WITH/CTE nem chega aqui: o
    # comando precisa começar com SELECT.)
    tabelas: set[str] = set()
    for tabela in arvore.find_all(exp.Table):
        if tabela.args.get("db") or tabela.args.get("catalog"):
            raise SqlInseguro(
                f"Tabela com schema qualificado não é permitida: {tabela.sql(dialect='mysql')}"
            )
        nome = tabela.name.lower()
        if nome:
            tabelas.add(nome)
    if not tabelas:
        raise SqlInseguro("A consulta precisa ler de pelo menos uma tabela permitida.")
    tabelas_fora_da_whitelist = tabelas - TABELAS_PERMITIDAS
    if tabelas_fora_da_whitelist:
        raise SqlInseguro(
            f"Tabela(s) não permitida(s): {', '.join(sorted(tabelas_fora_da_whitelist))}"
        )

    if ":cliente_caso_id" not in texto:
        raise SqlInseguro(
            "A consulta precisa filtrar por :cliente_caso_id para não vazar dados de outro caso."
        )

    # notas.situacao decide se uma nota CANCELADA entra na conta -- exigir a
    # coluna explicitamente na query (mesmo padrão de :cliente_caso_id acima)
    # força o SQL gerado a decidir isso, em vez de depender só da instrução
    # de prompt em app/ai/consulta_nl_sql.py (que a IA pode ignorar).
    if "notas" in tabelas and "situacao" not in texto.lower():
        raise SqlInseguro(
            "A consulta usa a tabela notas mas não menciona situacao -- declare "
            "explicitamente se deve incluir ou excluir notas canceladas."
        )

    # Só o LIMIT do comando externo conta: um LIMIT dentro de subquery não
    # limita o que volta para a API.
    limite = arvore.args.get("limit")
    if limite is None:
        return f"{sql_limpo} LIMIT {LIMIT_PADRAO}"

    valor = limite.expression
    # is_int também recusa 2.5 e 1e3, que antes estouravam ValueError no
    # int() abaixo, viravam 500 e escapavam do registro de auditoria.
    if not isinstance(valor, exp.Literal) or valor.is_string or not valor.is_int:
        raise SqlInseguro("O LIMIT precisa ser um número inteiro literal.")
    if int(valor.this) > LIMIT_PADRAO:
        raise SqlInseguro(f"O LIMIT não pode passar de {LIMIT_PADRAO} linhas.")

    return sql_limpo
