from datetime import datetime

from app.models.models import (
    ClienteCaso,
    ItemNota,
    LogAuditoria,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
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


def _criar_nota(session, caso_id, chave, tipo=TipoNota.ENTRADA, emitente=None, numero=None, data_emissao=None):
    nota = Nota(
        chave_acesso=chave,
        tipo=tipo,
        numero=numero,
        emitente_nome=emitente,
        cliente_caso_id=caso_id,
        data_emissao=data_emissao,
    )
    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota


def test_listar_itens_vinculados_com_sucesso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml", categoria="Bebidas")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    nota_entrada = _criar_nota(
        session, caso.id, "1" * 44, TipoNota.ENTRADA, emitente="Distribuidora Ouro Fino Ltda",
        numero="477", data_emissao=datetime(2026, 8, 29),
    )
    nota_saida = _criar_nota(
        session, caso.id, "2" * 44, TipoNota.SAIDA, emitente="Papelaria Central Norte",
        numero="479", data_emissao=datetime(2026, 8, 30),
    )
    session.add_all(
        [
            ItemNota(
                nota_id=nota_entrada.id,
                descricao_original="COCA COLA 350ML LT",
                quantidade=120,
                unidade="CX",
                valor_unitario=32,
                valor_total=3840,
                produto_canonico_id=canonico.id,
            ),
            ItemNota(
                nota_id=nota_saida.id,
                descricao_original="COCA COLA LATA 350",
                quantidade=24,
                unidade="UN",
                valor_unitario="4.20",
                valor_total="100.80",
                produto_canonico_id=canonico.id,
            ),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/canonicos/{canonico.id}/itens")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["produto_canonico"]["nome_canonico"] == "Coca-Cola Lata 350ml"
    assert corpo["total"] == 2
    assert len(corpo["itens"]) == 2
    primeiro = corpo["itens"][0]
    assert primeiro["tipo"] == "entrada"
    assert primeiro["fornecedor"] == "Distribuidora Ouro Fino Ltda"
    assert primeiro["quantidade"] == "120.0000"
    assert primeiro["valor_total"] == "3840.00"


def test_listar_itens_vinculados_filtra_por_fornecedor_e_data(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    nota_a = _criar_nota(
        session, caso.id, "3" * 44, emitente="Fornecedor A", numero="1", data_emissao=datetime(2026, 1, 1)
    )
    nota_b = _criar_nota(
        session, caso.id, "4" * 44, emitente="Fornecedor B", numero="2", data_emissao=datetime(2026, 6, 1)
    )
    session.add_all(
        [
            ItemNota(nota_id=nota_a.id, descricao_original="Item A", produto_canonico_id=canonico.id),
            ItemNota(nota_id=nota_b.id, descricao_original="Item B", produto_canonico_id=canonico.id),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp_fornecedor = client.get(
        f"/api/produtos/canonicos/{canonico.id}/itens", params={"fornecedor": "Fornecedor A"}
    )
    assert resp_fornecedor.status_code == 200
    assert resp_fornecedor.json()["total"] == 1
    assert resp_fornecedor.json()["itens"][0]["fornecedor"] == "Fornecedor A"

    resp_data = client.get(
        f"/api/produtos/canonicos/{canonico.id}/itens",
        params={"data_inicio": "2026-03-01", "data_fim": "2026-12-31"},
    )
    assert resp_data.status_code == 200
    assert resp_data.json()["total"] == 1
    assert resp_data.json()["itens"][0]["fornecedor"] == "Fornecedor B"


def test_listar_itens_vinculados_filtra_por_tipo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    nota_entrada = _criar_nota(session, caso.id, "5" * 44, TipoNota.ENTRADA, numero="1")
    nota_saida = _criar_nota(session, caso.id, "6" * 44, TipoNota.SAIDA, numero="2")
    session.add_all(
        [
            ItemNota(nota_id=nota_entrada.id, descricao_original="Item Entrada", produto_canonico_id=canonico.id),
            ItemNota(nota_id=nota_saida.id, descricao_original="Item Saida", produto_canonico_id=canonico.id),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/canonicos/{canonico.id}/itens", params={"tipo": "saida"})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["descricao_original"] == "Item Saida"


def test_listar_itens_vinculados_tipo_invalido_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Item X")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/produtos/canonicos/{canonico.id}/itens", params={"tipo": "invalido"})
    assert resp.status_code == 400


def test_reatribuir_item_com_sucesso_grava_log(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    canonico_antigo = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml")
    canonico_novo = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Coca-Cola Lata 350ml (novo)")
    session.add_all([canonico_antigo, canonico_novo])
    session.commit()
    session.refresh(canonico_antigo)
    session.refresh(canonico_novo)

    nota = _criar_nota(session, caso.id, "7" * 44)
    item = ItemNota(nota_id=nota.id, descricao_original="Item X", produto_canonico_id=canonico_antigo.id)
    session.add(item)
    session.commit()
    session.refresh(item)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(
        f"/api/produtos/itens/{item.id}", json={"produto_canonico_id": canonico_novo.id}
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["produto_canonico_id"] == canonico_novo.id

    session = db_session_factory()
    item_atualizado = session.get(ItemNota, item.id)
    assert item_atualizado.produto_canonico_id == canonico_novo.id
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "reatribuicao_item_produto_canonico"
    session.close()


def test_reatribuir_item_para_canonico_de_outro_caso_retorna_400(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso_a = _criar_caso(session, "Caso A")
    caso_b = _criar_caso(session, "Caso B")
    canonico_a = ProdutoCanonico(cliente_caso_id=caso_a.id, nome_canonico="Item A")
    canonico_b = ProdutoCanonico(cliente_caso_id=caso_b.id, nome_canonico="Item B")
    session.add_all([canonico_a, canonico_b])
    session.commit()
    session.refresh(canonico_a)
    session.refresh(canonico_b)

    nota = _criar_nota(session, caso_a.id, "8" * 44)
    item = ItemNota(nota_id=nota.id, descricao_original="Item X", produto_canonico_id=canonico_a.id)
    session.add(item)
    session.commit()
    session.refresh(item)
    session.close()
    logar_usuario(usuario)

    resp = client.patch(f"/api/produtos/itens/{item.id}", json={"produto_canonico_id": canonico_b.id})

    assert resp.status_code == 400


def test_reatribuir_item_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.patch("/api/produtos/itens/999999", json={"produto_canonico_id": 1})

    assert resp.status_code == 404


def test_reatribuir_item_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.patch("/api/produtos/itens/1", json={"produto_canonico_id": 1})
    assert resp.status_code == 401


def test_listar_itens_vinculados_canonico_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/produtos/canonicos/999999/itens")

    assert resp.status_code == 404


def test_listar_itens_vinculados_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/produtos/canonicos/1/itens")
    assert resp.status_code == 401
