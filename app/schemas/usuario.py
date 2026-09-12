import email_validator
from fastapi_users import schemas

from app.models.models import RoleUsuario, StatusCadastro

# O e-mail de dev/admin do projeto usa a TLD ".local" (ver
# app/core/config.py::email_from = "no-reply@leitorxml.local" -- mailhog só
# captura, nunca entrega de verdade). O email-validator, usado pelo EmailStr
# de UsuarioRead/UsuarioCreate (herdado de fastapi_users.schemas.BaseUser),
# rejeita ".local" por padrão como TLD reservada (RFC 6762, mDNS): sem isso,
# nenhum usuário com e-mail @*.local pode ser serializado numa resposta da
# API (ex.: GET /api/auth/users/me estoura 500 com ValidationError). Continua
# rejeitando as outras TLDs reservadas (test, example, invalid, arpa).
if "local" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
    email_validator.SPECIAL_USE_DOMAIN_NAMES.remove("local")


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
