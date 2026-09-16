"""
Proteção anti-CSRF para o cookie de sessão (app/core/auth.py::cookie_backend).

SameSite=Lax não cobre um POST form-urlencoded cross-site: o browser ainda
manda o cookie em navegação de topo (é para isso que Lax existe), e um
`Set-Cookie` de resposta nunca é bloqueado por SameSite -- só o envio do
cookie em requisições futuras é. Isso inclui o próprio login por cookie: um
formulário cross-site pode logar a vítima na conta do atacante sem trocar
nenhum cabeçalho.

A mitigação aqui é o header customizado abaixo, que só JS same-origin
consegue setar (um <form> comum não anexa headers). Bearer nunca passa por
este middleware: não carrega o cookie de sessão, e não mira a rota de login
por cookie.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.auth import NOME_COOKIE_SESSAO

CAMINHO_LOGIN_COOKIE = "/api/auth/cookie/login"
NOME_HEADER_ANTI_CSRF = "X-Requested-With"
VALOR_HEADER_ANTI_CSRF = "XMLHttpRequest"
METODOS_QUE_MUDAM_ESTADO = {"POST", "PUT", "PATCH", "DELETE"}


class ExigirHeaderAntiCsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in METODOS_QUE_MUDAM_ESTADO:
            precisa_do_header = (
                NOME_COOKIE_SESSAO in request.cookies or request.url.path == CAMINHO_LOGIN_COOKIE
            )
            if precisa_do_header and request.headers.get(NOME_HEADER_ANTI_CSRF) != VALOR_HEADER_ANTI_CSRF:
                return JSONResponse(
                    {"detail": "Requisição rejeitada: header anti-CSRF ausente ou inválido."},
                    status_code=403,
                )
        return await call_next(request)
