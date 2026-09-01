import time

from app.core.config import settings
from app.core.tokens import gerar_token_aprovacao
from app.models.models import LogAuditoria, RoleUsuario, StatusCadastro, Usuario


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


def _criar_admin(session, email):
    return _criar_usuario(
        session,
        email,
        role=RoleUsuario.ADMINISTRADOR,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )


def test_aprovar_cadastro_pendente_com_sucesso(client, db_session_factory):
    session = db_session_factory()
    admin = _criar_admin(session, "admin1@x.com")
    usuario = _criar_usuario(session, "fulano@x.com")
    session.close()

    token = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")
    resp = client.get(f"/api/auth/aprovar-cadastro?token={token}")

    assert resp.status_code == 200
    assert "aprovado" in resp.text.lower()

    session = db_session_factory()
    atualizado = session.get(Usuario, usuario.id)
    assert atualizado.status_cadastro == StatusCadastro.APROVADO
    assert atualizado.is_active is True
    assert atualizado.aprovado_por_usuario_id == admin.id
    assert atualizado.aprovado_em is not None

    log = session.query(LogAuditoria).filter_by(usuario_id=admin.id).one()
    assert log.acao == "aprovacao_cadastro"
    session.close()


def test_reprovar_cadastro_pendente_com_sucesso(client, db_session_factory):
    session = db_session_factory()
    admin = _criar_admin(session, "admin2@x.com")
    usuario = _criar_usuario(session, "ciclano@x.com")
    session.close()

    token = gerar_token_aprovacao(admin.id, usuario.id, "reprovar")
    resp = client.get(f"/api/auth/reprovar-cadastro?token={token}")

    assert resp.status_code == 200
    assert "reprovado" in resp.text.lower()

    session = db_session_factory()
    atualizado = session.get(Usuario, usuario.id)
    assert atualizado.status_cadastro == StatusCadastro.REPROVADO
    assert atualizado.is_active is False
    assert atualizado.aprovado_por_usuario_id == admin.id
    session.close()


def test_link_de_uso_unico_segunda_tentativa_nao_reprocessa(client, db_session_factory):
    session = db_session_factory()
    admin = _criar_admin(session, "admin3@x.com")
    usuario = _criar_usuario(session, "beltrano@x.com")
    session.close()

    token = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")

    primeira = client.get(f"/api/auth/aprovar-cadastro?token={token}")
    segunda = client.get(f"/api/auth/aprovar-cadastro?token={token}")

    assert "aprovado com sucesso" in primeira.text.lower()
    assert segunda.status_code == 200
    assert "já" in segunda.text.lower()


def test_token_de_aprovar_nao_funciona_no_endpoint_de_reprovar(client, db_session_factory):
    session = db_session_factory()
    admin = _criar_admin(session, "admin4@x.com")
    usuario = _criar_usuario(session, "ze@x.com")
    session.close()

    token_de_aprovar = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")
    resp = client.get(f"/api/auth/reprovar-cadastro?token={token_de_aprovar}")

    assert resp.status_code == 200
    assert "inválido" in resp.text.lower()

    session = db_session_factory()
    ainda_pendente = session.get(Usuario, usuario.id)
    assert ainda_pendente.status_cadastro == StatusCadastro.PENDENTE
    session.close()


def test_token_expirado_nao_aprova(client, db_session_factory, monkeypatch):
    session = db_session_factory()
    admin = _criar_admin(session, "admin5@x.com")
    usuario = _criar_usuario(session, "carlos@x.com")
    session.close()

    monkeypatch.setattr(settings, "token_aprovacao_expira_minutos", 0)
    token = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")
    time.sleep(1.1)

    resp = client.get(f"/api/auth/aprovar-cadastro?token={token}")

    assert resp.status_code == 200
    assert "expirado" in resp.text.lower()

    session = db_session_factory()
    ainda_pendente = session.get(Usuario, usuario.id)
    assert ainda_pendente.status_cadastro == StatusCadastro.PENDENTE
    session.close()


def test_token_malformado_retorna_pagina_de_erro(client):
    resp = client.get("/api/auth/aprovar-cadastro?token=isso-nao-e-valido")

    assert resp.status_code == 200
    assert "inválido" in resp.text.lower()


def test_nome_do_usuario_e_escapado_na_pagina_html(client, db_session_factory):
    """O nome vem do próprio cadastro (não confiável) e é interpolado na
    página que o admin vê -- precisa escapar para não abrir XSS refletido."""
    session = db_session_factory()
    admin = _criar_admin(session, "admin6@x.com")
    usuario = _criar_usuario(session, "xss@x.com", nome="<script>alert(1)</script>")
    session.close()

    token = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")
    resp = client.get(f"/api/auth/aprovar-cadastro?token={token}")

    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text
