"""
Normalização de descrições de produtos (xProd) via IA.

Cada NF-e descreve o mesmo produto de formas diferentes ("ARROZ TIO JOAO 5KG",
"ARROZ TIO JOÃO 5 KG"). Este módulo pede à IA para agrupar descrições em
produtos canônicos, dando-lhe a lista de canônicos já existentes como contexto
de matching (sem embeddings/busca vetorial -- ver Instruções do Projeto).
A IA nunca escreve direto no banco: só sugere, revisão humana decide.
"""

from typing import Optional

import anthropic
from pydantic import BaseModel

from app.ai.anthropic_retry import retry_anthropic
from app.core.config import settings

_client: Optional[anthropic.Anthropic] = None

# max_tokens é obrigatório na Anthropic (diferente do Gemini). Lote de até
# TAMANHO_LOTE_IA=50 itens (app/workers/tasks.py) -- 50 sugestões em JSON
# (descricao_original + confianca + produto_canonico_id/novo_produto_canonico)
# ficam bem abaixo disso; o valor dá margem de segurança sem chegar perto do
# teto de saída do modelo. Revisar junto se TAMANHO_LOTE_IA mudar.
_MAX_TOKENS = 8000

_NOME_TOOL_SUGESTOES = "registrar_sugestoes_normalizacao"

_TOOL_SUGESTOES = {
    "name": _NOME_TOOL_SUGESTOES,
    "description": (
        "Registra, para cada descrição recebida, a sugestão de normalização "
        "correspondente (produto canônico existente ou novo), na mesma ordem."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sugestoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "descricao_original": {"type": "string"},
                        "confianca": {"type": "number"},
                        "produto_canonico_id": {"type": ["integer", "null"]},
                        "novo_produto_canonico": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "nome_canonico": {"type": "string"},
                                        "categoria": {"type": ["string", "null"]},
                                    },
                                    "required": ["nome_canonico"],
                                },
                                {"type": "null"},
                            ]
                        },
                    },
                    "required": ["descricao_original", "confianca"],
                },
            }
        },
        "required": ["sugestoes"],
    },
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # max_retries=0: o SDK da Anthropic já retenta 429/5xx/erro de rede
        # por padrão (max_retries=2) -- zerar aqui evita duas camadas de
        # retry sobrepostas (a do SDK + a do tenacity via retry_anthropic),
        # que multiplicariam tentativas/backoffs de forma imprevisível.
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0)
    return _client


@retry_anthropic
def _gerar_conteudo(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    return client.messages.create(**kwargs)


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
produto_canonico_id que não esteja na lista de canônicos existentes. Informe \
confianca entre 0 e 1 refletindo sua certeza no agrupamento.

O nome canônico deve ser o mais genérico possível, mantendo apenas os \
atributos que de fato diferenciam produtos para fins de reconciliação de \
estoque. Três atributos SEMPRE diferenciam produtos, mesmo com o restante da \
descrição idêntico:

1. Parte, tipo ou categoria do item (ex: peito de frango, coxa de frango e \
sobrecoxa de frango são produtos DIFERENTES entre si -- nunca agrupe partes \
distintas de um mesmo animal ou variantes de tipo em um único canônico).
2. Marca/fabricante, quando aparecer na descrição (ex: "peito de frango 1kg \
sadia" e "peito de frango 1kg perdigão" são produtos DIFERENTES).
3. Quantidade, peso ou volume (ex: "cerveja stella 350ml" e "cerveja stella \
600ml" são produtos DIFERENTES; "arroz 1kg" e "arroz 5kg" são produtos \
DIFERENTES).

Fora desses três atributos, ignore variações de preparo, corte ou manuseio ao \
decidir se é o mesmo produto -- elas não criam um canônico novo. Por exemplo, \
"peito de frango sem pele 1kg" e "peito de frango desossado 1kg" são o MESMO \
produto e devem virar o canônico "peito de frango 1kg" (termos como sem pele, \
com/sem osso, desossado, resfriado, congelado, in natura, a granel ou \
embalado descrevem a mesma mercadoria, não produtos distintos). O mesmo vale \
para pequenas variações de grafia, acentuação, abreviação ou espaçamento, que \
nunca justificam um canônico novo."""


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

    response = _gerar_conteudo(
        client,
        model=settings.anthropic_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        thinking={"type": "disabled"},
        tools=[_TOOL_SUGESTOES],
        tool_choice={"type": "tool", "name": _NOME_TOOL_SUGESTOES},
        messages=[{"role": "user", "content": user_message}],
    )

    tool_use = next((bloco for bloco in response.content if bloco.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError(
            "Resposta da IA sem bloco tool_use esperado "
            f"(stop_reason={response.stop_reason!r})"
        )

    resposta = _RespostaNormalizacao.model_validate(tool_use.input)
    return resposta.sugestoes
