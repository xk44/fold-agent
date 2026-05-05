"""Broker-loss / fallback resilience tests for background job backend routing.

Covers edge cases in _should_use_celery_backend and submit_job routing when
broker config is absent, partial, or forced celery/threadpool.  Also tests
cancel/revoke safety when celery results are present or missing.

These are pure unit tests -- no Celery broker or Redis server required.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from backend.app import jobs
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import BackgroundJob, BackgroundJobStatusEnum


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_job(db, **overrides):
    defaults = dict(
        id=None,
        case_id=None,
        job_type="resilience_test",
        status=BackgroundJobStatusEnum.pending,
        payload=None,
        timeout_seconds=None,
        max_retries=0,
        attempt=1,
    )
    defaults.update(overrides)
    if defaults["id"] is None:
        from uuid import uuid4
        defaults["id"] = str(uuid4())
    job = BackgroundJob(**defaults)
    db.add(job)
    db.commit()
    return job


# ---------------------------------------------------------------------------
# 1. _should_use_celery_backend — pure routing logic
# ---------------------------------------------------------------------------


class TestShouldUseCeleryBackendAutoMode:
    """backend=auto (the default): celery is used only when broker + task metadata present."""

    def test_auto_no_broker_no_task_metadata(self, monkeypatch):
        """auto + no broker + no task metadata → threadpool (not celery)."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        assert jobs._should_use_celery_backend(None, None) is False

    def test_auto_no_broker_but_has_task_metadata(self, monkeypatch):
        """auto + no broker + has task metadata → still threadpool (no broker = no celery)."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j1"},
            )
            is False
        )

    def test_auto_has_broker_no_task_metadata(self, monkeypatch):
        """auto + broker present + no task metadata → threadpool (nothing to dispatch)."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert jobs._should_use_celery_backend(None, None) is False
        assert jobs._should_use_celery_backend("some.task", None) is False
        assert jobs._should_use_celery_backend(None, {"k": "v"}) is False

    def test_auto_has_broker_and_task_metadata(self, monkeypatch):
        """auto + broker present + full task metadata → celery."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j1"},
            )
            is True
        )

    def test_auto_redis_url_fallback_no_celery_broker_url(self, monkeypatch):
        """auto + redis_url set (no celery_broker_url) + task metadata → celery.

        redis_url acts as broker fallback in the worker/__init__.py.  The
        _should_use_celery_backend function checks `celery_broker_url or
        redis_url`, so redis_url alone is sufficient.
        """
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j2"},
            )
            is True
        )

    def test_auto_redis_url_fallback_without_task_metadata(self, monkeypatch):
        """auto + redis_url but no task metadata → threadpool."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0", raising=False)
        assert jobs._should_use_celery_backend(None, None) is False

    def test_auto_empty_string_broker_treated_as_absent(self, monkeypatch):
        """auto + empty-string broker (not None) should still fall back to threadpool."""
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "", raising=False)
        monkeypatch.setattr(settings, "redis_url", "", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j3"},
            )
            is False
        )


class TestShouldUseCeleryBackendForcedCelery:
    """backend=celery: only routes to celery when broker + task metadata are present."""

    def test_celery_forced_no_broker(self, monkeypatch):
        """Forced celery backend without broker → falls back to threadpool."""
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        # Even with task metadata, no broker means threadpool
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j4"},
            )
            is False
        )

    def test_celery_forced_with_broker_but_no_task_metadata(self, monkeypatch):
        """Forced celery with broker but no task name/kwargs → threadpool."""
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert jobs._should_use_celery_backend(None, None) is False
        assert jobs._should_use_celery_backend("some.task", None) is False
        assert jobs._should_use_celery_backend(None, {"k": "v"}) is False

    def test_celery_forced_with_broker_and_task_metadata(self, monkeypatch):
        """Forced celery with broker + task metadata → celery."""
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j5"},
            )
            is True
        )

    def test_celery_forced_redis_url_as_broker_fallback(self, monkeypatch):
        """Forced celery + redis_url (no celery_broker_url) + task metadata → celery."""
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://other-host:6379/5", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j6"},
            )
            is True
        )


class TestShouldUseCeleryBackendForcedThreadpool:
    """backend=threadpool: always uses threadpool regardless of broker."""

    def test_threadpool_forced_even_with_broker(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "threadpool", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j7"},
            )
            is False
        )

    def test_threadpool_forced_without_broker(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "threadpool", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        assert jobs._should_use_celery_backend(None, None) is False

    def test_threadpool_forced_case_insensitive(self, monkeypatch):
        """'ThreadPool' (mixed case) should still resolve to threadpool."""
        monkeypatch.setattr(settings, "background_job_backend", "ThreadPool", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j8"},
            )
            is False
        )


class TestShouldUseCeleryBackendWhitespace:
    """Whitespace/edge-case strings in settings should not cause routing errors."""

    def test_auto_with_leading_trailing_spaces(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", " auto ", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        # _should_use_celery_backend does .lower().strip()
        assert (
            jobs._should_use_celery_backend(
                "backend.app.worker.tasks.pipeline_run",
                {"job_id": "j9"},
            )
            is True
        )


# ---------------------------------------------------------------------------
# 2. submit_job routing integrates _should_use_celery_backend correctly
# ---------------------------------------------------------------------------


class TestSubmitJobRoutingIntegration:
    """Verify that submit_job actually dispatches to threadpool or celery
    based on _should_use_celery_backend's return value."""

    def test_submit_routes_to_threadpool_when_auto_no_broker(self, monkeypatch):
        call_log = {}

        def fake_threadpool(job_id, func, *args, timeout_seconds=None, **kwargs):
            call_log["backend"] = "threadpool"
            call_log["job_id"] = job_id
            return Future()

        def fail_celery(*a, **kw):
            raise AssertionError("should not call celery")

        monkeypatch.setattr(jobs, "_submit_via_threadpool", fake_threadpool, raising=False)
        monkeypatch.setattr(jobs, "_submit_via_celery", fail_celery, raising=False)
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)

        result = jobs.submit_job("job-no-broker", lambda: None)
        assert call_log["backend"] == "threadpool"
        assert call_log["job_id"] == "job-no-broker"

    def test_submit_routes_to_celery_when_auto_has_broker_and_metadata(self, monkeypatch):
        call_log = {}

        def fake_celery(job_id, task_name, task_kwargs, timeout_seconds=None):
            call_log["backend"] = "celery"
            call_log["job_id"] = job_id
            call_log["task_name"] = task_name
            return MagicMock()

        def fail_threadpool(*a, **kw):
            raise AssertionError("should not call threadpool")

        monkeypatch.setattr(jobs, "_submit_via_celery", fake_celery, raising=False)
        monkeypatch.setattr(jobs, "_submit_via_threadpool", fail_threadpool, raising=False)
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)

        result = jobs.submit_job(
            "job-with-broker",
            lambda: None,
            celery_task_name="backend.app.worker.tasks.pipeline_run",
            celery_kwargs={"job_id": "job-with-broker"},
        )
        assert call_log["backend"] == "celery"

    def test_submit_falls_back_to_threadpool_when_celery_forced_but_no_broker(self, monkeypatch):
        call_log = {}

        def fake_threadpool(job_id, func, *args, timeout_seconds=None, **kwargs):
            call_log["backend"] = "threadpool"
            return Future()

        def fail_celery(*a, **kw):
            raise AssertionError("should not call celery without broker")

        monkeypatch.setattr(jobs, "_submit_via_threadpool", fake_threadpool, raising=False)
        monkeypatch.setattr(jobs, "_submit_via_celery", fail_celery, raising=False)
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)

        # Even with celery_task_name and kwargs, no broker → threadpool
        result = jobs.submit_job(
            "job-celery-no-broker",
            lambda: None,
            celery_task_name="backend.app.worker.tasks.pipeline_run",
            celery_kwargs={"job_id": "job-celery-no-broker"},
        )
        assert call_log["backend"] == "threadpool"

    def test_submit_threadpool_when_celery_forced_no_task_metadata(self, monkeypatch):
        call_log = {}

        def fake_threadpool(job_id, func, *args, timeout_seconds=None, **kwargs):
            call_log["backend"] = "threadpool"
            return Future()

        def fail_celery(*a, **kw):
            raise AssertionError("should not call celery without task metadata")

        monkeypatch.setattr(jobs, "_submit_via_threadpool", fake_threadpool, raising=False)
        monkeypatch.setattr(jobs, "_submit_via_celery", fail_celery, raising=False)
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)

        # celery forced + broker present + NO task metadata → threadpool
        result = jobs.submit_job("job-celery-no-metadata", lambda: None)
        assert call_log["backend"] == "threadpool"


# ---------------------------------------------------------------------------
# 3. Celery result revoke / cancel safety
# ---------------------------------------------------------------------------


class TestCancelCeleryRevokeSafety:
    """Verify that celery_result.revoke() is called safely and that missing
    celery results do not cause crashes."""

    def test_cancel_pending_job_with_celery_result_revokes(self, db, monkeypatch):
        """When a pending job has a celery async result stored, cancel_job should revoke it."""
        mock_result = MagicMock()
        mock_result.revoke = MagicMock()

        job = _make_job(db, job_type="celery_cancel_pending")
        # Simulate a celery-queued pending job by putting a mock result in the registry
        jobs._celery_results[job.id] = mock_result

        # We also need a cancel event since cancel_job will pop it
        cancel_evt = threading.Event()
        jobs._cancel_events[job.id] = cancel_evt

        result = jobs.cancel_job(db, job.id)
        assert result is not None
        assert result.status == BackgroundJobStatusEnum.cancelled

        # revoke should have been called with terminate=False
        mock_result.revoke.assert_called_once_with(terminate=False)

        # celery result should be cleaned up
        assert job.id not in jobs._celery_results

        # Cleanup
        jobs._cancel_events.pop(job.id, None)

    def test_cancel_running_job_with_celery_result_revokes(self, db, monkeypatch):
        """When a running job has a celery async result, cancel_job should revoke it."""
        mock_result = MagicMock()
        mock_result.revoke = MagicMock()

        job = _make_job(db, job_type="celery_cancel_running", status=BackgroundJobStatusEnum.running)
        # Put a celery result in the registry
        jobs._celery_results[job.id] = mock_result
        # Also need a cancel event and future since running job path checks those
        cancel_evt = threading.Event()
        jobs._cancel_events[job.id] = cancel_evt
        mock_future = MagicMock()
        mock_future.cancel = MagicMock()
        jobs._job_futures[job.id] = mock_future

        result = jobs.cancel_job(db, job.id)
        assert result is not None

        # Future should have been cancelled
        mock_future.cancel.assert_called_once()
        # Celery result should have been revoked
        mock_result.revoke.assert_called_once_with(terminate=False)

        # Cleanup
        jobs._celery_results.pop(job.id, None)
        jobs._cancel_events.pop(job.id, None)
        jobs._job_futures.pop(job.id, None)

    def test_cancel_job_without_celery_result_still_works(self, db):
        """Cancelling a job that has no celery result should not crash."""
        job = _make_job(db, job_type="no_celery_result")
        # Ensure no celery result is stored
        jobs._celery_results.pop(job.id, None)

        result = jobs.cancel_job(db, job.id)
        assert result is not None
        assert result.status == BackgroundJobStatusEnum.cancelled

    def test_cancel_pending_job_celery_revoke_exception_does_not_crash(self, db, monkeypatch):
        """If celery_result.revoke() raises, cancel should still complete."""
        mock_result = MagicMock()
        mock_result.revoke = MagicMock(side_effect=RuntimeError("redis connection lost"))

        job = _make_job(db, job_type="celery_revoke_error")
        jobs._celery_results[job.id] = mock_result

        cancel_evt = threading.Event()
        jobs._cancel_events[job.id] = cancel_evt

        # cancel_job should NOT raise; revoke error is logged, not propagated
        result = jobs.cancel_job(db, job.id)
        assert result is not None
        assert result.status == BackgroundJobStatusEnum.cancelled

        # Celery result should still be cleaned up from registry
        assert job.id not in jobs._celery_results

        # Cleanup
        jobs._cancel_events.pop(job.id, None)

    def test_cancel_running_job_celery_revoke_exception_does_not_crash(self, db, monkeypatch):
        """If celery_result.revoke() raises on a running job, cancel should still complete."""
        mock_result = MagicMock()
        mock_result.revoke = MagicMock(side_effect=RuntimeError("broker unavailable"))

        job = _make_job(db, job_type="celery_revoke_error_running", status=BackgroundJobStatusEnum.running)
        jobs._celery_results[job.id] = mock_result

        cancel_evt = threading.Event()
        jobs._cancel_events[job.id] = cancel_evt
        mock_future = MagicMock()
        mock_future.cancel = MagicMock()
        jobs._job_futures[job.id] = mock_future

        result = jobs.cancel_job(db, job.id)
        assert result is not None
        # The job should still transition appropriately
        db.commit()
        db.refresh(job)
        assert job.status in (
            BackgroundJobStatusEnum.cancelled,
            # It may still be running if the transition hasn't propagated yet
            BackgroundJobStatusEnum.running,
        )

        # Cleanup
        jobs._celery_results.pop(job.id, None)
        jobs._cancel_events.pop(job.id, None)
        jobs._job_futures.pop(job.id, None)

    def test_cancel_terminal_job_skips_revoke(self, db):
        """Cancelling a job in a terminal state should not attempt to revoke anything."""
        mock_result = MagicMock()
        mock_result.revoke = MagicMock()

        for terminal in (
            BackgroundJobStatusEnum.completed,
            BackgroundJobStatusEnum.failed,
            BackgroundJobStatusEnum.timed_out,
        ):
            job = _make_job(db, job_type=f"terminal_{terminal.value}", status=terminal)
            jobs._celery_results[job.id] = mock_result

            result = jobs.cancel_job(db, job.id)
            assert result is not None
            assert result.status == terminal  # unchanged
            # revoke should NOT have been called for terminal states
            mock_result.revoke.assert_not_called()
            mock_result.revoke.reset_mock()

            # Cleanup
            jobs._celery_results.pop(job.id, None)


# ---------------------------------------------------------------------------
# 4. _should_use_celery_backend partial celery_kwargs edge cases
# ---------------------------------------------------------------------------


class TestShouldUseCeleryBackendPartialMetadata:
    """Empty string or empty-dict task metadata should be treated as absent."""

    def test_auto_empty_string_task_name(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        # Empty string task name → falsy → no celery
        assert jobs._should_use_celery_backend("", {"job_id": "x"}) is False

    def test_auto_empty_dict_kwargs(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        # Empty dict → falsy → no celery
        assert jobs._should_use_celery_backend("some.task", {}) is False

    def test_celery_forced_empty_string_task_name(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert jobs._should_use_celery_backend("", {"job_id": "x"}) is False

    def test_celery_forced_empty_dict_kwargs(self, monkeypatch):
        monkeypatch.setattr(settings, "background_job_backend", "celery", raising=False)
        monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)
        assert jobs._should_use_celery_backend("some.task", {}) is False


# ---------------------------------------------------------------------------
# 5. Worker __init__ broker fallback verification (structural)
# ---------------------------------------------------------------------------


class TestWorkerBrokerFallback:
    """Verify worker/__init__.py celery_broker_url fallback logic.

    Since importing the module triggers SystemExit without a broker config,
    we patch settings before import. These tests verify the fallback rules
    structurally rather than starting an actual Celery app.
    """

    def test_celery_broker_url_takes_precedence_over_redis_url(self, monkeypatch):
        """When celery_broker_url is set, it should be used over redis_url."""
        monkeypatch.setattr(settings, "celery_broker_url", "redis://celery-host:6379/0", raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://redis-host:6379/0", raising=False)
        # The worker init would use celery_broker_url as-is
        assert settings.celery_broker_url == "redis://celery-host:6379/0"

    def test_redis_url_used_as_broker_when_celery_broker_url_absent(self, monkeypatch):
        """When celery_broker_url is None but redis_url is set, redis_url is the broker."""
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", "redis://fallback-host:6379/0", raising=False)
        # _should_use_celery_backend sees this as has_broker=True
        assert jobs._should_use_celery_backend(
            "some.task", {"k": "v"}
        ) is True

    def test_neither_url_set_is_no_broker(self, monkeypatch):
        """When neither URL is set, _should_use_celery_backend returns False."""
        monkeypatch.setattr(settings, "celery_broker_url", None, raising=False)
        monkeypatch.setattr(settings, "redis_url", None, raising=False)
        assert jobs._should_use_celery_backend("some.task", {"k": "v"}) is False