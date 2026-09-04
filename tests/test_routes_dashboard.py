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


def test_estatisticas_dashboard_filtra_por_caso(client, db_session_factory, logar_usuario):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso = _criar_caso(session, "Cliente A")
    outro_caso = _criar_caso(session, "Cliente B")

    lote = Lote(
        id="lote-stats-a",
        cliente_caso_id=caso.id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=4,
        criado_por_usuario_id=usuario.id,
    )
    session.add(lote)
    session.flush()
    session.add_all(
        [
            ArquivoLote(lote_id=lote.id, nome_arquivo="a.xml", status=StatusProcessamento.SUCESSO),
            ArquivoLote(lote_id=lote.id, nome_arquivo="b.xml", status=StatusProcessamento.SUCESSO),
            ArquivoLote(lote_id=lote.id, nome_arquivo="c.xml", status=StatusProcessamento.PENDENTE),
            ArquivoLote(
                lote_id=lote.id, nome_arquivo="d.xml", status=StatusProcessamento.ERRO, motivo_erro="x"
            ),
        ]
    )

    lote_outro = Lote(
        id="lote-stats-b",
        cliente_caso_id=outro_caso.id,
        cnpj_cliente="11111111000100",
        total_arquivos=1,
        criado_por_usuario_id=usuario.id,
    )
    session.add(lote_outro)
    session.flush()
    session.add(ArquivoLote(lote_id=lote_outro.id, nome_arquivo="e.xml", status=StatusProcessamento.SUCESSO))
    session.commit()
    session.close()
    logar_usuario(usuario)

    resp = client.get(f"/api/dashboard/estatisticas?cliente_caso_id={caso.id}")
    assert resp.status_code == 200
    assert resp.json() == {"notas_processadas": 2, "pendentes": 1, "erros": 1}

    resp_geral = client.get("/api/dashboard/estatisticas")
    assert resp_geral.status_code == 200
    assert resp_geral.json()["notas_processadas"] == 3


def test_estatisticas_dashboard_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.get("/api/dashboard/estatisticas")
    assert resp.status_code == 401
