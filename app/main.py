from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import (
    routes_auth,
    routes_casos,
    routes_consulta,
    routes_dashboard,
    routes_notas,
    routes_produtos,
    routes_upload,
)
from app.core.config import settings
from app.core.database import async_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Só as rotas do fastapi-users (login, registro, /users/me, redefinição
    # de senha) usam a engine assíncrona -- o resto do app usa SessionLocal
    # síncrono. Como ela é criada na importação do módulo mas só abre a
    # primeira conexão de verdade na primeira requisição, e a API roda com
    # --reload (reinicia a cada alteração de arquivo), o primeiro login
    # depois de cada reinício pagava esse custo na hora e às vezes estourava
    # 500, funcionando só na segunda tentativa. Abrindo e fechando uma
    # conexão aqui, isso acontece no startup, não na requisição do usuário.
    try:
        async with async_engine.connect() as conexao:
            await conexao.execute(text("SELECT 1"))
    except Exception:
        pass  # se o banco ainda não estiver pronto, a API sobe assim mesmo
    yield


app = FastAPI(
    title="Sistema de Análise de Notas Fiscais (XML) com IA",
    version="0.1.0",
    lifespan=lifespan,
)

# O frontend React (web/) roda no browser do host e chama a API por
# fetch/XHR, então precisa de CORS -- o Streamlit nunca precisou porque
# chama a API do lado do servidor com `requests`. allow_credentials fica
# desligado de propósito: a autenticação é Bearer no header
# (app/core/auth.py, BearerTransport), não cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origem.strip() for origem in settings.cors_origins.split(",") if origem.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(routes_auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(routes_upload.router, prefix="/api/notas", tags=["notas"])
app.include_router(routes_notas.router, prefix="/api/notas", tags=["notas"])
app.include_router(routes_produtos.router, prefix="/api/produtos", tags=["produtos"])
app.include_router(routes_casos.router, prefix="/api/casos", tags=["casos"])
app.include_router(routes_dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(routes_consulta.router, prefix="/api/consulta", tags=["consulta"])


@app.get("/health")
def health():
    return {"status": "ok"}
