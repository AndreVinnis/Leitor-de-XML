"""
Teto de tamanho do corpo de qualquer requisição, aplicado antes da rota.

O FastAPI faz o parse do multipart ANTES de resolver as dependências (inclusive
a de autenticação), e o Starlette grava em disco temporário todo arquivo
acima de 1 MB. Sem este middleware, um POST de vários GB enchia o /tmp do
container antes mesmo de a resposta 401 sair -- o teto por arquivo/lote de
app/api/routes_upload.py só limita a cópia final, feita depois disso.

Duas checagens: `Content-Length` declarado acima do teto é recusado de cara;
sem ele (chunked), os bytes são contados à medida que chegam e, ao passar
do teto, o app recebe um `http.disconnect` (para de ler) e a resposta que ele
tentar mandar é trocada por 413. Levantar exceção no `receive` não serve: o
ServerErrorMiddleware do Starlette a transformaria em 500. Middleware ASGI
puro (não BaseHTTPMiddleware) para poder envolver `receive` e `send`.
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

# Folga para os cabeçalhos de cada parte do multipart e os campos de texto
# (cliente_caso_id, cnpj_cliente) em volta dos arquivos.
_FOLGA_BYTES = 1024 * 1024


def tamanho_maximo_corpo() -> int:
    return settings.upload_max_bytes_por_lote + _FOLGA_BYTES


class LimiteTamanhoCorpoMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limite = tamanho_maximo_corpo()
        for nome, valor in scope.get("headers", []):
            if nome == b"content-length":
                try:
                    declarado = int(valor)
                except ValueError:
                    declarado = 0
                if declarado > limite:
                    await _responder_413(send, limite)
                    return

        recebidos = 0
        excedeu = False
        resposta_iniciada = False

        async def receive_limitado() -> Message:
            nonlocal recebidos, excedeu
            if excedeu:
                return {"type": "http.disconnect"}
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebidos += len(mensagem.get("body", b""))
                if recebidos > limite:
                    excedeu = True
                    return {"type": "http.disconnect"}
            return mensagem

        async def send_filtrado(mensagem: Message) -> None:
            # Depois de estourar, o que o app tentar responder (400 de corpo
            # inválido, em geral) é descartado em favor do 413 abaixo.
            nonlocal resposta_iniciada
            if excedeu and not resposta_iniciada:
                return
            if mensagem["type"] == "http.response.start":
                resposta_iniciada = True
            await send(mensagem)

        await self.app(scope, receive_limitado, send_filtrado)
        if excedeu and not resposta_iniciada:
            await _responder_413(send, limite)


async def _responder_413(send: Send, limite: int) -> None:
    corpo = (
        '{"detail":"Requisição maior que o permitido '
        f'({limite // (1024 * 1024)} MB). Divida o envio em lotes menores."}}'
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(corpo)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corpo})
