from app.models.models import LogAuditoria, RoleUsuario, StatusCadastro, Usuario


def _criar_usuario(
    session,
    email="usuario@x.com",
    nome="Usuária Teste",
    role=RoleUsuario.COMUM,
    status_cadastro=StatusCadastro.APROVADO,
    is_active=True,
):
    usuario = Usuario(
        nome=nome,
        email=email,
        hashed_password="x",
        role=role,
        status_cadastro=status_cadastro,
        is_active=is_active,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def _criar_admin(session, email="admin@x.com", nome="Admin Teste"):
    return _criar_usuario(session, email=email, nome=nome, role=RoleUsuario.ADMINISTRADOR)


# --------------------------------------------------------------------------
# GET /api/usuarios
# --------------------------------------------------------------------------


def test_listar_usuarios_com_sucesso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    _criar_usuario(session, email="comum1@x.com", nome="Comum Um")
    _criar_usuario(session, email="comum2@x.com", nome="Comum Dois", status_cadastro=StatusCadastro.PENDENTE)
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/usuarios")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 3
    assert len(corpo["itens"]) == 3


def test_listar_usuarios_filtra_por_role_e_status_e_busca(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    _criar_usuario(session, email="pendente@x.com", nome="Fulano Pendente", status_cadastro=StatusCadastro.PENDENTE)
    _criar_usuario(session, email="aprovado@x.com", nome="Beltrano Aprovado")
    session.close()
    logar_usuario(admin)

    resp_role = client.get("/api/usuarios", params={"role": "administrador"})
    assert resp_role.status_code == 200
    assert resp_role.json()["total"] == 1

    resp_status = client.get("/api/usuarios", params={"status_cadastro": "pendente"})
    assert resp_status.status_code == 200
    assert resp_status.json()["total"] == 1
    assert resp_status.json()["itens"][0]["email"] == "pendente@x.com"

    resp_busca = client.get("/api/usuarios", params={"busca": "beltrano"})
    assert resp_busca.status_code == 200
    assert resp_busca.json()["total"] == 1
    assert resp_busca.json()["itens"][0]["email"] == "aprovado@x.com"


def test_listar_usuarios_status_invalido_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/usuarios", params={"status_cadastro": "invalido"})
    assert resp.status_code == 400


def test_listar_usuarios_sem_ser_admin_retorna_403(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    comum = _criar_usuario(session)
    session.close()
    logar_usuario(comum)

    resp = client.get("/api/usuarios")
    assert resp.status_code == 403


def test_listar_usuarios_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/usuarios")
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# PATCH /api/usuarios/{id}
# --------------------------------------------------------------------------


def test_editar_usuario_troca_papel_com_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch(f"/api/usuarios/{alvo.id}", json={"role": "administrador"})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["role"] == "administrador"

    session = db_session_factory()
    alvo_atualizado = session.get(Usuario, alvo.id)
    assert alvo_atualizado.role == RoleUsuario.ADMINISTRADOR
    log = session.query(LogAuditoria).filter_by(usuario_id=admin.id, acao="edicao_usuario").one()
    assert "papel" in log.resultado_resumo
    session.close()


def test_editar_usuario_toggle_is_active(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch(f"/api/usuarios/{alvo.id}", json={"is_active": False})

    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_editar_usuario_papel_invalido_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch(f"/api/usuarios/{alvo.id}", json={"role": "super-admin"})
    assert resp.status_code == 400


def test_editar_usuario_sem_campos_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch(f"/api/usuarios/{alvo.id}", json={})
    assert resp.status_code == 400


def test_editar_usuario_autoedicao_bloqueada(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch(f"/api/usuarios/{admin.id}", json={"role": "comum"})
    assert resp.status_code == 400


def test_editar_usuario_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    session.close()
    logar_usuario(admin)

    resp = client.patch("/api/usuarios/999999", json={"role": "comum"})
    assert resp.status_code == 404


def test_editar_usuario_sem_ser_admin_retorna_403(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    comum = _criar_usuario(session)
    alvo = _criar_usuario(session, email="outro@x.com")
    session.close()
    logar_usuario(comum)

    resp = client.patch(f"/api/usuarios/{alvo.id}", json={"role": "administrador"})
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Aprovar / reprovar (unitário e em lote)
# --------------------------------------------------------------------------


def test_aprovar_usuario_pendente_com_sucesso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session, status_cadastro=StatusCadastro.PENDENTE, is_active=False)
    session.close()
    logar_usuario(admin)

    resp = client.post(f"/api/usuarios/{alvo.id}/aprovar")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "usuario_id": alvo.id}

    session = db_session_factory()
    alvo_atualizado = session.get(Usuario, alvo.id)
    assert alvo_atualizado.status_cadastro == StatusCadastro.APROVADO
    assert alvo_atualizado.is_active is True
    assert alvo_atualizado.aprovado_por_usuario_id == admin.id
    session.close()


def test_reprovar_usuario_pendente_com_sucesso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session, status_cadastro=StatusCadastro.PENDENTE, is_active=False)
    session.close()
    logar_usuario(admin)

    resp = client.post(f"/api/usuarios/{alvo.id}/reprovar")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "usuario_id": alvo.id}

    session = db_session_factory()
    alvo_atualizado = session.get(Usuario, alvo.id)
    assert alvo_atualizado.status_cadastro == StatusCadastro.REPROVADO
    assert alvo_atualizado.is_active is False
    session.close()


def test_aprovar_usuario_ja_processado_retorna_erro_no_corpo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    alvo = _criar_usuario(session, status_cadastro=StatusCadastro.APROVADO)
    session.close()
    logar_usuario(admin)

    resp = client.post(f"/api/usuarios/{alvo.id}/aprovar")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "erro"


def test_aprovar_usuario_inexistente_retorna_erro_no_corpo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    session.close()
    logar_usuario(admin)

    resp = client.post("/api/usuarios/999999/aprovar")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "erro"


def test_aprovar_usuario_sem_ser_admin_retorna_403(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    comum = _criar_usuario(session)
    alvo = _criar_usuario(session, email="outro@x.com", status_cadastro=StatusCadastro.PENDENTE)
    session.close()
    logar_usuario(comum)

    resp = client.post(f"/api/usuarios/{alvo.id}/aprovar")
    assert resp.status_code == 403


def test_aprovar_usuarios_lote_com_sucesso_parcial(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    pendente = _criar_usuario(session, email="pendente@x.com", status_cadastro=StatusCadastro.PENDENTE, is_active=False)
    ja_aprovado = _criar_usuario(session, email="ja@x.com", status_cadastro=StatusCadastro.APROVADO)
    session.close()
    logar_usuario(admin)

    resp = client.post("/api/usuarios/aprovar-lote", json={"ids": [pendente.id, ja_aprovado.id, 999999]})

    assert resp.status_code == 200
    resultados = resp.json()["resultados"]
    assert resultados[0]["status"] == "ok"
    assert resultados[1]["status"] == "erro"
    assert resultados[2]["status"] == "erro"


def test_reprovar_usuarios_lote_com_sucesso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    pendente_a = _criar_usuario(session, email="a@x.com", status_cadastro=StatusCadastro.PENDENTE, is_active=False)
    pendente_b = _criar_usuario(session, email="b@x.com", status_cadastro=StatusCadastro.PENDENTE, is_active=False)
    session.close()
    logar_usuario(admin)

    resp = client.post("/api/usuarios/reprovar-lote", json={"ids": [pendente_a.id, pendente_b.id]})

    assert resp.status_code == 200
    resultados = resp.json()["resultados"]
    assert all(r["status"] == "ok" for r in resultados)

    session = db_session_factory()
    assert session.get(Usuario, pendente_a.id).status_cadastro == StatusCadastro.REPROVADO
    assert session.get(Usuario, pendente_b.id).status_cadastro == StatusCadastro.REPROVADO
    session.close()
