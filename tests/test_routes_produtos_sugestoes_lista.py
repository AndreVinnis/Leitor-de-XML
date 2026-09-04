from app.models.models import (
    ClienteCaso,
    ItemNota,
    LogAuditoria,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
    StatusRevisao,
    SugestaoNormalizacao,
    TipoNota,
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


def _criar_sugestao(
    session,
    caso_id,
    chave_acesso,
    descricao,
    nome_canonico,
    categoria=None,
    emitente_nome=None,
    confianca=0.9,
    status=StatusRevisao.PENDENTE,
):
    """Monta nota + item + canônico + sugestão, alimentando o índice de filtros da tela."""
    nota = Nota(
        chave_acesso=chave_acesso,
        tipo=TipoNota.ENTRADA,
        cliente_caso_id=caso_id,
        emitente_nome=emitente_nome,
    )
    session.add(nota)
    session.commit()
    session.refresh(nota)

    item = ItemNota(nota_id=nota.id, descricao_original=descricao)
    session.add(item)
    session.commit()
    session.refresh(item)

    canonico = ProdutoCanonico(cliente_caso_id=caso_id, nome_canonico=nome_canonico, categoria=categoria)
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    sugestao = SugestaoNormalizacao(
        item_nota_id=item.id,
        produto_canonico_sugerido_id=canonico.id,
        confianca=confianca,
        status=status,
    )
    session.add(sugestao)
    session.commit()
    session.refresh(sugestao)

    return sugestao, item, canonico, nota


def test_listar_sugestoes_devolve_nome_canonico_categoria_e_fornecedor(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    sugestao, item, canonico, nota = _criar_sugestao(
        session,
        caso.id,
        "1" * 44,
        "COCA COLA 350ML LT",
        "Coca-Cola Lata 350ml",
        categoria="Bebidas",
        emitente_nome="Distribuidora ABC",
    )
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/sugestoes?cliente_caso_id={caso.id}")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    (item_resp,) = corpo["itens"]
    assert item_resp["nome_canonico"] == "Coca-Cola Lata 350ml"
    assert item_resp["categoria"] == "Bebidas"
    assert item_resp["fornecedor"] == "Distribuidora ABC"
    assert item_resp["produto_canonico_sugerido_id"] == canonico.id


def test_listar_sugestoes_status_todos_nao_filtra(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_sugestao(
        session, caso.id, "1" * 44, "ITEM A", "Item A", status=StatusRevisao.PENDENTE
    )
    _criar_sugestao(
        session, caso.id, "2" * 44, "ITEM B", "Item B", status=StatusRevisao.CONFIRMADO
    )
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=todos")

    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_listar_sugestoes_status_invalido_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=inexistente")

    assert resp.status_code == 400


def test_listar_sugestoes_filtro_categoria(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_sugestao(
        session, caso.id, "1" * 44, "ITEM A", "Item A", categoria="Bebidas"
    )
    _criar_sugestao(
        session, caso.id, "2" * 44, "ITEM B", "Item B", categoria="Limpeza"
    )
    session.close()
    logar_usuario(usuario)

    resp = client.get(
        f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=todos&categoria=Bebidas"
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["categoria"] == "Bebidas"


def test_listar_sugestoes_filtro_fornecedor(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_sugestao(
        session, caso.id, "1" * 44, "ITEM A", "Item A", emitente_nome="Fornecedor X"
    )
    _criar_sugestao(
        session, caso.id, "2" * 44, "ITEM B", "Item B", emitente_nome="Fornecedor Y"
    )
    session.close()
    logar_usuario(usuario)

    resp = client.get(
        "/api/produtos/sugestoes",
        params={"cliente_caso_id": caso.id, "status": "todos", "fornecedor": "Fornecedor X"},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["fornecedor"] == "Fornecedor X"


def test_listar_sugestoes_busca_por_descricao_ou_canonico(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_sugestao(session, caso.id, "1" * 44, "COCA COLA 350ML LT", "Coca-Cola Lata 350ml")
    _criar_sugestao(session, caso.id, "2" * 44, "DETERG NEUTRO 500ML", "Detergente Neutro 500ml")
    session.close()
    logar_usuario(usuario)

    # busca deve casar tanto pela descrição original quanto pelo nome canônico,
    # e ser case-insensitive (ILIKE) tanto no MySQL de produção quanto no SQLite dos testes.
    resp = client.get(f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=todos&busca=coca")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["nome_canonico"] == "Coca-Cola Lata 350ml"


def test_listar_sugestoes_paginacao(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    for i in range(5):
        _criar_sugestao(session, caso.id, str(i) * 44, f"ITEM {i}", f"Item Canônico {i}")
    session.close()
    logar_usuario(usuario)

    resp = client.get(
        f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=todos&limit=2&offset=0"
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 5
    assert len(corpo["itens"]) == 2

    resp2 = client.get(
        f"/api/produtos/sugestoes?cliente_caso_id={caso.id}&status=todos&limit=2&offset=4"
    )
    corpo2 = resp2.json()
    assert corpo2["total"] == 5
    assert len(corpo2["itens"]) == 1


def test_confirmar_sugestoes_em_lote(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    sugestao1, item1, _, _ = _criar_sugestao(session, caso.id, "1" * 44, "ITEM A", "Item A")
    sugestao2, item2, _, _ = _criar_sugestao(session, caso.id, "2" * 44, "ITEM B", "Item B")
    ids = [sugestao1.id, sugestao2.id]
    session.close()
    logar_usuario(usuario)

    resp = client.post("/api/produtos/sugestoes/lote/confirmar", json={"ids": ids})

    assert resp.status_code == 200
    resultados = resp.json()["resultados"]
    assert all(r["status"] == "ok" for r in resultados)

    session = db_session_factory()
    item1_atualizado = session.get(ItemNota, item1.id)
    item2_atualizado = session.get(ItemNota, item2.id)
    assert item1_atualizado.produto_canonico_id == sugestao1.produto_canonico_sugerido_id
    assert item2_atualizado.produto_canonico_id == sugestao2.produto_canonico_sugerido_id
    logs = session.query(LogAuditoria).filter_by(
        usuario_id=usuario.id, acao="confirmacao_sugestao_normalizacao"
    ).all()
    assert len(logs) == 2
    session.close()


def test_rejeitar_sugestoes_em_lote(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    sugestao1, item1, _, _ = _criar_sugestao(session, caso.id, "1" * 44, "ITEM A", "Item A")
    sugestao2, item2, _, _ = _criar_sugestao(session, caso.id, "2" * 44, "ITEM B", "Item B")
    ids = [sugestao1.id, sugestao2.id]
    session.close()
    logar_usuario(usuario)

    resp = client.post("/api/produtos/sugestoes/lote/rejeitar", json={"ids": ids})

    assert resp.status_code == 200
    resultados = resp.json()["resultados"]
    assert all(r["status"] == "ok" for r in resultados)

    session = db_session_factory()
    item1_inalterado = session.get(ItemNota, item1.id)
    item2_inalterado = session.get(ItemNota, item2.id)
    assert item1_inalterado.produto_canonico_id is None
    assert item2_inalterado.produto_canonico_id is None
    sugestao1_atualizada = session.get(SugestaoNormalizacao, sugestao1.id)
    assert sugestao1_atualizada.status == StatusRevisao.REJEITADO
    logs = session.query(LogAuditoria).filter_by(
        usuario_id=usuario.id, acao="rejeicao_sugestao_normalizacao"
    ).all()
    assert len(logs) == 2
    session.close()


def test_acoes_em_lote_sem_autenticacao_retornam_401(client, db_session_factory):
    db_session_factory()
    resp = client.post("/api/produtos/sugestoes/lote/confirmar", json={"ids": [1, 2]})
    assert resp.status_code == 401


def test_listar_canonicos_do_caso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso_a = _criar_caso(session, "Caso A")
    caso_b = _criar_caso(session, "Caso B")
    session.add(ProdutoCanonico(cliente_caso_id=caso_a.id, nome_canonico="Item A", categoria="Cat A"))
    session.add(ProdutoCanonico(cliente_caso_id=caso_b.id, nome_canonico="Item B", categoria="Cat B"))
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/canonicos?cliente_caso_id={caso_a.id}")

    assert resp.status_code == 200
    corpo = resp.json()
    assert len(corpo) == 1
    assert corpo[0]["nome_canonico"] == "Item A"
    assert corpo[0]["categoria"] == "Cat A"


def test_listar_canonicos_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/produtos/canonicos?cliente_caso_id=1")
    assert resp.status_code == 401
