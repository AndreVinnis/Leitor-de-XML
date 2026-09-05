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


def _montar_sugestao_pendente(session, chave_acesso):
    caso = ClienteCaso(nome_cliente="Cliente Teste")
    session.add(caso)
    session.commit()
    session.refresh(caso)

    nota = Nota(chave_acesso=chave_acesso, tipo=TipoNota.ENTRADA, cliente_caso_id=caso.id)
    session.add(nota)
    session.commit()
    session.refresh(nota)

    item = ItemNota(nota_id=nota.id, descricao_original="ITEM X")
    session.add(item)
    session.commit()
    session.refresh(item)

    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item X")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    sugestao = SugestaoNormalizacao(
        item_nota_id=item.id,
        produto_canonico_sugerido_id=canonico.id,
        confianca=0.9,
        status=StatusRevisao.PENDENTE,
    )
    session.add(sugestao)
    session.commit()
    session.refresh(sugestao)

    return sugestao, item


def test_confirmar_sugestao_usa_usuario_do_jwt_e_grava_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    sugestao, item = _montar_sugestao_pendente(session, "1" * 44)
    session.close()
    logar_usuario(usuario)

    resp = client.post(f"/api/produtos/sugestoes/{sugestao.id}/confirmar")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "sugestao_id": sugestao.id}

    session = db_session_factory()
    item_atualizado = session.get(ItemNota, item.id)
    sugestao_atualizada = session.get(SugestaoNormalizacao, sugestao.id)
    assert item_atualizado.produto_canonico_id == sugestao.produto_canonico_sugerido_id
    assert sugestao_atualizada.status == StatusRevisao.CONFIRMADO
    assert sugestao_atualizada.revisado_por_usuario_id == usuario.id

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "confirmacao_sugestao_normalizacao"
    session.close()


def test_rejeitar_sugestao_usa_usuario_do_jwt_e_grava_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "revisor2@x.com")
    sugestao, item = _montar_sugestao_pendente(session, "2" * 44)
    session.close()
    logar_usuario(usuario)

    resp = client.post(f"/api/produtos/sugestoes/{sugestao.id}/rejeitar")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "sugestao_id": sugestao.id}

    session = db_session_factory()
    item_inalterado = session.get(ItemNota, item.id)
    sugestao_atualizada = session.get(SugestaoNormalizacao, sugestao.id)
    assert item_inalterado.produto_canonico_id is None
    assert sugestao_atualizada.status == StatusRevisao.REJEITADO
    assert sugestao_atualizada.revisado_por_usuario_id == usuario.id

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "rejeicao_sugestao_normalizacao"
    session.close()


def test_confirmar_sugestao_sem_autenticacao_retorna_401(client, db_session_factory):
    session = db_session_factory()
    sugestao, _ = _montar_sugestao_pendente(session, "3" * 44)
    session.close()

    resp = client.post(f"/api/produtos/sugestoes/{sugestao.id}/confirmar")
    assert resp.status_code == 401


def test_listar_sugestoes_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/produtos/sugestoes?cliente_caso_id=1")
    assert resp.status_code == 401


def test_corrigir_sugestao_usa_canonico_escolhido_e_preserva_sugerido_original(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    sugestao, item = _montar_sugestao_pendente(session, "4" * 44)
    caso_id = session.get(Nota, item.nota_id).cliente_caso_id
    outro_canonico = ProdutoCanonico(cliente_caso_id=caso_id, nome_canonico="Item Y")
    session.add(outro_canonico)
    session.commit()
    session.refresh(outro_canonico)
    produto_sugerido_original_id = sugestao.produto_canonico_sugerido_id
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/sugestoes/{sugestao.id}/corrigir",
        json={"produto_canonico_id": outro_canonico.id},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "sugestao_id": sugestao.id}

    session = db_session_factory()
    item_atualizado = session.get(ItemNota, item.id)
    sugestao_atualizada = session.get(SugestaoNormalizacao, sugestao.id)
    assert item_atualizado.produto_canonico_id == outro_canonico.id
    assert sugestao_atualizada.produto_canonico_sugerido_id == produto_sugerido_original_id
    assert sugestao_atualizada.status == StatusRevisao.CONFIRMADO
    assert sugestao_atualizada.revisado_por_usuario_id == usuario.id

    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "correcao_sugestao_normalizacao"
    session.close()


def test_corrigir_sugestao_com_canonico_de_outro_caso_retorna_400(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    sugestao, item = _montar_sugestao_pendente(session, "5" * 44)
    outro_caso = ClienteCaso(nome_cliente="Outro Cliente")
    session.add(outro_caso)
    session.commit()
    session.refresh(outro_caso)
    canonico_outro_caso = ProdutoCanonico(cliente_caso_id=outro_caso.id, nome_canonico="Item Z")
    session.add(canonico_outro_caso)
    session.commit()
    session.refresh(canonico_outro_caso)
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        f"/api/produtos/sugestoes/{sugestao.id}/corrigir",
        json={"produto_canonico_id": canonico_outro_caso.id},
    )

    assert resp.status_code == 400

    session = db_session_factory()
    item_inalterado = session.get(ItemNota, item.id)
    sugestao_inalterada = session.get(SugestaoNormalizacao, sugestao.id)
    assert item_inalterado.produto_canonico_id is None
    assert sugestao_inalterada.status == StatusRevisao.PENDENTE
    session.close()


def test_corrigir_sugestao_ja_nao_pendente_retorna_erro_no_corpo(
    client, db_session_factory, logar_usuario
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    sugestao, item = _montar_sugestao_pendente(session, "6" * 44)
    caso_id = session.get(Nota, item.nota_id).cliente_caso_id
    outro_canonico = ProdutoCanonico(cliente_caso_id=caso_id, nome_canonico="Item W")
    session.add(outro_canonico)
    session.commit()
    session.refresh(outro_canonico)
    session.close()
    logar_usuario(usuario)

    # confirma a sugestão primeiro, deixando-a fora do status PENDENTE.
    client.post(f"/api/produtos/sugestoes/{sugestao.id}/confirmar")

    resp = client.post(
        f"/api/produtos/sugestoes/{sugestao.id}/corrigir",
        json={"produto_canonico_id": outro_canonico.id},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "erro"

    session = db_session_factory()
    item_inalterado = session.get(ItemNota, item.id)
    assert item_inalterado.produto_canonico_id == sugestao.produto_canonico_sugerido_id
    session.close()


def test_corrigir_sugestao_sem_autenticacao_retorna_401(client, db_session_factory):
    session = db_session_factory()
    sugestao, _ = _montar_sugestao_pendente(session, "7" * 44)
    session.close()

    resp = client.post(
        f"/api/produtos/sugestoes/{sugestao.id}/corrigir",
        json={"produto_canonico_id": 1},
    )
    assert resp.status_code == 401
