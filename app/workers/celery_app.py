from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "nfe_sistema",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Evita que um worker prenda várias mensagens pré-buscadas que ficariam
    # travadas até o visibility_timeout se ele morrer no meio de uma delas.
    worker_prefetch_multiplier=1,
    # Redelivery mais rápido em caso de crash do worker (default do Redis é
    # 3600s) -- compatível com o tempo esperado de processar um XML/lote.
    broker_transport_options={"visibility_timeout": 1800},
)
