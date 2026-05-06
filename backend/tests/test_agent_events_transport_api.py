from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.shared.event_stream_client import parse_sse_snapshot


def _create_demo_case(client: TestClient) -> str:
    response = client.post(
        "/cases", json={"species": "demo", "diagnosis_summary": "event transport"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_agent_events_snapshot_includes_sse_id_lines(client: TestClient) -> None:
    _create_demo_case(client)

    response = client.get("/agent/events?limit=10")
    assert response.status_code == 200

    events = parse_sse_snapshot(response.text)
    assert events, "expected at least one event in snapshot"
    first = events[0]
    assert first.event_id is not None
    assert first.event_id == first.data["log_id"]


def test_agent_events_prefix_filter_returns_only_matching_families(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    dry_run = client.post(
        "/agent/tasks/dry-run",
        json={"case_id": case_id, "framework": "hermes", "skill_name": "monitor_case_progress"},
    )
    assert dry_run.status_code == 200

    response = client.get("/agent/events?limit=50&prefix=agent_task.")
    assert response.status_code == 200

    events = parse_sse_snapshot(response.text)
    assert events, "expected filtered agent_task events"
    assert all((evt.event or "").startswith("agent_task.") for evt in events)
    assert any(evt.event == "agent_task.dry_run" for evt in events)


def test_agent_events_after_event_id_only_returns_newer_events(client: TestClient) -> None:
    case_id = _create_demo_case(client)

    first_snapshot = client.get("/agent/events?limit=50")
    assert first_snapshot.status_code == 200
    first_events = parse_sse_snapshot(first_snapshot.text)
    assert first_events, "expected initial event snapshot"
    cursor_id = first_events[-1].event_id
    assert cursor_id is not None

    dry_run = client.post(
        "/agent/tasks/dry-run",
        json={"case_id": case_id, "framework": "hermes", "skill_name": "monitor_case_progress"},
    )
    assert dry_run.status_code == 200

    incremental = client.get(f"/agent/events?limit=50&after_event_id={cursor_id}")
    assert incremental.status_code == 200
    incremental_events = parse_sse_snapshot(incremental.text)

    assert incremental_events, "expected incremental events after cursor"
    assert all(evt.event_id != cursor_id for evt in incremental_events)
    assert any(evt.event == "agent_task.dry_run" for evt in incremental_events)
