from fastapi_users import schemas

from app.models.models import RoleUsuario, StatusCadastro


class UsuarioRead(schemas.BaseUser[int]):
    nome: str
    role: RoleUsuario
    status_cadastro: StatusCadastro


class UsuarioCreate(schemas.BaseUserCreate):
    """Só expõe os campos que o próprio usuário pode definir no cadastro.
    `role` e `status_cadastro` são controlados só pelo servidor."""

    nome: str


class UsuarioUpdate(schemas.BaseUserUpdate):
    nome: str | None = None
