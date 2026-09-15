from datetime import datetime

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


def _criar_log(session, usuario_id, acao, criado_em, **kwargs):
    log = LogAuditoria(usuario_id=usuario_id, acao=acao, criado_em=criado_em, **kwargs)
    session.add(log)
    session.commit()
    session.refresh(log)
    return log


# --------------------------------------------------------------------------
# GET /api/logs-auditoria
# --------------------------------------------------------------------------


def test_listar_logs_com_sucesso_ordenado_do_mais_recente(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com", nome="Maria Silva")
    _criar_log(session, autor.id, "login", datetime(2026, 9, 13, 17, 2), resultado_resumo="Acesso ao sistema")
    _criar_log(session, autor.id, "upload_xml", datetime(2026, 9, 15, 11, 47), resultado_resumo="Enviou lote com 42 notas")
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 2
    assert corpo["itens"][0]["acao"] == "upload_xml"
    assert corpo["itens"][1]["acao"] == "login"
    assert corpo["itens"][0]["usuario_nome"] == "Maria Silva"


def test_listar_logs_inclui_detalhe_de_consulta_ia(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com")
    _criar_log(
        session,
        autor.id,
        "consulta_ia",
        datetime(2026, 9, 15, 14, 32),
        pergunta_usuario="Quantas notas entraram em agosto?",
        sql_gerado="SELECT COUNT(*) FROM notas",
        resultado_resumo="Quantas notas entraram em agosto?",
    )
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria")

    assert resp.status_code == 200
    item = resp.json()["itens"][0]
    assert item["pergunta_usuario"] == "Quantas notas entraram em agosto?"
    assert item["sql_gerado"] == "SELECT COUNT(*) FROM notas"


def test_listar_logs_sem_detalhe_extra(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com")
    _criar_log(session, autor.id, "login", datetime(2026, 9, 13, 17, 2), resultado_resumo="Acesso ao sistema")
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria")

    item = resp.json()["itens"][0]
    assert item["pergunta_usuario"] is None
    assert item["sql_gerado"] is None


def test_listar_logs_filtra_por_intervalo_de_data(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com")
    _criar_log(session, autor.id, "login", datetime(2026, 9, 10, 9, 0))
    _criar_log(session, autor.id, "login", datetime(2026, 9, 15, 9, 0))
    _criar_log(session, autor.id, "login", datetime(2026, 9, 20, 9, 0))
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria", params={"data_inicio": "2026-09-12", "data_fim": "2026-09-16"})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1


def test_listar_logs_data_fim_inclui_o_dia_inteiro(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com")
    _criar_log(session, autor.id, "login", datetime(2026, 9, 15, 23, 59))
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria", params={"data_fim": "2026-09-15"})

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_listar_logs_respeita_paginacao(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    autor = _criar_usuario(session, email="autor@x.com")
    for dia in range(1, 6):
        _criar_log(session, autor.id, "login", datetime(2026, 9, dia, 9, 0))
    session.close()
    logar_usuario(admin)

    resp = client.get("/api/logs-auditoria", params={"limit": 2, "offset": 0})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 5
    assert len(corpo["itens"]) == 2


def test_listar_logs_sem_ser_admin_retorna_403(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    comum = _criar_usuario(session)
    session.close()
    logar_usuario(comum)

    resp = client.get("/api/logs-auditoria")
    assert resp.status_code == 403


def test_listar_logs_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/logs-auditoria")
    assert resp.status_code == 401
