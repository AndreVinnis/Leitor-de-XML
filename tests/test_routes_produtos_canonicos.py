from app.models.models import (
    ClienteCaso,
    LogAuditoria,
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
    Usuario,
)


def _criar_usuario(session, email="revisor@x.com"):
    usuario = Usuario(
        nome="Revisora",
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


def _criar_caso(session, nome="Cliente Teste"):
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def test_criar_canonico_com_sucesso_grava_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        "/api/produtos/canonicos",
        json={"cliente_caso_id": caso.id, "nome_canonico": "Item Novo", "categoria": "Bebidas"},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["nome_canonico"] == "Item Novo"
    assert corpo["categoria"] == "Bebidas"
    assert "id" in corpo

    session = db_session_factory()
    canonico = session.get(ProdutoCanonico, corpo["id"])
    assert canonico is not None
    assert canonico.cliente_caso_id == caso.id

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "criacao_produto_canonico"
    session.close()


def test_criar_canonico_nome_duplicado_no_mesmo_caso_retorna_400(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.add(ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Existente"))
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        "/api/produtos/canonicos",
        json={"cliente_caso_id": caso.id, "nome_canonico": "Item Existente", "categoria": None},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    total = (
        session.query(ProdutoCanonico)
        .filter_by(cliente_caso_id=caso.id, nome_canonico="Item Existente")
        .count()
    )
    assert total == 1
    session.close()


def test_criar_canonico_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.post(
        "/api/produtos/canonicos",
        json={"cliente_caso_id": 1, "nome_canonico": "Item X", "categoria": None},
    )
    assert resp.status_code == 401


def test_editar_canonico_nome_e_categoria_com_sucesso_grava_log(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Antigo", categoria="Cat A")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        f"/api/produtos/canonicos/{canonico.id}",
        json={"nome_canonico": "Item Novo", "categoria": "Cat B"},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["nome_canonico"] == "Item Novo"
    assert corpo["categoria"] == "Cat B"

    session = db_session_factory()
    canonico_atualizado = session.get(ProdutoCanonico, canonico.id)
    assert canonico_atualizado.nome_canonico == "Item Novo"
    assert canonico_atualizado.categoria == "Cat B"

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "edicao_produto_canonico"
    session.close()


def test_editar_canonico_categoria_vazia_limpa_o_campo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item X", categoria="Cat A")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        f"/api/produtos/canonicos/{canonico.id}",
        json={"nome_canonico": None, "categoria": ""},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["categoria"] is None

    session = db_session_factory()
    canonico_atualizado = session.get(ProdutoCanonico, canonico.id)
    assert canonico_atualizado.nome_canonico == "Item X"
    assert canonico_atualizado.categoria is None
    session.close()


def test_editar_canonico_nome_duplicado_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico_a = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item A")
    canonico_b = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item B")
    session.add_all([canonico_a, canonico_b])
    session.commit()
    session.refresh(canonico_a)
    session.refresh(canonico_b)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        f"/api/produtos/canonicos/{canonico_b.id}",
        json={"nome_canonico": "Item A", "categoria": None},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    canonico_b_inalterado = session.get(ProdutoCanonico, canonico_b.id)
    assert canonico_b_inalterado.nome_canonico == "Item B"
    session.close()


def test_editar_canonico_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        "/api/produtos/canonicos/999999",
        json={"nome_canonico": "Item X", "categoria": None},
    )

    assert resp.status_code == 404


def test_editar_canonico_sem_campos_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item X")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        f"/api/produtos/canonicos/{canonico.id}",
        json={"nome_canonico": None, "categoria": None},
    )

    assert resp.status_code == 400


def test_editar_canonico_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.patch(
        "/api/produtos/canonicos/1",
        json={"nome_canonico": "Item X", "categoria": None},
    )
    assert resp.status_code == 401
