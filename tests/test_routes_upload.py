from io import BytesIO
from unittest.mock import MagicMock

from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    Lote,
    RoleUsuario,
    StatusCadastro,
    StatusProcessamento,
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
