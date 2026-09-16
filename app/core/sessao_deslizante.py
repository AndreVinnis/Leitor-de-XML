"""
Sessão deslizante para o cookie HttpOnly (app/core/auth.py::cookie_backend).

Em vez de um par access/refresh token com rotação (que exigiria uma segunda
credencial, tabela de revogação e migração), a sessão desliza: qualquer
requisição que chegue com o cookie já passado da metade da vida reemite um
JWT novo com vida cheia, no Set-Cookie da própria resposta. Não depende do
resultado da autenticação da rota (roda mesmo em rotas públicas) -- só olha
se o cookie existe e ainda é válido.

Sem `iat` custom: como JWTStrategy.write_token só grava `exp` (ver
fastapi_users.jwt.generate_jwt), a idade do token é inferida a partir dele
(tempo restante < metade da vida configurada implica token com mais da
metade da vida já passada).
"""
from datetime import datetime, timezone

import jwt as pyjwt
from fastapi_users.jwt import decode_jwt, generate_jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.auth import NOME_COOKIE_SESSAO
from app.core.config import settings

AUDIENCIA_JWT = ["fastapi-users:auth"]  # default do fastapi-users, usado nos dois backends


class SessaoDeslizanteMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        token = request.cookies.get(NOME_COOKIE_SESSAO)
        if not token:
            return response

        try:
            payload = decode_jwt(token, settings.secret_key, AUDIENCIA_JWT, algorithms=["HS256"])
        except pyjwt.PyJWTError:
            return response

        sub = payload.get("sub")
        exp = payload.get("exp")
        if sub is None or exp is None:
            return response

        tempo_restante = exp - datetime.now(timezone.utc).timestamp()
        if tempo_restante >= settings.cookie_max_age_segundos / 2:
            return response  # ainda na primeira metade da vida, nada a fazer

        novo_token = generate_jwt(
            {"sub": sub, "aud": AUDIENCIA_JWT},
            settings.secret_key,
            settings.cookie_max_age_segundos,
        )
        response.set_cookie(
            NOME_COOKIE_SESSAO,
            novo_token,
            max_age=settings.cookie_max_age_segundos,
            path="/",
            secure=settings.cookie_secure,
            httponly=True,
            samesite=settings.cookie_samesite,
        )
        return response
