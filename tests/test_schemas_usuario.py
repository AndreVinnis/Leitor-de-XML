from app.schemas.usuario import UsuarioCreate


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
