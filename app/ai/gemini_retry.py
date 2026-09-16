"""Política de retry/backoff compartilhada pelas chamadas ao SDK do Gemini.

Só retenta erros transitórios (5xx, timeout, conexão, rate limit 429) --
erros de cliente permanentes (chave inválida, requisição malformada, prompt
rejeitado) propagam na primeira tentativa. `reraise=True` preserva o
comportamento de propagação de erro que já existia em cada call site (quem
chama continua recebendo a mesma exceção do SDK, só que depois de até 3
tentativas em vez de nenhuma)."""

import tenacity
from google.genai import errors as genai_errors


def _deve_tentar_novamente(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError) and getattr(exc, "code", None) == 429:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError))


retry_gemini = tenacity.retry(
    retry=tenacity.retry_if_exception(_deve_tentar_novamente),
    wait=tenacity.wait_exponential_jitter(initial=1, max=6),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
)
