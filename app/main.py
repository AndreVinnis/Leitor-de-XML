from fastapi import FastAPI

from app.api import (
    routes_auth,
    routes_casos,
    routes_dashboard,
    routes_notas,
    routes_produtos,
    routes_upload,
)

app = FastAPI(
    title="Sistema de Análise de Notas Fiscais (XML) com IA",
    version="0.1.0",
)

app.include_router(routes_auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(routes_upload.router, prefix="/api/notas", tags=["notas"])
app.include_router(routes_notas.router, prefix="/api/notas", tags=["notas"])
app.include_router(routes_produtos.router, prefix="/api/produtos", tags=["produtos"])
app.include_router(routes_casos.router, prefix="/api/casos", tags=["casos"])
app.include_router(routes_dashboard.router, prefix="/api/dashboard", tags=["dashboard"])


@app.get("/health")
def health():
    return {"status": "ok"}
