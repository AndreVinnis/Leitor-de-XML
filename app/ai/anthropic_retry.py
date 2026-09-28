"""Política de retry/backoff compartilhada pelas chamadas ao SDK da Anthropic.

Mesma política de app/ai/gemini_retry.py (retry só em erros transitórios --
5xx, sobrecarga (529), timeout, conexão e rate limit 429; erros de cliente
permanentes propagam na primeira tentativa; `reraise=True` preserva o
comportamento de propagação de erro que já existia em cada call site), mas
usando as exceções do SDK `anthropic` em vez do `google-genai`. Módulo
separado porque app/ai/embeddings.py continua no Gemini -- gemini_retry.py
permanece dedicado só a ele, este aqui é usado por normalizador_produtos.py e
consulta_nl_sql.py.

Todo `anthropic.APIStatusError` já expõe `.status_code` (RateLimitError=429,
InternalServerError/ServiceUnavailableError/OverloadedError/
DeadlineExceededError e qualquer 5xx não modelado especificamente), então a
checagem é feita por status_code em vez de isinstance de cada subclasse --
mais robusto a novas subclasses de erro 5xx que a Anthropic vier a adicionar.
"""

import anthropic
import tenacity


def _deve_tentar_novamente(exc: BaseException) -> bool:
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    if isinstance(exc, anthropic.APIConnectionError):  # cobre APITimeoutError (subclasse)
        return True
    return isinstance(exc, (ConnectionError, TimeoutError))


retry_anthropic = tenacity.retry(
    retry=tenacity.retry_if_exception(_deve_tentar_novamente),
    wait=tenacity.wait_exponential_jitter(initial=1, max=6),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
)
