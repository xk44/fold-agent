"""Background job manager for async execution with persisted lifecycle state.

Uses a simple thread-based executor backed by the SQLAlchemy DB for state
persistence.  Jobs transition through: pending -> running -> completed/failed/timed_out.
Cancellation sets status to cancelled if caught before completion.
Timeout is enforced via cooperative cancellation with a watchdog thread.
Retry re-dispatches a failed/timed_out job up to its max_retries limit.

Each lifecycle transition emits an audit log entry so that SSE consumers
subscribing to /agent/events are notified of background job progress.
"""

from __future__ import annotations

import json
import structlog
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import (
    BackgroundJob,
    BackgroundJobStatusEnum,
    CandidateAntigen,
    PipelineRun,
    StructureJob,
)
from backend.app.safety.audit import log_action


def _pipeline_step_action(step_status: str) -> str:
    return "pipeline.step.failed" if step_status == "failed" else "pipeline.step.completed"


def _pipeline_terminal_action(pipeline_status: str) -> str:
    return "pipeline.failed" if pipeline_status == "failed" else "pipeline.completed"


logger = structlog.get_logger()

# Module-level executor - one shared pool keeps things simple and predictable.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-job")

# Per-job cancellation events: job_id -> threading.Event
# When set, signals the running job that it should abort cooperatively.
_cancel_events: dict[str, threading.Event] = {}

# Per-job futures: job_id -> Future (for timeout enforcement and local cancellation)
_job_futures: dict[str, Future] = {}

# Per-job Celery async results: job_id -> AsyncResult-like object
_celery_results: dict[str, Any] = {}

# Map BackgroundJobStatusEnum values to audit action names
_STATUS_ACTION_MAP = {
    BackgroundJobStatusEnum.pending: "background_job.created",
    BackgroundJobStatusEnum.running: "background_job.running",
    BackgroundJobStatusEnum.completed: "background_job.completed",
    BackgroundJobStatusEnum.failed: "background_job.failed",
    BackgroundJobStatusEnum.cancelled: "background_job.cancelled",
    BackgroundJobStatusEnum.timed_out: "background_job.timed_out",
}


def _emit_audit(job_id: str, case_id: str | None, action: str, details: dict | None = None) -> None:
    """Emit an audit log entry for a background job lifecycle event.

    Uses its own DB session so it works from worker threads.
    """
    audit_db = SessionLocal()
    try:
        log_action(
            audit_db,
            case_id=case_id,
            actor="bg_job",
            action=action,
            inputs={"job_id": job_id},
            outputs={},
            details=details,
        )
        audit_db.commit()
    except Exception:
        logger.exception("bg_job_audit_emit_error", job_id=job_id, action=action)
        audit_db.rollback()
    finally:
        audit_db.close()


def create_job(
    db: Session,
    *,
    case_id: str | None,
    job_type: str,
    payload: dict | None = None,
    timeout_seconds: int | None = None,
    max_retries: int = 0,
) -> BackgroundJob:
    """Persist a new job record in *pending* state and return it."""
    job = BackgroundJob(
        id=str(uuid4()),
        case_id=case_id,
        job_type=job_type,
        status=BackgroundJobStatusEnum.pending,
        payload=payload,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        attempt=1,
        timed_out=False,
    )
    db.add(job)
    db.flush()
    return job


def _transition(
    job_id: str,
    new_status: BackgroundJobStatusEnum,
    *,
    result: dict | None = None,
    error: str | None = None,
    timed_out: bool | None = None,
) -> None:
    """Transition a job to *new_status* in its own DB session."""
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("bg_job_transition_missing", job_id=job_id)
            return
        job.status = new_status
        if new_status == BackgroundJobStatusEnum.running:
            job.started_at = datetime.now(UTC)
        if new_status in (
            BackgroundJobStatusEnum.completed,
            BackgroundJobStatusEnum.failed,
            BackgroundJobStatusEnum.cancelled,
            BackgroundJobStatusEnum.timed_out,
        ):
            job.finished_at = datetime.now(UTC)
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        if timed_out is not None:
            job.timed_out = timed_out
        db.commit()
    except Exception:
        logger.exception("bg_job_transition_error", job_id=job_id)
        db.rollback()
    finally:
        db.close()

    # Emit audit event for the transition (separate session since we closed the first)
    action = _STATUS_ACTION_MAP.get(new_status)
    if action:
        details: dict[str, Any] = {"job_id": job_id, "status": new_status.value}
        if result is not None:
            details["result"] = result
        if error is not None:
            details["error"] = error
        if timed_out:
            details["timed_out"] = True
        # Retrieve case_id from the job for the audit log
        case_id = None
        lookup_db = SessionLocal()
        try:
            job = lookup_db.get(BackgroundJob, job_id)
            if job is not None:
                case_id = job.case_id
        except Exception:
            pass
        finally:
            lookup_db.close()
        _emit_audit(job_id, case_id, action, details=details)

    if new_status in (
        BackgroundJobStatusEnum.completed,
        BackgroundJobStatusEnum.failed,
        BackgroundJobStatusEnum.cancelled,
        BackgroundJobStatusEnum.timed_out,
    ):
        _celery_results.pop(job_id, None)


def _timeout_watcher(job_id: str, timeout_seconds: int, cancel_event: threading.Event) -> None:
    """Watchdog thread that marks a job as timed_out after timeout_seconds.

    If the cancel_event is set (job completed/cancelled normally), the watcher exits early.
    Otherwise, after timeout_seconds, it transitions the job to timed_out and cancels the future.
    """
    # Wait for timeout or early cancellation
    if cancel_event.wait(timeout=timeout_seconds):
        # Event was set - job completed or was cancelled normally
        return

    # Timeout reached - mark job as timed_out
    logger.warning("bg_job_timeout_exceeded", job_id=job_id, timeout_seconds=timeout_seconds)

    # Try to cancel the future if it's still running
    future = _job_futures.get(job_id)
    if future is not None:
        future.cancel()

    _transition(
        job_id,
        BackgroundJobStatusEnum.timed_out,
        error=f"Job timed out after {timeout_seconds} seconds",
        timed_out=True,
    )

    # Signal the cancel event so the running job can check it
    cancel_event.set()

    # Clean up
    _cancel_events.pop(job_id, None)
    _job_futures.pop(job_id, None)


def run_pipeline_job(
    *,
    case_id: str,
    job_id: str,
    run_pipeline_sync: Callable[[str], dict],
    pipeline_mode: str,
) -> dict:
    """Persist pipeline-run side effects for either threadpool or worker execution."""
    _db = SessionLocal()
    try:
        log_action(
            _db,
            case_id=case_id,
            actor="bg_job",
            action="pipeline.started",
            inputs={"case_id": case_id, "mode": pipeline_mode, "background_job_id": job_id},
            outputs={"status": "running"},
        )
        _db.commit()
    except Exception:
        logger.exception("pipeline_bg_log_started")
    finally:
        _db.close()

    result_data = run_pipeline_sync(case_id)
    pipeline_status = result_data.get("status", "completed")

    _db2 = SessionLocal()
    try:
        for step in result_data["steps"]:
            log_action(
                _db2,
                case_id=case_id,
                actor="bg_job",
                action=_pipeline_step_action(step["status"]),
                inputs={"case_id": case_id, "background_job_id": job_id, "step_name": step["step_name"]},
                outputs={"step_name": step["step_name"], "status": step["status"]},
                details={
                    "job_id": job_id,
                    "step_name": step["step_name"],
                    "step_version": step["step_version"],
                    "status": step["status"],
                    "errors": step["errors"],
                    "warnings": step["warnings"],
                },
            )
        pipeline_run = PipelineRun(
            id=str(uuid4()),
            case_id=case_id,
            status=pipeline_status,
            current_step=result_data["steps"][-1]["step_name"] if result_data["steps"] else None,
            completed_steps=result_data["completed_steps"],
            total_steps=result_data["total_steps"],
            step_results={"steps": result_data["steps"]},
            finished_at=datetime.now(UTC),
        )
        _db2.add(pipeline_run)
        _db2.flush()
        log_action(
            _db2,
            case_id=case_id,
            actor="bg_job",
            action=_pipeline_terminal_action(pipeline_status),
            inputs={"case_id": case_id, "background_job_id": job_id},
            outputs={"pipeline_run_id": pipeline_run.id, "status": pipeline_status},
        )
        _db2.commit()
    except Exception:
        logger.exception("pipeline_bg_persist_error")
        _db2.rollback()
    finally:
        _db2.close()

    return {"status": pipeline_status, "pipeline_steps": len(result_data["steps"])}



def run_alphafold_job(
    *,
    case_id: str | None,
    job_id: str,
    backend_name: str,
    payload: dict,
    run_alphafold_sync: Callable[[str, dict], dict],
) -> dict:
    """Persist AlphaFold side effects for either threadpool or worker execution."""
    _db_started = SessionLocal()
    try:
        log_action(
            _db_started,
            case_id=case_id,
            actor="bg_job",
            action="alphafold.job.started",
            inputs={"backend": backend_name, "background_job_id": job_id, **payload},
            outputs={"status": "running"},
        )
        _db_started.commit()
    except Exception:
        logger.exception("alphafold_bg_log_started")
        _db_started.rollback()
    finally:
        _db_started.close()

    result_dict = run_alphafold_sync(backend_name, payload)

    _db = SessionLocal()
    try:
        if case_id and payload.get("candidate_id"):
            candidate = _db.get(CandidateAntigen, payload["candidate_id"])
            if candidate is not None and candidate.case_id == case_id:
                structure_payload = result_dict.get("structure", {})
                if isinstance(result_dict.get("stdout"), str):
                    try:
                        parsed = json.loads(result_dict["stdout"])
                        structure_payload = parsed.get("structure", structure_payload)
                    except json.JSONDecodeError:
                        pass
                output_path = structure_payload.get("model_cif") or structure_payload.get("pdb_file")
                confidence_metrics = {
                    key: structure_payload[key]
                    for key in (
                        "pLDDT_mean",
                        "pAE_mean",
                        "ranking_score",
                        "ptm",
                        "iptm",
                        "chain_pair_iptm",
                        "source_url",
                        "summary_confidences_json",
                        "output_format",
                        "accession",
                    )
                    if key in structure_payload
                }
                structure_job = StructureJob(
                    id=str(uuid4()),
                    case_id=case_id,
                    candidate_id=candidate.id,
                    backend_used=backend_name,
                    output_path=output_path,
                    confidence_metrics=confidence_metrics,
                    status=result_dict.get("status", "failed"),
                )
                _db.add(structure_job)
        log_action(
            _db,
            case_id=case_id,
            actor="bg_job",
            action="alphafold.job.completed",
            inputs={"backend": backend_name, "background_job_id": job_id},
            outputs={"status": result_dict.get("status", "unknown")},
        )
        log_action(
            _db,
            case_id=case_id,
            actor="bg_job",
            action="alphafold.backend.completed",
            inputs={"backend": backend_name, "background_job_id": job_id},
            outputs={"status": result_dict.get("status", "unknown")},
        )
        _db.commit()
    except Exception:
        logger.exception("alphafold_bg_persist_error")
        _db.rollback()
    finally:
        _db.close()

    return result_dict



def _submit_via_threadpool(
    job_id: str,
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: int | None = None,
    **kwargs: Any,
) -> Future:
    """Submit *func* to the local thread pool and wire up state transitions."""
    cancel_event = threading.Event()
    _cancel_events[job_id] = cancel_event

    def _run() -> Any:
        if cancel_event.is_set():
            _transition(job_id, BackgroundJobStatusEnum.cancelled)
            raise RuntimeError(f"Job {job_id} cancelled before execution")

        _transition(job_id, BackgroundJobStatusEnum.running)
        try:
            rv = func(*args, **kwargs)
            cancel_event.set()

            check_db = SessionLocal()
            try:
                job = check_db.get(BackgroundJob, job_id)
                if job is not None and job.status in (
                    BackgroundJobStatusEnum.cancelled,
                    BackgroundJobStatusEnum.timed_out,
                ):
                    return rv
            except Exception:
                pass
            finally:
                check_db.close()

            _transition(job_id, BackgroundJobStatusEnum.completed, result=rv if isinstance(rv, dict) else None)
            return rv
        except Exception as exc:
            cancel_event.set()
            _transition(job_id, BackgroundJobStatusEnum.failed, error=str(exc))
            logger.exception("bg_job_failed", job_id=job_id)
            raise
        finally:
            _cancel_events.pop(job_id, None)
            _job_futures.pop(job_id, None)

    future = _executor.submit(_run)
    _job_futures[job_id] = future

    if timeout_seconds is not None and timeout_seconds > 0:
        watcher = threading.Thread(
            target=_timeout_watcher,
            args=(job_id, timeout_seconds, cancel_event),
            name=f"bg-job-timeout-{job_id[:8]}",
            daemon=True,
        )
        watcher.start()

    return future



def _submit_via_celery(
    job_id: str,
    task_name: str,
    task_kwargs: dict[str, Any],
    timeout_seconds: int | None = None,
) -> Any:
    """Dispatch a background job through the configured Celery worker."""
    from backend.app.worker import app as celery_app

    async_result = celery_app.send_task(
        task_name,
        kwargs=task_kwargs,
        time_limit=timeout_seconds if timeout_seconds and timeout_seconds > 0 else None,
        soft_time_limit=timeout_seconds if timeout_seconds and timeout_seconds > 0 else None,
    )
    _celery_results[job_id] = async_result
    return async_result



def _should_use_celery_backend(celery_task_name: str | None, celery_kwargs: dict[str, Any] | None) -> bool:
    backend = settings.background_job_backend.lower().strip()
    has_broker = bool(settings.celery_broker_url or settings.redis_url)
    has_task_metadata = bool(celery_task_name and celery_kwargs)

    if backend == "threadpool":
        return False
    if backend == "celery":
        return has_broker and has_task_metadata
    return has_broker and has_task_metadata



def submit_job(
    job_id: str,
    func: Callable[..., Any],
    *args: Any,
    timeout_seconds: int | None = None,
    celery_task_name: str | None = None,
    celery_kwargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Submit a background job via the configured backend.

    Routes to Celery when configured and task metadata is provided; otherwise
    falls back to the local threadpool executor.
    """
    if _should_use_celery_backend(celery_task_name, celery_kwargs):
        return _submit_via_celery(
            job_id,
            celery_task_name or "",
            celery_kwargs or {},
            timeout_seconds=timeout_seconds,
        )
    return _submit_via_threadpool(job_id, func, *args, timeout_seconds=timeout_seconds, **kwargs)


def cancel_job(db: Session, job_id: str) -> BackgroundJob | None:
    """Attempt to cancel a job.  Returns the updated job or None if not found.

    - If the job is pending, immediately mark as cancelled.
    - If the job is running, signal cancellation via the cancel event.
      The job will transition to cancelled cooperatively.
    - If the job is already in a terminal state, return it unchanged.
    """
    job = db.get(BackgroundJob, job_id)
    if job is None:
        return None

    terminal_states = (
        BackgroundJobStatusEnum.completed,
        BackgroundJobStatusEnum.failed,
        BackgroundJobStatusEnum.cancelled,
        BackgroundJobStatusEnum.timed_out,
    )
    if job.status in terminal_states:
        return job

    if job.status == BackgroundJobStatusEnum.pending:
        job.status = BackgroundJobStatusEnum.cancelled
        job.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)
        _emit_audit(job_id, job.case_id, "background_job.cancelled", details={"job_id": job_id, "status": "cancelled"})
        # Signal and clean up the cancel event if it exists
        cancel_event = _cancel_events.pop(job_id, None)
        if cancel_event is not None:
            cancel_event.set()
        celery_result = _celery_results.pop(job_id, None)
        if celery_result is not None:
            try:
                celery_result.revoke(terminate=False)
            except Exception:
                logger.exception("bg_job_celery_revoke_pending_failed", job_id=job_id)
        return job

    if job.status == BackgroundJobStatusEnum.running:
        # Signal cancellation via the event
        cancel_event = _cancel_events.get(job_id)
        if cancel_event is not None:
            cancel_event.set()

        # Try to cancel the future if it hasn't started yet
        future = _job_futures.get(job_id)
        if future is not None:
            future.cancel()
        celery_result = _celery_results.get(job_id)
        if celery_result is not None:
            try:
                celery_result.revoke(terminate=False)
            except Exception:
                logger.exception("bg_job_celery_revoke_running_failed", job_id=job_id)

        # Transition to cancelled in our own session
        _transition(job_id, BackgroundJobStatusEnum.cancelled)

        # Refresh from the test session's perspective
        db.refresh(job)
        _emit_audit(job_id, job.case_id, "background_job.cancelled", details={"job_id": job_id, "status": "cancelled"})
        return job

    return job


def retry_job(db: Session, job_id: str) -> BackgroundJob | None:
    """Retry a failed or timed-out job.

    Increments the attempt counter and re-queues the job as pending.
    Returns the updated job on success, None if the job doesn't exist,
    or raises ValueError if retry is not allowed.

    Retry is allowed when:
    - The job status is 'failed' or 'timed_out'
    - The current attempt is less than or equal to max_retries
      (attempt starts at 1, so attempt <= max_retries means retries remain)

    After calling retry_job, the caller must submit the job again via submit_job.
    """
    job = db.get(BackgroundJob, job_id)
    if job is None:
        return None

    # Only failed or timed_out jobs can be retried
    if job.status not in (BackgroundJobStatusEnum.failed, BackgroundJobStatusEnum.timed_out):
        raise ValueError(f"Job {job_id} is in status {job.status.value}, cannot be retried")

    # Check retry budget
    if job.attempt >= job.max_retries + 1:
        # attempt 1 is the first try, attempt=2 means 1 retry, etc.
        # max_retries=0 means no retries allowed (only 1 attempt)
        # max_retries=2 means 2 retries allowed (3 total attempts)
        # So retry is allowed when attempt <= max_retries
        # Actually: max_retries=2, attempt=1 -> can retry (attempt 2)
        #           max_retries=2, attempt=2 -> can retry (attempt 3)
        #           max_retries=2, attempt=3 -> cannot retry (would be attempt 4, > max_retries+1)
        raise ValueError(f"Job {job_id} has exceeded max retries (attempt={job.attempt}, max_retries={job.max_retries})")

    # Recalculate: retry allowed when next_attempt <= max_retries + 1
    next_attempt = job.attempt + 1
    if next_attempt > job.max_retries + 1:
        raise ValueError(f"Job {job_id} would exceed max retries on next attempt")

    # Reset the job for retry
    job.status = BackgroundJobStatusEnum.pending
    job.attempt = next_attempt
    job.error = None
    job.result = None
    job.finished_at = None
    job.started_at = None
    job.timed_out = False
    db.commit()
    db.refresh(job)

    _emit_audit(job_id, job.case_id, "background_job.retried", details={"job_id": job_id, "attempt": next_attempt})

    return job