"""Tests for event detail drilldown helpers — pure functions, no Streamlit dependency.

Covers:
- derive_event_detail: derives a detail dict from an SSEEvent
- derive_event_shortcuts: derives related shortcut metadata from an SSEEvent
- format_event_detail: renders detail dict as compact text
- format_event_payload_json: formats event data as pretty-printed JSON
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    derive_event_detail,
    derive_event_shortcuts,
    format_event_detail,
    format_event_payload_json,
)
from skills.shared.event_stream_client import SSEEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_event(
    event: str = "pipeline.completed",
    case_id: str = "c1",
    action: str = "pipeline.completed",
    ts: str = "2025-04-20T10:00:00",
    status: str = "",
    safety_gate: str = "",
    job_id: str = "",
    actor: str = "",
    event_id: str | None = None,
    extra_data: dict | None = None,
) -> SSEEvent:
    """Create an SSEEvent with common fields and optional extras."""
    data: dict = {
        "case_id": case_id,
        "action": action,
        "timestamp": ts,
    }
    if status:
        data["status"] = status
    if safety_gate:
        data["safety_gate_result"] = safety_gate
    if job_id:
        data["job_id"] = job_id
    if actor:
        data["actor"] = actor
    if extra_data:
        data.update(extra_data)
    return SSEEvent(event=event, data=data, event_id=event_id)


# ---------------------------------------------------------------------------
# derive_event_detail
# ---------------------------------------------------------------------------


class TestDeriveEventDetailBasic:
    """Test derive_event_detail with simple events."""

    def test_basic_pipeline_event(self):
        evt = _make_event(event="pipeline.completed", case_id="c1")
        detail = derive_event_detail(evt)
        assert detail["event"] == "pipeline.completed"
        assert detail["family"] == "pipeline"
        assert detail["action_type"] == "completed"
        assert detail["case_id"] == "c1"
        assert detail["timestamp"] == "2025-04-20T10:00:00"

    def test_event_with_status(self):
        evt = _make_event(event="pipeline.completed", status="ok")
        detail = derive_event_detail(evt)
        assert detail["data"]["status"] == "ok"
        # summary should include status
        assert "status=ok" in detail["summary"]

    def test_event_with_safety_gate(self):
        evt = _make_event(event="safety.preflight", safety_gate="pass")
        detail = derive_event_detail(evt)
        assert detail["data"]["safety_gate_result"] == "pass"
        assert "safety_gate=pass" in detail["summary"]

    def test_event_with_job_id(self):
        evt = _make_event(event="pipeline.started", job_id="j123")
        detail = derive_event_detail(evt)
        assert detail["job_id"] == "j123"

    def test_event_with_no_data(self):
        evt = SSEEvent(event="ping", data={}, event_id=None)
        detail = derive_event_detail(evt)
        assert detail["event"] == "ping"
        assert detail["case_id"] is None
        assert detail["job_id"] is None
        assert detail["family"] == "ping"
        assert detail["action_type"] == "ping"

    def test_event_with_none_event_name(self):
        evt = SSEEvent(event=None, data={"case_id": "c1"}, event_id=None)
        detail = derive_event_detail(evt)
        assert detail["event"] == "message"
        assert detail["family"] == "message"
        assert detail["action_type"] == "message"

    def test_event_with_event_id(self):
        evt = _make_event(event_id="evt-42")
        detail = derive_event_detail(evt)
        assert detail["event_id"] == "evt-42"

    def test_action_falls_back_to_event_name(self):
        evt = SSEEvent(event="custom.action", data={"case_id": "c1"}, event_id=None)
        detail = derive_event_detail(evt)
        # action comes from data["action"] if present, else event name
        assert detail["action"] == "custom.action"  # data has no action key

    def test_action_from_data(self):
        evt = _make_event(event="pipeline.completed", action="pipeline.done")
        detail = derive_event_detail(evt)
        assert detail["action"] == "pipeline.done"


class TestDeriveEventDetailSummary:
    """Test the summary field in derive_event_detail."""

    def test_summary_with_timestamp_only(self):
        evt = SSEEvent(
            event="heartbeat",
            data={"timestamp": "2025-04-20T10:00:00"},
            event_id=None,
        )
        detail = derive_event_detail(evt)
        assert detail["summary"] == "[2025-04-20T10:00:00] heartbeat"

    def test_summary_with_case_id(self):
        evt = _make_event(event="pipeline.started", case_id="case-abc")
        detail = derive_event_detail(evt)
        assert "case=case-abc" in detail["summary"]

    def test_summary_with_status(self):
        evt = _make_event(event="pipeline.completed", status="completed")
        detail = derive_event_detail(evt)
        assert "status=completed" in detail["summary"]

    def test_summary_with_safety_gate(self):
        evt = _make_event(event="safety.preflight", safety_gate="fail")
        detail = derive_event_detail(evt)
        assert "safety_gate=fail" in detail["summary"]

    def test_summary_combines_all(self):
        evt = _make_event(
            event="safety.preflight",
            case_id="c2",
            status="blocked",
            safety_gate="fail",
        )
        detail = derive_event_detail(evt)
        summary = detail["summary"]
        assert "case=c2" in summary
        assert "status=blocked" in summary
        assert "safety_gate=fail" in summary


class TestDeriveEventDetailShortcuts:
    """Test that derive_event_detail includes shortcuts from derive_event_shortcuts."""

    def test_shortcuts_included(self):
        evt = _make_event(event="pipeline.completed", case_id="c1")
        detail = derive_event_detail(evt)
        assert detail["shortcuts"] is not None
        assert detail["shortcuts"]["case_shortcut"] is True
        assert detail["shortcuts"]["case_id"] == "c1"

    def test_shortcuts_none_when_no_derivable(self):
        evt = SSEEvent(event="heartbeat", data={"timestamp": "T"}, event_id=None)
        detail = derive_event_detail(evt)
        assert detail["shortcuts"] is None


# ---------------------------------------------------------------------------
# derive_event_shortcuts
# ---------------------------------------------------------------------------


class TestDeriveEventShortcuts:
    """Test derive_event_shortcuts independently."""

    def test_no_shortcuts_for_empty_data(self):
        evt = SSEEvent(event="heartbeat", data={}, event_id=None)
        result = derive_event_shortcuts(evt)
        assert result is None

    def test_no_shortcuts_for_unrecognized_family(self):
        """Event family not in pipeline/safety, and no case_id/job_id."""
        evt = SSEEvent(event="unknown.ping", data={"timestamp": "T"}, event_id=None)
        result = derive_event_shortcuts(evt)
        assert result is None

    def test_case_shortcut(self):
        evt = _make_event(event="case.created", case_id="c1")
        result = derive_event_shortcuts(evt)
        assert result is not None
        assert result["case_id"] == "c1"
        assert result["case_shortcut"] is True

    def test_job_shortcut(self):
        evt = _make_event(event="pipeline.started", job_id="j42")
        result = derive_event_shortcuts(evt)
        assert result is not None
        assert result["job_id"] == "j42"
        assert result["job_shortcut"] is True

    def test_pipeline_shortcut(self):
        evt = _make_event(event="pipeline.completed")
        result = derive_event_shortcuts(evt)
        assert result is not None
        assert result["pipeline_shortcut"] is True
        assert result["safety_shortcut"] is False
        assert result["job_type_hint"] == "pipeline"

    def test_safety_shortcut(self):
        evt = _make_event(event="safety.preflight")
        result = derive_event_shortcuts(evt)
        assert result is not None
        assert result["safety_shortcut"] is True
        assert result["pipeline_shortcut"] is False
        assert result["job_type_hint"] == "safety"

    def test_combined_shortcuts(self):
        evt = _make_event(
            event="pipeline.completed",
            case_id="c1",
            job_id="j99",
        )
        result = derive_event_shortcuts(evt)
        assert result is not None
        assert result["case_shortcut"] is True
        assert result["job_shortcut"] is True
        assert result["pipeline_shortcut"] is True
        assert result["case_id"] == "c1"
        assert result["job_id"] == "j99"
        assert result["job_type_hint"] == "pipeline"


# ---------------------------------------------------------------------------
# format_event_detail
# ---------------------------------------------------------------------------


class TestFormatEventDetail:
    """Test format_event_detail rendering."""

    def test_empty_dict(self):
        result = format_event_detail({})
        assert result == "No event detail available."

    def test_basic_detail(self):
        detail = derive_event_detail(
            _make_event(
                event="pipeline.completed",
                case_id="c1",
                action="pipeline.done",
                ts="2025-04-20T10:00:00",
            )
        )
        result = format_event_detail(detail)
        assert "Event detail — pipeline.completed" in result
        assert "pipeline" in result  # family
        assert "completed" in result  # action_type
        assert "c1" in result
        assert "2025-04-20T10:00:00" in result

    def test_detail_with_status_field(self):
        detail = derive_event_detail(
            _make_event(
                event="pipeline.completed",
                status="ok",
            )
        )
        result = format_event_detail(detail)
        assert "status" in result
        assert "ok" in result

    def test_detail_with_safety_gate_field(self):
        detail = derive_event_detail(
            _make_event(
                event="safety.preflight",
                safety_gate="pass",
            )
        )
        result = format_event_detail(detail)
        assert "safety_gate_result" in result
        assert "pass" in result

    def test_detail_with_shortcuts(self):
        detail = derive_event_detail(
            _make_event(
                event="pipeline.completed",
                case_id="c1",
                job_id="j42",
            )
        )
        result = format_event_detail(detail)
        assert "shortcuts" in result
        assert "case=c1" in result
        assert "job=j42" in result
        assert "pipeline" in result

    def test_detail_with_no_shortcuts(self):
        detail = derive_event_detail(
            SSEEvent(
                event="heartbeat",
                data={"timestamp": "T"},
                event_id=None,
            )
        )
        result = format_event_detail(detail)
        # No shortcuts line when None
        assert "shortcuts:" not in result

    def test_detail_with_long_data_value(self):
        """Long data values should be truncated in the detail output."""
        long_msg = "x" * 300
        detail = derive_event_detail(
            _make_event(
                event="pipeline.completed",
                extra_data={"message": long_msg},
            )
        )
        result = format_event_detail(detail)
        # The message line should be truncated
        msg_line = [l for l in result.splitlines() if "message" in l]
        assert len(msg_line) > 0
        assert "..." in msg_line[0]
        assert len(msg_line[0]) < 400

    def test_detail_with_job_id(self):
        detail = derive_event_detail(
            _make_event(
                event="pipeline.started",
                job_id="j-abc-123",
            )
        )
        result = format_event_detail(detail)
        assert "j-abc-123" in result

    def test_detail_preserves_all_data_fields(self):
        detail = derive_event_detail(
            _make_event(
                event="pipeline.completed",
                extra_data={"step": 3, "total_steps": 10},
            )
        )
        result = format_event_detail(detail)
        assert "step" in result
        assert "3" in result
        assert "total_steps" in result


# ---------------------------------------------------------------------------
# format_event_payload_json
# ---------------------------------------------------------------------------


class TestFormatEventPayloadJson:
    """Test format_event_payload_json rendering."""

    def test_empty_data(self):
        evt = SSEEvent(event="ping", data={}, event_id=None)
        result = format_event_payload_json(evt)
        assert result == "{}"

    def test_simple_data(self):
        evt = _make_event(event="pipeline.completed", case_id="c1", action="pipeline.done")
        result = format_event_payload_json(evt)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["case_id"] == "c1"
        assert parsed["action"] == "pipeline.done"

    def test_nested_data(self):
        evt = SSEEvent(
            event="pipeline.completed",
            data={"case_id": "c1", "nested": {"key": "val"}},
            event_id=None,
        )
        result = format_event_payload_json(evt)
        parsed = json.loads(result)
        assert parsed["nested"]["key"] == "val"

    def test_sorted_keys(self):
        evt = SSEEvent(
            event="pipeline.completed",
            data={"zebra": 1, "alpha": 2},
            event_id=None,
        )
        result = format_event_payload_json(evt)
        # Alpha should come before zebra in the output
        alpha_pos = result.index("alpha")
        zebra_pos = result.index("zebra")
        assert alpha_pos < zebra_pos

    def test_non_serializable_value(self):
        """Non-serializable values should be converted via default=str."""
        evt = SSEEvent(
            event="pipeline.completed",
            data={"case_id": "c1", "binary": b"hello"},
            event_id=None,
        )
        result = format_event_payload_json(evt)
        # Should not crash and should contain the string representation
        assert "c1" in result


# ---------------------------------------------------------------------------
# Integration: derive_event_detail + format_event_detail round-trip
# ---------------------------------------------------------------------------


class TestEventDetailRoundTrip:
    """End-to-end: derive then format a detail dict."""

    def test_round_trip_pipeline_event(self):
        evt = _make_event(
            event="pipeline.completed",
            case_id="c1",
            ts="2025-04-20T10:00:00",
            status="completed",
            job_id="j42",
        )
        detail = derive_event_detail(evt)
        text = format_event_detail(detail)
        assert "pipeline.completed" in text
        assert "c1" in text
        assert "j42" in text
        assert "completed" in text

    def test_round_trip_safety_event(self):
        evt = _make_event(
            event="safety.preflight",
            case_id="c2",
            safety_gate="pass",
        )
        detail = derive_event_detail(evt)
        text = format_event_detail(detail)
        assert "safety.preflight" in text
        assert "safety" in text  # family
        assert "preflight" in text  # action_type
        assert "c2" in text
        assert "pass" in text
        assert "safety_shortcut" in text or "safety" in text

    def test_round_trip_minimal_event(self):
        evt = SSEEvent(event=None, data={}, event_id=None)
        detail = derive_event_detail(evt)
        text = format_event_detail(detail)
        assert "message" in text  # default event name

    def test_derive_shortcuts_round_trip(self):
        """Verify derive_event_shortcuts matches what derive_event_detail produces."""
        evt = _make_event(event="pipeline.completed", case_id="c1", job_id="j1")
        detail = derive_event_detail(evt)
        shortcuts_direct = derive_event_shortcuts(evt)
        assert detail["shortcuts"] == shortcuts_direct
