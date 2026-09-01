from unittest.mock import patch

from app.models.models import RoleUsuario, StatusCadastro, Usuario
from app.workers.tasks import (
    enviar_notificacao_novo_cadastro,
    enviar_notificacao_resultado_cadastro,
)


def _criar_usuario(session, email, **kwargs):
    usuario = Usuario(
        nome=kwargs.get("nome", "Teste"),
        email=email,
        hashed_password="x",
        role=kwargs.get("role", RoleUsuario.COMUM),
        status_cadastro=kwargs.get("status_cadastro", StatusCadastro.PENDENTE),
        is_active=kwargs.get("is_active", False),
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


@patch("app.workers.tasks.enviar_email")
def test_notifica_apenas_admins_ja_aprovados(mock_enviar_email, db_session_factory):
    session = db_session_factory()
    admin_aprovado = _criar_usuario(
        session,
        "admin@x.com",
        role=RoleUsuario.ADMINISTRADOR,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )
    # Admin cadastrado mas ainda pendente -- não deve receber notificação
    # (evita um admin não aprovado aprovando outros cadastros).
    _criar_usuario(
        session,
        "admin-pendente@x.com",
        role=RoleUsuario.ADMINISTRADOR,
        status_cadastro=StatusCadastro.PENDENTE,
    )
    novo = _criar_usuario(session, "novo@x.com", nome="Novo Usuario")
    session.close()

    resultado = enviar_notificacao_novo_cadastro(novo.id)

    assert resultado == {"status": "ok", "admins_notificados": 1}
    mock_enviar_email.assert_called_once()

    destinatario, assunto, corpo = mock_enviar_email.call_args[0]
    assert destinatario == "admin@x.com"
    assert "novo@x.com" in corpo
    assert "Novo Usuario" in corpo
    assert "aprovar-cadastro?token=" in corpo
    assert "reprovar-cadastro?token=" in corpo
    assert "30 minutos" in corpo


@patch("app.workers.tasks.enviar_email")
def test_notifica_usuario_inexistente_nao_quebra(mock_enviar_email, db_session_factory):
    db_session_factory()  # garante as tabelas criadas

    resultado = enviar_notificacao_novo_cadastro(9999)

    assert resultado["status"] == "erro"
    mock_enviar_email.assert_not_called()


@patch("app.workers.tasks.enviar_email")
def test_notifica_resultado_aprovado(mock_enviar_email, db_session_factory):
    session = db_session_factory()
    usuario = _criar_usuario(session, "fulano@x.com", nome="Fulano")
    session.close()

    resultado = enviar_notificacao_resultado_cadastro(usuario.id, True)

    assert resultado == {"status": "ok"}
    destinatario, assunto, corpo = mock_enviar_email.call_args[0]
    assert destinatario == "fulano@x.com"
    assert "aprovado" in assunto.lower()
    assert "Fulano" in corpo


@patch("app.workers.tasks.enviar_email")
def test_notifica_resultado_reprovado(mock_enviar_email, db_session_factory):
    session = db_session_factory()
    usuario = _criar_usuario(session, "ciclano@x.com", nome="Ciclano")
    session.close()

    enviar_notificacao_resultado_cadastro(usuario.id, False)

    destinatario, assunto, corpo = mock_enviar_email.call_args[0]
    assert destinatario == "ciclano@x.com"
    assert "não foi aprovado" in assunto.lower()
