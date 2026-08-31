from fastapi import FastAPI

from app.api import routes_upload

app = FastAPI(
    title="Sistema de Análise de Notas Fiscais (XML) com IA",
    version="0.1.0",
)

app.include_router(routes_upload.router, prefix="/api/notas", tags=["notas"])


@app.get("/health")
def health():
    return {"status": "ok"}
