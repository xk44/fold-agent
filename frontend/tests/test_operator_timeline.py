"""Tests for operator timeline helpers — pure functions, no Streamlit dependency.

Covers:
- derive_operator_timeline: synthesizes timeline from job detail, lifecycle, linkback, result/error
- format_operator_timeline: renders timeline as compact operator-oriented text
- build_operator_timeline_rows: converts timeline to flat row dicts
- _severity_from_event_action: infers severity from event action strings
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    _TL_CREATED,
    _TL_ERROR,
    _TL_LIFECYCLE,
    _TL_LINKBACK,
    _TL_RESULT,
    _TL_RETRY,
    _severity_from_event_action,
    build_operator_timeline_rows,
    derive_operator_timeline,
    format_operator_timeline,
)
from skills.shared.event_stream_client import SSEEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_api_job(
    job_id: str = "j-timeline-01",
    case_id: str = "c-timeline-01",
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


def _make_card_from_api_job(api_job: dict) -> dict:
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


def _make_pipeline_event(
    case_id: str = "c-timeline-01",
    status: str = "completed",
    ts: str = "2025-04-20T10:00:00",
    job_id: str | None = None,
    action: str = "pipeline.completed",
) -> SSEEvent:
    data = {
        "case_id": case_id,
        "action": action,
        "timestamp": ts,
        "status": status,
    }
    if job_id:
        data["job_id"] = job_id
    return SSEEvent(event=action, data=data)


# ---------------------------------------------------------------------------
# derive_operator_timeline — basic creation entry
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineCreation:
    """The timeline always starts with a 'created' entry for the job."""

    def test_created_entry_present(self):
        api_job = _make_api_job(job_id="j-abc123def", case_id="c1")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        created = [e for e in timeline if e["type"] == _TL_CREATED]
        assert len(created) == 1
        assert "pipeline_run" in created[0]["label"]
        assert "j-abc123" in created[0]["label"]  # short_id = first 8 chars

    def test_created_entry_has_timestamp(self):
        api_job = _make_api_job(created_at="2025-04-20T09:55:00")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        created = [e for e in timeline if e["type"] == _TL_CREATED]
        assert created[0]["timestamp"] == "2025-04-20T09:55:00"

    def test_created_entry_includes_case_id(self):
        api_job = _make_api_job(case_id="c-99")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        created = [e for e in timeline if e["type"] == _TL_CREATED]
        assert "c-99" in created[0]["detail"]

    def test_created_entry_severity_is_info(self):
        api_job = _make_api_job()
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        created = [e for e in timeline if e["type"] == _TL_CREATED]
        assert created[0]["severity"] == "info"


# ---------------------------------------------------------------------------
# derive_operator_timeline — lifecycle events
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineLifecycle:
    """Lifecycle events from SSE are merged into the timeline."""

    def test_lifecycle_events_merged(self):
        api_job = _make_api_job(job_id="j1", case_id="c1")
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(job_id="j1", action="pipeline.started", ts="2025-04-20T10:00:00"),
            _make_pipeline_event(
                job_id="j1", action="pipeline.completed", ts="2025-04-20T10:05:00"
            ),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        lifecycle = [e for e in timeline if e["type"] == _TL_LIFECYCLE]
        assert len(lifecycle) == 2
        assert lifecycle[0]["label"] == "pipeline.started"
        assert lifecycle[1]["label"] == "pipeline.completed"

    def test_lifecycle_creation_duplicate_filtered(self):
        """Creation-duplicate events (.created) are skipped from lifecycle."""
        api_job = _make_api_job(job_id="j1", case_id="c1")
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(job_id="j1", action="pipeline.created", ts="2025-04-20T09:55:00"),
            _make_pipeline_event(
                job_id="j1", action="pipeline.completed", ts="2025-04-20T10:05:00"
            ),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        lifecycle = [e for e in timeline if e["type"] == _TL_LIFECYCLE]
        # pipeline.created should be skipped; only pipeline.completed remains
        assert len(lifecycle) == 1
        assert lifecycle[0]["label"] == "pipeline.completed"

    def test_lifecycle_severity_from_action(self):
        api_job = _make_api_job(job_id="j1", case_id="c1", status="failed", error="boom")
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(job_id="j1", action="pipeline.failed", ts="2025-04-20T10:10:00"),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        lifecycle = [e for e in timeline if e["type"] == _TL_LIFECYCLE]
        assert len(lifecycle) == 1
        assert lifecycle[0]["severity"] == "error"

    def test_no_matching_events_empty_lifecycle(self):
        api_job = _make_api_job(job_id="j1", case_id="c1")
        card = _make_card_from_api_job(api_job)
        events = [
            SSEEvent(event="case.created", data={"case_id": "c-other"}),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        lifecycle = [e for e in timeline if e["type"] == _TL_LIFECYCLE]
        assert len(lifecycle) == 0


# ---------------------------------------------------------------------------
# derive_operator_timeline — retry milestone
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineRetry:
    """Retry milestone appears when attempt > 1."""

    def test_retry_milestone_present(self):
        api_job = _make_api_job(attempt=2, max_retries=3)
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        retries = [e for e in timeline if e["type"] == _TL_RETRY]
        assert len(retries) == 1
        assert "2/4" in retries[0]["label"]  # attempt 2, max_retries+1 = 4
        assert retries[0]["severity"] == "warning"

    def test_no_retry_milestone_for_first_attempt(self):
        api_job = _make_api_job(attempt=1, max_retries=0)
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        retries = [e for e in timeline if e["type"] == _TL_RETRY]
        assert len(retries) == 0

    def test_no_retry_milestone_when_attempt_none(self):
        card = {"source": "api", "job_id": "j1", "status": "completed", "job_type": "pipeline_run"}
        timeline = derive_operator_timeline(card)
        retries = [e for e in timeline if e["type"] == _TL_RETRY]
        assert len(retries) == 0


# ---------------------------------------------------------------------------
# derive_operator_timeline — structure linkback milestone
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineLinkback:
    """Structure linkback milestone appears for alphafold jobs."""

    def test_linkback_present_for_alphafold(self):
        api_job = _make_api_job(
            job_type="alphafold_backend",
            case_id="case-1",
            result={"status": "completed", "structure_job_id": "sj-long-id-42"},
        )
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        linkbacks = [e for e in timeline if e["type"] == _TL_LINKBACK]
        assert len(linkbacks) == 1
        assert linkbacks[0]["severity"] == "info"
        # Should contain structure job reference (first 8 chars)
        assert "sj-long-" in linkbacks[0]["detail"]

    def test_no_linkback_for_pipeline_run(self):
        api_job = _make_api_job(job_type="pipeline_run")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        linkbacks = [e for e in timeline if e["type"] == _TL_LINKBACK]
        assert len(linkbacks) == 0


# ---------------------------------------------------------------------------
# derive_operator_timeline — result/error terminal state
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineTerminalState:
    """Result or error entry reflects terminal state."""

    def test_error_entry_for_failed_job(self):
        api_job = _make_api_job(status="failed", error="GPU OOM")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        errors = [e for e in timeline if e["type"] == _TL_ERROR]
        assert len(errors) == 1
        assert "Failed" in errors[0]["label"]
        assert "GPU OOM" in errors[0]["detail"]
        assert errors[0]["severity"] == "error"

    def test_result_entry_for_completed_job(self):
        api_job = _make_api_job(
            status="completed",
            result={"status": "completed", "output_file": "/tmp/result.csv"},
        )
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        results = [e for e in timeline if e["type"] == _TL_RESULT]
        assert len(results) == 1
        assert "completed" in results[0]["label"]
        assert results[0]["severity"] == "ok"

    def test_result_entry_with_non_completed_status(self):
        api_job = _make_api_job(
            status="completed",
            result={"status": "partial"},
        )
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        results = [e for e in timeline if e["type"] == _TL_RESULT]
        assert len(results) == 1
        assert results[0]["severity"] == "info"

    def test_error_truncation(self):
        long_error = "x" * 300
        api_job = _make_api_job(status="failed", error=long_error)
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        errors = [e for e in timeline if e["type"] == _TL_ERROR]
        assert len(errors[0]["detail"]) < 210  # truncated to ~200

    def test_no_result_nor_error_for_pending(self):
        api_job = _make_api_job(status="pending")
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        terminals = [e for e in timeline if e["type"] in (_TL_RESULT, _TL_ERROR)]
        # Pending jobs have no result dict and no error — just created entry
        assert len(terminals) == 0


# ---------------------------------------------------------------------------
# derive_operator_timeline — chronological sorting
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineSorting:
    """Timeline entries are sorted chronologically; empty timestamps go last."""

    def test_timestamp_sorting(self):
        api_job = _make_api_job(
            job_id="j1",
            case_id="c1",
            created_at="2025-04-20T09:55:00",
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(job_id="j1", action="pipeline.started", ts="2025-04-20T10:00:00"),
            _make_pipeline_event(
                job_id="j1", action="pipeline.completed", ts="2025-04-20T10:05:00"
            ),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        # Created + 2 lifecycle entries
        assert len(timeline) >= 3
        # First entry should have earliest timestamp (or the created entry)
        timestamps_with_ts = [e["timestamp"] for e in timeline if e["timestamp"]]
        assert timestamps_with_ts == sorted(timestamps_with_ts)

    def test_empty_timestamps_sort_last(self):
        api_job = _make_api_job(
            job_id="j1",
            case_id="c1",
            status="failed",
            error="boom",
        )
        card = _make_card_from_api_job(api_job)
        timeline = derive_operator_timeline(card, api_job=api_job)
        # Error entry has no timestamp — it should be at the end
        error_entries = [e for e in timeline if e["type"] == _TL_ERROR]
        assert len(error_entries) == 1
        assert error_entries[0]["timestamp"] == ""
        # Created entry should have a timestamp and come before error
        created_entries = [e for e in timeline if e["type"] == _TL_CREATED]
        assert created_entries[0]["timestamp"] != ""


# ---------------------------------------------------------------------------
# derive_operator_timeline — comprehensive integration
# ---------------------------------------------------------------------------


class TestDeriveOperatorTimelineIntegration:
    """Integration: full timeline from card + api_job + events."""

    def test_full_failed_job_timeline(self):
        api_job = _make_api_job(
            job_id="j-full-01",
            case_id="c-full-01",
            job_type="alphafold_backend",
            status="failed",
            attempt=2,
            max_retries=2,
            error="GPU OOM",
            result=None,
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(
                job_id="j-full-01",
                case_id="c-full-01",
                action="pipeline.started",
                ts="2025-04-20T10:00:00",
            ),
            _make_pipeline_event(
                job_id="j-full-01",
                case_id="c-full-01",
                action="pipeline.failed",
                ts="2025-04-20T10:05:00",
            ),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        types = [e["type"] for e in timeline]
        # Should have: created, lifecycle(started), lifecycle(failed), retry, linkback, error
        assert _TL_CREATED in types
        assert _TL_LIFECYCLE in types
        assert _TL_RETRY in types
        assert _TL_LINKBACK in types  # alphafold_backend has structure linkback
        assert _TL_ERROR in types

    def test_full_completed_pipeline_timeline(self):
        api_job = _make_api_job(
            job_id="j-comp-01",
            case_id="c-comp-01",
            job_type="pipeline_run",
            status="completed",
            result={"status": "completed", "report_id": "rep-1"},
        )
        card = _make_card_from_api_job(api_job)
        events = [
            _make_pipeline_event(
                job_id="j-comp-01",
                case_id="c-comp-01",
                action="pipeline.started",
                ts="2025-04-20T10:00:00",
            ),
            _make_pipeline_event(
                job_id="j-comp-01",
                case_id="c-comp-01",
                action="pipeline.completed",
                ts="2025-04-20T10:05:00",
            ),
        ]
        timeline = derive_operator_timeline(card, api_job=api_job, events=events)
        types = [e["type"] for e in timeline]
        assert _TL_CREATED in types
        assert _TL_LIFECYCLE in types
        assert _TL_RESULT in types
        # No error, no linkback for pipeline_run
        assert _TL_ERROR not in types
        assert _TL_LINKBACK not in types

    def test_card_only_minimal_timeline(self):
        """With just a card and no events/api_job, we still get a created entry."""
        card = {
            "source": "api",
            "job_id": "j-min",
            "job_type": "pipeline_run",
            "status": "pending",
            "case_id": "c-min",
            "created_at": "2025-04-20T09:00:00",
        }
        timeline = derive_operator_timeline(card)
        types = [e["type"] for e in timeline]
        assert _TL_CREATED in types
        # Pending job with no result/error — should only have created
        assert len(timeline) == 1


# ---------------------------------------------------------------------------
# format_operator_timeline
# ---------------------------------------------------------------------------


class TestFormatOperatorTimeline:
    def test_empty_timeline(self):
        result = format_operator_timeline([])
        assert result == "No timeline entries."

    def test_single_entry(self):
        timeline = [
            {
                "type": _TL_CREATED,
                "timestamp": "2025-04-20T09:55:00",
                "label": "pipeline_run j1 created",
                "detail": "case=c1",
                "severity": "info",
            }
        ]
        result = format_operator_timeline(timeline)
        assert "1 entry" in result
        assert "pipeline_run j1 created" in result
        assert "INFO" in result
        assert "case=c1" in result

    def test_multiple_entries(self):
        timeline = [
            {
                "type": _TL_CREATED,
                "timestamp": "T1",
                "label": "job created",
                "detail": "",
                "severity": "info",
            },
            {
                "type": _TL_LIFECYCLE,
                "timestamp": "T2",
                "label": "pipeline.started",
                "detail": "running",
                "severity": "running",
            },
            {
                "type": _TL_ERROR,
                "timestamp": "",
                "label": "Failed: error",
                "detail": "OOM",
                "severity": "error",
            },
        ]
        result = format_operator_timeline(timeline)
        assert "3 entry" in result
        assert "ERROR" in result
        assert "OOM" in result

    def test_entry_without_detail_has_no_pipe(self):
        timeline = [
            {
                "type": _TL_CREATED,
                "timestamp": "T1",
                "label": "job created",
                "detail": "",
                "severity": "info",
            }
        ]
        result = format_operator_timeline(timeline)
        assert "|" not in result


# ---------------------------------------------------------------------------
# build_operator_timeline_rows
# ---------------------------------------------------------------------------


class TestBuildOperatorTimelineRows:
    def test_empty_timeline(self):
        assert build_operator_timeline_rows([]) == []

    def test_row_type_label_mapping(self):
        timeline = [
            {
                "type": _TL_CREATED,
                "timestamp": "",
                "label": "created",
                "detail": "",
                "severity": "info",
            },
            {
                "type": _TL_ERROR,
                "timestamp": "",
                "label": "error",
                "detail": "OOM",
                "severity": "error",
            },
        ]
        rows = build_operator_timeline_rows(timeline)
        assert len(rows) == 2
        assert rows[0]["type_label"] == "Created"
        assert rows[1]["type_label"] == "Error"
        assert rows[0]["severity"] == "info"
        assert rows[1]["detail"] == "OOM"

    def test_row_preserves_all_fields(self):
        timeline = [
            {
                "type": _TL_LIFECYCLE,
                "timestamp": "T1",
                "label": "pipeline.started",
                "detail": "running",
                "severity": "running",
            }
        ]
        rows = build_operator_timeline_rows(timeline)
        assert len(rows) == 1
        row = rows[0]
        assert row["type"] == _TL_LIFECYCLE
        assert row["type_label"] == "Event"
        assert row["timestamp"] == "T1"
        assert row["label"] == "pipeline.started"
        assert row["detail"] == "running"
        assert row["severity"] == "running"


# ---------------------------------------------------------------------------
# _severity_from_event_action
# ---------------------------------------------------------------------------


class TestSeverityFromEventAction:
    def test_failure_severity(self):
        assert _severity_from_event_action("pipeline.failed") == "error"
        assert _severity_from_event_action("job.error") == "error"
        assert _severity_from_event_action("task.timeout") == "error"

    def test_warning_severity(self):
        assert _severity_from_event_action("pipeline.retry") == "warning"
        assert _severity_from_event_action("job.blocked") == "warning"
        assert _severity_from_event_action("task.pending") == "warning"

    def test_ok_severity(self):
        assert _severity_from_event_action("pipeline.completed") == "ok"
        assert _severity_from_event_action("job.success") == "ok"
        assert _severity_from_event_action("safety.pass") == "ok"

    def test_running_severity(self):
        assert _severity_from_event_action("pipeline.running") == "running"
        assert _severity_from_event_action("job.started") == "running"
        assert _severity_from_event_action("task.submitted") == "running"

    def test_info_default(self):
        assert _severity_from_event_action("case.created") == "info"
        assert _severity_from_event_action("") == "info"
