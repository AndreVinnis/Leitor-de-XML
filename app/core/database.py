import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Conexão só para executar o SQL gerado pela IA no NL->SQL
# (app/api/routes_consulta.py). Em produção, DATABASE_URL_CONSULTA aponta
# para um usuário MySQL com SELECT apenas em notas, itens_nota e
# produtos_canonicos (docker/mysql/criar_usuario_consulta.sh): é a segunda
# camada, depois de app/core/sql_seguranca.py -- se o validador deixar
# passar algo, o banco ainda recusa. Sem a variável, usa a mesma URL da
# conexão principal (dev/testes) e avisa no log.
#
# Engine própria nos dois casos, para o teto de tempo de execução valer
# sempre: é o controle de DoS de verdade (SLEEP, produto cartesiano),
# independente do que o validador conseguir enxergar.
TEMPO_MAXIMO_CONSULTA_MS = 10_000

_url_consulta = settings.database_url_consulta or settings.database_url
if not settings.database_url_consulta:
    logger.warning(
        "DATABASE_URL_CONSULTA não configurada: o NL->SQL roda com o usuário "
        "principal do banco, sem a camada de somente leitura."
    )
_args_consulta = (
    {"init_command": f"SET SESSION max_execution_time={TEMPO_MAXIMO_CONSULTA_MS}"}
    if _url_consulta.startswith("mysql")
    else {}
)
engine_consulta = create_engine(_url_consulta, pool_pre_ping=True, connect_args=_args_consulta)
SessionConsulta = sessionmaker(autocommit=False, autoflush=False, bind=engine_consulta)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Sessão assíncrona usada exclusivamente pelo fastapi-users (a lib exige
# AsyncSession). O resto da aplicação continua síncrono via `SessionLocal`
# acima -- as duas engines apontam para o mesmo banco, só trocam o driver.
_async_database_url = settings.database_url.replace("mysql+pymysql://", "mysql+asyncmy://", 1)
async_engine = create_async_engine(_async_database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session
