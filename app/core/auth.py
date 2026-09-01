from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi_users import BaseUserManager, FastAPIUsers, IntegerIDMixin
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.models.models import RoleUsuario, Usuario
from app.workers.tasks import enviar_notificacao_novo_cadastro


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


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncGenerator[UserManager, None]:
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.secret_key, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[Usuario, int](get_user_manager, [auth_backend])

usuario_atual_ativo = fastapi_users.current_user(active=True)


async def requer_administrador(usuario: Usuario = Depends(usuario_atual_ativo)) -> Usuario:
    if usuario.role != RoleUsuario.ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return usuario
