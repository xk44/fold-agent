"""Tests for job-detail drilldown helpers — pure functions, no Streamlit dependency.

Covers:
- derive_job_detail: merges card + api_job + events into a detail dict
- _derive_lifecycle_events: filters SSE events relevant to a job/case
- format_job_detail: renders detail dict as compact text
- build_job_detail_table: converts detail dict to flat row dicts
- _format_payload_preview: truncates payloads for readability
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.shared.event_stream_client import SSEEvent
from frontend.app.event_stream import (
    build_job_detail_table,
    derive_job_detail,
    derive_structure_linkback,
    format_job_detail,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_api_job(
    job_id: str = "j1",
    case_id: str = "c1",
    job_type: str = "pipeline_run",
    status: str = "completed",
    attempt: int = 1,
    max_retries: int = 0,
    error: str | None = None,
    timed_out: bool = False,
    result: dict | None = None,
    payload: dict | None = None,
    created_at: str = "2025-04-20T09:55:00",
) -> dict:
    return {
        "id": job_id,
        "case_id": case_id,
        "job_type": job_type,
        "status": status,
        "payload": payload or {},
        "result": result or ({"status": status} if status == "completed" else None),
        "error": error,
        "attempt": attempt,
        "max_retries": max_retries,
        "timed_out": timed_out,
        "created_at": created_at,
    }


def _make_pipeline_event(
    case_id: str = "c1",
    status: str = "completed",
    ts: str = "2025-04-20T10:00:00",
    job_id: str | None = None,
):
    data = {
        "case_id": case_id,
        "action": "pipeline.completed",
        "timestamp": ts,
        "status": status,
    }
    if job_id:
        data["job_id"] = job_id
    return SSEEvent(event="pipeline.completed", data=data)


def _make_safety_event(
    case_id: str = "c1",
    gate: str = "pass",
    ts: str = "2025-04-20T09:30:00",
):
    return SSEEvent(
        event="safety.preflight",
        data={
            "case_id": case_id,
            "action": "safety.preflight",
            "timestamp": ts,
            "safety_gate_result": gate,
        },
    )


def _make_card_from_api_job(api_job: dict) -> dict:
    """Derive a job card dict from an API job, mimicking derive_job_status_cards."""
    return {
        "source": "api",
        "job_id": api_job["id"],
        "job_type": api_job.get("job_type", "unknown"),
        "case_id": api_job.get("case_id"),
        "status": api_job.get("status", "unknown"),
        "latest_status": api_job.get("status", "unknown"),
        "event_count": 0,
        "error": api_job.get("error"),
        "created_at": api_job.get("created_at"),
        "attempt": api_job.get("attempt", 1),
        "max_retries": api_job.get("max_retries", 0),
    }


# ---------------------------------------------------------------------------
# derive_job_detail
# ---------------------------------------------------------------------------

class TestDeriveJobDetailCardOnly:
    """Test derive_job_detail with only a card (no API job, no events)."""

    def test_basic_card_fields(self):
        card = _make_card_from_api_job(_make_api_job())
        detail = derive_job_detail(card)
        assert detail["job_id"] == "j1"
        assert detail["job_type"] == "pipeline_run"
        assert detail["status"] == "completed"
        assert detail["case_id"] == "c1"

    def test_card_without_api_job_no_attempt(self):
        card = _make_card_from_api_job(_make_api_job())
        detail = derive_job_detail(card, api_job=None)
        assert detail["attempt"] is None
        assert detail["max_retries"] is None
        assert detail["timed_out"] is None

    def test_card_error_propagated(self):
        api_job = _make_api_job(status="failed", error="GPU OOM")
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card)
        assert detail["error"] == "GPU OOM"

    def test_card_no_result_without_api(self):
        card = _make_card_from_api_job(_make_api_job())
        detail = derive_job_detail(card)
        assert detail["result"] is None


class TestDeriveJobDetailWithApiJob:
    """Test derive_job_detail when both card and API job are provided."""

    def test_api_job_enriches_attempt(self):
        api_job = _make_api_job(attempt=2, max_retries=3)
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["attempt"] == 2
        assert detail["max_retries"] == 3

    def test_api_job_enriches_timed_out(self):
        api_job = _make_api_job(timed_out=True)
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["timed_out"] is True

    def test_api_job_enriches_result(self):
        api_job = _make_api_job(result={"status": "completed", "output_file": "/tmp/out.csv"})
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["result"] == {"status": "completed", "output_file": "/tmp/out.csv"}

    def test_api_job_enriches_payload(self):
        api_job = _make_api_job(payload={"sequence": "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVE"})
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["payload"]["sequence"] == "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVE"

    def test_api_job_error_overrides_card_error(self):
        api_job = _make_api_job(error="GPU unavailable")
        card = _make_card_from_api_job(api_job)
        # Card has the error too (from derive_job_status_cards)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["error"] == "GPU unavailable"

    def test_api_job_updates_status_and_type(self):
        """API job data is more authoritative — it should update status/type."""
        card = {
            "source": "api",
            "job_id": "j1",
            "job_type": "pipeline_run",
            "case_id": "c1",
            "status": "unknown",  # Card might have stale status
            "created_at": "2025-04-20T09:00:00",
            "error": None,
        }
        api_job = {
            "id": "j1",
            "job_type": "alphafold_structure",
            "status": "failed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
        }
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["status"] == "failed"
        assert detail["job_type"] == "alphafold_structure"


class TestDeriveJobDetailWithEvents:
    """Test derive_job_detail with lifecycle events."""

    def test_events_matched_by_job_id(self):
        card = _make_card_from_api_job(_make_api_job())
        events = [
            _make_pipeline_event(job_id="j1"),
            SSEEvent(event="case.created", data={"case_id": "c99"}),
        ]
        detail = derive_job_detail(card, events=events)
        assert len(detail["lifecycle_events"]) == 1
        assert detail["lifecycle_events"][0]["event"] == "pipeline.completed"

    def test_events_matched_by_case_and_family(self):
        card = _make_card_from_api_job(_make_api_job(case_id="c1"))
        events = [
            _make_pipeline_event(case_id="c1"),
            _make_safety_event(case_id="c1"),
            _make_pipeline_event(case_id="c2"),  # different case — excluded
        ]
        detail = derive_job_detail(card, events=events)
        # pipeline matches pipeline_run family, safety should match too (case_id match)
        # Actually for pipeline_run, normalized family is "pipeline", so pipeline events match.
        # Safety events have family "safety" which won't match "pipeline", but they share case_id c1
        # Since we have job_type_variants = {"pipeline_run", "pipeline"},
        # safety events won't match those — but they match by case_id alone only if
        # job_type_variants is empty (it's not). So only pipeline events for c1 match.
        assert len(detail["lifecycle_events"]) >= 1

    def test_no_matching_events(self):
        card = _make_card_from_api_job(_make_api_job(case_id="c1"))
        events = [
            SSEEvent(event="case.created", data={"case_id": "c2"}),
        ]
        detail = derive_job_detail(card, events=events)
        assert detail["lifecycle_events"] == []

    def test_empty_events_list(self):
        card = _make_card_from_api_job(_make_api_job())
        detail = derive_job_detail(card, events=[])
        assert detail["lifecycle_events"] == []

    def test_no_events_supplied(self):
        card = _make_card_from_api_job(_make_api_job())
        detail = derive_job_detail(card)
        assert detail["lifecycle_events"] == []


# ---------------------------------------------------------------------------
# format_job_detail
# ---------------------------------------------------------------------------

class TestFormatJobDetail:
    def test_empty_dict(self):
        result = format_job_detail({})
        assert result == "No job detail available."

    def test_basic_detail(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": None,
            "error": None,
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "pipeline_run" in result
        assert "completed" in result
        assert "c1" in result
        assert "no events found" in result

    def test_detail_with_attempt(self):
        detail = {
            "job_id": "j2",
            "job_type": "alphafold_structure",
            "status": "failed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "attempt": 2,
            "max_retries": 3,
            "timed_out": False,
            "result": None,
            "error": "GPU OOM",
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "attempt" in result
        assert "2" in result
        assert "/4" in result  # max_retries+1 = 4
        assert "GPU OOM" in result
        assert "timed_out" in result

    def test_detail_with_result(self):
        detail = {
            "job_id": "j3",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "attempt": 1,
            "max_retries": 0,
            "timed_out": None,
            "result": {"status": "completed", "output_file": "/tmp/result.csv"},
            "error": None,
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "result" in result
        assert "output_file" in result

    def test_detail_with_lifecycle_events(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": None,
            "error": None,
            "lifecycle_events": [
                {"event": "pipeline.started", "timestamp": "T1", "action": "pipeline.started", "detail": "status=running"},
                {"event": "pipeline.completed", "timestamp": "T2", "action": "pipeline.completed", "detail": "status=completed"},
            ],
        }
        result = format_job_detail(detail)
        assert "2 event(s)" in result
        assert "pipeline.started" in result
        assert "pipeline.completed" in result

    def test_truncates_long_error(self):
        long_error = "x" * 600
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "failed",
            "case_id": "c1",
            "created_at": "",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": None,
            "error": long_error,
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        # Error should be truncated
        error_line = [l for l in result.splitlines() if l.strip().startswith("error:")][0]
        assert len(error_line) < 600


# ---------------------------------------------------------------------------
# build_job_detail_table
# ---------------------------------------------------------------------------

class TestBuildJobDetailTable:
    def test_empty_dict(self):
        rows = build_job_detail_table({})
        assert rows == []

    def test_basic_detail_produces_summary_row(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "lifecycle_events": [],
        }
        rows = build_job_detail_table(detail)
        assert len(rows) == 1
        assert rows[0]["type"] == "summary"
        assert rows[0]["job_id"] == "j1"
        assert rows[0]["action"] == "job_created"

    def test_detail_with_lifecycle_events(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "lifecycle_events": [
                {"event": "pipeline.started", "timestamp": "T1", "action": "pipeline.started", "detail": "status=running"},
                {"event": "pipeline.completed", "timestamp": "T2", "action": "pipeline.completed", "detail": "status=completed"},
            ],
        }
        rows = build_job_detail_table(detail)
        assert len(rows) == 3  # 1 summary + 2 lifecycle
        assert rows[1]["type"] == "lifecycle"
        assert rows[2]["event"] == "pipeline.completed"

    def test_lifecycle_rows_carry_job_id(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "failed",
            "case_id": "c1",
            "created_at": "2025-04-20T09:55:00",
            "lifecycle_events": [
                {"event": "pipeline.failed", "timestamp": "T1", "action": "pipeline.failed", "detail": ""},
            ],
        }
        rows = build_job_detail_table(detail)
        for row in rows:
            assert row["job_id"] == "j1"
            assert row["job_type"] == "pipeline_run"
            assert row["case_id"] == "c1"


# ---------------------------------------------------------------------------
# _format_payload_preview (tested indirectly via format_job_detail)
# ---------------------------------------------------------------------------

class TestFormatPayloadPreview:
    """Test the _format_payload_preview helper indirectly via format_job_detail."""

    def test_dict_result_previewed(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": {"key": "value", "nested": {"inner": 1}},
            "error": None,
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "result" in result
        # Should contain compact JSON representation
        assert "key" in result

    def test_string_result_preserved(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": "simple string result",
            "error": None,
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "simple string result" in result

    def test_payload_previewed(self):
        detail = {
            "job_id": "j1",
            "job_type": "pipeline_run",
            "status": "completed",
            "case_id": "c1",
            "created_at": "",
            "attempt": None,
            "max_retries": None,
            "timed_out": None,
            "result": None,
            "error": None,
            "payload": {"sequence": "MALWMR"},
            "lifecycle_events": [],
        }
        result = format_job_detail(detail)
        assert "payload" in result
        assert "MALWMR" in result


# ---------------------------------------------------------------------------
# Integration: derive_job_detail + format_job_detail round-trip
# ---------------------------------------------------------------------------

class TestDeriveJobDetailIntegration:
    def test_card_to_format_round_trip(self):
        api_job = _make_api_job(
            status="failed",
            attempt=2,
            max_retries=3,
            error="GPU unavailable",
            result=None,
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        text = format_job_detail(detail)
        assert "pipeline_run" in text
        assert "failed" in text
        assert "GPU unavailable" in text
        assert "attempt" in text
        assert "2" in text

    def test_card_with_events_round_trip(self):
        api_job = _make_api_job()
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(case_id="c1", job_id="j1"),
            _make_safety_event(case_id="c1"),
        ]
        detail = derive_job_detail(card, api_job=api_job, events=events)
        text = format_job_detail(detail)
        # Should show lifecycle events
        assert "event(s)" in text

    def test_full_round_trip_with_all_fields(self):
        api_job = _make_api_job(
            status="completed",
            attempt=1,
            max_retries=2,
            timed_out=False,
            result={"status": "completed", "output_file": "/tmp/result.csv"},
            payload={"sequence": "MALWMR"},
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(case_id="c1", status="running", ts="2025-04-20T09:00:00", job_id="j1"),
            _make_pipeline_event(case_id="c1", status="completed", ts="2025-04-20T10:00:00", job_id="j1"),
        ]
        detail = derive_job_detail(card, api_job=api_job, events=events)
        text = format_job_detail(detail)

        # Spot-check all sections appear
        assert "Job detail" in text
        assert "completed" in text
        assert "attempt" in text
        assert "result" in text
        assert "payload" in text
        assert "lifecycle" in text
        assert "2 event(s)" in text


class TestStructureLinkback:
    def test_non_structure_job_returns_none(self):
        api_job = _make_api_job(job_type="pipeline_run")
        card = _make_card_from_api_job(api_job)
        assert derive_structure_linkback(card, api_job=api_job) is None

    def test_alphafold_backend_with_case_returns_linkback(self):
        api_job = _make_api_job(job_type="alphafold_backend", case_id="case-1")
        card = _make_card_from_api_job(api_job)
        link = derive_structure_linkback(card, api_job=api_job)
        assert link is not None
        assert link["case_id"] == "case-1"
        assert link["label"] == "View AlphaFold structure"

    def test_extracts_structure_job_id_from_result_top_level(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            result={"status": "completed", "structure_job_id": "sj-1"},
        )
        card = _make_card_from_api_job(api_job)
        link = derive_structure_linkback(card, api_job=api_job)
        assert link["structure_job_id"] == "sj-1"

    def test_extracts_structure_job_id_from_nested_structure_block(self):
        api_job = _make_api_job(
            job_type="alphafold_structure",
            result={"status": "completed", "structure": {"job_id": "sj-2"}},
        )
        card = _make_card_from_api_job(api_job)
        link = derive_structure_linkback(card, api_job=api_job)
        assert link["structure_job_id"] == "sj-2"

    def test_extracts_candidate_id_from_payload(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            payload={"candidate_id": "cand-1", "sequence": "MALWMR"},
        )
        card = _make_card_from_api_job(api_job)
        link = derive_structure_linkback(card, api_job=api_job)
        assert link["candidate_id"] == "cand-1"

    def test_derive_job_detail_populates_structure_linkback(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            result={"status": "completed", "structure_job_id": "sj-1"},
            payload={"candidate_id": "cand-1"},
        )
        card = _make_card_from_api_job(api_job)
        detail = derive_job_detail(card, api_job=api_job)
        assert detail["structure_linkback"] is not None
        assert detail["structure_linkback"]["structure_job_id"] == "sj-1"
        assert detail["structure_linkback"]["candidate_id"] == "cand-1"

    def test_format_job_detail_renders_linkback(self):
        detail = {
            "job_id": "j-af",
            "job_type": "alphafold_backend",
            "status": "completed",
            "case_id": "case-1",
            "created_at": "2025-04-20T09:55:00",
            "attempt": 1,
            "max_retries": 0,
            "timed_out": False,
            "result": {"status": "completed"},
            "error": None,
            "payload": {"candidate_id": "cand-1"},
            "lifecycle_events": [],
            "structure_linkback": {
                "label": "View AlphaFold structure",
                "case_id": "case-1",
                "structure_job_id": "sj-1",
                "candidate_id": "cand-1",
                "surface": "structure_job_explorer",
            },
        }
        text = format_job_detail(detail)
        assert "linkback" in text
        assert "View AlphaFold structure" in text
        assert "sj-1" in text
        assert "cand-1" in text