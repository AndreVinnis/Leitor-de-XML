import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from app.workers.tasks import processar_xml_nfe

router = APIRouter()

UPLOAD_DIR = Path("/tmp/nfe_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_notas(
    cliente_caso_id: int = Form(...),
    cnpj_cliente: str = Form(...),
    arquivos: list[UploadFile] = File(...),
):
    """
    Recebe um lote de arquivos XML, salva em disco e enfileira o
    processamento de cada um via Celery. Responde imediatamente
    (não trava a API esperando mil+ XMLs serem processados).
    """
    lote_id = str(uuid.uuid4())
    lote_dir = UPLOAD_DIR / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)

    task_ids = []
    for arquivo in arquivos:
        destino = lote_dir / arquivo.filename
        with destino.open("wb") as f:
            shutil.copyfileobj(arquivo.file, f)

        task = processar_xml_nfe.delay(str(destino), cnpj_cliente, cliente_caso_id)
        task_ids.append(task.id)

    return {
        "status": "processando",
        "lote_id": lote_id,
        "total_arquivos": len(arquivos),
        "task_ids": task_ids,
    }


@router.get("/upload/{task_id}/status")
async def status_processamento(task_id: str):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}
