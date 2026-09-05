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


def _criar_usuario(session, email="advogado@x.com"):
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


def _montar_nota_com_item(session, chave_acesso):
    caso = ClienteCaso(nome_cliente="Cliente Teste")
    session.add(caso)
    session.commit()
    session.refresh(caso)

    nota = Nota(
        chave_acesso=chave_acesso,
        tipo=TipoNota.ENTRADA,
        cliente_caso_id=caso.id,
        valor_total=100,
    )
    session.add(nota)
    session.commit()
    session.refresh(nota)

    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Arroz 5kg")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    item = ItemNota(
        nota_id=nota.id,
        descricao_original="ARROZ TIO JOAO 5KG",
        produto_canonico_id=canonico.id,
        quantidade=10,
        valor_total=100,
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    return caso, nota, item


def test_consulta_caminho_feliz_executa_sql_e_grava_log(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso, nota, item = _montar_nota_com_item(session, "1" * 44)
    session.close()
    logar_usuario(usuario)

    sql_fixo = (
        "SELECT n.id, i.descricao_original, i.valor_total FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "WHERE n.cliente_caso_id = :cliente_caso_id"
    )
    chamadas = []

    def _gerar_sql_fake(pergunta, canonicos_existentes):
        chamadas.append((pergunta, canonicos_existentes))
        return sql_fixo

    monkeypatch.setattr("app.api.routes_consulta.gerar_sql", _gerar_sql_fake)

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "quais notas tem arroz?", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["pergunta"] == "quais notas tem arroz?"
    assert "LIMIT" in corpo["sql_gerado"]
    assert corpo["total_linhas"] == 1
    assert corpo["colunas"] == ["id", "descricao_original", "valor_total"]
    assert corpo["linhas"][0][1] == "ARROZ TIO JOAO 5KG"

    session = db_session_factory()
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "consulta_ia"
    assert log.pergunta_usuario == "quais notas tem arroz?"
    assert "1 linha" in log.resultado_resumo
    session.close()

    assert len(chamadas) == 1
    pergunta_recebida, canonicos_recebidos = chamadas[0]
    assert pergunta_recebida == "quais notas tem arroz?"
    assert canonicos_recebidos == [
        {"id": item.produto_canonico_id, "nome_canonico": "Arroz 5kg", "categoria": None}
    ]


def test_consulta_bloqueada_por_sql_inseguro_retorna_422_e_grava_log(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado2@x.com")
    caso, _, _ = _montar_nota_com_item(session, "2" * 44)
    session.close()
    logar_usuario(usuario)

    sql_inseguro = (
        "SELECT * FROM notas WHERE cliente_caso_id = :cliente_caso_id; "
        "DROP TABLE notas"
    )
    monkeypatch.setattr(
        "app.api.routes_consulta.gerar_sql",
        lambda pergunta, canonicos_existentes: sql_inseguro,
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "apague as notas", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 422
    assert "bloqueada" in resp.json()["detail"].lower()

    session = db_session_factory()
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert log.acao == "consulta_ia"
    assert "bloqueada" in log.resultado_resumo.lower()
    session.close()


def test_consulta_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.post(
        "/api/consulta", json={"pergunta": "qualquer coisa", "cliente_caso_id": 1}
    )
    assert resp.status_code == 401
