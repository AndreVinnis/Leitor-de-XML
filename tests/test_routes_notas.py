from datetime import datetime

from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    ItemNota,
    Lote,
    Nota,
    RoleUsuario,
    StatusCadastro,
    StatusProcessamento,
    TipoNota,
    Usuario,
)

CNPJ_CLIENTE = "98765432000188"


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


def _criar_caso(session, nome="Cliente A"):
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def _criar_nota(session, caso_id, chave, numero, emitente_nome="Fornecedor X", valor_total=100):
    nota = Nota(
        chave_acesso=chave,
        tipo=TipoNota.ENTRADA,
        numero=numero,
        emitente_nome=emitente_nome,
        valor_total=valor_total,
        cliente_caso_id=caso_id,
        data_emissao=datetime(2024, 5, 10),
    )
    session.add(nota)
    session.commit()
    session.refresh(nota)
    return nota


def test_listar_notas_com_paginacao_e_filtro_por_caso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso_a = _criar_caso(session, "Cliente A")
    caso_b = _criar_caso(session, "Cliente B")

    for i in range(3):
        _criar_nota(session, caso_a.id, chave=str(i) * 44, numero=str(i))
    _criar_nota(session, caso_b.id, chave="9" * 44, numero="99")
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso_a.id}&limit=2&offset=0")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 3
    assert len(corpo["itens"]) == 2
    # valor_total é dinheiro: serializado como string decimal, nunca float.
    assert corpo["itens"][0]["valor_total"] == "100.00"
    assert isinstance(corpo["itens"][0]["valor_total"], str)

    resp_pagina_2 = client.get(f"/api/notas?cliente_caso_id={caso_a.id}&limit=2&offset=2")
    assert len(resp_pagina_2.json()["itens"]) == 1


def test_listar_notas_filtra_por_status(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    nota_ok = _criar_nota(session, caso.id, chave="1" * 44, numero="1")
    _criar_nota(session, caso.id, chave="2" * 44, numero="2")  # sem ArquivoLote associado

    lote = Lote(
        id="lote-status",
        cliente_caso_id=caso.id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=1,
        criado_por_usuario_id=usuario.id,
    )
    session.add(lote)
    session.flush()
    session.add(
        ArquivoLote(
            lote_id=lote.id,
            nome_arquivo="a.xml",
            status=StatusProcessamento.SUCESSO,
            nota_id=nota_ok.id,
        )
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&status=sucesso")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["id"] == nota_ok.id
    assert corpo["itens"][0]["status"] == "sucesso"


def test_obter_nota_com_itens(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    nota = _criar_nota(session, caso.id, chave="3" * 44, numero="3")
    session.add(
        ItemNota(
            nota_id=nota.id,
            descricao_original="ARROZ TIO JOAO 5KG",
            quantidade=10,
            valor_unitario="25.50",
            valor_total="255.00",
        )
    )
    session.commit()
    nota_id = nota.id
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas/{nota_id}")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["id"] == nota_id
    assert len(corpo["itens"]) == 1
    assert corpo["itens"][0]["descricao_original"] == "ARROZ TIO JOAO 5KG"


def test_obter_nota_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/notas/999999")
    assert resp.status_code == 404


def test_progresso_lote(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    lote = Lote(
        id="lote-progresso",
        cliente_caso_id=caso.id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=3,
        criado_por_usuario_id=usuario.id,
    )
    session.add(lote)
    session.flush()
    session.add_all(
        [
            ArquivoLote(lote_id=lote.id, nome_arquivo="a.xml", status=StatusProcessamento.SUCESSO),
            ArquivoLote(
                lote_id=lote.id,
                nome_arquivo="b.xml",
                status=StatusProcessamento.ERRO,
                motivo_erro="deu ruim",
            ),
            ArquivoLote(lote_id=lote.id, nome_arquivo="c.xml", status=StatusProcessamento.PENDENTE),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas/lotes/{lote.id}")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total_arquivos"] == 3
    assert corpo["concluidos"] == 2
    assert corpo["com_erro"] == 1
    assert len(corpo["arquivos"]) == 3


def test_progresso_lote_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/notas/lotes/nao-existe")
    assert resp.status_code == 404


def test_listar_notas_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()  # garante as tabelas criadas
    resp = client.get("/api/notas")
    assert resp.status_code == 401
