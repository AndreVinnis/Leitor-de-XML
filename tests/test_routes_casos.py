from decimal import Decimal

from app.models.models import (
    AchadoReconciliacao,
    ArquivoLote,
    ClienteCaso,
    EventoNFe,
    ItemNota,
    LogAuditoria,
    Lote,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
    StatusProcessamento,
    StatusRevisao,
    SugestaoNormalizacao,
    TipoAchado,
    TipoNota,
    Usuario,
)


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


def _criar_admin(session, email="admin@x.com"):
    usuario = Usuario(
        nome="Administradora",
        email=email,
        hashed_password="x",
        role=RoleUsuario.ADMINISTRADOR,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def _criar_caso_legado_sem_cnpj(session, nome="Caso Legado"):
    """Simula um caso criado antes de cnpj_cliente existir/virar obrigatório
    -- hoje só é possível chegar nesse estado via dado pré-existente no
    banco, não mais pela API (POST /api/casos exige cnpj_cliente)."""
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def test_criar_e_listar_caso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp_criar = client.post(
        "/api/casos",
        json={
            "nome_cliente": "Cliente A",
            "identificacao_caso": "Processo 123",
            "cnpj_cliente": "11222333000181",
        },
    )
    assert resp_criar.status_code == 200
    corpo = resp_criar.json()
    assert corpo["nome_cliente"] == "Cliente A"
    assert corpo["identificacao_caso"] == "Processo 123"
    assert corpo["cnpj_cliente"] == "11222333000181"
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

    resp = client.post(
        "/api/casos", json={"nome_cliente": "Cliente B", "cnpj_cliente": "11222333000181"}
    )
    assert resp.status_code == 200
    assert resp.json()["identificacao_caso"] is None


def test_criar_caso_com_cnpj_normaliza_pontuacao(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv4@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.post(
        "/api/casos",
        json={"nome_cliente": "Cliente D", "cnpj_cliente": "11.222.333/0001-81"},
    )
    assert resp.status_code == 200
    assert resp.json()["cnpj_cliente"] == "11222333000181"


def test_criar_caso_com_cnpj_invalido_retorna_422(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv5@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.post("/api/casos", json={"nome_cliente": "Cliente E", "cnpj_cliente": "123"})
    assert resp.status_code == 422


def test_criar_caso_sem_cnpj_retorna_422(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv8@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.post("/api/casos", json={"nome_cliente": "Cliente G"})
    assert resp.status_code == 422


def test_atualizar_caso_preenche_cnpj_de_caso_legado(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv6@x.com")
    caso = _criar_caso_legado_sem_cnpj(session, "Cliente F")
    caso_id = caso.id
    session.close()
    logar_usuario(usuario)

    resp = client.patch(f"/api/casos/{caso_id}", json={"cnpj_cliente": "11222333000181"})
    assert resp.status_code == 200
    assert resp.json()["cnpj_cliente"] == "11222333000181"
    assert resp.json()["nome_cliente"] == "Cliente F"  # campo não enviado permanece igual


def test_atualizar_caso_sem_mexer_no_cnpj_nao_altera(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv9@x.com")
    session.close()
    logar_usuario(usuario)

    caso_id = client.post(
        "/api/casos", json={"nome_cliente": "Cliente H", "cnpj_cliente": "11222333000181"}
    ).json()["id"]

    resp = client.patch(f"/api/casos/{caso_id}", json={"nome_cliente": "Cliente H Editado"})
    assert resp.status_code == 200
    assert resp.json()["nome_cliente"] == "Cliente H Editado"
    assert resp.json()["cnpj_cliente"] == "11222333000181"  # não foi tocado, permanece


def test_atualizar_caso_nao_permite_remover_cnpj(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv10@x.com")
    session.close()
    logar_usuario(usuario)

    caso_id = client.post(
        "/api/casos", json={"nome_cliente": "Cliente I", "cnpj_cliente": "11222333000181"}
    ).json()["id"]

    resp = client.patch(f"/api/casos/{caso_id}", json={"cnpj_cliente": None})
    assert resp.status_code == 422


def test_atualizar_caso_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv7@x.com")
    session.close()
    logar_usuario(usuario)

    resp = client.patch("/api/casos/999999", json={"cnpj_cliente": "11222333000181"})
    assert resp.status_code == 404


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
    resp = client.post(
        "/api/casos", json={"nome_cliente": "Cliente C", "cnpj_cliente": "11222333000181"}
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# CNPJ imutável depois de definido (PATCH /api/casos/{id})
# --------------------------------------------------------------------------


def test_atualizar_caso_com_cnpj_ja_definido_retorna_422(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv11@x.com")
    session.close()
    logar_usuario(usuario)

    caso_id = client.post(
        "/api/casos", json={"nome_cliente": "Cliente J", "cnpj_cliente": "11222333000181"}
    ).json()["id"]

    resp = client.patch(f"/api/casos/{caso_id}", json={"cnpj_cliente": "11444777000161"})
    assert resp.status_code == 422


def test_atualizar_caso_reenviar_mesmo_cnpj_nao_da_erro(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv12@x.com")
    session.close()
    logar_usuario(usuario)

    caso_id = client.post(
        "/api/casos", json={"nome_cliente": "Cliente K", "cnpj_cliente": "11222333000181"}
    ).json()["id"]

    resp = client.patch(f"/api/casos/{caso_id}", json={"cnpj_cliente": "11222333000181"})
    assert resp.status_code == 200
    assert resp.json()["cnpj_cliente"] == "11222333000181"


# --------------------------------------------------------------------------
# DELETE /api/casos/{id}
# --------------------------------------------------------------------------


def _montar_caso_com_dados_relacionados(session, cliente_caso_id):
    """Cria uma nota, um item, um produto canônico, uma sugestão de
    normalização, um achado de reconciliação e um lote/arquivo de lote, tudo
    vinculado ao mesmo cliente_caso_id -- cobre toda a cadeia de FK que o
    DELETE precisa limpar."""
    nota = Nota(
        chave_acesso="1" * 44,
        tipo=TipoNota.ENTRADA,
        cliente_caso_id=cliente_caso_id,
    )
    session.add(nota)
    session.commit()
    session.refresh(nota)

    produto = ProdutoCanonico(cliente_caso_id=cliente_caso_id, nome_canonico="Produto X")
    session.add(produto)
    session.commit()
    session.refresh(produto)

    item = ItemNota(
        nota_id=nota.id,
        descricao_original="Produto X original",
        produto_canonico_id=produto.id,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    sugestao = SugestaoNormalizacao(
        item_nota_id=item.id,
        produto_canonico_sugerido_id=produto.id,
        confianca=Decimal("0.9000"),
        status=StatusRevisao.PENDENTE,
    )
    achado = AchadoReconciliacao(
        produto_canonico_id=produto.id,
        cliente_caso_id=cliente_caso_id,
        tipo=TipoAchado.SALDO_NEGATIVO,
    )
    session.add_all([sugestao, achado])
    session.commit()

    lote = Lote(
        id="11111111-1111-1111-1111-111111111111",
        cliente_caso_id=cliente_caso_id,
        cnpj_cliente="11222333000181",
        total_arquivos=1,
        criado_por_usuario_id=session.query(Usuario).first().id,
    )
    session.add(lote)
    session.commit()

    arquivo = ArquivoLote(
        lote_id=lote.id,
        nome_arquivo="nota.xml",
        status=StatusProcessamento.SUCESSO,
        nota_id=nota.id,
    )
    session.add(arquivo)
    session.commit()

    evento = EventoNFe(
        cliente_caso_id=cliente_caso_id,
        chave_acesso=nota.chave_acesso,
        tipo_evento="110111",
        numero_sequencia=1,
        cstat="135",
        aplicado=True,
        nota_id=nota.id,
    )
    session.add(evento)
    session.commit()

    return {
        "nota_id": nota.id,
        "item_id": item.id,
        "produto_id": produto.id,
        "sugestao_id": sugestao.id,
        "achado_id": achado.id,
        "lote_id": lote.id,
        "arquivo_id": arquivo.id,
        "evento_id": evento.id,
    }


def test_excluir_caso_admin_remove_tudo_e_gera_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session)
    caso = ClienteCaso(nome_cliente="Cliente L", cnpj_cliente="11222333000181")
    session.add(caso)
    session.commit()
    session.refresh(caso)
    caso_id = caso.id

    ids = _montar_caso_com_dados_relacionados(session, caso_id)
    session.close()
    logar_usuario(admin)

    resp = client.delete(f"/api/casos/{caso_id}")
    assert resp.status_code == 204

    session = db_session_factory()
    assert session.get(ClienteCaso, caso_id) is None
    assert session.get(Nota, ids["nota_id"]) is None
    assert session.get(ItemNota, ids["item_id"]) is None
    assert session.get(ProdutoCanonico, ids["produto_id"]) is None
    assert session.get(SugestaoNormalizacao, ids["sugestao_id"]) is None
    assert session.get(AchadoReconciliacao, ids["achado_id"]) is None
    assert session.get(Lote, ids["lote_id"]) is None
    assert session.get(ArquivoLote, ids["arquivo_id"]) is None
    assert session.get(EventoNFe, ids["evento_id"]) is None

    logs = session.query(LogAuditoria).filter(LogAuditoria.acao == "exclusao_cliente_caso").all()
    assert len(logs) == 1
    assert logs[0].usuario_id == admin.id
    assert "Cliente L" in logs[0].resultado_resumo
    session.close()


def test_excluir_caso_usuario_comum_retorna_403(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, "adv13@x.com")
    caso = ClienteCaso(nome_cliente="Cliente M", cnpj_cliente="11222333000181")
    session.add(caso)
    session.commit()
    session.refresh(caso)
    caso_id = caso.id
    session.close()
    logar_usuario(usuario)

    resp = client.delete(f"/api/casos/{caso_id}")
    assert resp.status_code == 403


def test_excluir_caso_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    admin = _criar_admin(session, "admin2@x.com")
    session.close()
    logar_usuario(admin)

    resp = client.delete("/api/casos/999999")
    assert resp.status_code == 404


def test_excluir_caso_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.delete("/api/casos/999999")
    assert resp.status_code == 401
