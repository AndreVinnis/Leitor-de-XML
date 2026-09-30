"""
Tradução de pergunta em linguagem natural para um plano de consulta SQL
somente leitura (RF-006).

Nenhum SQL devolvido aqui é executado diretamente -- cada um ainda passa por
app/core/sql_seguranca.py::validar_e_finalizar_sql antes de qualquer contato
com o banco (RNF-003). Este módulo só decide o texto do(s) SQL(s) e o modelo
de frase-resposta; quem decide se cada SQL roda é a validação determinística,
e quem decide o valor que preenche cada marcador da frase é
app/core/resposta_consulta.py -- a IA não escreve o número final diretamente
na frase, ela escreve o SQL que o produz e um marcador; app/api/routes_consulta.py
e app/core/resposta_consulta.py são quem valida a estrutura do plano (consulta
"resposta" precisa devolver 1 linha só, marcador só pode ler de "resposta"
etc.) antes de aceitar o valor.
"""

from dataclasses import dataclass
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel

from app.ai.anthropic_retry import retry_anthropic
from app.core.config import settings

_client: Optional[anthropic.Anthropic] = None

FINALIDADES_VALIDAS = {"resposta", "fontes", "listagem"}
MAX_CONSULTAS = 3

# Saída bem menor que a normalização: no máximo MAX_CONSULTAS=3 SQLs (SQL
# neste domínio raramente passa de ~300 tokens) + um resposta_modelo curto.
# 2048 dá margem folgada mesmo para consultas com vários JOINs.
_MAX_TOKENS = 2048

_NOME_TOOL_PLANO = "registrar_plano_consulta"

_TOOL_PLANO = {
    "name": _NOME_TOOL_PLANO,
    "description": (
        "Registra o plano de consultas SQL somente leitura (até 3) e, "
        "quando aplicável, o modelo de frase-resposta com marcadores."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "consultas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "finalidade": {
                            "type": "string",
                            "enum": ["resposta", "fontes", "listagem"],
                        },
                        "sql": {"type": "string"},
                    },
                    "required": ["finalidade", "sql"],
                },
            },
            "resposta_modelo": {"type": ["string", "null"]},
        },
        "required": ["consultas"],
    },
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0)
    return _client


@retry_anthropic
def _gerar_conteudo(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    return client.messages.create(**kwargs)


class _ConsultaPlanejada(BaseModel):
    finalidade: Literal["resposta", "fontes", "listagem"]
    sql: str


class _PlanoConsultaResposta(BaseModel):
    consultas: list[_ConsultaPlanejada]
    resposta_modelo: Optional[str] = None


@dataclass
class ConsultaPlanejada:
    finalidade: str
    sql: str


@dataclass
class PlanoConsulta:
    consultas: list[ConsultaPlanejada]
    resposta_modelo: Optional[str]


_SYSTEM_PROMPT = """\
Você traduz perguntas em linguagem natural, feitas por advogados sobre notas \
fiscais eletrônicas (NF-e) já processadas, para um plano de consultas SQL \
somente leitura (SELECT). Use exclusivamente estas tabelas e colunas:

- notas (id, chave_acesso, tipo ['entrada'|'saida'], numero, serie, \
data_emissao, emitente_cnpj, emitente_nome, destinatario_cnpj, \
destinatario_nome, valor_total, cliente_caso_id, arquivo_origem, \
situacao ['autorizada'|'cancelada'], cancelada_em, criado_em)
- itens_nota (id, nota_id, numero_item, codigo_produto, descricao_original, \
ncm, cfop, unidade, quantidade, valor_unitario, valor_total, \
produto_canonico_id)
- produtos_canonicos (id, cliente_caso_id, nome_canonico, categoria, \
criado_em)

Regras obrigatórias para CADA consulta do plano, sem exceção:
- Escreva exatamente um comando por consulta, e ele deve ser um SELECT.
- Nunca use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE ou qualquer outro \
comando que não seja leitura.
- Sempre filtre por notas.cliente_caso_id = :cliente_caso_id -- escreva \
literalmente o placeholder nomeado ":cliente_caso_id" (nunca um número), o \
valor real é injetado depois pelo backend.
- Nota com situacao = 'cancelada' não vale mais e não deve entrar em soma, \
contagem ou qualquer agregação de valor: sempre filtre \
notas.situacao = 'autorizada', a menos que a pergunta peça explicitamente \
por notas canceladas ou pelo histórico de cancelamentos.
- Para perguntas sobre um produto, faça JOIN de itens_nota com \
produtos_canonicos (por produto_canonico_id) e/ou notas (por nota_id) \
conforme necessário para responder quantidade, valor total, preço e \
categoria.
- Não use nenhuma tabela ou coluna fora da lista acima.
- Não use comentários SQL, variáveis (@), WITH/CTE nem LIMIT acima de 200 \
-- o backend recusa a consulta inteira se encontrar qualquer um deles.

Como decidir o formato do plano (campo "consultas", uma lista):
1. Pergunta de LISTAGEM (o usuário quer ver notas ou itens individuais, não \
um número agregado, ex.: "quais notas...", "liste os itens..."): devolva \
exatamente 1 consulta com finalidade "listagem", incluindo sempre a coluna \
"notas.id AS nota_id" (o usuário usa esse id para baixar os XMLs), e deixe \
resposta_modelo nulo.
2. Pergunta OBJETIVA (o usuário quer um número, total ou contagem, ex.: \
"quantos itens...", "qual o valor total..."): devolva 1 consulta com \
finalidade "resposta" (agregada, com SUM/COUNT/etc., e um alias de coluna \
claro, ex. "SELECT SUM(i.quantidade) AS total_itens FROM ..."), seguida de \
exatamente 1 consulta com finalidade "fontes" que usa OS MESMOS FILTROS da \
consulta "resposta" mas SEM agregação, listando as notas/itens individuais \
que entraram no cálculo -- sempre com "notas.id AS nota_id", número da nota, \
data de emissão, emitente e destinatário, e (quando a pergunta for sobre um \
produto) descrição, quantidade e valor do item. No máximo 3 consultas no \
total. A consulta "resposta" tem que devolver SEMPRE exatamente uma linha: \
nunca use GROUP BY nela (se a pergunta pedir totais separados por grupo, ex. \
"quanto entrou e quanto saiu", isso não é uma pergunta objetiva de um único \
número -- trate como listagem, com finalidade "listagem" e sem \
resposta_modelo), e nunca repita o mesmo alias de coluna duas vezes.
3. Preencha resposta_modelo (só quando houver consulta "resposta" -- se não \
houver consulta "resposta" no plano, deixe resposta_modelo nulo) com uma \
frase curta em português, natural, respondendo à pergunta, usando \
marcadores no formato {N.coluna} ou {N.coluna|formato} no lugar de QUALQUER \
número, valor monetário ou data -- N é a posição da consulta "resposta" no \
array "consultas" (a primeira consulta é 1); um marcador NUNCA pode \
referenciar uma consulta de finalidade "fontes" ou "listagem" (elas listam \
várias linhas, então ler "a primeira" seria arbitrário). coluna é o alias \
exato que você deu na consulta "resposta", e formato é um destes três: \
"numero", "moeda" ou "data" (omita o formato para texto simples). Exemplo: \
consultas = [{"finalidade": "resposta", "sql": "SELECT SUM(i.quantidade) AS \
total_itens FROM ..."}, {"finalidade": "fontes", "sql": "..."}], \
resposta_modelo = "Foram encontrados {1.total_itens|numero} itens do \
produto Carne nas notas de entrada do caso selecionado." NUNCA escreva um \
número, valor ou data literal na frase -- todo dado variável tem que vir de \
um marcador, porque quem preenche o marcador com o valor real do banco é o \
backend, nunca você. Garanta também que o agregado nunca devolva NULL sem \
querer (ex.: "SELECT COALESCE(SUM(i.quantidade), 0) AS total_itens ..." em \
vez de só SUM(...), já que SUM/AVG/MAX/MIN sobre zero linhas correspondentes \
devolvem NULL, não zero) -- um marcador que recebe NULL do banco é \
rejeitado e a resposta não é exibida.

Você recebe também a lista de produtos canônicos já cadastrados no caso (id, \
nome_canonico, categoria) -- são os nomes revisados por humano, e a grafia \
usada nas notas fiscais originais (itens_nota.descricao_original) costuma \
variar bastante em relação a eles (abreviação, acentuação, plural, marca vs. \
nome genérico etc.). Se a pergunta mencionar um produto que corresponda, \
mesmo com grafia diferente, a algum item dessa lista, filtre por \
itens_nota.produto_canonico_id = <id> (ou IN (...) para mais de um) em vez \
de tentar casar o texto exato da pergunta contra descricao_original -- isso \
evita falso-negativo por diferença de grafia entre a pergunta e a nota \
fiscal. Só recorra a LIKE sobre descricao_original/nome_canonico quando não \
houver nenhuma correspondência razoável na lista de canônicos."""


def gerar_plano_consulta(pergunta: str, canonicos_existentes: list[dict]) -> PlanoConsulta:
    """
    Chama a IA para traduzir `pergunta` em um plano de até MAX_CONSULTAS SQLs
    brutos (ainda não validados -- ver o aviso no topo do módulo) mais,
    quando a pergunta for objetiva, um modelo de frase-resposta com
    marcadores para o backend preencher.

    `canonicos_existentes` é a lista de {"id": int, "nome_canonico": str,
    "categoria": str | None} já cadastrados no caso (mesmo formato usado por
    app.ai.normalizador_produtos.sugerir_normalizacao), dada como contexto
    para a IA resolver produtos mencionados na pergunta com grafia diferente
    da nota fiscal original para o nome canônico correto.
    """
    client = _get_client()

    canonicos_texto = "\n".join(
        f"- id={c['id']}: {c['nome_canonico']}"
        + (f" (categoria: {c['categoria']})" if c.get("categoria") else "")
        for c in canonicos_existentes
    ) or "(nenhum produto canônico cadastrado ainda neste caso)"

    user_message = (
        f"Produtos canônicos já cadastrados neste caso:\n{canonicos_texto}\n\n"
        f"Pergunta: {pergunta}"
    )

    response = _gerar_conteudo(
        client,
        model=settings.anthropic_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        thinking={"type": "disabled"},
        tools=[_TOOL_PLANO],
        tool_choice={"type": "tool", "name": _NOME_TOOL_PLANO},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_use = next((bloco for bloco in response.content if bloco.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError(
            "Resposta da IA sem bloco tool_use esperado "
            f"(stop_reason={response.stop_reason!r})"
        )

    resposta = _PlanoConsultaResposta.model_validate(tool_use.input)

    return PlanoConsulta(
        consultas=[
            ConsultaPlanejada(finalidade=c.finalidade, sql=c.sql) for c in resposta.consultas
        ],
        resposta_modelo=resposta.resposta_modelo,
    )
