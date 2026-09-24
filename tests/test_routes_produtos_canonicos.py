from datetime import datetime

from app.models.models import (
    AchadoReconciliacao,
    ClienteCaso,
    ItemNota,
    LogAuditoria,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    SituacaoNota,
    StatusCadastro,
    StatusRevisao,
    SugestaoNormalizacao,
    TipoAchado,
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


def test_listar_canonicos_devolve_envelope_com_contagem_de_itens(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    com_itens = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola", categoria="Bebidas")
    sem_itens = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Caderno", categoria="Papelaria")
    session.add_all([com_itens, sem_itens])
    session.commit()
    session.refresh(com_itens)
    nota = Nota(chave_acesso="1" * 44, tipo=TipoNota.ENTRADA, cliente_caso_id=caso.id)
    session.add(nota)
    session.commit()
    session.refresh(nota)
    session.add_all(
        [
            ItemNota(
                nota_id=nota.id,
                descricao_original="COCA 350ML",
                produto_canonico_id=com_itens.id,
            ),
            ItemNota(
                nota_id=nota.id,
                descricao_original="COCA 2L",
                produto_canonico_id=com_itens.id,
            ),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/produtos/canonicos", params={"cliente_caso_id": caso.id})

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 2
    por_nome = {item["nome_canonico"]: item for item in corpo["itens"]}
    assert por_nome["Coca-Cola"]["itens_vinculados_count"] == 2
    assert por_nome["Caderno"]["itens_vinculados_count"] == 0


def test_listar_canonicos_nao_conta_item_de_nota_cancelada(
    client, db_session_factory, logar_usuario
):
    """Item de nota cancelada não pode contar como vínculo -- é exatamente
    a "prova" que a situação da nota existe para invalidar."""
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola", categoria="Bebidas")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    nota_autorizada = Nota(chave_acesso="1" * 44, tipo=TipoNota.ENTRADA, cliente_caso_id=caso.id)
    nota_cancelada = Nota(
        chave_acesso="2" * 44,
        tipo=TipoNota.ENTRADA,
        cliente_caso_id=caso.id,
        situacao=SituacaoNota.CANCELADA,
    )
    session.add_all([nota_autorizada, nota_cancelada])
    session.commit()
    session.refresh(nota_autorizada)
    session.refresh(nota_cancelada)
    session.add_all(
        [
            ItemNota(
                nota_id=nota_autorizada.id,
                descricao_original="COCA 350ML",
                produto_canonico_id=canonico.id,
            ),
            ItemNota(
                nota_id=nota_cancelada.id,
                descricao_original="COCA 2L",
                produto_canonico_id=canonico.id,
            ),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/produtos/canonicos", params={"cliente_caso_id": caso.id})

    assert resp.status_code == 200
    corpo = resp.json()
    por_nome = {item["nome_canonico"]: item for item in corpo["itens"]}
    assert por_nome["Coca-Cola"]["itens_vinculados_count"] == 1  # só o item da nota autorizada


def test_listar_canonicos_filtra_por_categoria_e_busca(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.add_all(
        [
            ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml", categoria="Bebidas"),
            ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Caderno Universitário", categoria="Papelaria"),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(
        "/api/produtos/canonicos", params={"cliente_caso_id": caso.id, "categoria": "Bebidas"}
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["nome_canonico"] == "Coca-Cola Lata 350ml"

    resp_busca = client.get(
        "/api/produtos/canonicos", params={"cliente_caso_id": caso.id, "busca": "caderno"}
    )
    assert resp_busca.status_code == 200
    corpo_busca = resp_busca.json()
    assert corpo_busca["total"] == 1
    assert corpo_busca["itens"][0]["nome_canonico"] == "Caderno Universitário"


def test_listar_canonicos_pagina_com_limit_e_offset(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.add_all(
        [
            ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico=f"Produto {i}")
            for i in range(3)
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(
        "/api/produtos/canonicos",
        params={"cliente_caso_id": caso.id, "limit": 2, "offset": 0},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 3
    assert len(corpo["itens"]) == 2


def test_listar_canonicos_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/produtos/canonicos", params={"cliente_caso_id": 1})
    assert resp.status_code == 401


def test_transferir_canonico_move_itens_exclui_origem_e_grava_log(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    origem = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="MANTEIGA NATVILLE 200G")
    destino = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Manteiga Natville 200g")
    outro = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Caderno Universitário")
    session.add_all([origem, destino, outro])
    session.commit()
    session.refresh(origem)
    session.refresh(destino)
    session.refresh(outro)

    nota_autorizada = Nota(chave_acesso="1" * 44, tipo=TipoNota.ENTRADA, cliente_caso_id=caso.id)
    nota_cancelada = Nota(
        chave_acesso="2" * 44,
        tipo=TipoNota.ENTRADA,
        cliente_caso_id=caso.id,
        situacao=SituacaoNota.CANCELADA,
    )
    session.add_all([nota_autorizada, nota_cancelada])
    session.commit()
    session.refresh(nota_autorizada)
    session.refresh(nota_cancelada)

    item_autorizado = ItemNota(
        nota_id=nota_autorizada.id, descricao_original="MANT NATIVILLE 200G", produto_canonico_id=origem.id
    )
    item_cancelado = ItemNota(
        nota_id=nota_cancelada.id, descricao_original="MANT NATIVILLE 200G", produto_canonico_id=origem.id
    )
    item_outro = ItemNota(
        nota_id=nota_autorizada.id, descricao_original="CADERNO", produto_canonico_id=outro.id
    )
    session.add_all([item_autorizado, item_cancelado, item_outro])
    session.commit()
    session.refresh(item_autorizado)
    session.refresh(item_cancelado)
    session.refresh(item_outro)
    origem_id, destino_id, outro_id = origem.id, destino.id, outro.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["destino_id"] == destino_id
    assert corpo["itens_movidos"] == 2

    session = db_session_factory()
    assert session.get(ProdutoCanonico, origem_id) is None
    assert session.get(ItemNota, item_autorizado.id).produto_canonico_id == destino_id
    assert session.get(ItemNota, item_cancelado.id).produto_canonico_id == destino_id
    assert session.get(ItemNota, item_outro.id).produto_canonico_id == outro_id

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "transferencia_produto_canonico"
    assert "2 item(ns)" in log.resultado_resumo
    session.close()


def test_transferir_canonico_reponta_sugestoes_pendentes_e_revisadas(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    origem = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Origem")
    destino = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Destino")
    session.add_all([origem, destino])
    session.commit()
    session.refresh(origem)
    session.refresh(destino)

    nota = Nota(chave_acesso="1" * 44, tipo=TipoNota.ENTRADA, cliente_caso_id=caso.id)
    session.add(nota)
    session.commit()
    session.refresh(nota)

    item_pendente = ItemNota(nota_id=nota.id, descricao_original="A")
    item_confirmado = ItemNota(nota_id=nota.id, descricao_original="B", produto_canonico_id=origem.id)
    item_do_destino = ItemNota(nota_id=nota.id, descricao_original="C", produto_canonico_id=destino.id)
    session.add_all([item_pendente, item_confirmado, item_do_destino])
    session.commit()
    session.refresh(item_pendente)
    session.refresh(item_confirmado)
    session.refresh(item_do_destino)

    sugestao_pendente = SugestaoNormalizacao(
        item_nota_id=item_pendente.id,
        produto_canonico_sugerido_id=origem.id,
        confianca=0.9,
        status=StatusRevisao.PENDENTE,
    )
    revisado_em = datetime(2026, 9, 12)
    sugestao_confirmada = SugestaoNormalizacao(
        item_nota_id=item_confirmado.id,
        produto_canonico_sugerido_id=origem.id,
        confianca=0.95,
        status=StatusRevisao.CONFIRMADO,
        revisado_por_usuario_id=usuario.id,
        revisado_em=revisado_em,
    )
    sugestao_do_destino = SugestaoNormalizacao(
        item_nota_id=item_do_destino.id,
        produto_canonico_sugerido_id=destino.id,
        confianca=0.8,
        status=StatusRevisao.PENDENTE,
    )
    session.add_all([sugestao_pendente, sugestao_confirmada, sugestao_do_destino])
    session.commit()
    session.refresh(sugestao_pendente)
    session.refresh(sugestao_confirmada)
    session.refresh(sugestao_do_destino)
    origem_id, destino_id = origem.id, destino.id
    total_antes = session.query(SugestaoNormalizacao).count()
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 200
    assert resp.json()["sugestoes_repontadas"] == 2

    session = db_session_factory()
    assert session.query(SugestaoNormalizacao).count() == total_antes

    pendente_atualizada = session.get(SugestaoNormalizacao, sugestao_pendente.id)
    assert pendente_atualizada.produto_canonico_sugerido_id == destino_id

    confirmada_atualizada = session.get(SugestaoNormalizacao, sugestao_confirmada.id)
    assert confirmada_atualizada.produto_canonico_sugerido_id == destino_id
    assert confirmada_atualizada.status == StatusRevisao.CONFIRMADO
    assert confirmada_atualizada.revisado_por_usuario_id == usuario.id
    assert confirmada_atualizada.revisado_em == revisado_em

    do_destino_inalterada = session.get(SugestaoNormalizacao, sugestao_do_destino.id)
    assert do_destino_inalterada.produto_canonico_sugerido_id == destino_id
    session.close()


def test_transferir_canonico_reponta_achados_reconciliacao(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    origem = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Origem")
    destino = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Destino")
    session.add_all([origem, destino])
    session.commit()
    session.refresh(origem)
    session.refresh(destino)

    achado = AchadoReconciliacao(
        produto_canonico_id=origem.id,
        cliente_caso_id=caso.id,
        tipo=TipoAchado.PRODUTO_SEM_ENTRADA,
    )
    session.add(achado)
    session.commit()
    session.refresh(achado)
    origem_id, destino_id, caso_id, achado_id = origem.id, destino.id, caso.id, achado.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 200
    assert resp.json()["achados_repontados"] == 1

    session = db_session_factory()
    achado_atualizado = session.get(AchadoReconciliacao, achado_id)
    assert achado_atualizado.produto_canonico_id == destino_id
    assert achado_atualizado.cliente_caso_id == caso_id
    session.close()


def test_transferir_canonico_sem_itens_vinculados_funciona(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    origem = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Origem")
    destino = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Destino")
    session.add_all([origem, destino])
    session.commit()
    session.refresh(origem)
    session.refresh(destino)
    origem_id, destino_id = origem.id, destino.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["itens_movidos"] == 0
    assert corpo["sugestoes_repontadas"] == 0
    assert corpo["achados_repontados"] == 0

    session = db_session_factory()
    assert session.get(ProdutoCanonico, origem_id) is None
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "transferencia_produto_canonico"
    session.close()


def test_transferir_canonico_para_destino_de_outro_caso_retorna_400(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso_a = _criar_caso(session, nome="Caso A")
    caso_b = _criar_caso(session, nome="Caso B")
    origem = ProdutoCanonico(cliente_caso_id=caso_a.id, nome_canonico="Item Origem")
    destino = ProdutoCanonico(cliente_caso_id=caso_b.id, nome_canonico="Item Destino")
    session.add_all([origem, destino])
    session.commit()
    session.refresh(origem)
    session.refresh(destino)

    nota = Nota(chave_acesso="1" * 44, tipo=TipoNota.ENTRADA, cliente_caso_id=caso_a.id)
    session.add(nota)
    session.commit()
    session.refresh(nota)
    item = ItemNota(nota_id=nota.id, descricao_original="A", produto_canonico_id=origem.id)
    session.add(item)
    session.commit()
    session.refresh(item)
    origem_id, destino_id, item_id = origem.id, destino.id, item.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    assert session.get(ProdutoCanonico, origem_id) is not None
    assert session.get(ItemNota, item_id).produto_canonico_id == origem_id
    assert session.query(LogAuditoria).count() == 0
    session.close()


def test_transferir_canonico_para_si_mesmo_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item X")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)
    canonico_id = canonico.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{canonico_id}/transferir",
        json={"destino_id": canonico_id},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    assert session.get(ProdutoCanonico, canonico_id) is not None
    assert session.query(LogAuditoria).count() == 0
    session.close()


def test_transferir_canonico_destino_inexistente_retorna_400(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    origem = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Origem")
    session.add(origem)
    session.commit()
    session.refresh(origem)
    origem_id = origem.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/canonicos/{origem_id}/transferir",
        json={"destino_id": 999999},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    assert session.get(ProdutoCanonico, origem_id) is not None
    session.close()


def test_transferir_canonico_origem_inexistente_retorna_404(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    destino = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item Destino")
    session.add(destino)
    session.commit()
    session.refresh(destino)
    destino_id = destino.id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        "/api/produtos/canonicos/999999/transferir",
        json={"destino_id": destino_id},
    )

    assert resp.status_code == 404


def test_transferir_canonico_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.post(
        "/api/produtos/canonicos/1/transferir",
        json={"destino_id": 2},
    )
    assert resp.status_code == 401
