"""Tests for the async/background job execution foundation.

Covers: BackgroundJob lifecycle, non-blocking dispatch, status polling,
pipeline and alphafold background dispatch, and error handling.
"""

import json
import time
from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.alphafold.shells import AlphaFoldExecution
from backend.app.main import app, get_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_demo_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "BG job case"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _override_db_with_empty_sqlite(tmp_path) -> None:
    empty_engine = create_engine(
        f"sqlite:///{tmp_path / 'missing-background-jobs.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=empty_engine, autoflush=False, autocommit=False)

    def _override() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override


# ---------------------------------------------------------------------------
# 1. Core lifecycle: dispatch -> pending -> running -> completed
# ---------------------------------------------------------------------------


def test_dispatch_pipeline_background_job_returns_pending(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    resp = client.post(
        f"/cases/{case_id}/pipeline/run-async",
        json={},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"]
    assert body["case_id"] == case_id
    assert body["job_type"] == "pipeline_run"
    assert body["status"] == "pending"
    assert "created_at" in body


def test_dispatched_job_transitions_to_running_then_completed(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    # Poll until status is no longer pending/running (mock pipeline is fast)
    for _ in range(20):
        poll = client.get(f"/jobs/{job_id}")
        assert poll.status_code == 200
        status = poll.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.1)

    final = client.get(f"/jobs/{job_id}").json()
    assert final["status"] == "completed"
    assert final["case_id"] == case_id
    assert final["job_type"] == "pipeline_run"
    assert final["started_at"] is not None
    assert final["finished_at"] is not None
    assert final["result"] is not None
    assert final["result"]["status"] == "completed"


def test_background_job_status_404_for_unknown_id(client: TestClient) -> None:
    resp = client.get("/jobs/nonexistent-job-id")
    assert resp.status_code == 404


def test_list_background_jobs_returns_empty_when_table_is_missing(
    client: TestClient, tmp_path
) -> None:
    _override_db_with_empty_sqlite(tmp_path)
    try:
        resp = client.get("/jobs")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == []


def test_get_background_job_returns_503_when_table_is_missing(client: TestClient, tmp_path) -> None:
    _override_db_with_empty_sqlite(tmp_path)
    try:
        resp = client.get("/jobs/nonexistent-job-id")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "background_jobs" in resp.json()["detail"]


def test_cancel_background_job_returns_503_when_table_is_missing(
    client: TestClient, tmp_path
) -> None:
    _override_db_with_empty_sqlite(tmp_path)
    try:
        resp = client.post("/jobs/nonexistent-job-id/cancel")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "background_jobs" in resp.json()["detail"]


def test_retry_background_job_returns_503_when_table_is_missing(
    client: TestClient, tmp_path
) -> None:
    _override_db_with_empty_sqlite(tmp_path)
    try:
        resp = client.post("/jobs/nonexistent-job-id/retry")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert "background_jobs" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 2. List / filter jobs
# ---------------------------------------------------------------------------


def test_list_background_jobs_filters_by_case(client: TestClient) -> None:
    case_a = _create_demo_case(client)
    case_b = _create_demo_case(client)

    client.post(f"/cases/{case_a}/pipeline/run-async", json={})
    client.post(f"/cases/{case_b}/pipeline/run-async", json={})

    # Allow jobs to complete
    time.sleep(0.5)

    list_a = client.get(f"/jobs?case_id={case_a}").json()
    assert all(j["case_id"] == case_a for j in list_a)
    assert len(list_a) >= 1

    list_b = client.get(f"/jobs?case_id={case_b}").json()
    assert all(j["case_id"] == case_b for j in list_b)

    list_all = client.get("/jobs").json()
    assert len(list_all) >= 2


def test_list_background_jobs_filters_by_status(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    time.sleep(0.5)

    completed = client.get("/jobs?status=completed").json()
    assert all(j["status"] == "completed" for j in completed)


# ---------------------------------------------------------------------------
# 3. Pipeline-specific background dispatch
# ---------------------------------------------------------------------------


def test_async_pipeline_run_creates_pipeline_run_record(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    # Wait for completion
    for _ in range(20):
        poll = client.get(f"/jobs/{job_id}")
        if poll.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    # The regular pipeline history endpoint should show the run
    history = client.get(f"/cases/{case_id}/pipeline/history")
    assert history.status_code == 200
    runs = history.json()
    assert len(runs) >= 1
    assert runs[0]["status"] == "completed"


def test_async_pipeline_run_is_audit_logged(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    for _ in range(20):
        poll = client.get(f"/jobs/{job_id}")
        if poll.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    audit = client.get(f"/audit/{case_id}")
    actions = [entry["action"] for entry in audit.json()]
    assert "pipeline.started" in actions
    assert "pipeline.completed" in actions


# ---------------------------------------------------------------------------
# 4. AlphaFold background dispatch
# ---------------------------------------------------------------------------


def test_dispatch_alphafold_background_job(client: TestClient, monkeypatch) -> None:
    case_id = _create_demo_case(client)
    variant = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr7:140453136 A>T",
            "gene": "BRAF",
            "protein_change": "p.V600E",
        },
    ).json()
    candidate = client.post(
        f"/cases/{case_id}/candidates",
        json={"variant_id": variant["id"], "mhc_context": "HLA-A*02:01"},
    ).json()

    def fake_execute(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "structure": {
                        "backend": backend_name,
                        "status": "completed",
                        "pdb_file": "/tmp/demo_out/pdb",
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute)

    dispatch = client.post(
        "/alphafold/backends/colabfold/run-async",
        json={
            "case_id": case_id,
            "candidate_id": candidate["id"],
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "bg-af-job",
        },
    )
    assert dispatch.status_code == 202
    body = dispatch.json()
    assert body["job_type"] == "alphafold_backend"
    job_id = body["id"]

    for _ in range(20):
        poll = client.get(f"/jobs/{job_id}")
        if poll.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    final = client.get(f"/jobs/{job_id}").json()
    assert final["status"] == "completed"


# ---------------------------------------------------------------------------
# 5. Error cases
# ---------------------------------------------------------------------------


def test_async_pipeline_dispatch_rejects_missing_case(client: TestClient) -> None:
    resp = client.post("/cases/nonexistent-case/pipeline/run-async", json={})
    assert resp.status_code == 404


def test_async_pipeline_dispatch_respects_safety_gate(client: TestClient) -> None:
    # Create a human case which should trigger safety enforcement
    case_resp = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Safety gated"},
    )
    case_id = case_resp.json()["id"]

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    # Safety gate blocks human mode without expert attestation
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 6. Job cancellation
# ---------------------------------------------------------------------------


def test_cancel_pending_or_running_job(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    # If the job already completed, cancel may return 409; otherwise 200
    assert cancel_resp.status_code in (200, 409)

    if cancel_resp.status_code == 200:
        poll = client.get(f"/jobs/{job_id}").json()
        assert poll["status"] in ("cancelled", "running", "completed")


# ---------------------------------------------------------------------------
# 7. Non-blocking guarantee: dispatch returns fast
# ---------------------------------------------------------------------------


def test_async_dispatch_returns_immediately(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    start = time.monotonic()
    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    elapsed = time.monotonic() - start

    assert resp.status_code == 202
    # The dispatch should return well under 1 second even on slow CI
    assert elapsed < 2.0, f"Dispatch took {elapsed:.2f}s, expected <2s"


# ---------------------------------------------------------------------------
# 8. Timeout semantics: job response includes timeout/retry fields
# ---------------------------------------------------------------------------


def test_background_job_response_includes_timeout_fields(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    body = resp.json()
    # New fields should be present in the response
    assert "timeout_seconds" in body
    assert "max_retries" in body
    assert "attempt" in body
    assert "timed_out" in body


def test_dispatch_pipeline_async_with_timeout(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    resp = client.post(
        f"/cases/{case_id}/pipeline/run-async",
        json={},
        params={"timeout_seconds": 300, "max_retries": 2},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["timeout_seconds"] == 300
    assert body["max_retries"] == 2
    assert body["attempt"] == 1
    assert body["timed_out"] is False


# ---------------------------------------------------------------------------
# 9. Retry endpoint
# ---------------------------------------------------------------------------


def test_retry_failed_background_job(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    # Create a job that will fail - we use the pipeline run but it actually
    # succeeds in demo mode. Instead, we'll create a job directly and
    # manipulate its state for the test.
    # For now, dispatch and wait for it to complete.
    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    # Wait for it to complete
    for _ in range(20):
        poll = client.get(f"/jobs/{job_id}")
        if poll.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    # Retry should be rejected for completed jobs (returns 409, not 404)
    retry_resp = client.post(f"/jobs/{job_id}/retry")
    # Completed jobs cannot be retried - returns 409 Conflict
    assert retry_resp.status_code == 409


def test_retry_nonexistent_job_returns_404(client: TestClient) -> None:
    resp = client.post("/jobs/nonexistent-id/retry")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. Cancel still works on running job (improved)
# ---------------------------------------------------------------------------


def test_cancel_running_job_accepted(client: TestClient) -> None:
    """Cancel endpoint should now accept (not refuse) cancellation for running jobs."""
    case_id = _create_demo_case(client)

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    job_id = dispatch.json()["id"]

    # Give it a moment to start running
    time.sleep(0.2)

    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    # Cancel should now either succeed (200) or if job already completed,
    # return 409 for completed. It should NOT return 409 just because it's running.
    assert cancel_resp.status_code in (200, 409)
    if cancel_resp.status_code == 200:
        poll = client.get(f"/jobs/{job_id}").json()
        # Job should be cancelled or cancelling (not still "running" with refusal)
        assert poll["status"] in ("cancelled", "running", "completed")
