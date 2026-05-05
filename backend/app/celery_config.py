"""NeoVax-Agent Celery Configuration — Infrastructure Stubs

Config/registry scaffold. Actual Celery app creation is deferred.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class CeleryConfig:
    """Celery broker/backend configuration."""

    broker_url: str
    result_backend: str
    task_serializer: str
    accept_content: list[str]


CELERY_TASK_REGISTRY: dict[str, str] = {
    "run_pipeline": "Execute a full variant-calling / neoantigen pipeline run",
    "run_alphafold": "Submit an AlphaFold structure prediction job",
    "generate_report": "Build and persist a case report document",
    "export_data": "Export case data bundle to the requested format",
    "cleanup_expired": "Purge expired artifacts and temporary files",
}


def get_celery_config() -> CeleryConfig:
    """Build a CeleryConfig from settings/env, with sensible defaults."""
    from backend.app.config import settings

    broker = (
        settings.celery_broker_url
        or settings.redis_url
        or "redis://localhost:6379/0"
    )
    backend = (
        settings.celery_result_backend
        or settings.redis_url
        or "redis://localhost:6379/0"
    )
    return CeleryConfig(
        broker_url=broker,
        result_backend=backend,
        task_serializer="json",
        accept_content=["json"],
    )


def check_celery_status() -> dict:
    """Stub: check whether Celery is importable and the broker is reachable."""
    # Importability
    celery_importable = importlib.util.find_spec("celery") is not None

    cfg = get_celery_config()

    # Broker reachability (best-effort, no hard dependency on redis)
    broker_reachable = False
    broker_error: str | None = None
    if celery_importable:
        try:
            import redis  # type: ignore

            url = cfg.broker_url
            # Only attempt ping for redis:// URLs
            if url.startswith("redis://"):
                host_part = url.removeprefix("redis://")
                host, _, rest = host_part.partition(":")
                port_str, _, _db = rest.partition("/")
                port = int(port_str) if port_str.isdigit() else 6379
                r = redis.Redis(host=host or "localhost", port=port, socket_connect_timeout=2)
                r.ping()
                broker_reachable = True
        except Exception as exc:
            broker_error = str(exc)

    return {
        "celery_importable": celery_importable,
        "broker_url": cfg.broker_url,
        "result_backend": cfg.result_backend,
        "broker_reachable": broker_reachable,
        "broker_error": broker_error,
        "note": "Actual Celery app creation deferred; config scaffold only.",
    }
