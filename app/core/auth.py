from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.models.models import RoleUsuario, Usuario
from app.workers.tasks import enviar_email_redefinicao_senha, enviar_notificacao_novo_cadastro


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, Usuario)


class UserManager(IntegerIDMixin, BaseUserManager[Usuario, int]):
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def on_after_register(self, user: Usuario, request: Optional[Request] = None) -> None:
        # O router de registro do fastapi-users cria o usuário com
        # is_active=True (create com safe=True). Aqui a gente desliga na
        # marra -- só volta a True quando um administrador aprova o cadastro
        # (status_cadastro já nasce "pendente" pelo default da coluna).
        await self.user_db.update(user, {"is_active": False})
        enviar_notificacao_novo_cadastro.delay(user.id)

    async def on_after_forgot_password(
        self, user: Usuario, token: str, request: Optional[Request] = None
    ) -> None:
        # Mesmo padrão de on_after_register: o envio de e-mail (SMTP
        # síncrono) não deve rodar dentro da request assíncrona do
        # fastapi-users -- delega pro worker.
        enviar_email_redefinicao_senha.delay(user.id, token)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


# Bearer no header, sem cookie -- usado pelo Streamlit (frontend/api_client.py)
# e pelos testes. O frontend React (web/) migrou para cookie_backend, abaixo.
bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")

# Nome do cookie de sessão do frontend React -- compartilhado com
# app/core/csrf.py e app/core/sessao_deslizante.py (que precisam saber se
# uma requisição carrega este cookie, sem reimportar todo este módulo).
NOME_COOKIE_SESSAO = "sessao_nfe"

cookie_transport = CookieTransport(
    cookie_name=NOME_COOKIE_SESSAO,
    cookie_max_age=settings.cookie_max_age_segundos,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite=settings.cookie_samesite,
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.secret_key, lifetime_seconds=3600)


def get_cookie_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.secret_key, lifetime_seconds=settings.cookie_max_age_segundos)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

cookie_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_cookie_jwt_strategy,
)

fastapi_users = FastAPIUsers[Usuario, int](get_user_manager, [auth_backend, cookie_backend])

usuario_atual_ativo = fastapi_users.current_user(active=True)


async def requer_administrador(usuario: Usuario = Depends(usuario_atual_ativo)) -> Usuario:
    if usuario.role != RoleUsuario.ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return usuario
