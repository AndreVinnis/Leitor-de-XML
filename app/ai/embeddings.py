"""
Embeddings de texto via Gemini, usados como pré-filtro de similaridade antes
da normalização por IA generativa (ver
app/workers/tasks.py::normalizar_produtos_pendentes). Não decide nada
sozinho -- só reduz o catálogo de produtos canônicos que chega no prompt de
app/ai/normalizador_produtos.py, para catálogos grandes demais para caber
inteiros no contexto. A IA generativa continua sendo quem decide o match
final (inclusive "nenhum destes, é produto novo").
"""

from typing import Optional

import numpy as np
from google import genai
from google.genai import types

from app.core.config import settings

_client: Optional[genai.Client] = None

_TAMANHO_LOTE_EMBEDDING = 100


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def gerar_embeddings(textos: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """
    Gera um vetor de embedding por texto de entrada, na mesma ordem.

    `task_type` segue o vocabulário da API Gemini: "RETRIEVAL_DOCUMENT" para
    os nomes de produtos canônicos (o lado "catálogo") e "RETRIEVAL_QUERY"
    para as descrições de item a normalizar (o lado "busca") -- usar o par
    certo melhora a qualidade do ranking por similaridade.
    """
    if not textos:
        return []

    client = _get_client()
    vetores: list[list[float]] = []

    for i in range(0, len(textos), _TAMANHO_LOTE_EMBEDDING):
        lote = textos[i : i + _TAMANHO_LOTE_EMBEDDING]
        response = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=lote,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        vetores.extend(embedding.values for embedding in response.embeddings)

    return vetores


def selecionar_candidatos_similares(
    chaves_lote: list[str],
    embeddings_descricoes: dict[str, list[float]],
    embeddings_canonicos: dict[int, list[float]],
    top_k: int,
    max_total: int,
) -> list[int]:
    """
    Para cada descrição em `chaves_lote`, calcula a similaridade de cosseno
    contra todos os canônicos em `embeddings_canonicos` e retorna a união
    (deduplicada, na ordem em que aparece) dos `top_k` mais similares de
    cada descrição, capada em `max_total` ids -- é essa lista de ids que
    substitui o catálogo completo no prompt da IA generativa.

    Retorna lista vazia se não houver nenhum canônico com embedding ainda
    (ex: catálogo grande mas backfill de embeddings não rodou).
    """
    if not embeddings_canonicos:
        return []

    ids_matriz = list(embeddings_canonicos.keys())
    matriz = np.array([embeddings_canonicos[cid] for cid in ids_matriz])
    normas = np.linalg.norm(matriz, axis=1)
    normas[normas == 0] = 1

    ids_candidatos: list[int] = []
    vistos: set[int] = set()
    for chave in chaves_lote:
        vetor_descricao = embeddings_descricoes.get(chave)
        if vetor_descricao is None:
            continue
        vetor = np.array(vetor_descricao)
        norma_vetor = np.linalg.norm(vetor) or 1
        similaridades = (matriz @ vetor) / (normas * norma_vetor)
        top_indices = np.argsort(-similaridades)[:top_k]
        for idx in top_indices:
            cid = ids_matriz[idx]
            if cid not in vistos:
                vistos.add(cid)
                ids_candidatos.append(cid)

    return ids_candidatos[:max_total]
