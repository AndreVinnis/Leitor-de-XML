from datetime import datetime

from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    ItemNota,
    Lote,
    Nota,
    RoleUsuario,
    SituacaoNota,
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


def _criar_nota(
    session,
    caso_id,
    chave,
    numero,
    emitente_nome="Fornecedor X",
    valor_total=100,
    tipo=TipoNota.ENTRADA,
    destinatario_nome=None,
    data_emissao=datetime(2024, 5, 10),
    situacao=SituacaoNota.AUTORIZADA,
):
    nota = Nota(
        chave_acesso=chave,
        tipo=tipo,
        numero=numero,
        emitente_nome=emitente_nome,
        destinatario_nome=destinatario_nome,
        valor_total=valor_total,
        cliente_caso_id=caso_id,
        data_emissao=data_emissao,
        situacao=situacao,
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


def test_listar_notas_retorna_tipo_e_destinatario(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(
        session,
        caso.id,
        chave="4" * 44,
        numero="4",
        tipo=TipoNota.SAIDA,
        destinatario_nome="Cliente Final Ltda",
    )
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}")
    assert resp.status_code == 200
    item = resp.json()["itens"][0]
    assert item["tipo"] == "saida"
    assert item["destinatario_nome"] == "Cliente Final Ltda"


def test_listar_notas_filtra_por_tipo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(session, caso.id, chave="5" * 44, numero="5", tipo=TipoNota.ENTRADA)
    _criar_nota(session, caso.id, chave="6" * 44, numero="6", tipo=TipoNota.SAIDA)
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&tipo=saida")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["numero"] == "6"


def test_listar_notas_filtra_por_situacao(client, db_session_factory, logar_usuario):
    from datetime import datetime as _dt

    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(session, caso.id, chave="5" * 44, numero="5")
    cancelada = _criar_nota(session, caso.id, chave="6" * 44, numero="6")
    cancelada.situacao = SituacaoNota.CANCELADA
    cancelada.cancelada_em = _dt(2024, 6, 1)
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&situacao=cancelada")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["numero"] == "6"
    assert corpo["itens"][0]["situacao"] == "cancelada"

    resp_todas = client.get(f"/api/notas?cliente_caso_id={caso.id}")
    assert resp_todas.status_code == 200
    assert resp_todas.json()["total"] == 2


def test_listar_notas_busca_textual_por_numero_chave_ou_emitente(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(session, caso.id, chave="7" * 44, numero="7000", emitente_nome="Distribuidora Ouro Fino")
    _criar_nota(session, caso.id, chave="8" * 44, numero="8000", emitente_nome="Comércio Beira Rio")
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&q=ouro")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["numero"] == "7000"


def test_listar_notas_filtra_por_periodo(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(session, caso.id, chave="1" * 43 + "1", numero="10", data_emissao=datetime(2024, 1, 5))
    _criar_nota(session, caso.id, chave="1" * 43 + "2", numero="11", data_emissao=datetime(2024, 6, 15))
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&data_inicio=2024-05-01&data_fim=2024-07-01")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["numero"] == "11"


def test_listar_notas_periodo_inclui_dia_final_com_hora(client, db_session_factory, logar_usuario):
    # Regressão: data_emissao tem hora (não é meia-noite) na maioria das
    # notas reais -- "data_fim" precisa incluir o dia inteiro, não só
    # 00:00:00 daquele dia.
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    _criar_nota(session, caso.id, chave="1" * 43 + "3", numero="12", data_emissao=datetime(2024, 8, 1, 23, 30))
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas?cliente_caso_id={caso.id}&data_inicio=2024-08-01&data_fim=2024-08-01")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["numero"] == "12"


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
    assert corpo["situacao"] == "autorizada"
    assert corpo["cancelada_em"] is None
    assert len(corpo["itens"]) == 1
    assert corpo["itens"][0]["descricao_original"] == "ARROZ TIO JOAO 5KG"


def test_obter_nota_inexistente_retorna_404(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    session.close()
    logar_usuario(usuario)

    resp = client.get("/api/notas/999999")
    assert resp.status_code == 404


def test_listar_lotes_com_erro_retorna_so_lotes_com_erro_e_usuario(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session, email="ana@x.com")
    usuario.nome = "Ana Paula"
    caso = _criar_caso(session)

    lote_com_erro = Lote(
        id="lote-com-erro",
        cliente_caso_id=caso.id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=2,
        criado_por_usuario_id=usuario.id,
    )
    lote_sem_erro = Lote(
        id="lote-sem-erro",
        cliente_caso_id=caso.id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=1,
        criado_por_usuario_id=usuario.id,
    )
    session.add_all([lote_com_erro, lote_sem_erro])
    session.flush()
    session.add_all(
        [
            ArquivoLote(
                lote_id=lote_com_erro.id,
                nome_arquivo="a.xml",
                status=StatusProcessamento.ERRO,
                motivo_erro="chave inválida",
            ),
            ArquivoLote(lote_id=lote_com_erro.id, nome_arquivo="b.xml", status=StatusProcessamento.SUCESSO),
            ArquivoLote(lote_id=lote_sem_erro.id, nome_arquivo="c.xml", status=StatusProcessamento.SUCESSO),
        ]
    )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas/lotes?cliente_caso_id={caso.id}")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 1
    item = corpo["itens"][0]
    assert item["id"] == lote_com_erro.id
    assert item["usuario_nome"] == "Ana Paula"
    assert item["total_arquivos"] == 2
    assert item["arquivos_com_erro"] == 1


def test_listar_lotes_com_erro_pagina_resultados(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)

    for i in range(3):
        lote = Lote(
            id=f"lote-erro-{i}",
            cliente_caso_id=caso.id,
            cnpj_cliente=CNPJ_CLIENTE,
            total_arquivos=1,
            criado_por_usuario_id=usuario.id,
        )
        session.add(lote)
        session.flush()
        session.add(
            ArquivoLote(lote_id=lote.id, nome_arquivo="a.xml", status=StatusProcessamento.ERRO, motivo_erro="x")
        )
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/notas/lotes?cliente_caso_id={caso.id}&limit=2&offset=0")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total"] == 3
    assert len(corpo["itens"]) == 2

    resp_pagina_2 = client.get(f"/api/notas/lotes?cliente_caso_id={caso.id}&limit=2&offset=2")
    assert len(resp_pagina_2.json()["itens"]) == 1


def test_listar_lotes_com_erro_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/notas/lotes")
    assert resp.status_code == 401


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


# -- GET /api/notas/ids e POST /api/notas/download -------------------------


def test_listar_ids_notas_respeita_filtros(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso_a = _criar_caso(session, "Cliente A")
    caso_b = _criar_caso(session, "Cliente B")
    n1 = _criar_nota(session, caso_a.id, "A" * 44, "1", tipo=TipoNota.ENTRADA)
    _criar_nota(session, caso_a.id, "B" * 44, "2", tipo=TipoNota.SAIDA)
    _criar_nota(session, caso_b.id, "C" * 44, "3", tipo=TipoNota.ENTRADA)
    logar_usuario(usuario)

    resposta = client.get(f"/api/notas/ids?cliente_caso_id={caso_a.id}&tipo=entrada")

    assert resposta.status_code == 200
    assert resposta.json() == {"ids": [n1.id], "total": 1, "limitado": False}


def test_listar_ids_notas_limita_a_500(client, db_session_factory, logar_usuario, monkeypatch):
    monkeypatch.setattr("app.api.routes_notas.LIMITE_DOWNLOAD_NOTAS", 2)
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    for i in range(3):
        _criar_nota(session, caso.id, str(i) * 44, str(i))
    logar_usuario(usuario)

    corpo = client.get(f"/api/notas/ids?cliente_caso_id={caso.id}").json()

    assert len(corpo["ids"]) == 2
    assert corpo["total"] == 3
    assert corpo["limitado"] is True


def _nota_com_xml(session, caso_id, chave, numero, caminho):
    nota = _criar_nota(session, caso_id, chave, numero)
    nota.arquivo_origem = str(caminho)
    session.commit()
    return nota


def test_download_uma_nota_devolve_o_xml(client, db_session_factory, logar_usuario, tmp_path, monkeypatch):
    monkeypatch.setattr("app.api.routes_upload.UPLOAD_DIR", tmp_path)
    xml = tmp_path / "lote" / "nota1.xml"
    xml.parent.mkdir()
    xml.write_text("<NFe>1</NFe>")
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    nota = _nota_com_xml(session, caso.id, "A" * 44, "1", xml)
    logar_usuario(usuario)

    resposta = client.post("/api/notas/download", json={"ids": [nota.id]})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/xml")
    assert 'filename="nota1.xml"' in resposta.headers["content-disposition"]
    assert resposta.text == "<NFe>1</NFe>"


def test_download_varias_notas_devolve_zip_e_conta_ausentes(
    client, db_session_factory, logar_usuario, tmp_path, monkeypatch
):
    import io
    import zipfile

    monkeypatch.setattr("app.api.routes_upload.UPLOAD_DIR", tmp_path)
    (tmp_path / "lote1").mkdir()
    (tmp_path / "lote2").mkdir()
    # Mesmo nome de arquivo em lotes diferentes: o ZIP não pode sobrescrever.
    xml1 = tmp_path / "lote1" / "nota.xml"
    xml2 = tmp_path / "lote2" / "nota.xml"
    xml1.write_text("<NFe>1</NFe>")
    xml2.write_text("<NFe>2</NFe>")
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    n1 = _nota_com_xml(session, caso.id, "A" * 44, "1", xml1)
    n2 = _nota_com_xml(session, caso.id, "B" * 44, "2", xml2)
    n3 = _nota_com_xml(session, caso.id, "C" * 44, "3", tmp_path / "lote1" / "sumiu.xml")
    logar_usuario(usuario)

    resposta = client.post("/api/notas/download", json={"ids": [n1.id, n2.id, n3.id]})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/zip"
    assert resposta.headers["x-arquivos-ausentes"] == "1"
    with zipfile.ZipFile(io.BytesIO(resposta.content)) as zf:
        assert len(zf.namelist()) == 2
        assert {zf.read(nome).decode() for nome in zf.namelist()} == {"<NFe>1</NFe>", "<NFe>2</NFe>"}


def test_download_ignora_caminho_fora_do_diretorio_de_uploads(
    client, db_session_factory, logar_usuario, tmp_path, monkeypatch
):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr("app.api.routes_upload.UPLOAD_DIR", uploads)
    fora = tmp_path / "segredo.xml"
    fora.write_text("<segredo/>")
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    nota = _nota_com_xml(session, caso.id, "A" * 44, "1", fora)
    logar_usuario(usuario)

    resposta = client.post("/api/notas/download", json={"ids": [nota.id]})

    assert resposta.status_code == 404


def test_download_valida_quantidade_de_ids(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    logar_usuario(_criar_usuario(session))

    assert client.post("/api/notas/download", json={"ids": []}).status_code == 422
    assert client.post("/api/notas/download", json={"ids": list(range(1, 502))}).status_code == 422
