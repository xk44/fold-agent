"""Tests for background job lifecycle events surfacing through audit log / SSE stream.

TDD: these tests verify that when background jobs transition through
pending -> running -> completed/failed/cancelled, the corresponding
audit log entries are created and appear in the /agent/events stream.
"""

import json
import time

from fastapi.testclient import TestClient

from backend.app.models import BackgroundJob


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_demo_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "BG audit case"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _wait_for_job_completion(client: TestClient, job_id: str, timeout: float = 3.0) -> dict:
    """Poll until a background job reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        poll = client.get(f"/jobs/{job_id}")
        assert poll.status_code == 200
        status = poll.json()["status"]
        if status in ("completed", "failed", "cancelled"):
            return poll.json()
        time.sleep(0.05)
    # Return last state even if still running
    return client.get(f"/jobs/{job_id}").json()


def _poll_sse_actions(client: TestClient, required_actions: set[str], timeout: float = 3.0) -> list[str]:
    deadline = time.monotonic() + timeout
    latest_actions: list[str] = []
    while time.monotonic() < deadline:
        events_resp = client.get("/agent/events?limit=50")
        assert events_resp.status_code == 200
        latest_actions = []
        for line in events_resp.text.splitlines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                latest_actions.append(payload["action"])
        if required_actions.issubset(set(latest_actions)):
            return latest_actions
        time.sleep(0.05)
    return latest_actions


def _poll_audit_actions(client: TestClient, case_id: str, required_actions: set[str], timeout: float = 3.0) -> list[str]:
    deadline = time.monotonic() + timeout
    latest_actions: list[str] = []
    while time.monotonic() < deadline:
        audit_resp = client.get(f"/audit/{case_id}")
        assert audit_resp.status_code == 200
        latest_actions = [entry["action"] for entry in audit_resp.json()]
        if required_actions.issubset(set(latest_actions)):
            return latest_actions
        time.sleep(0.05)
    return latest_actions


# ---------------------------------------------------------------------------
# 1. Pipeline background job lifecycle emits audit events
# ---------------------------------------------------------------------------

def test_pipeline_async_job_emits_created_audit_event(client: TestClient) -> None:
    """Dispatching a pipeline background job should emit a background_job.created audit event."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    # Check that the audit log includes a background_job.created event
    events_resp = client.get("/agent/events?limit=50")
    assert events_resp.status_code == 200
    events_text = events_resp.text
    # Parse SSE stream lines
    actions = []
    for line in events_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            actions.append(payload["action"])

    assert "background_job.created" in actions, (
        f"Expected 'background_job.created' in SSE events, got actions: {actions}"
    )


def test_pipeline_async_job_emits_running_audit_event(client: TestClient) -> None:
    """A pipeline background job transitioning to running should emit background_job.running."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    events_resp = client.get("/agent/events?limit=50")
    events_text = events_resp.text
    actions = []
    for line in events_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            actions.append(payload["action"])

    assert "background_job.running" in actions, (
        f"Expected 'background_job.running' in SSE events, got actions: {actions}"
    )


def test_pipeline_async_job_emits_completed_audit_event(client: TestClient) -> None:
    """A pipeline background job completing should emit background_job.completed."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    actions = _poll_sse_actions(client, {"background_job.completed", "pipeline.step.completed"})

    assert "background_job.completed" in actions, (
        f"Expected 'background_job.completed' in SSE events, got actions: {actions}"
    )
    assert "pipeline.step.completed" in actions, (
        f"Expected 'pipeline.step.completed' in SSE events, got actions: {actions}"
    )


def test_pipeline_async_job_audit_events_contain_job_id(client: TestClient) -> None:
    """Lifecycle audit events for background jobs should include the job_id in details."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    events_resp = client.get("/agent/events?limit=50")
    events_text = events_resp.text
    bg_events = []
    for line in events_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if payload["action"].startswith("background_job."):
                bg_events.append(payload)

    assert len(bg_events) >= 1, "Expected at least one background_job event"
    # Verify at least one event contains job_id in details
    events_with_job_id = [
        e for e in bg_events
        if e.get("details") and e["details"].get("job_id") == job_id
    ]
    assert len(events_with_job_id) >= 1, (
        f"Expected at least one event with job_id={job_id}, got: {bg_events}"
    )


# ---------------------------------------------------------------------------
# 2. Cancelled job emits audit event
# ---------------------------------------------------------------------------

def test_cancelled_job_emits_audit_event(client: TestClient) -> None:
    """Cancelling a pending background job should emit background_job.cancelled."""
    from backend.app.db import SessionLocal
    from backend.app.jobs import create_job
    from backend.app.models import BackgroundJobStatusEnum

    case_id = _create_demo_case(client)

    # Create a job directly in pending state (no submit) so it stays pending
    db = SessionLocal()
    try:
        job = create_job(db, case_id=case_id, job_type="test_cancel")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    # Cancel it while it's still pending
    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == 200

    events_resp = client.get("/agent/events?limit=50")
    events_text = events_resp.text
    actions = []
    for line in events_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            actions.append(payload["action"])

    assert "background_job.cancelled" in actions, (
        f"Expected 'background_job.cancelled' in SSE events, got actions: {actions}"
    )


# ---------------------------------------------------------------------------
# 3. Failing job emits failed audit event (unit-level)
# ---------------------------------------------------------------------------

def test_failed_job_transition_emits_audit_event(client: TestClient) -> None:
    """A background job that fails should emit background_job.failed."""
    from backend.app.db import SessionLocal
    from backend.app.jobs import create_job, submit_job
    from backend.app.models import BackgroundJobStatusEnum

    case_id = _create_demo_case(client)

    db = SessionLocal()
    try:
        job = create_job(db, case_id=case_id, job_type="test_failure")
        db.commit()

        def _fail():
            raise RuntimeError("intentional test failure")

        submit_job(job.id, _fail)
    finally:
        db.close()

    # Wait for failure to propagate
    for _ in range(30):
        poll = client.get(f"/jobs/{job.id}")
        if poll.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    events_resp = client.get("/agent/events?limit=50")
    events_text = events_resp.text
    actions = []
    for line in events_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            actions.append(payload["action"])

    assert "background_job.failed" in actions, (
        f"Expected 'background_job.failed' in SSE events, got actions: {actions}"
    )


# ---------------------------------------------------------------------------
# 4. SSE stream filter includes background_job. prefix
# ---------------------------------------------------------------------------

def test_agent_events_stream_includes_background_job_prefix(client: TestClient) -> None:
    """The /agent/events SSE stream should include events with the background_job. prefix."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    events_resp = client.get("/agent/events?limit=50")
    assert events_resp.status_code == 200

    # The stream should contain event lines with background_job. prefix
    event_lines = [line for line in events_resp.text.splitlines() if line.startswith("event: background_job.")]
    assert len(event_lines) >= 1, (
        f"Expected SSE event lines with 'background_job.' prefix, got: {events_resp.text[:500]}"
    )


# ---------------------------------------------------------------------------
# 5. Verify audit log directly for background job transitions
# ---------------------------------------------------------------------------

def test_audit_log_direct_query_for_background_job_events(client: TestClient) -> None:
    """Verify audit log rows exist for background job transitions via /audit endpoint."""
    case_id = _create_demo_case(client)

    resp = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    _wait_for_job_completion(client, job_id)

    actions = _poll_audit_actions(
        client,
        case_id,
        {"background_job.created", "background_job.running", "background_job.completed"},
    )

    assert "background_job.created" in actions, (
        f"Expected 'background_job.created' in audit log, got: {actions}"
    )
    assert "background_job.running" in actions, (
        f"Expected 'background_job.running' in audit log, got: {actions}"
    )
    assert "background_job.completed" in actions, (
        f"Expected 'background_job.completed' in audit log, got: {actions}"
    )