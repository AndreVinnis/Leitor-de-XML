import pytest
from pydantic import ValidationError

from app.schemas.usuario import UsuarioCreate, UsuarioRead
from app.models.models import RoleUsuario, StatusCadastro


def test_usuario_read_aceita_email_com_tld_local():
    """
    Regressão: app/core/config.py usa "no-reply@leitorxml.local" como
    convenção de e-mail de dev (mailhog só captura, nunca entrega de
    verdade). O email-validator rejeita ".local" por padrão como TLD
    reservada (RFC 6762) -- sem o ajuste em app/schemas/usuario.py, nenhum
    usuário com e-mail @*.local pode ser serializado numa resposta da API
    (GET /api/auth/users/me estourava 500).
    """
    usuario = UsuarioRead(
        id=1,
        email="admin@leitorxml.local",
        nome="Admin",
        role=RoleUsuario.ADMINISTRADOR,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
        is_superuser=True,
        is_verified=True,
    )
    assert usuario.email == "admin@leitorxml.local"


def test_usuario_create_ainda_rejeita_outras_tlds_reservadas():
    """A liberação de ".local" é específica -- as demais TLDs reservadas
    (RFC 2606: test, example, invalid) continuam bloqueadas."""
    with pytest.raises(ValidationError):
        UsuarioCreate(email="a@x.test", password="senha-forte-123", nome="Fulano")


def test_usuario_create_ignora_role_e_status_enviados_pelo_cliente():
    """
    role e status_cadastro não existem em UsuarioCreate de propósito -- só o
    servidor pode setá-los (default da coluna = comum/pendente). Mesmo que
    alguém mande esses campos no corpo do POST /api/auth/register, eles
    precisam ser descartados antes de chegar no banco.
    """
    dados = UsuarioCreate(
        email="malicioso@x.com",
        password="senha-forte-123",
        nome="Fulano",
        role="administrador",
        status_cadastro="aprovado",
        is_superuser=True,
    )

    campos = dados.model_dump()
    assert "role" not in campos
    assert "status_cadastro" not in campos
    # is_superuser existe no schema base do fastapi-users, mas create() com
    # safe=True (usado pelo router de registro) ignora esse valor mesmo
    # assim -- não é responsabilidade deste schema.
