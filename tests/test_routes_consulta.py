from app.ai.consulta_nl_sql import ConsultaPlanejada, PlanoConsulta
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


def _mockar_plano(monkeypatch, plano_ou_fake):
    if callable(plano_ou_fake) and not isinstance(plano_ou_fake, PlanoConsulta):
        monkeypatch.setattr("app.api.routes_consulta.gerar_plano_consulta", plano_ou_fake)
    else:
        monkeypatch.setattr(
            "app.api.routes_consulta.gerar_plano_consulta",
            lambda pergunta, canonicos_existentes: plano_ou_fake,
        )


def test_consulta_listagem_sem_resposta_executa_sql_e_grava_log(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session)
    caso, nota, item = _montar_nota_com_item(session, "1" * 44)
    session.close()
    logar_usuario(usuario)

    # SQLite (usado nesta suíte) compara string com case sensitivo; MySQL
    # (produção) usa collation case-insensitive por padrão. SAEnum grava o
    # NOME do membro em maiúsculo (AUTORIZADA), não o valor Python
    # ("autorizada") -- daí o literal aqui precisar do case exato para bater
    # em SQLite, mesmo a IA normalmente gerando em minúsculo (funciona igual
    # em produção, graças à collation do MySQL).
    sql_fixo = (
        "SELECT n.id AS nota_id, i.descricao_original, i.valor_total FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"
    )
    chamadas = []

    def _gerar_plano_fake(pergunta, canonicos_existentes):
        chamadas.append((pergunta, canonicos_existentes))
        return PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="listagem", sql=sql_fixo)],
            resposta_modelo=None,
        )

    _mockar_plano(monkeypatch, _gerar_plano_fake)

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "quais notas tem arroz?", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["pergunta"] == "quais notas tem arroz?"
    assert corpo["resposta"] is None
    assert corpo["resposta_pretendida"] is False
    assert corpo["fontes_truncadas"] is False
    assert "LIMIT" in corpo["sql_gerado"]
    assert corpo["total_linhas"] == 1
    assert corpo["colunas"] == ["nota_id", "descricao_original", "valor_total"]
    assert corpo["linhas"][0][1] == "ARROZ TIO JOAO 5KG"
    assert len(corpo["consultas"]) == 1
    assert corpo["consultas"][0]["finalidade"] == "listagem"
    assert corpo["consultas"][0]["truncado"] is False

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


def test_consulta_objetiva_monta_resposta_com_valor_real_e_mostra_fontes(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado3@x.com")
    caso, nota, item = _montar_nota_com_item(session, "3" * 44)
    session.close()
    logar_usuario(usuario)

    sql_resposta = (
        "SELECT SUM(i.quantidade) AS total_itens FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"
    )
    sql_fontes = (
        "SELECT n.id AS nota_id, n.numero, i.descricao_original, i.quantidade FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"
    )

    def _gerar_plano_fake(pergunta, canonicos_existentes):
        return PlanoConsulta(
            consultas=[
                ConsultaPlanejada(finalidade="resposta", sql=sql_resposta),
                ConsultaPlanejada(finalidade="fontes", sql=sql_fontes),
            ],
            resposta_modelo="Foram encontrados {1.total_itens|numero} itens do produto Arroz.",
        )

    _mockar_plano(monkeypatch, _gerar_plano_fake)

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "quantos itens de arroz?", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["resposta"] == "Foram encontrados 10 itens do produto Arroz."
    assert corpo["resposta_pretendida"] is True
    assert corpo["fontes_truncadas"] is False
    assert corpo["colunas"] == ["nota_id", "numero", "descricao_original", "quantidade"]
    assert corpo["total_linhas"] == 1
    assert len(corpo["consultas"]) == 2
    assert corpo["consultas"][0]["finalidade"] == "resposta"
    assert corpo["consultas"][1]["finalidade"] == "fontes"
    assert "Consulta 1 (resposta)" in corpo["sql_gerado"]
    assert "Consulta 2 (fontes)" in corpo["sql_gerado"]
    assert "Modelo de resposta" in corpo["sql_gerado"]

    session = db_session_factory()
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert "Foram encontrados 10 itens" in log.resultado_resumo
    assert "2 consulta(s)" in log.resultado_resumo
    assert "Consulta 1 (resposta)" in log.sql_gerado
    assert "Consulta 2 (fontes)" in log.sql_gerado
    assert "Modelo de resposta" in log.sql_gerado
    session.close()


def test_consulta_com_sql_inseguro_bloqueia_o_plano_inteiro(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado2@x.com")
    caso, _, _ = _montar_nota_com_item(session, "2" * 44)
    session.close()
    logar_usuario(usuario)

    sql_seguro = "SELECT COUNT(*) AS total FROM notas WHERE cliente_caso_id = :cliente_caso_id AND situacao = 'AUTORIZADA'"
    sql_inseguro = (
        "SELECT * FROM notas WHERE cliente_caso_id = :cliente_caso_id; DROP TABLE notas"
    )

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[
                ConsultaPlanejada(finalidade="resposta", sql=sql_seguro),
                ConsultaPlanejada(finalidade="fontes", sql=sql_inseguro),
            ],
            resposta_modelo="Total: {1.total|numero}.",
        ),
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
    assert "DROP TABLE" in log.sql_gerado
    session.close()


def test_consulta_com_plano_maior_que_max_consultas_bloqueia(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado4@x.com")
    caso, _, _ = _montar_nota_com_item(session, "4" * 44)
    session.close()
    logar_usuario(usuario)

    sql_base = "SELECT COUNT(*) AS total FROM notas WHERE cliente_caso_id = :cliente_caso_id AND situacao = 'AUTORIZADA'"

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="resposta", sql=sql_base) for _ in range(4)],
            resposta_modelo="Total: {1.total|numero}.",
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "pergunta qualquer", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 422
    assert "bloqueada" in resp.json()["detail"].lower()


def test_consulta_com_modelo_de_resposta_invalido_devolve_200_com_resposta_nula(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado5@x.com")
    caso, _, _ = _montar_nota_com_item(session, "5" * 44)
    session.close()
    logar_usuario(usuario)

    sql_resposta = "SELECT COUNT(*) AS total FROM notas WHERE cliente_caso_id = :cliente_caso_id AND situacao = 'AUTORIZADA'"
    sql_fontes = "SELECT n.id AS nota_id FROM notas n WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[
                ConsultaPlanejada(finalidade="resposta", sql=sql_resposta),
                ConsultaPlanejada(finalidade="fontes", sql=sql_fontes),
            ],
            # "coluna_que_nao_existe" não está no resultado da consulta 1.
            resposta_modelo="Total: {1.coluna_que_nao_existe|numero}.",
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "quantas notas existem?", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["resposta"] is None
    assert corpo["resposta_pretendida"] is True
    # A tabela de fontes continua aparecendo mesmo sem a frase.
    assert corpo["colunas"] == ["nota_id"]

    session = db_session_factory()
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert "Resposta não montada" in log.resultado_resumo
    session.close()


def test_consulta_com_resposta_sem_fontes_e_bloqueada(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado6@x.com")
    caso, _, _ = _montar_nota_com_item(session, "6" * 44)
    session.close()
    logar_usuario(usuario)

    sql_resposta = "SELECT COUNT(*) AS total FROM notas WHERE cliente_caso_id = :cliente_caso_id AND situacao = 'AUTORIZADA'"

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="resposta", sql=sql_resposta)],
            resposta_modelo="Total: {1.total|numero}.",
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "quantas notas existem?", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 422
    assert "fontes" in resp.json()["detail"].lower()


def test_consulta_com_modelo_de_resposta_sem_consulta_resposta_e_bloqueada(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado7@x.com")
    caso, _, _ = _montar_nota_com_item(session, "7" * 44)
    session.close()
    logar_usuario(usuario)

    sql_listagem = "SELECT n.id AS nota_id FROM notas n WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="listagem", sql=sql_listagem)],
            resposta_modelo="Total: {1.total|numero}.",
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "liste as notas", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 422
    assert "modelo de frase-resposta" in resp.json()["detail"].lower()


def test_consulta_com_erro_de_execucao_grava_log_e_retorna_502(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado8@x.com")
    caso, _, _ = _montar_nota_com_item(session, "8" * 44)
    session.close()
    logar_usuario(usuario)

    sql_com_coluna_inexistente = (
        "SELECT n.id AS nota_id, n.coluna_que_nao_existe FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA'"
    )

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="listagem", sql=sql_com_coluna_inexistente)],
            resposta_modelo=None,
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "liste algo quebrado", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 502

    session = db_session_factory()
    log = session.query(LogAuditoria).filter_by(usuario_id=usuario.id).one()
    assert "Erro ao executar consulta gerada" in log.resultado_resumo
    assert "coluna_que_nao_existe" in log.sql_gerado
    session.close()


def test_consulta_com_fontes_no_limite_marca_truncado(
    client, db_session_factory, logar_usuario, monkeypatch
):
    session = db_session_factory()
    usuario = _criar_usuario(session, "advogado9@x.com")
    caso, nota, item = _montar_nota_com_item(session, "9" * 44)
    session.close()
    logar_usuario(usuario)

    sql_com_limit_baixo = (
        "SELECT n.id AS nota_id FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'AUTORIZADA' LIMIT 1"
    )

    _mockar_plano(
        monkeypatch,
        PlanoConsulta(
            consultas=[ConsultaPlanejada(finalidade="listagem", sql=sql_com_limit_baixo)],
            resposta_modelo=None,
        ),
    )

    resp = client.post(
        "/api/consulta",
        json={"pergunta": "liste as notas", "cliente_caso_id": caso.id},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["total_linhas"] == 1
    assert corpo["fontes_truncadas"] is True
    assert corpo["consultas"][0]["truncado"] is True


def test_consulta_sem_autenticacao_retorna_401(client, db_session_factory):
    db_session_factory()
    resp = client.post(
        "/api/consulta", json={"pergunta": "qualquer coisa", "cliente_caso_id": 1}
    )
    assert resp.status_code == 401
