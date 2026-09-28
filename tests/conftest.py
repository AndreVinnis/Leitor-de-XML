from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import models  # noqa: F401 -- registra as tabelas em Base.metadata


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _sem_broker_de_verdade(monkeypatch):
    """
    routes_auth._processar_decisao chama enviar_notificacao_resultado_cadastro
    .delay(...) de verdade -- em CI não existe Redis (só roda `pytest -v`,
    sem serviço de broker), então isso derrubava os testes do endpoint de
    aprovação com "Error -3 connecting to redis". Autouse porque qualquer
    teste que bata nesse endpoint precisa disso, e não custa nada nos que não
    batem.
    """
    monkeypatch.setattr(
        "app.api.routes_auth.enviar_notificacao_resultado_cadastro", MagicMock()
    )
    # _atualizar_status_arquivo_lote dispara aplicar_eventos_pendentes.delay(...)
    # assim que o último ArquivoLote de um lote termina -- qualquer teste que
    # processe um lote até o fim bateria nisso, mesmo sem tocar em eventos.
    monkeypatch.setattr("app.workers.tasks.aplicar_eventos_pendentes.delay", MagicMock())


@pytest.fixture(autouse=True)
def _sem_embedding_de_verdade(monkeypatch):
    """
    Mesmo racional do fixture de broker acima, mas para a API de embedding
    do Gemini: app.workers.tasks (ao criar um ProdutoCanonico sugerido pela
    IA) e app.api.routes_produtos::criar_canonico chamam gerar_embeddings de
    verdade -- sem API key/rede em CI, isso quebraria qualquer teste que
    crie um produto canônico. Devolve um vetor fixo (não-nulo) por texto de
    entrada; testes que precisam controlar o vetor/a similaridade sobrescrevem
    este mock localmente.
    """
    mock_embeddings = MagicMock(
        side_effect=lambda textos, *args, **kwargs: [[0.1, 0.2, 0.3] for _ in textos]
    )
    monkeypatch.setattr("app.workers.tasks.gerar_embeddings", mock_embeddings)
    monkeypatch.setattr("app.api.routes_produtos.gerar_embeddings", mock_embeddings)
    monkeypatch.setattr("app.scripts.backfill_embeddings.gerar_embeddings", mock_embeddings)


class TravaNormalizacaoFalsa:
    """Substitui o Redis de app/core/trava_normalizacao.py por um dict, com
    a mesma semântica (adquirir só se livre; renovar/liberar só pelo dono)."""

    def __init__(self):
        self.donos: dict[int, str] = {}

    def adquirir(self, cliente_caso_id, task_id):
        if cliente_caso_id in self.donos:
            return False
        self.donos[cliente_caso_id] = task_id
        return True

    def task_em_andamento(self, cliente_caso_id):
        return self.donos.get(cliente_caso_id)

    def renovar(self, cliente_caso_id, task_id):
        return self.donos.get(cliente_caso_id) == task_id

    def liberar(self, cliente_caso_id, task_id):
        if self.donos.get(cliente_caso_id) == task_id:
            del self.donos[cliente_caso_id]


@pytest.fixture(autouse=True)
def trava_normalizacao(monkeypatch):
    """
    Mesmo racional de _sem_broker_de_verdade: em CI não existe Redis, e a
    rota de disparo e a task de normalização usam a trava por caso. Zera
    também as esperas entre tentativas de um lote, para os testes de retry
    não dormirem de verdade.
    """
    trava = TravaNormalizacaoFalsa()
    for nome in ("adquirir", "task_em_andamento", "renovar", "liberar"):
        monkeypatch.setattr(f"app.core.trava_normalizacao.{nome}", getattr(trava, nome))
    monkeypatch.setattr("app.workers.tasks.ESPERAS_ENTRE_TENTATIVAS", (0, 0))
    return trava


@pytest.fixture
def db_session_factory(monkeypatch):
    """
    Banco SQLite em memória, isolado por teste, usado no lugar do MySQL real.
    As rotas/tasks que fazem `SessionLocal()` direto (sem Depends) são
    repatchadas para essa fábrica -- é assim que o projeto acessa o banco
    fora do fluxo async do fastapi-users (ver app/core/database.py).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    # expire_on_commit=False: os testes seguram referências a objetos ORM
    # depois de fechar a sessão que os criou (ex: pegar admin.id depois de
    # um commit posterior na mesma sessão) -- sem isso, o SQLAlchemy expira
    # os atributos no commit e tentar acessá-los de novo estoura
    # DetachedInstanceError.
    TestSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
    )

    monkeypatch.setattr("app.api.routes_auth.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.workers.tasks.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_produtos.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_casos.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_upload.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_notas.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_dashboard.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_consulta.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_usuarios.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.api.routes_auditoria.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.scripts.backfill_embeddings.SessionLocal", TestSessionLocal)

    yield TestSessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def logar_usuario():
    """
    Sobrescreve a dependência usuario_atual_ativo (fastapi-users, que roda
    no engine async) para simular um usuário logado nas rotas de negócio,
    sem precisar gerar um JWT de verdade. `client` é scope="session", então
    não dá pra usar monkeypatch aqui -- o override é global no app e
    precisa ser limpo no teardown de cada teste pra não vazar pros outros.
    """
    from app.core.auth import usuario_atual_ativo
    from app.main import app

    def _logar(usuario):
        app.dependency_overrides[usuario_atual_ativo] = lambda: usuario
        return usuario

    yield _logar

    app.dependency_overrides.pop(usuario_atual_ativo, None)
