"""Celery worker package for NeoVax-Agent.

Run with:
    celery -A backend.app.worker worker --loglevel=info

Or via the Makefile:
    make worker
"""

from __future__ import annotations

from backend.app.config import settings

# Only configure Celery if Redis broker URL is available.
_redis_url = settings.redis_url
_celery_broker = settings.celery_broker_url
_celery_backend = settings.celery_result_backend

if not _celery_broker:
    if _redis_url:
        _celery_broker = _redis_url
    else:
        raise SystemExit(
            "Neither NEOVAX_CELERY_BROKER_URL nor NEOVAX_REDIS_URL is set. "
            "The worker requires a message broker to function. "
            "See .env.example for configuration options."
        )

if not _celery_backend:
    if _redis_url:
        _celery_backend = _redis_url.rstrip("/") + "/1"
    else:
        _celery_backend = _celery_broker.rstrip("/") + "/1"

try:
    from celery import Celery
except ImportError:
    raise SystemExit(
        "Celery is not installed. Install with: pip install -e '.[worker]'"
    ) from None

app = Celery(
    "neovax",
    broker=_celery_broker,
    backend=_celery_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "backend.app.worker.tasks.pipeline_run": {"queue": "pipeline"},
        "backend.app.worker.tasks.structure_prediction": {"queue": "alphafold"},
    },
)

app.autodiscover_tasks(["backend.app.worker"])