from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
