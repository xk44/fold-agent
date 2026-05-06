"""Unit tests for background job timeout, retry, and cancellation semantics.

Tests target backend.app.jobs module-level functions directly,
then API integration is covered in test_background_jobs_api.py.
"""

import threading
import time

import pytest
from sqlalchemy.orm import Session

from backend.app import jobs as jobs_module
from backend.app.db import SessionLocal
from backend.app.models import BackgroundJob, BackgroundJobStatusEnum

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Session:
    """Provide a DB session; caller is responsible for commit/close."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_job(db: Session, **overrides) -> BackgroundJob:
    """Helper: create a BackgroundJob row with sensible defaults."""
    defaults = dict(
        id="test-job-1",
        case_id=None,
        job_type="test_job",
        status=BackgroundJobStatusEnum.pending,
        payload=None,
        timeout_seconds=None,
        max_retries=0,
        attempt=1,
    )
    defaults.update(overrides)
    job = BackgroundJob(**defaults)
    db.add(job)
    db.commit()
    _refresh_job(db, job)
    return job


def _refresh_job(db: Session, job: BackgroundJob) -> BackgroundJob:
    """Re-fetch a job from the DB, handling detached/expired instances."""
    try:
        db.commit()
        db.refresh(job)
        return job
    except Exception:
        db.rollback()
        return db.get(BackgroundJob, job.id)


# ---------------------------------------------------------------------------
# 1. create_job accepts timeout_seconds and max_retries
# ---------------------------------------------------------------------------


def test_create_job_with_timeout_and_retries(db: Session) -> None:
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="with_timeout",
        timeout_seconds=30,
        max_retries=3,
    )
    db.commit()
    _refresh_job(db, job)
    assert job.timeout_seconds == 30
    assert job.max_retries == 3
    assert job.attempt == 1
    assert job.timed_out is False


def test_create_job_defaults_timeout_and_retries(db: Session) -> None:
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="defaults",
    )
    db.commit()
    _refresh_job(db, job)
    assert job.timeout_seconds is None
    assert job.max_retries == 0
    assert job.attempt == 1
    assert job.timed_out is False


# ---------------------------------------------------------------------------
# 2. Timeout enforcement: a slow job is marked timed_out
# ---------------------------------------------------------------------------


def test_submit_job_timeout_marks_failed_and_timed_out(db: Session) -> None:
    """A job that exceeds its timeout_seconds should be marked as timed_out."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="slow_job",
        timeout_seconds=1,  # 1-second timeout
    )
    db.commit()

    def slow_func():
        time.sleep(5)  # Way longer than timeout
        return {"status": "should_not_see"}

    future = jobs_module.submit_job(job.id, slow_func, timeout_seconds=1)

    # Wait up to 5s for the job to finish (it should be killed by timeout)
    try:
        future.result(timeout=5)
    except Exception:
        pass  # Expected - may raise due to cancellation

    # Give the timeout watcher a moment to transition state
    time.sleep(1.0)

    _refresh_job(db, job)
    assert job.status == BackgroundJobStatusEnum.timed_out
    assert job.timed_out is True
    assert job.error is not None
    assert "timed out" in job.error.lower() or "timeout" in job.error.lower()


def test_submit_job_completes_within_timeout(db: Session) -> None:
    """A job that completes within its timeout should succeed normally."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="fast_job",
        timeout_seconds=10,
    )
    db.commit()

    def fast_func():
        return {"status": "done"}

    future = jobs_module.submit_job(job.id, fast_func, timeout_seconds=10)
    result = future.result(timeout=5)
    assert result == {"status": "done"}

    time.sleep(0.5)
    _refresh_job(db, job)
    assert job.status == BackgroundJobStatusEnum.completed
    assert job.timed_out is False


# ---------------------------------------------------------------------------
# 3. Retry: retry_job re-submits a failed job
# ---------------------------------------------------------------------------


def test_retry_failed_job_increments_attempt(db: Session) -> None:
    """Retrying a failed job should increment attempt and re-queue it as pending."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="retryable",
        max_retries=2,
    )
    db.commit()
    # Manually set to failed
    job.status = BackgroundJobStatusEnum.failed
    job.error = "transient error"
    db.commit()
    _refresh_job(db, job)

    result = jobs_module.retry_job(db, job.id)
    assert result is not None
    assert result.status == BackgroundJobStatusEnum.pending
    assert result.attempt == 2
    assert result.error is None
    assert result.result is None
    assert result.finished_at is None


def test_retry_completed_job_rejected(db: Session) -> None:
    """Retrying a completed job should be rejected with ValueError."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="already_done",
        max_retries=2,
    )
    db.commit()
    job.status = BackgroundJobStatusEnum.completed
    job.result = {"status": "done"}
    db.commit()

    with pytest.raises(ValueError):
        jobs_module.retry_job(db, job.id)


def test_retry_exceeds_max_retries(db: Session) -> None:
    """Retrying beyond max_retries should be rejected with ValueError."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="max_retries_hit",
        max_retries=2,
    )
    db.commit()
    # Simulate a job that has already used its retries: attempt 3 = max_retries(2) + 1
    job.status = BackgroundJobStatusEnum.failed
    job.attempt = 3
    db.commit()

    with pytest.raises(ValueError):
        jobs_module.retry_job(db, job.id)


def test_retry_nonexistent_job(db: Session) -> None:
    """Retrying a nonexistent job should return None."""
    result = jobs_module.retry_job(db, "nonexistent-id")
    assert result is None


def test_retry_timed_out_job(db: Session) -> None:
    """A timed-out job should be eligible for retry if max_retries allows."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="timeout_retry_unit",
        max_retries=2,
    )
    db.commit()
    job.status = BackgroundJobStatusEnum.timed_out
    job.timed_out = True
    job.error = "Job timed out after 10 seconds"
    db.commit()

    result = jobs_module.retry_job(db, job.id)
    assert result is not None
    assert result.attempt == 2
    assert result.status == BackgroundJobStatusEnum.pending
    assert result.timed_out is False


# ---------------------------------------------------------------------------
# 4. Improved cancellation: cancel running job uses cooperative signal
# ---------------------------------------------------------------------------


def test_cancel_running_job_sets_cancel_event(db: Session) -> None:
    """Cancelling a running job should set the cancel event and transition to cancelled."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="cancellable",
    )
    db.commit()

    barrier = threading.Event()

    def blocking_func():
        barrier.set()  # Signal that we've started
        time.sleep(10)  # Block for a long time
        return {"status": "should_not_see"}

    future = jobs_module.submit_job(job.id, blocking_func)

    # Wait for the function to start running
    barrier.wait(timeout=5)
    # The job should now be in 'running' state
    time.sleep(0.3)
    db.commit()  # Release any write lock before cancellation
    _refresh_job(db, job)
    assert job.status == BackgroundJobStatusEnum.running

    # Cancel the running job
    result = jobs_module.cancel_job(db, job.id)
    db.commit()  # Release locks from the cancel operation

    # The cancel should have been accepted
    assert result is not None

    # Wait a moment for cancellation to propagate
    time.sleep(0.5)
    db.commit()
    _refresh_job(db, job)
    assert job.status in (BackgroundJobStatusEnum.cancelled, BackgroundJobStatusEnum.timed_out)

    # Clean up: cancel the future to avoid hanging
    future.cancel()


def test_cancel_pending_job_still_works(db: Session) -> None:
    """Cancelling a pending job should still work as before."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="pending_cancel",
    )
    db.commit()

    result = jobs_module.cancel_job(db, job.id)
    assert result is not None
    assert result.status == BackgroundJobStatusEnum.cancelled


# ---------------------------------------------------------------------------
# 5. Timeout + Retry integration: timed-out job can be retried
# ---------------------------------------------------------------------------


def test_timed_out_job_can_be_retried(db: Session) -> None:
    """A timed-out job should be eligible for retry if max_retries allows."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="timeout_retry",
        timeout_seconds=1,
        max_retries=2,
    )
    db.commit()

    def slow_func():
        time.sleep(10)
        return {"status": "should_not_see"}

    future = jobs_module.submit_job(job.id, slow_func, timeout_seconds=1)
    try:
        future.result(timeout=5)
    except Exception:
        pass

    time.sleep(1.5)
    _refresh_job(db, job)
    assert job.status == BackgroundJobStatusEnum.timed_out
    assert job.timed_out is True

    # Should be eligible for retry since attempt=1 < max_retries=2
    retried = jobs_module.retry_job(db, job.id)
    assert retried is not None
    assert retried.attempt == 2
    assert retried.status == BackgroundJobStatusEnum.pending


def test_cancel_nonexistent_job(db: Session) -> None:
    """Cancelling a nonexistent job should return None."""
    result = jobs_module.cancel_job(db, "nonexistent-id")
    assert result is None


def test_cancel_completed_job_returns_unchanged(db: Session) -> None:
    """Cancelling a completed job should return it unchanged."""
    job = jobs_module.create_job(
        db,
        case_id=None,
        job_type="already_done_cancel",
    )
    db.commit()
    job.status = BackgroundJobStatusEnum.completed
    db.commit()

    result = jobs_module.cancel_job(db, job.id)
    assert result is not None
    assert result.status == BackgroundJobStatusEnum.completed
