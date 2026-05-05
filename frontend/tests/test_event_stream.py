"""Tests for the Streamlit-compatible live event stream integration.

Only tests pure functions — format_sse_event_feed, format_sse_event_summary,
and format_sse_event_table_rows — which have no Streamlit dependency.
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
    format_sse_event_feed,
    format_sse_event_summary,
    format_sse_event_table_rows,
)


class TestFormatSSEEventSummary:
    def test_empty_events(self) -> None:
        result = format_sse_event_summary([])
        assert result["total_events"] == 0
        assert result["event_family_counts"] == {}

    def test_single_event(self) -> None:
        events = [SSEEvent(event="case.created", data={"case_id": "c1"})]
        result = format_sse_event_summary(events)
        assert result["total_events"] == 1
        assert result["event_family_counts"]["case"] == 1

    def test_multiple_families(self) -> None:
        events = [
            SSEEvent(event="case.created", data={}),
            SSEEvent(event="case.updated", data={}),
            SSEEvent(event="agent_task.created", data={}),
            SSEEvent(event="pipeline.completed", data={}),
            SSEEvent(event="safety.preflight", data={}),
        ]
        result = format_sse_event_summary(events)
        assert result["total_events"] == 5
        assert result["event_family_counts"]["case"] == 2
        assert result["event_family_counts"]["agent_task"] == 1
        assert result["event_family_counts"]["pipeline"] == 1
        assert result["event_family_counts"]["safety"] == 1

    def test_unknown_event_family(self) -> None:
        events = [SSEEvent(event=None, data={})]
        result = format_sse_event_summary(events)
        assert result["event_family_counts"]["unknown"] == 1


class TestFormatSSEEventFeed:
    def test_empty_events(self) -> None:
        result = format_sse_event_feed([])
        assert result == "No live events."

    def test_single_event_with_data(self) -> None:
        events = [
            SSEEvent(
                event="case.created",
                data={
                    "case_id": "c1",
                    "action": "case.created",
                    "timestamp": "2025-04-20T08:00:00",
                    "actor": "api",
                },
            )
        ]
        result = format_sse_event_feed(events)
        assert "Live event feed" in result
        assert "1 events" in result
        assert "case:1" in result
        assert "case.created" in result
        assert "case=c1" in result

    def test_limit_truncates_display(self) -> None:
        events = [
            SSEEvent(event=f"evt.{i}", data={"case_id": f"c{i}"})
            for i in range(20)
        ]
        result = format_sse_event_feed(events, limit=5)
        # Summary still shows total of 20
        assert "20 events" in result
        # But only last 5 events are shown
        lines = [l for l in result.splitlines() if l.strip().startswith("[")]
        assert len(lines) == 5

    def test_event_with_status_detail(self) -> None:
        events = [
            SSEEvent(
                event="pipeline.completed",
                data={
                    "case_id": "c1",
                    "action": "pipeline.completed",
                    "timestamp": "2025-04-20T08:00:00",
                    "status": "ok",
                },
            )
        ]
        result = format_sse_event_feed(events)
        assert "status=ok" in result

    def test_event_without_timestamp(self) -> None:
        events = [
            SSEEvent(event="case.created", data={"case_id": "c1"})
        ]
        result = format_sse_event_feed(events)
        assert "n/a" in result


class TestFormatSSEEventTableRows:
    def test_empty_events(self) -> None:
        rows = format_sse_event_table_rows([])
        assert rows == []

    def test_single_event(self) -> None:
        events = [
            SSEEvent(
                event="case.created",
                data={
                    "case_id": "c1",
                    "action": "case.created",
                    "timestamp": "2025-04-20T08:00:00",
                    "actor": "api",
                    "safety_gate_result": "pass",
                },
            )
        ]
        rows = format_sse_event_table_rows(events)
        assert len(rows) == 1
        assert rows[0]["event"] == "case.created"
        assert rows[0]["case_id"] == "c1"
        assert rows[0]["actor"] == "api"
        assert rows[0]["safety_gate_result"] == "pass"

    def test_multiple_events(self) -> None:
        events = [
            SSEEvent(event="case.created", data={"case_id": "c1"}),
            SSEEvent(event="agent_task.created", data={"case_id": "c1", "task_id": "t1"}),
        ]
        rows = format_sse_event_table_rows(events)
        assert len(rows) == 2
        assert rows[0]["event"] == "case.created"
        assert rows[1]["event"] == "agent_task.created"

    def test_event_with_none_event_name(self) -> None:
        events = [SSEEvent(event=None, data={"case_id": "c1"})]
        rows = format_sse_event_table_rows(events)
        assert rows[0]["event"] == "message"

    def test_missing_data_fields_default_empty(self) -> None:
        events = [SSEEvent(event="x", data={})]
        rows = format_sse_event_table_rows(events)
        assert rows[0]["case_id"] == ""
        assert rows[0]["timestamp"] == ""
        assert rows[0]["actor"] == ""