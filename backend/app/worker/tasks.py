"""Celery task definitions for FoldAgent.

Each task enforces safety preflight before execution.
Discoverable by the Celery app via autodiscover_tasks.
"""

from __future__ import annotations

from backend.app.worker import app as celery_app


@celery_app.task(bind=True, name="backend.app.worker.tasks.pipeline_run", max_retries=3)
def pipeline_run(self, *, job_id: str, payload: dict, case_id: str | None = None) -> dict:
    """Run a pipeline background job through the shared persistence path."""
    from backend.app.jobs import run_pipeline_job
    from backend.app.main import _run_pipeline_sync
    from backend.app.safety.preflight import PreflightResult, preflight_action

    pipeline_case_id = case_id or payload.get("case_id")
    if not pipeline_case_id:
        raise ValueError("pipeline_run requires case_id")

    action = payload.get("action", "run_pipeline")
    species_mode = payload.get("species_mode", "demo")
    result = preflight_action(
        action=action,
        species_mode=species_mode,
        involves_sequence_data=species_mode != "demo",
    )
    if result.status != PreflightResult.PASS:
        raise ValueError(f"Pipeline worker blocked by safety preflight: {result.reason}")

    return run_pipeline_job(
        case_id=pipeline_case_id,
        job_id=job_id,
        run_pipeline_sync=_run_pipeline_sync,
        pipeline_mode=payload.get("pipeline_mode", "mock"),
    )


@celery_app.task(bind=True, name="backend.app.worker.tasks.structure_prediction", max_retries=2)
def structure_prediction(self, *, job_id: str, backend_name: str, payload: dict, case_id: str | None = None) -> dict:
    """Run an AlphaFold background job through the shared persistence path."""
    from backend.app.jobs import run_alphafold_job
    from backend.app.main import _run_alphafold_sync

    return run_alphafold_job(
        case_id=case_id or payload.get("case_id"),
        job_id=job_id,
        backend_name=backend_name,
        payload=payload,
        run_alphafold_sync=_run_alphafold_sync,
    )
