"""Tests for job status card helpers — pure functions, no Streamlit dependency.

Covers: derive_job_status_cards, format_job_status_cards,
and build_job_status_table_rows from frontend.app.event_stream.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.shared.event_stream_client import SSEEvent
from frontend.app.event_stream import (
    build_job_status_table_rows,
    derive_job_status_cards,
    format_job_status_cards,
)


# ---------------------------------------------------------------------------
# Fixtures — sample data
# ---------------------------------------------------------------------------

def _make_pipeline_event(case_id: str = "c1", status: str = "completed", ts: str = "2025-04-20T10:00:00"):
    return SSEEvent(
        event="pipeline.completed",
        data={
            "case_id": case_id,
            "action": "pipeline.completed",
            "timestamp": ts,
            "status": status,
        },
    )


def _make_agent_task_event(case_id: str = "c1", action: str = "agent_task.created", ts: str = "2025-04-20T09:00:00"):
    return SSEEvent(
        event="agent_task.created",
        data={
            "case_id": case_id,
            "action": action,
            "timestamp": ts,
        },
    )


def _make_safety_event(case_id: str = "c1", gate: str = "pass", ts: str = "2025-04-20T09:30:00"):
    return SSEEvent(
        event="safety.preflight",
        data={
            "case_id": case_id,
            "action": "safety.preflight",
            "timestamp": ts,
            "safety_gate_result": gate,
        },
    )


def _make_api_job(
    job_id: str = "j1",
    case_id: str = "c1",
    job_type: str = "pipeline_run",
    status: str = "completed",
    created_at: str = "2025-04-20T09:55:00",
    error: str | None = None,
) -> dict:
    return {
        "id": job_id,
        "case_id": case_id,
        "job_type": job_type,
        "status": status,
        "payload": {},
        "result": {"status": status} if status == "completed" else None,
        "error": error,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# derive_job_status_cards
# ---------------------------------------------------------------------------

class TestDeriveJobStatusCardsEmpty:
    def test_no_events_no_jobs(self):
        cards = derive_job_status_cards([], [])
        assert cards == []

    def test_no_events_with_jobs(self):
        jobs = [_make_api_job()]
        cards = derive_job_status_cards([], jobs)
        assert len(cards) == 1
        assert cards[0]["source"] == "api"
        assert cards[0]["job_type"] == "pipeline_run"
        assert cards[0]["status"] == "completed"

    def test_events_no_jobs(self):
        events = [_make_pipeline_event()]
        cards = derive_job_status_cards(events, [])
        assert len(cards) == 1
        assert cards[0]["source"] == "event"
        assert cards[0]["job_type"] == "pipeline"

    def test_empty_events_and_empty_jobs(self):
        cards = derive_job_status_cards([], [])
        assert cards == []


class TestDeriveJobStatusCardsFromEvents:
    def test_single_pipeline_event(self):
        events = [_make_pipeline_event()]
        cards = derive_job_status_cards(events, [])
        assert len(cards) == 1
        card = cards[0]
        assert card["source"] == "event"
        assert card["job_type"] == "pipeline"
        assert card["case_id"] == "c1"
        assert card["latest_status"] == "completed"
        assert card["event_count"] == 1

    def test_multiple_events_same_family(self):
        events = [
            _make_pipeline_event(status="running", ts="2025-04-20T09:00:00"),
            _make_pipeline_event(status="completed", ts="2025-04-20T10:00:00"),
        ]
        cards = derive_job_status_cards(events, [])
        assert len(cards) == 1
        card = cards[0]
        assert card["event_count"] == 2
        # latest_status should reflect the chronologically latest event
        assert card["latest_status"] == "completed"

    def test_events_grouped_by_family_and_case(self):
        events = [
            _make_pipeline_event(case_id="c1"),
            _make_pipeline_event(case_id="c2"),
            _make_agent_task_event(case_id="c1"),
            _make_safety_event(case_id="c2"),
        ]
        cards = derive_job_status_cards(events, [])
        # Groups: (pipeline, c1), (pipeline, c2), (agent_task, c1), (safety, c2)
        assert len(cards) == 4
        families = {(c["job_type"], c["case_id"]) for c in cards}
        assert ("pipeline", "c1") in families
        assert ("pipeline", "c2") in families
        assert ("agent_task", "c1") in families
        assert ("safety", "c2") in families

    def test_event_with_safety_gate(self):
        events = [_make_safety_event(gate="blocked")]
        cards = derive_job_status_cards(events, [])
        assert len(cards) == 1
        card = cards[0]
        assert card["job_type"] == "safety"
        assert card["latest_status"] == "blocked"

    def test_unknown_event_family(self):
        events = [SSEEvent(event=None, data={"case_id": "c1"})]
        cards = derive_job_status_cards(events, [])
        assert len(cards) == 1
        assert cards[0]["job_type"] == "unknown"


class TestDeriveJobStatusCardsFromApiJobs:
    def test_single_api_job(self):
        jobs = [_make_api_job()]
        cards = derive_job_status_cards([], jobs)
        assert len(cards) == 1
        card = cards[0]
        assert card["source"] == "api"
        assert card["job_id"] == "j1"
        assert card["job_type"] == "pipeline_run"
        assert card["status"] == "completed"
        assert card["case_id"] == "c1"

    def test_multiple_api_jobs_different_types(self):
        jobs = [
            _make_api_job(job_id="j1", job_type="pipeline_run", status="completed"),
            _make_api_job(job_id="j2", job_type="alphafold_structure", status="running"),
            _make_api_job(job_id="j3", job_type="pipeline_run", status="failed", error="timeout"),
        ]
        cards = derive_job_status_cards([], jobs)
        assert len(cards) == 3
        statuses = {c["status"] for c in cards}
        assert statuses == {"completed", "running", "failed"}
        # Failed job should carry error info
        failed = [c for c in cards if c["status"] == "failed"][0]
        assert failed["error"] == "timeout"

    def test_api_jobs_with_null_case_id(self):
        jobs = [_make_api_job(case_id=None)]
        cards = derive_job_status_cards([], jobs)
        assert len(cards) == 1
        assert cards[0]["case_id"] is None


class TestDeriveJobStatusCardsMerge:
    def test_event_and_api_job_for_same_case(self):
        events = [_make_pipeline_event(case_id="c1")]
        jobs = [_make_api_job(job_id="j1", case_id="c1", job_type="pipeline_run")]
        cards = derive_job_status_cards(events, jobs)
        # Should have event-sourced card AND api card (different sources)
        assert len(cards) == 2
        sources = {c["source"] for c in cards}
        assert sources == {"event", "api"}

    def test_dedup_prefers_api_for_matching_type_and_case(self):
        """When deduplicating (same type+case), API-sourced card wins.

        Note: dedup matches on (job_type, case_id).  Event families like
        'pipeline' and API job_type 'pipeline_run' differ, so they produce
        separate cards.  When the type matches exactly, dedup collapses them.
        """
        events = [SSEEvent(
            event="pipeline_run.completed",
            data={"case_id": "c1", "action": "pipeline_run.completed", "timestamp": "2025-04-20T10:00:00"},
        )]
        jobs = [_make_api_job(job_id="j1", case_id="c1", job_type="pipeline_run")]
        cards = derive_job_status_cards(events, jobs, dedup=True)
        # Should have 1 card, sourced from API
        assert len(cards) == 1
        assert cards[0]["source"] == "api"

    def test_dedup_no_merge_when_type_differs(self):
        """When event family and API job_type differ, they are separate cards."""
        events = [_make_pipeline_event(case_id="c1")]
        jobs = [_make_api_job(job_id="j1", case_id="c1", job_type="pipeline_run")]
        cards = derive_job_status_cards(events, jobs, dedup=True)
        # 'pipeline' (event family) != 'pipeline_run' (API job type) => 2 cards
        assert len(cards) == 2


# ---------------------------------------------------------------------------
# format_job_status_cards
# ---------------------------------------------------------------------------

class TestFormatJobStatusCards:
    def test_empty_cards(self):
        result = format_job_status_cards([])
        assert result == "No job status cards."

    def test_single_card(self):
        cards = [
            {
                "source": "api",
                "job_id": "j1",
                "job_type": "pipeline_run",
                "case_id": "c1",
                "status": "completed",
                "latest_status": "completed",
                "event_count": 0,
                "error": None,
                "created_at": "2025-04-20T09:55:00",
            }
        ]
        result = format_job_status_cards(cards)
        assert "pipeline_run" in result
        assert "completed" in result
        assert "c1" in result

    def test_multiple_cards(self):
        cards = [
            {
                "source": "api",
                "job_id": "j1",
                "job_type": "pipeline_run",
                "case_id": "c1",
                "status": "running",
                "latest_status": "running",
                "event_count": 0,
                "error": None,
                "created_at": "2025-04-20T09:00:00",
            },
            {
                "source": "event",
                "job_id": None,
                "job_type": "safety",
                "case_id": "c2",
                "status": "blocked",
                "latest_status": "blocked",
                "event_count": 3,
                "error": None,
                "created_at": None,
            },
        ]
        result = format_job_status_cards(cards)
        assert "pipeline_run" in result
        assert "safety" in result
        assert "running" in result
        assert "blocked" in result

    def test_failed_card_includes_error(self):
        cards = [
            {
                "source": "api",
                "job_id": "j3",
                "job_type": "alphafold_structure",
                "case_id": "c1",
                "status": "failed",
                "latest_status": "failed",
                "event_count": 0,
                "error": "GPU unavailable",
                "created_at": "2025-04-20T08:00:00",
            }
        ]
        result = format_job_status_cards(cards)
        assert "GPU unavailable" in result
        assert "failed" in result


# ---------------------------------------------------------------------------
# build_job_status_table_rows
# ---------------------------------------------------------------------------

class TestBuildJobStatusTableRows:
    def test_empty_cards(self):
        rows = build_job_status_table_rows([])
        assert rows == []

    def test_single_card(self):
        cards = [
            {
                "source": "api",
                "job_id": "j1",
                "job_type": "pipeline_run",
                "case_id": "c1",
                "status": "completed",
                "latest_status": "completed",
                "event_count": 2,
                "error": None,
                "created_at": "2025-04-20T09:55:00",
            }
        ]
        rows = build_job_status_table_rows(cards)
        assert len(rows) == 1
        row = rows[0]
        assert row["source"] == "api"
        assert row["job_id"] == "j1"
        assert row["job_type"] == "pipeline_run"
        assert row["status"] == "completed"
        assert row["case_id"] == "c1"
        assert row["event_count"] == 2

    def test_card_without_job_id(self):
        cards = [
            {
                "source": "event",
                "job_id": None,
                "job_type": "safety",
                "case_id": "c2",
                "status": "blocked",
                "latest_status": "blocked",
                "event_count": 5,
                "error": None,
                "created_at": None,
            }
        ]
        rows = build_job_status_table_rows(cards)
        assert rows[0]["job_id"] == ""

    def test_severity_derived_from_status(self):
        """Cards should derive severity: running=pending, completed=ok, failed=error."""
        cards = [
            {
                "source": "api",
                "job_id": "j1",
                "job_type": "pipeline_run",
                "case_id": "c1",
                "status": "completed",
                "latest_status": "completed",
                "event_count": 0,
                "error": None,
                "created_at": "2025-04-20T09:55:00",
            },
            {
                "source": "api",
                "job_id": "j2",
                "job_type": "pipeline_run",
                "case_id": "c1",
                "status": "running",
                "latest_status": "running",
                "event_count": 0,
                "error": None,
                "created_at": "2025-04-20T10:00:00",
            },
            {
                "source": "api",
                "job_id": "j3",
                "job_type": "alphafold_structure",
                "case_id": "c1",
                "status": "failed",
                "latest_status": "failed",
                "event_count": 0,
                "error": "timeout",
                "created_at": "2025-04-20T08:00:00",
            },
        ]
        rows = build_job_status_table_rows(cards)
        assert rows[0]["severity"] == "ok"
        assert rows[1]["severity"] == "running"
        assert rows[2]["severity"] == "error"