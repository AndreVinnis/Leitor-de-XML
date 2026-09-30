from io import BytesIO
from unittest.mock import MagicMock

from app.api.routes_upload import LIMITE_ARQUIVOS_POR_LOTE
from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    Lote,
    RoleUsuario,
    StatusCadastro,
    StatusProcessamento,
    Usuario,
)

CNPJ_CLIENTE = "11222333000181"


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


def test_upload_persiste_lote_e_arquivos_antes_de_enfileirar(
    client, db_session_factory, logar_usuario, monkeypatch
):
    """
    O broker de verdade (Redis) não existe neste ambiente de teste -- por
    isso o Celery é substituído por um dublê aqui. O que se testa é a parte
    determinística da Etapa 3: Lote e ArquivoLote (um por arquivo) precisam
    existir no banco, com task_id preenchido, antes/depois da resposta.
    """
    fake_task = MagicMock()
    fake_task.id = "fake-task-id"
    fake_processar = MagicMock()
    fake_processar.delay = MagicMock(return_value=fake_task)
    monkeypatch.setattr("app.api.routes_upload.processar_xml_nfe", fake_processar)

    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.close()
    logar_usuario(usuario)

    arquivos = [
        ("arquivos", ("nota1.xml", BytesIO(b"<a/>"), "text/xml")),
        ("arquivos", ("nota2.xml", BytesIO(b"<a/>"), "text/xml")),
    ]
    resp = client.post(
        "/api/notas/upload",
        data={"cliente_caso_id": caso.id, "cnpj_cliente": CNPJ_CLIENTE},
        files=arquivos,
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total_arquivos"] == 2
    assert corpo["task_ids"] == ["fake-task-id", "fake-task-id"]
    lote_id = corpo["lote_id"]
    assert fake_processar.delay.call_count == 2

    session = db_session_factory()
    lote = session.get(Lote, lote_id)
    assert lote is not None
    assert lote.total_arquivos == 2
    assert lote.cliente_caso_id == caso.id
    assert lote.criado_por_usuario_id == usuario.id

    arquivos_db = session.query(ArquivoLote).filter_by(lote_id=lote_id).all()
    assert len(arquivos_db) == 2
    assert {a.nome_arquivo for a in arquivos_db} == {"nota1.xml", "nota2.xml"}
    assert all(a.status == StatusProcessamento.PENDENTE for a in arquivos_db)
    assert all(a.task_id == "fake-task-id" for a in arquivos_db)
    session.close()


def test_upload_com_cnpj_invalido_retorna_422_e_nao_cria_lote(
    client, db_session_factory, logar_usuario, monkeypatch
):
    fake_processar = MagicMock()
    monkeypatch.setattr("app.api.routes_upload.processar_xml_nfe", fake_processar)

    session = db_session_factory()
    usuario = _criar_usuario(session, "adv-upload-cnpj@x.com")
    caso = _criar_caso(session, "Cliente Upload Inválido")
    session.close()
    logar_usuario(usuario)

    arquivos = [("arquivos", ("nota1.xml", BytesIO(b"<a/>"), "text/xml"))]
    resp = client.post(
        "/api/notas/upload",
        data={"cliente_caso_id": caso.id, "cnpj_cliente": "98765432000188"},
        files=arquivos,
    )
    assert resp.status_code == 422
    fake_processar.delay.assert_not_called()

    session = db_session_factory()
    assert session.query(Lote).count() == 0
    session.close()


def test_upload_acima_do_limite_retorna_422_e_nao_cria_lote(
    client, db_session_factory, logar_usuario, monkeypatch
):
    fake_processar = MagicMock()
    monkeypatch.setattr("app.api.routes_upload.processar_xml_nfe", fake_processar)

    session = db_session_factory()
    usuario = _criar_usuario(session, "adv-upload-limite@x.com")
    caso = _criar_caso(session, "Cliente Upload Limite")
    session.close()
    logar_usuario(usuario)

    arquivos = [
        ("arquivos", (f"nota{i}.xml", BytesIO(b"<a/>"), "text/xml"))
        for i in range(LIMITE_ARQUIVOS_POR_LOTE + 1)
    ]
    resp = client.post(
        "/api/notas/upload",
        data={"cliente_caso_id": caso.id, "cnpj_cliente": CNPJ_CLIENTE},
        files=arquivos,
    )
    assert resp.status_code == 422
    fake_processar.delay.assert_not_called()

    session = db_session_factory()
    assert session.query(Lote).count() == 0
    session.close()


def _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path):
    """UPLOAD_DIR vai para tmp_path: os testes de nome malicioso precisam
    enxergar exatamente o que foi gravado (e o que não foi) em disco."""
    monkeypatch.setattr("app.api.routes_upload.UPLOAD_DIR", tmp_path / "uploads")
    fake_task = MagicMock()
    fake_task.id = "fake-task-id"
    fake_processar = MagicMock()
    fake_processar.delay = MagicMock(return_value=fake_task)
    monkeypatch.setattr("app.api.routes_upload.processar_xml_nfe", fake_processar)

    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session)
    session.close()
    logar_usuario(usuario)
    return caso


def _enviar(client, caso, nomes_e_conteudos):
    return client.post(
        "/api/notas/upload",
        data={"cliente_caso_id": caso.id, "cnpj_cliente": CNPJ_CLIENTE},
        files=[
            ("arquivos", (nome, BytesIO(conteudo), "text/xml"))
            for nome, conteudo in nomes_e_conteudos
        ],
    )


def _arquivos_gravados(raiz):
    return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file())


def test_upload_com_nome_de_caminho_grava_so_o_basename_dentro_do_lote(
    client, db_session_factory, logar_usuario, monkeypatch, tmp_path
):
    """Path traversal: o nome do multipart vem do cliente e não pode
    escapar do diretório do lote, nem com ../, nem absoluto, nem com barra invertida."""
    caso = _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path)

    resp = _enviar(
        client,
        caso,
        [
            ("../../fora1.xml", b"<a/>"),
            ("/etc/fora2.xml", b"<a/>"),
            (r"..\..\fora3.xml", b"<a/>"),
        ],
    )

    assert resp.status_code == 200
    lote_id = resp.json()["lote_id"]
    assert _arquivos_gravados(tmp_path) == [
        f"uploads/{lote_id}/fora1.xml",
        f"uploads/{lote_id}/fora2.xml",
        f"uploads/{lote_id}/fora3.xml",
    ]
    session = db_session_factory()
    nomes = sorted(a.nome_arquivo for a in session.query(ArquivoLote).all())
    session.close()
    assert nomes == ["fora1.xml", "fora2.xml", "fora3.xml"]


def test_upload_com_nomes_repetidos_nao_sobrescreve(
    client, db_session_factory, logar_usuario, monkeypatch, tmp_path
):
    caso = _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path)

    resp = _enviar(client, caso, [("nota.xml", b"<um/>"), ("pasta/nota.xml", b"<dois/>")])

    assert resp.status_code == 200
    lote_dir = tmp_path / "uploads" / resp.json()["lote_id"]
    assert (lote_dir / "nota.xml").read_bytes() == b"<um/>"
    assert (lote_dir / "2_nota.xml").read_bytes() == b"<dois/>"


def test_upload_de_arquivo_que_nao_e_xml_retorna_422_e_desfaz_o_lote(
    client, db_session_factory, logar_usuario, monkeypatch, tmp_path
):
    caso = _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path)

    resp = _enviar(client, caso, [("nota.xml", b"<a/>"), ("script.py", b"print(1)")])

    assert resp.status_code == 422
    assert _arquivos_gravados(tmp_path) == []
    session = db_session_factory()
    assert session.query(Lote).count() == 0
    assert session.query(ArquivoLote).count() == 0
    session.close()


def test_upload_acima_do_tamanho_por_arquivo_retorna_413_e_desfaz_o_lote(
    client, db_session_factory, logar_usuario, monkeypatch, tmp_path
):
    caso = _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.routes_upload.settings.upload_max_bytes_por_arquivo", 10)

    resp = _enviar(client, caso, [("pequena.xml", b"<a/>"), ("grande.xml", b"<a>" + b"x" * 50 + b"</a>")])

    assert resp.status_code == 413
    assert _arquivos_gravados(tmp_path) == []
    session = db_session_factory()
    assert session.query(Lote).count() == 0
    session.close()


def test_upload_acima_do_tamanho_do_lote_retorna_413(
    client, db_session_factory, logar_usuario, monkeypatch, tmp_path
):
    caso = _preparar_upload_isolado(db_session_factory, logar_usuario, monkeypatch, tmp_path)
    monkeypatch.setattr("app.api.routes_upload.settings.upload_max_bytes_por_lote", 30)

    resp = _enviar(client, caso, [("a.xml", b"<a>" + b"x" * 15 + b"</a>"), ("b.xml", b"<a>" + b"x" * 15 + b"</a>")])

    assert resp.status_code == 413
    assert _arquivos_gravados(tmp_path) == []
