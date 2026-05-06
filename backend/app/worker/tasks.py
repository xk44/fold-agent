"""Celery task definitions for FoldAgent.

Each task enforces safety preflight before execution.
Discoverable by the Celery app via autodiscover_tasks.
"""

from __future__ import annotations

from backend.app.worker import app as celery_app

# When no broker is configured celery_app is None; define no-op stubs so the
# module can be imported without error. Tasks are only dispatched by jobs.py
# when celery_app is not None.
if celery_app is None:

    def pipeline_run(**kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery worker not configured (no broker URL)")

    def structure_prediction(**kwargs):  # type: ignore[misc]
        raise RuntimeError("Celery worker not configured (no broker URL)")
else:

    @celery_app.task(bind=True, name="backend.app.worker.tasks.pipeline_run", max_retries=3)
    def pipeline_run(self, *, job_id: str, payload: dict, case_id: str | None = None) -> dict:
        """Run a pipeline background job through the shared persistence path."""
        from backend.app.db import SessionLocal
        from backend.app.jobs import _transition, run_pipeline_job
        from backend.app.main import _run_pipeline_sync
        from backend.app.models import BackgroundJobStatusEnum, Case
        from backend.app.safety.preflight import PreflightResult, preflight_action

        pipeline_case_id = case_id or payload.get("case_id")
        if not pipeline_case_id:
            raise ValueError("pipeline_run requires case_id")

        # Load species_mode from DB — never trust payload
        db = SessionLocal()
        try:
            case = db.get(Case, pipeline_case_id)
            species_mode = case.species.value if case is not None else "demo"
        finally:
            db.close()

        action = payload.get("action", "run_pipeline")
        result = preflight_action(
            action=action,
            species_mode=species_mode,
            involves_sequence_data=species_mode != "demo",
        )
        if result.status != PreflightResult.PASS:
            _transition(
                job_id,
                BackgroundJobStatusEnum.failed,
                error=f"Pipeline worker blocked by safety preflight: {result.reason}",
            )
            raise ValueError(f"Pipeline worker blocked by safety preflight: {result.reason}")

        _transition(job_id, BackgroundJobStatusEnum.running)
        try:
            rv = run_pipeline_job(
                case_id=pipeline_case_id,
                job_id=job_id,
                run_pipeline_sync=_run_pipeline_sync,
                pipeline_mode=payload.get("pipeline_mode", "mock"),
            )
            _transition(
                job_id,
                BackgroundJobStatusEnum.completed,
                result=rv if isinstance(rv, dict) else None,
            )
            return rv
        except Exception as exc:
            _transition(job_id, BackgroundJobStatusEnum.failed, error=str(exc))
            raise

    @celery_app.task(bind=True, name="backend.app.worker.tasks.structure_prediction", max_retries=2)
    def structure_prediction(
        self, *, job_id: str, backend_name: str, payload: dict, case_id: str | None = None
    ) -> dict:
        """Run an AlphaFold background job through the shared persistence path."""
        from backend.app.db import SessionLocal
        from backend.app.jobs import _transition, run_alphafold_job
        from backend.app.main import _run_alphafold_sync
        from backend.app.models import BackgroundJobStatusEnum, Case
        from backend.app.safety.preflight import PreflightResult, preflight_action

        alphafold_case_id = case_id or payload.get("case_id")

        # Load species_mode from DB — never trust payload
        species_mode = "demo"
        if alphafold_case_id:
            db = SessionLocal()
            try:
                case = db.get(Case, alphafold_case_id)
                if case is not None:
                    species_mode = case.species.value
            finally:
                db.close()

        # Safety preflight for structure prediction
        involves_external_upload = backend_name == "alphafold_server"
        external_upload_acknowledged = payload.get("acknowledge_external_upload", False)
        result = preflight_action(
            action="alphafold_backend_run",
            species_mode=species_mode,
            involves_external_upload=involves_external_upload and not external_upload_acknowledged,
            involves_sequence_data=species_mode != "demo",
        )
        if result.status != PreflightResult.PASS:
            _transition(
                job_id,
                BackgroundJobStatusEnum.failed,
                error=f"Structure prediction blocked by safety preflight: {result.reason}",
            )
            raise ValueError(f"Structure prediction blocked by safety preflight: {result.reason}")

        _transition(job_id, BackgroundJobStatusEnum.running)
        try:
            rv = run_alphafold_job(
                case_id=alphafold_case_id,
                job_id=job_id,
                backend_name=backend_name,
                payload=payload,
                run_alphafold_sync=_run_alphafold_sync,
            )
            _transition(
                job_id,
                BackgroundJobStatusEnum.completed,
                result=rv if isinstance(rv, dict) else None,
            )
            return rv
        except Exception as exc:
            _transition(job_id, BackgroundJobStatusEnum.failed, error=str(exc))
            raise
