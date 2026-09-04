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

    yield TestSessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def client():
    from app.main import app

    return TestClient(app)
