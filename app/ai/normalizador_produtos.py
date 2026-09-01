"""
Normalização de descrições de produtos (xProd) via IA.

Cada NF-e descreve o mesmo produto de formas diferentes ("ARROZ TIO JOAO 5KG",
"ARROZ TIO JOÃO 5 KG"). Este módulo pede à IA para agrupar descrições em
produtos canônicos, dando-lhe a lista de canônicos já existentes como contexto
de matching (sem embeddings/busca vetorial -- ver Instruções do Projeto).
A IA nunca escreve direto no banco: só sugere, revisão humana decide.
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


class NovoProdutoCanonicoIA(BaseModel):
    nome_canonico: str
    categoria: Optional[str] = None


class SugestaoIA(BaseModel):
    descricao_original: str
    confianca: float
    produto_canonico_id: Optional[int] = None
    novo_produto_canonico: Optional[NovoProdutoCanonicoIA] = None


class _RespostaNormalizacao(BaseModel):
    sugestoes: list[SugestaoIA]


_SYSTEM_PROMPT = """\
Você normaliza descrições de produtos extraídas de notas fiscais eletrônicas \
(NF-e) brasileiras. Para cada descrição de entrada, decida se ela corresponde \
a um produto canônico já existente (informe produto_canonico_id) ou se \
representa um produto novo (preencha novo_produto_canonico com um nome \
canônico limpo e, se possível, uma categoria). Nunca invente um \
produto_canonico_id que não esteja na lista de canônicos existentes. Uma \
descrição corresponde ao mesmo produto canônico mesmo com pequenas variações \
de grafia, acentuação, abreviação ou espaçamento -- mas produtos com \
quantidade/tamanho diferentes (ex: 1KG vs 5KG) são produtos distintos. Informe \
confianca entre 0 e 1 refletindo sua certeza no agrupamento."""


def sugerir_normalizacao(
    descricoes: list[str], canonicos_existentes: list[dict]
) -> list[SugestaoIA]:
    """
    Chama a IA para sugerir, para cada descrição em `descricoes`, um
    produto_canonico existente (por id) ou um novo produto canônico.

    `canonicos_existentes` é uma lista de {"id": int, "nome_canonico": str,
    "categoria": str | None} usada como contexto de matching.
    """
    if not descricoes:
        return []

    client = _get_client()

    canonicos_texto = "\n".join(
        f"- id={c['id']}: {c['nome_canonico']}"
        + (f" (categoria: {c['categoria']})" if c.get("categoria") else "")
        for c in canonicos_existentes
    ) or "(nenhum produto canônico cadastrado ainda)"

    descricoes_texto = "\n".join(f"- {d}" for d in descricoes)

    user_message = (
        f"Produtos canônicos existentes:\n{canonicos_texto}\n\n"
        f"Descrições a normalizar:\n{descricoes_texto}\n\n"
        "Retorne uma sugestão para cada descrição listada acima, na mesma ordem."
    )

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_RespostaNormalizacao,
        ),
    )

    resposta = response.parsed
    if resposta is None:
        resposta = _RespostaNormalizacao.model_validate_json(response.text)
    return resposta.sugestoes
