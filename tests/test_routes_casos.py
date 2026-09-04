from app.models.models import RoleUsuario, StatusCadastro, Usuario


def _criar_usuario(session, email="adv@x.com"):
    usuario = Usuario(
        nome="Advogada",
        email=email,
        hashed_password="x",
        role=RoleUsuario.COMUM,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def test_criar_e_listar_caso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp_criar = client.post(
        "/api/casos", json={"nome_cliente": "Cliente A", "identificacao_caso": "Processo 123"}
    )
    assert resp_criar.status_code == 200
    corpo = resp_criar.json()
    assert corpo["nome_cliente"] == "Cliente A"
    assert corpo["identificacao_caso"] == "Processo 123"
    caso_id = corpo["id"]

    resp_lista = client.get("/api/casos")
    assert resp_lista.status_code == 200
    assert any(c["id"] == caso_id for c in resp_lista.json())

    resp_get = client.get(f"/api/casos/{caso_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["nome_cliente"] == "Cliente A"


def test_criar_caso_sem_identificacao_e_opcional(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv2@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.post("/api/casos", json={"nome_cliente": "Cliente B"})
    assert resp.status_code == 200
    assert resp.json()["identificacao_caso"] is None


def test_obter_caso_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv3@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/casos/999999")
    assert resp.status_code == 404


def test_listar_casos_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()  # garante as tabelas criadas
    resp = client.get("/api/casos")
    assert resp.status_code == 401


def test_criar_caso_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.post("/api/casos", json={"nome_cliente": "Cliente C"})
    assert resp.status_code == 401
