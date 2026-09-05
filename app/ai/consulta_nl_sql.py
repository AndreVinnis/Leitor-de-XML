"""
Tradução de pergunta em linguagem natural para SQL somente leitura (RF-006).

O SQL devolvido aqui NUNCA é executado diretamente -- ele ainda passa por
app/core/sql_seguranca.py::validar_e_finalizar_sql antes de qualquer contato
com o banco (RNF-003). Este módulo só decide o texto do SQL; quem decide se
ele roda é a validação determinística, não a IA.
"""

from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.config import settings

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


class _RespostaConsulta(BaseModel):
    sql: str


_SYSTEM_PROMPT = """\
Você traduz perguntas em linguagem natural, feitas por advogados sobre notas \
fiscais eletrônicas (NF-e) já processadas, para uma única consulta SQL \
somente leitura (SELECT). Use exclusivamente estas tabelas e colunas:

- notas (id, chave_acesso, tipo ['entrada'|'saida'], numero, serie, \
data_emissao, emitente_cnpj, emitente_nome, destinatario_cnpj, \
destinatario_nome, valor_total, cliente_caso_id, arquivo_origem, criado_em)
- itens_nota (id, nota_id, numero_item, codigo_produto, descricao_original, \
ncm, cfop, unidade, quantidade, valor_unitario, valor_total, \
produto_canonico_id)
- produtos_canonicos (id, cliente_caso_id, nome_canonico, categoria, \
criado_em)

Regras obrigatórias, sem exceção:
- Escreva exatamente um comando, e ele deve ser um SELECT.
- Nunca use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE ou qualquer outro \
comando que não seja leitura.
- Sempre filtre por notas.cliente_caso_id = :cliente_caso_id -- escreva \
literalmente o placeholder nomeado ":cliente_caso_id" (nunca um número), o \
valor real é injetado depois pelo backend.
- Para perguntas sobre um produto, faça JOIN de itens_nota com \
produtos_canonicos (por produto_canonico_id) e/ou notas (por nota_id) \
conforme necessário para responder quantidade, valor total, preço e \
categoria.
- Não use nenhuma tabela ou coluna fora da lista acima.

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


def gerar_sql(pergunta: str, canonicos_existentes: list[dict]) -> str:
    """
    Chama a IA para traduzir `pergunta` em um SQL bruto (ainda não validado
    -- ver o aviso no topo do módulo).

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

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_RespostaConsulta,
        ),
    )

    resposta = response.parsed
    if resposta is None:
        resposta = _RespostaConsulta.model_validate_json(response.text)
    return resposta.sql
