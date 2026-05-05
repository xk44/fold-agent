from concurrent.futures import Future

from backend.app import jobs
from backend.app.config import settings


class _DummyAsyncResult:
    def __init__(self) -> None:
        self.revoked = False

    def revoke(self, terminate: bool = False) -> None:
        self.revoked = True


def test_submit_job_uses_threadpool_when_backend_forced(monkeypatch) -> None:
    called: dict = {}
    expected_future = Future()

    def fake_threadpool(job_id, func, *args, timeout_seconds=None, **kwargs):
        called["job_id"] = job_id
        called["args"] = args
        called["kwargs"] = kwargs
        called["timeout_seconds"] = timeout_seconds
        return expected_future

    def fail_celery(*args, **kwargs):
        raise AssertionError("celery dispatch should not be used")

    monkeypatch.setattr(jobs, "_submit_via_threadpool", fake_threadpool, raising=False)
    monkeypatch.setattr(jobs, "_submit_via_celery", fail_celery, raising=False)
    monkeypatch.setattr(settings, "background_job_backend", "threadpool", raising=False)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)

    future = jobs.submit_job(
        "job-threadpool",
        lambda value: {"value": value},
        "demo",
        timeout_seconds=15,
        celery_task_name="backend.app.worker.tasks.pipeline_run",
        celery_kwargs={"job_id": "job-threadpool", "case_id": "case-1", "payload": {"case_id": "case-1"}},
    )

    assert future is expected_future
    assert called == {
        "job_id": "job-threadpool",
        "args": ("demo",),
        "kwargs": {},
        "timeout_seconds": 15,
    }


def test_submit_job_uses_celery_when_auto_backend_has_broker(monkeypatch) -> None:
    called: dict = {}
    expected_result = _DummyAsyncResult()

    def fake_celery(job_id, task_name, task_kwargs, timeout_seconds=None):
        called["job_id"] = job_id
        called["task_name"] = task_name
        called["task_kwargs"] = task_kwargs
        called["timeout_seconds"] = timeout_seconds
        return expected_result

    def fail_threadpool(*args, **kwargs):
        raise AssertionError("threadpool dispatch should not be used")

    monkeypatch.setattr(jobs, "_submit_via_celery", fake_celery, raising=False)
    monkeypatch.setattr(jobs, "_submit_via_threadpool", fail_threadpool, raising=False)
    monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)

    result = jobs.submit_job(
        "job-celery",
        lambda: {"status": "unused"},
        timeout_seconds=30,
        celery_task_name="backend.app.worker.tasks.pipeline_run",
        celery_kwargs={"job_id": "job-celery", "case_id": "case-2", "payload": {"case_id": "case-2"}},
    )

    assert result is expected_result
    assert called == {
        "job_id": "job-celery",
        "task_name": "backend.app.worker.tasks.pipeline_run",
        "task_kwargs": {"job_id": "job-celery", "case_id": "case-2", "payload": {"case_id": "case-2"}},
        "timeout_seconds": 30,
    }


def test_submit_job_falls_back_to_threadpool_when_auto_backend_lacks_celery_metadata(monkeypatch) -> None:
    called: dict = {}
    expected_future = Future()

    def fake_threadpool(job_id, func, *args, timeout_seconds=None, **kwargs):
        called["job_id"] = job_id
        called["timeout_seconds"] = timeout_seconds
        return expected_future

    monkeypatch.setattr(jobs, "_submit_via_threadpool", fake_threadpool, raising=False)
    monkeypatch.setattr(settings, "background_job_backend", "auto", raising=False)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://localhost:6379/0", raising=False)

    result = jobs.submit_job("job-fallback", lambda: {"status": "ok"}, timeout_seconds=5)

    assert result is expected_future
    assert called == {"job_id": "job-fallback", "timeout_seconds": 5}
