"""
Normalização lote a lote (app/workers/tasks.py::normalizar_produtos_pendentes):
cada lote é commitado antes do próximo, um lote com erro é tentado de novo
até TENTATIVAS_POR_LOTE vezes, e na última falha a task para mantendo os
lotes anteriores salvos. Também cobre a trava por caso contra execuções
concorrentes (app/core/trava_normalizacao.py, trocada por um dict no
conftest) e as rotas de disparo/acompanhamento.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

from app.ai.normalizador_produtos import SugestaoIA
from app.models.models import (
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
    SugestaoNormalizacao,
    Usuario,
)
from app.workers.tasks import TENTATIVAS_POR_LOTE, normalizar_produtos_pendentes
from tests.test_normalizacao_por_caso import _criar_caso, _criar_item_pendente


@pytest.fixture
def lote_de_um(monkeypatch):
    monkeypatch.setattr("app.workers.tasks.TAMANHO_LOTE_IA", 1)


def _sugestao_nova(descricao: str, nome: str) -> list[SugestaoIA]:
    return [
        SugestaoIA(
            descricao_original=descricao,
            confianca=0.9,
            novo_produto_canonico={"nome_canonico": nome},
        )
    ]


def _montar_caso_com_itens(db_session_factory, descricoes: list[str]) -> int:
    session = db_session_factory()
    caso = _criar_caso(session, "Cliente Lotes")
    for i, descricao in enumerate(descricoes):
        _criar_item_pendente(session, caso.id, str(i + 1).rjust(44, "0"), descricao)
    session.close()
    return caso.id


def _descricoes_enviadas(mock_sugerir) -> list[str]:
    return [d for chamada in mock_sugerir.call_args_list for d in chamada.args[0]]


@patch("app.workers.tasks.sugerir_normalizacao")
def test_lote_com_erro_e_tentado_de_novo_e_salvo(mock_sugerir, db_session_factory, lote_de_um):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A", "ITEM B"])
    mock_sugerir.side_effect = [
        RuntimeError("instável"),
        _sugestao_nova("ITEM A", "Item A"),
        _sugestao_nova("ITEM B", "Item B"),
    ]

    resultado = normalizar_produtos_pendentes(caso_id)

    assert resultado["status"] == "ok"
    assert resultado["sugestoes_criadas"] == 2
    assert mock_sugerir.call_count == 3
    session = db_session_factory()
    assert session.query(SugestaoNormalizacao).count() == 2


@patch("app.workers.tasks.sugerir_normalizacao")
def test_lote_que_esgota_tentativas_para_e_mantem_anteriores(
    mock_sugerir, db_session_factory, lote_de_um
):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A", "ITEM B", "ITEM C"])
    mock_sugerir.side_effect = [_sugestao_nova("ITEM A", "Item A")] + [
        RuntimeError("API fora do ar")
    ] * TENTATIVAS_POR_LOTE

    resultado = normalizar_produtos_pendentes(caso_id)

    assert resultado["status"] == "falha_lote"
    assert resultado["lote_com_falha"] == 2
    assert resultado["lotes_salvos"] == 1
    assert resultado["total_lotes"] == 3
    assert resultado["sugestoes_criadas"] == 1
    assert "API fora do ar" in resultado["motivo"]
    # 1 chamada do lote 1 + 3 tentativas do lote 2; o lote 3 nunca é enviado.
    assert mock_sugerir.call_count == 1 + TENTATIVAS_POR_LOTE
    assert "ITEM C" not in _descricoes_enviadas(mock_sugerir)

    session = db_session_factory()
    assert session.query(SugestaoNormalizacao).count() == 1
    assert [c.nome_canonico for c in session.query(ProdutoCanonico).all()] == ["Item A"]


@patch("app.workers.tasks.sugerir_normalizacao")
def test_novo_disparo_continua_de_onde_parou(mock_sugerir, db_session_factory, lote_de_um):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A", "ITEM B", "ITEM C"])
    mock_sugerir.side_effect = [_sugestao_nova("ITEM A", "Item A")] + [
        RuntimeError("API fora do ar")
    ] * TENTATIVAS_POR_LOTE
    normalizar_produtos_pendentes(caso_id)

    mock_sugerir.reset_mock()
    mock_sugerir.side_effect = [
        _sugestao_nova("ITEM B", "Item B"),
        _sugestao_nova("ITEM C", "Item C"),
    ]
    resultado = normalizar_produtos_pendentes(caso_id)

    assert resultado["status"] == "ok"
    assert resultado["sugestoes_criadas"] == 2
    assert _descricoes_enviadas(mock_sugerir) == ["ITEM B", "ITEM C"]
    session = db_session_factory()
    assert session.query(SugestaoNormalizacao).count() == 3


@pytest.fixture
def sqlite_com_savepoint(db_session_factory):
    """
    Receita do SQLAlchemy para SAVEPOINT no pysqlite: sem ela o driver não
    emite BEGIN antes do SAVEPOINT, e o RELEASE do begin_nested() da task
    commita de verdade -- o rollback do lote não desfaria o canônico criado
    dentro dele, ao contrário do MySQL. Só neste teste, porque outros testes
    abrem duas sessões ao mesmo tempo na mesma conexão (StaticPool), o que
    com BEGIN explícito vira "cannot start a transaction within a transaction".
    """
    engine = db_session_factory.kw["bind"]
    with engine.connect() as conexao:
        conexao.connection.driver_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emitir_begin(conn):
        conn.exec_driver_sql("BEGIN")

    yield db_session_factory
    event.remove(engine, "begin", _emitir_begin)


@patch("app.workers.tasks.sugerir_normalizacao")
def test_rollback_de_lote_nao_deixa_canonico_fantasma(
    mock_sugerir, sqlite_com_savepoint, monkeypatch
):
    """
    O canônico "Item A" é criado (flush) e em seguida o embedding de
    "Item B" falha no mesmo lote: o rollback desfaz os dois. A nova
    tentativa não pode receber o id desfeito como candidato, e ao final
    toda sugestão aponta para um canônico que existe.
    """
    caso_id = _montar_caso_com_itens(sqlite_com_savepoint, ["ITEM A", "ITEM B"])
    candidatos_por_chamada = []

    def _sugerir(descricoes, candidatos):
        # Cópia: a task passa a lista viva do catálogo, que cresce depois
        # do commit -- a referência guardada pelo mock não serviria.
        candidatos_por_chamada.append(list(candidatos))
        return [
            SugestaoIA(
                descricao_original="ITEM A", confianca=0.9, novo_produto_canonico={"nome_canonico": "Item A"}
            ),
            SugestaoIA(
                descricao_original="ITEM B", confianca=0.9, novo_produto_canonico={"nome_canonico": "Item B"}
            ),
        ]

    mock_sugerir.side_effect = _sugerir
    chamadas_embedding = {"n": 0}

    def _embedding_que_falha_uma_vez(textos, *args, **kwargs):
        chamadas_embedding["n"] += 1
        if chamadas_embedding["n"] == 2:
            raise RuntimeError("Gemini fora do ar")
        return [[0.1, 0.2, 0.3] for _ in textos]

    monkeypatch.setattr("app.workers.tasks.gerar_embeddings", _embedding_que_falha_uma_vez)

    resultado = normalizar_produtos_pendentes(caso_id)

    assert resultado["status"] == "ok"
    assert resultado["produtos_canonicos_criados"] == 2
    assert mock_sugerir.call_count == 2
    assert candidatos_por_chamada[1] == []

    session = sqlite_com_savepoint()
    ids_canonicos = {c.id for c in session.query(ProdutoCanonico).all()}
    assert len(ids_canonicos) == 2
    sugestoes = session.query(SugestaoNormalizacao).all()
    assert len(sugestoes) == 2
    assert {s.produto_canonico_sugerido_id for s in sugestoes} == ids_canonicos


# --------------------------------------------------------------------------
# Trava por caso na task
# --------------------------------------------------------------------------


@pytest.fixture
def sem_backend_de_resultado(monkeypatch):
    """update_state grava no backend de resultados (Redis) -- sem ele em CI."""
    update_state = MagicMock()
    monkeypatch.setattr(normalizar_produtos_pendentes, "update_state", update_state)
    return update_state


@patch("app.workers.tasks.sugerir_normalizacao")
def test_task_libera_trava_ao_terminar(
    mock_sugerir, db_session_factory, trava_normalizacao, sem_backend_de_resultado
):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A"])
    mock_sugerir.return_value = _sugestao_nova("ITEM A", "Item A")
    trava_normalizacao.adquirir(caso_id, "task-1")

    resultado = normalizar_produtos_pendentes.apply(args=[caso_id], task_id="task-1").get()

    assert resultado["status"] == "ok"
    assert trava_normalizacao.task_em_andamento(caso_id) is None
    metas = [c.kwargs["meta"] for c in sem_backend_de_resultado.call_args_list]
    assert metas[-1] == {"lotes_salvos": 1, "total_lotes": 1, "sugestoes_criadas": 1}


@patch("app.workers.tasks.sugerir_normalizacao")
def test_task_libera_trava_mesmo_com_falha_de_lote(
    mock_sugerir, db_session_factory, trava_normalizacao, sem_backend_de_resultado
):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A"])
    mock_sugerir.side_effect = RuntimeError("API fora do ar")
    trava_normalizacao.adquirir(caso_id, "task-1")

    resultado = normalizar_produtos_pendentes.apply(args=[caso_id], task_id="task-1").get()

    assert resultado["status"] == "falha_lote"
    assert trava_normalizacao.task_em_andamento(caso_id) is None


@patch("app.workers.tasks.sugerir_normalizacao")
def test_task_nao_roda_com_trava_de_outra_execucao(
    mock_sugerir, db_session_factory, trava_normalizacao, sem_backend_de_resultado
):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A"])
    trava_normalizacao.adquirir(caso_id, "outra-task")

    resultado = normalizar_produtos_pendentes.apply(args=[caso_id], task_id="task-2").get()

    assert resultado["status"] == "ja_em_andamento"
    mock_sugerir.assert_not_called()
    # A trava da outra execução continua intacta.
    assert trava_normalizacao.task_em_andamento(caso_id) == "outra-task"


@patch("app.workers.tasks.sugerir_normalizacao")
def test_task_para_se_perder_a_trava_no_meio(
    mock_sugerir, db_session_factory, trava_normalizacao, sem_backend_de_resultado, lote_de_um
):
    caso_id = _montar_caso_com_itens(db_session_factory, ["ITEM A", "ITEM B"])
    trava_normalizacao.adquirir(caso_id, "task-1")

    def _sugere_e_perde_trava(descricoes, candidatos):
        # Simula a trava expirando e outra execução assumindo o caso.
        trava_normalizacao.donos[caso_id] = "outra-task"
        return _sugestao_nova("ITEM A", "Item A")

    mock_sugerir.side_effect = _sugere_e_perde_trava

    resultado = normalizar_produtos_pendentes.apply(args=[caso_id], task_id="task-1").get()

    # A posse é conferida logo antes do commit: o lote em que a trava se
    # perdeu é desfeito (não commitado) e nenhum lote seguinte é enviado.
    assert resultado["status"] == "falha_lote"
    assert resultado["lotes_salvos"] == 0
    assert mock_sugerir.call_count == 1
    assert trava_normalizacao.task_em_andamento(caso_id) == "outra-task"
    session = db_session_factory()
    assert session.query(SugestaoNormalizacao).count() == 0


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------


def _usuario():
    return Usuario(
        id=1,
        nome="Revisora",
        email="revisora@x.com",
        hashed_password="x",
        role=RoleUsuario.COMUM,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )


@patch("app.api.routes_produtos.normalizar_produtos_pendentes")
def test_segundo_disparo_do_mesmo_caso_recebe_409(
    mock_task, client, logar_usuario, metas_do_backend
):
    logar_usuario(_usuario())

    primeira = client.post("/api/produtos/normalizar", json={"cliente_caso_id": 7})
    segunda = client.post("/api/produtos/normalizar", json={"cliente_caso_id": 7})

    assert primeira.status_code == 200
    assert segunda.status_code == 409
    assert mock_task.apply_async.call_count == 1
    task_id = primeira.json()["task_id"]
    assert mock_task.apply_async.call_args.kwargs == {"args": [7], "task_id": task_id}

    em_andamento = client.get("/api/produtos/normalizar/em-andamento", params={"cliente_caso_id": 7})
    assert em_andamento.json() == {"task_id": task_id}


@patch("app.api.routes_produtos.normalizar_produtos_pendentes")
def test_casos_diferentes_nao_se_bloqueiam(mock_task, client, logar_usuario):
    logar_usuario(_usuario())

    assert client.post("/api/produtos/normalizar", json={"cliente_caso_id": 7}).status_code == 200
    assert client.post("/api/produtos/normalizar", json={"cliente_caso_id": 8}).status_code == 200


def test_em_andamento_sem_execucao_devolve_null(client, logar_usuario):
    logar_usuario(_usuario())

    resposta = client.get("/api/produtos/normalizar/em-andamento", params={"cliente_caso_id": 7})

    assert resposta.json() == {"task_id": None}


@patch("app.api.routes_produtos.normalizar_produtos_pendentes")
def test_falha_ao_enfileirar_libera_a_trava(mock_task, client, logar_usuario, trava_normalizacao):
    logar_usuario(_usuario())
    mock_task.apply_async.side_effect = ConnectionError("broker fora do ar")

    with pytest.raises(ConnectionError):
        client.post("/api/produtos/normalizar", json={"cliente_caso_id": 7})

    assert trava_normalizacao.task_em_andamento(7) is None


@pytest.fixture
def metas_do_backend(monkeypatch):
    """Troca o backend de resultados do Celery (Redis) por um dict
    task_id -> meta; task sem meta registrada fica PENDING, como no Celery."""
    from app.workers.celery_app import celery_app

    metas: dict[str, dict] = {}
    # Na classe: celery_app.backend é uma instância por thread, e o
    # TestClient executa a rota em outra thread.
    monkeypatch.setattr(
        type(celery_app.backend),
        "get_task_meta",
        lambda self, task_id, *args, **kwargs: metas.get(
            task_id, {"status": "PENDING", "result": None}
        ),
    )
    return metas


def test_em_andamento_solta_trava_presa_de_task_terminada(
    client, logar_usuario, trava_normalizacao, metas_do_backend
):
    logar_usuario(_usuario())
    trava_normalizacao.adquirir(7, "task-morta")
    metas_do_backend["task-morta"] = {"status": "SUCCESS", "result": {"status": "ok"}}

    resposta = client.get("/api/produtos/normalizar/em-andamento", params={"cliente_caso_id": 7})

    assert resposta.json() == {"task_id": None}
    assert trava_normalizacao.task_em_andamento(7) is None


def test_status_informa_progresso_e_posse_da_trava(
    client, logar_usuario, trava_normalizacao, metas_do_backend
):
    logar_usuario(_usuario())
    trava_normalizacao.adquirir(7, "task-1")
    progresso = {"lotes_salvos": 2, "total_lotes": 5, "sugestoes_criadas": 80}
    metas_do_backend["task-1"] = {"status": "PROGRESS", "result": progresso}

    ativa = client.get("/api/produtos/normalizar/task-1/status", params={"cliente_caso_id": 7}).json()
    assert ativa == {
        "task_id": "task-1",
        "status": "PROGRESS",
        "ativa": True,
        "progresso": progresso,
        "resultado": None,
    }

    # Trava perdida (worker morto, TTL expirado): a tela para de acompanhar.
    trava_normalizacao.liberar(7, "task-1")
    morta = client.get("/api/produtos/normalizar/task-1/status", params={"cliente_caso_id": 7}).json()
    assert morta["ativa"] is False

    # Sem cliente_caso_id (cliente Streamlit), ativa não é calculada.
    sem_caso = client.get("/api/produtos/normalizar/task-1/status").json()
    assert sem_caso["ativa"] is None
