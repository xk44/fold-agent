"""Tests for SSE event stream client — TDD foundation.

These tests verify the SSE parsing, event buffering, and streaming
client logic without requiring a live server or Streamlit runtime.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import httpx

# Module under test
from skills.shared.event_stream_client import (
    EventBuffer,
    SSEEvent,
    parse_sse_lines,
    parse_sse_snapshot,
    EventStreamClient,
    WebSocketEventClient,
    EventClient,
)


# ---------------------------------------------------------------------------
# SSEEvent dataclass
# ---------------------------------------------------------------------------

class TestSSEEvent:
    def test_construct_with_required_fields(self) -> None:
        evt = SSEEvent(event="case.created", data={"case_id": "abc"})
        assert evt.event == "case.created"
        assert evt.data == {"case_id": "abc"}

    def test_construct_with_none_event(self) -> None:
        evt = SSEEvent(event=None, data={"x": 1})
        assert evt.event is None

    def test_equality(self) -> None:
        a = SSEEvent(event="ping", data={"v": 1})
        b = SSEEvent(event="ping", data={"v": 1})
        assert a == b

    def test_inequality(self) -> None:
        a = SSEEvent(event="ping", data={"v": 1})
        b = SSEEvent(event="pong", data={"v": 1})
        assert a != b


# ---------------------------------------------------------------------------
# parse_sse_lines — core SSE wire-format parser
# ---------------------------------------------------------------------------

class TestParseSSELines:
    def test_single_event_with_data(self) -> None:
        lines = [
            "event: case.created",
            'data: {"case_id": "c1", "actor": "api"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event == "case.created"
        assert events[0].data == {"case_id": "c1", "actor": "api"}

    def test_multiple_events(self) -> None:
        lines = [
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
            "event: agent_task.created",
            'data: {"task_id": "t1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[1].event == "agent_task.created"

    def test_data_without_event_yields_none_event(self) -> None:
        lines = [
            'data: {"case_id": "c1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event is None
        assert events[0].data == {"case_id": "c1"}

    def test_multiline_data_concatenated(self) -> None:
        lines = [
            "event: report.generated",
            'data: {"report_id":',
            'data: "r1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].data == {"report_id": "r1"}

    def test_comment_lines_ignored(self) -> None:
        lines = [
            ": this is a comment",
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_empty_input_yields_no_events(self) -> None:
        events = list(parse_sse_lines([]))
        assert events == []

    def test_blank_lines_without_data_ignored(self) -> None:
        lines = [
            "",
            "",
            "event: safety.preflight",
            'data: {"action": "run_pipeline"}',
            "",
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event == "safety.preflight"

    def test_id_field_preserved_on_event(self) -> None:
        lines = [
            "event: case.created",
            "id: evt-42",
            'data: {"case_id": "c1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event_id == "evt-42"

    def test_retry_field_ignored_gracefully(self) -> None:
        lines = [
            "retry: 5000",
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
        ]
        events = list(parse_sse_lines(lines))
        assert len(events) == 1
        assert events[0].event == "case.created"


# ---------------------------------------------------------------------------
# parse_sse_snapshot — convenience parser for full SSE response text
# ---------------------------------------------------------------------------

class TestParseSSESnapshot:
    def test_parse_full_response_text(self) -> None:
        text = (
            "event: case.created\n"
            'data: {"case_id": "c1"}\n'
            "\n"
            "event: agent_task.created\n"
            'data: {"task_id": "t1"}\n'
            "\n"
        )
        events = list(parse_sse_snapshot(text))
        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[1].event == "agent_task.created"

    def test_empty_text_yields_no_events(self) -> None:
        events = list(parse_sse_snapshot(""))
        assert events == []


# ---------------------------------------------------------------------------
# EventBuffer — thread-safe event accumulator
# ---------------------------------------------------------------------------

class TestEventBuffer:
    def test_append_and_latest(self) -> None:
        buf = EventBuffer(max_events=100)
        buf.append(SSEEvent(event="case.created", data={"case_id": "c1"}))
        buf.append(SSEEvent(event="agent_task.created", data={"task_id": "t1"}))
        assert buf.total_count == 2
        latest = buf.latest(2)
        assert latest[0].event == "case.created"
        assert latest[1].event == "agent_task.created"

    def test_max_events_prunes_older(self) -> None:
        buf = EventBuffer(max_events=3)
        for i in range(5):
            buf.append(SSEEvent(event=f"evt.{i}", data={"i": i}))
        assert buf.total_count == 3
        latest = buf.latest(3)
        assert latest[0].data == {"i": 2}
        assert latest[2].data == {"i": 4}

    def test_latest_with_count_exceeding_buffer(self) -> None:
        buf = EventBuffer(max_events=10)
        for i in range(3):
            buf.append(SSEEvent(event=f"evt.{i}", data={"i": i}))
        latest = buf.latest(10)
        assert len(latest) == 3

    def test_clear(self) -> None:
        buf = EventBuffer(max_events=10)
        buf.append(SSEEvent(event="x", data={}))
        assert buf.total_count == 1
        buf.clear()
        assert buf.total_count == 0
        assert buf.latest(10) == []

    def test_thread_safety(self) -> None:
        buf = EventBuffer(max_events=1000)
        errors = []

        def writer(start: int) -> None:
            try:
                for i in range(start, start + 100):
                    buf.append(SSEEvent(event=f"evt.{i}", data={"i": i}))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert buf.total_count == 500

    def test_family_counts(self) -> None:
        buf = EventBuffer(max_events=100)
        buf.append(SSEEvent(event="case.created", data={}))
        buf.append(SSEEvent(event="case.updated", data={}))
        buf.append(SSEEvent(event="agent_task.created", data={}))
        counts = buf.family_counts()
        assert counts["case"] == 2
        assert counts["agent_task"] == 1


# ---------------------------------------------------------------------------
# Helper — fake streaming context manager for SSE mocking
# ---------------------------------------------------------------------------

def _make_stream_cm(raw_lines: list[str]):
    """Create a fake streaming context manager that yields SSE lines via iter_lines()."""
    lines = list(raw_lines)

    class FakeResponse:
        def raise_for_status(self_inner):
            pass

        def iter_lines(self_inner):
            return iter(lines)

    class FakeCM:
        def __enter__(self_inner):
            return FakeResponse()

        def __exit__(self_inner, *args):
            pass

    return FakeCM()


# ---------------------------------------------------------------------------
# EventStreamClient — HTTP SSE streaming with parsing
# ---------------------------------------------------------------------------

class TestEventStreamClient:
    def _make_stream_cm(self, raw_lines: list[str]):
        return _make_stream_cm(raw_lines)

    def test_default_base_url_matches_foldagent_local_api_port(self) -> None:
        client = EventStreamClient()

        assert client._base_url == "http://localhost:8010"

    def test_parse_events_from_stream(self) -> None:
        """Verify EventStreamClient parses a mocked SSE stream correctly."""
        client = EventStreamClient(base_url="http://localhost:8000")

        sse_lines = [
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
            "event: pipeline.completed",
            'data: {"case_id": "c1", "status": "ok"}',
            "",
        ]

        fake_cm = self._make_stream_cm(sse_lines)
        client._client = MagicMock()
        client._client.stream.return_value = fake_cm

        events = list(client.stream_events("/agent/events"))
        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[0].data == {"case_id": "c1"}
        assert events[1].event == "pipeline.completed"
        assert events[1].data == {"case_id": "c1", "status": "ok"}

    def test_stream_events_passes_params(self) -> None:
        """Verify that stream_events passes query params correctly."""
        client = EventStreamClient(base_url="http://localhost:8000")

        fake_cm = self._make_stream_cm([])
        client._client = MagicMock()
        client._client.stream.return_value = fake_cm

        list(client.stream_events("/agent/events", params={"limit": 25}))

        call_args = client._client.stream.call_args
        assert call_args[1]["params"] == {"limit": 25}

    def test_collect_into_buffer(self) -> None:
        """Verify collect_into populates an EventBuffer from SSE stream."""
        client = EventStreamClient(base_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)

        sse_lines = [
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
        ]

        fake_cm = self._make_stream_cm(sse_lines)
        client._client = MagicMock()
        client._client.stream.return_value = fake_cm

        client.collect_into(buf, "/agent/events")
        assert buf.total_count == 1
        assert buf.latest(1)[0].event == "case.created"

    def test_snapshot_parses_one_shot_response(self) -> None:
        """Verify snapshot method parses entire SSE response text."""
        client = EventStreamClient(base_url="http://localhost:8000")

        sse_text = (
            "event: case.created\n"
            'data: {"case_id": "c1"}\n'
            "\n"
            "event: safety.preflight\n"
            'data: {"action": "run_pipeline"}\n'
            "\n"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sse_text
        mock_response.raise_for_status = MagicMock()

        client._client = MagicMock()
        client._client.get.return_value = mock_response

        events = client.snapshot("/agent/events")
        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[1].event == "safety.preflight"

    def test_custom_headers_and_timeout(self) -> None:
        """Verify constructor accepts API key and timeout."""
        client = EventStreamClient(
            base_url="http://localhost:8000",
            api_key="test-key",
            timeout=60.0,
        )
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Accept"] == "text/event-stream"

    def test_headers_without_api_key(self) -> None:
        """Verify headers don't include Authorization when no API key."""
        client = EventStreamClient(base_url="http://localhost:8000")
        headers = client._headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "text/event-stream"


# ---------------------------------------------------------------------------
# WebSocketEventClient — parsing and URL construction
# ---------------------------------------------------------------------------

class TestWebSocketEventClientParseMessage:
    """Tests for WebSocketEventClient._parse_ws_message."""

    def test_parse_event_message(self) -> None:
        raw = json.dumps({"event": "pipeline.completed", "id": "evt-1", "data": {"status": "ok"}})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is not None
        assert result.event == "pipeline.completed"
        assert result.event_id == "evt-1"
        assert result.data == {"status": "ok"}

    def test_parse_event_without_id(self) -> None:
        raw = json.dumps({"event": "case.created", "data": {"case_id": "c1"}})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is not None
        assert result.event == "case.created"
        assert result.event_id is None
        assert result.data == {"case_id": "c1"}

    def test_parse_event_with_null_event(self) -> None:
        raw = json.dumps({"event": None, "data": {"note": "unnamed"}})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is not None
        assert result.event is None

    def test_parse_heartbeat_ping_returns_none(self) -> None:
        raw = json.dumps({"type": "ping"})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is None

    def test_parse_non_json_returns_none(self) -> None:
        result = WebSocketEventClient._parse_ws_message("not json at all")
        assert result is None

    def test_parse_unrecognised_shape_returns_none(self) -> None:
        raw = json.dumps({"type": "unknown", "payload": 42})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is None

    def test_parse_data_as_non_dict_wraps_in_raw(self) -> None:
        raw = json.dumps({"event": "test", "data": "string_payload"})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is not None
        assert result.data == {"raw": "string_payload"}

    def test_parse_data_as_list_wraps_in_raw(self) -> None:
        raw = json.dumps({"event": "test", "data": [1, 2, 3]})
        result = WebSocketEventClient._parse_ws_message(raw)
        assert result is not None
        assert result.data == {"raw": [1, 2, 3]}

    def test_parse_event_matches_sse_event_structure(self) -> None:
        """WS-parsed events should be identical to equivalent SSE-parsed events."""
        ws_raw = json.dumps({"event": "case.created", "id": "e42", "data": {"case_id": "c1"}})
        ws_event = WebSocketEventClient._parse_ws_message(ws_raw)

        sse_lines = [
            "event: case.created",
            "id: e42",
            'data: {"case_id": "c1"}',
            "",
        ]
        sse_event = list(parse_sse_lines(sse_lines))[0]

        assert ws_event is not None
        assert ws_event.event == sse_event.event
        assert ws_event.data == sse_event.data
        assert ws_event.event_id == sse_event.event_id
        # SSEEvent eq comparison (event + data)
        assert ws_event == sse_event


class TestWebSocketEventClientURL:
    """Tests for WebSocketEventClient URL construction."""

    def test_default_base_url_matches_foldagent_local_api_port(self) -> None:
        client = WebSocketEventClient()

        assert client._ws_url_base == "ws://localhost:8010"

    def test_http_url_converts_to_ws(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")
        assert client._ws_url_base == "ws://localhost:8000"

    def test_https_url_converts_to_wss(self) -> None:
        client = WebSocketEventClient(base_url="https://foldagent.example.com")
        assert client._ws_url_base == "wss://foldagent.example.com"

    def test_trailing_slash_stripped(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000/")
        assert client._ws_url_base == "ws://localhost:8000"

    def test_build_url_with_params(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")
        url = client._build_url("/agent/events/ws", params={"heartbeat": "5", "prefix": "case."})
        assert url.startswith("ws://localhost:8000/agent/events/ws?")
        assert "heartbeat=5" in url
        assert "prefix=case." in url

    def test_build_url_with_api_key(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000", api_key="secret")
        url = client._build_url("/agent/events/ws")
        assert "api_key=secret" in url

    def test_build_url_no_query_without_params(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")
        url = client._build_url("/agent/events/ws")
        assert url == "ws://localhost:8000/agent/events/ws"

    def test_build_url_with_prefix_param(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")
        url = client._build_url("/agent/events/ws", params={"prefix": "agent_task.&pipeline."})
        assert "prefix=agent_task.%26pipeline." in url or "prefix=agent_task.&pipeline." in url


class TestWebSocketEventClientStreaming:
    """Tests for WebSocketEventClient.stream_events with a mock websocket."""

    def test_stream_events_yields_parsed_events(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        messages = [
            json.dumps({"event": "pipeline.started", "id": "ws-1", "data": {"timestamp": "t1"}}),
            json.dumps({"event": "pipeline.completed", "id": "ws-2", "data": {"status": "ok"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = list(client.stream_events("/agent/events/ws"))

        assert len(events) == 2
        assert events[0].event == "pipeline.started"
        assert events[0].data == {"timestamp": "t1"}
        assert events[0].event_id == "ws-1"
        assert events[1].event == "pipeline.completed"

    def test_stream_events_skips_heartbeats(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        messages = [
            json.dumps({"type": "ping"}),
            json.dumps({"event": "case.created", "data": {"case_id": "c1"}}),
            json.dumps({"type": "ping"}),
            json.dumps({"event": "case.updated", "data": {"case_id": "c1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = list(client.stream_events("/agent/events/ws"))

        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[1].event == "case.updated"

    def test_stream_events_skips_non_json(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        messages = [
            "not json",
            json.dumps({"event": "case.created", "data": {"case_id": "c1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = list(client.stream_events("/agent/events/ws"))

        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_collect_into_buffer(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)

        messages = [
            json.dumps({"event": "case.created", "id": "ws-1", "data": {"case_id": "c1"}}),
            json.dumps({"event": "pipeline.started", "id": "ws-2", "data": {"timestamp": "t1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            client.collect_into(buf, "/agent/events/ws")

        assert buf.total_count == 2
        latest = buf.latest(2)
        assert latest[0].event == "case.created"
        assert latest[1].event == "pipeline.started"

    def test_collect_into_with_prefix_filter(self) -> None:
        """Verify that prefix parameter is passed to the WS URL."""
        client = WebSocketEventClient(base_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)

        messages = [
            json.dumps({"event": "agent_task.created", "data": {"task_id": "t1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws) as mock_connect:
            client.collect_into(buf, "/agent/events/ws", params={"prefix": "agent_task."})
            # Verify prefix was passed in the URL
            call_url = mock_connect.call_args[0][0]
            assert "prefix=agent_task." in call_url

    def test_stream_events_empty_stream(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter([]))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = list(client.stream_events("/agent/events/ws"))

        assert events == []
    def test_drain_events_stops_on_heartbeat(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.recv = MagicMock(side_effect=[
            json.dumps({"event": "case.created", "id": "ws-1", "data": {"case_id": "c1"}}),
            json.dumps({"type": "ping"}),
        ])

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = client.drain_events("/agent/events/ws", idle_timeout=0.1)

        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_drain_events_stops_on_idle_timeout(self) -> None:
        client = WebSocketEventClient(base_url="http://localhost:8000")

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.recv = MagicMock(side_effect=[TimeoutError])

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = client.drain_events("/agent/events/ws", idle_timeout=0.1)

        assert events == []


# ---------------------------------------------------------------------------
# EventClient — transport-agnostic facade
# ---------------------------------------------------------------------------

class TestEventClientFacade:
    """Tests for the EventClient facade over SSE and WS transports."""

    def test_sse_transport_creates_event_stream_client(self) -> None:
        client = EventClient(base_url="http://localhost:8000", transport="sse")
        assert client.transport == "sse"
        assert isinstance(client._inner, EventStreamClient)

    def test_ws_transport_creates_websocket_client(self) -> None:
        client = EventClient(base_url="http://localhost:8000", transport="ws")
        assert client.transport == "ws"
        assert isinstance(client._inner, WebSocketEventClient)

    def test_invalid_transport_raises(self) -> None:
        with pytest.raises(ValueError, match="transport must be one of"):
            EventClient(base_url="http://localhost:8000", transport="mqtt")

    def test_sse_snapshot_delegates(self) -> None:
        client = EventClient(base_url="http://localhost:8000", transport="sse")

        sse_text = (
            "event: case.created\n"
            'data: {"case_id": "c1"}\n'
            "\n"
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = sse_text
        mock_response.raise_for_status = MagicMock()

        client._inner._client = MagicMock()
        client._inner._client.get.return_value = mock_response

        events = client.snapshot("/agent/events")
        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_sse_stream_delegates(self) -> None:
        """EventClient with SSE transport delegates stream_events to inner client."""
        client = EventClient(base_url="http://localhost:8000", transport="sse")

        sse_lines = [
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
        ]

        # Mock at the inner client level
        inner = client._inner
        mock_cm = _make_stream_cm(sse_lines)
        inner._client = MagicMock()
        inner._client.stream.return_value = mock_cm

        events = list(client.stream_events("/agent/events"))
        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_ws_stream_delegates(self) -> None:
        """EventClient with WS transport delegates stream_events to WebSocketEventClient."""
        client = EventClient(base_url="http://localhost:8000", transport="ws")

        messages = [
            json.dumps({"event": "case.created", "data": {"case_id": "c1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = list(client.stream_events())

        assert len(events) == 1
        assert events[0].event == "case.created"

    def test_ws_collect_into_via_facade(self) -> None:
        """EventClient with WS transport can collect into a buffer."""
        client = EventClient(base_url="http://localhost:8000", transport="ws")
        buf = EventBuffer(max_events=100)

        messages = [
            json.dumps({"event": "case.created", "id": "ws-1", "data": {"case_id": "c1"}}),
            json.dumps({"event": "pipeline.started", "id": "ws-2", "data": {"ts": "t1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            client.collect_into(buf)

        assert buf.total_count == 2
        assert buf.latest(1)[0].event == "pipeline.started"

    def test_ws_snapshot_collects_until_close(self) -> None:
        """EventClient WS snapshot collects events until connection closes."""
        client = EventClient(base_url="http://localhost:8000", transport="ws")

        messages = [
            json.dumps({"event": "case.created", "data": {"case_id": "c1"}}),
            json.dumps({"event": "pipeline.started", "data": {"ts": "t1"}}),
        ]

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter(messages))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws):
            events = client.snapshot()

        assert len(events) == 2
        assert events[0].event == "case.created"
        assert events[1].event == "pipeline.started"

    def test_facade_default_path_ws(self) -> None:
        """EventClient defaults to /agent/events/ws for WS stream_events."""
        client = EventClient(base_url="http://localhost:8000", transport="ws")

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter([]))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws) as mock_connect:
            list(client.stream_events())
            called_url = mock_connect.call_args[0][0]
            assert "/agent/events/ws" in called_url

    def test_facade_default_path_sse(self) -> None:
        """EventClient defaults to /agent/events for SSE stream_events."""
        client = EventClient(base_url="http://localhost:8000", transport="sse")
        inner = client._inner

        mock_cm = _make_stream_cm([])
        inner._client = MagicMock()
        inner._client.stream.return_value = mock_cm

        list(client.stream_events())
        call_args = inner._client.stream.call_args
        assert call_args[0][1] == "/agent/events"

    def test_sse_collect_into_via_facade(self) -> None:
        """EventClient with SSE transport can collect into a buffer."""
        client = EventClient(base_url="http://localhost:8000", transport="sse")
        buf = EventBuffer(max_events=100)

        sse_lines = [
            "event: case.created",
            'data: {"case_id": "c1"}',
            "",
        ]

        inner = client._inner
        mock_cm = _make_stream_cm(sse_lines)
        inner._client = MagicMock()
        inner._client.stream.return_value = mock_cm

        client.collect_into(buf, "/agent/events")
        assert buf.total_count == 1
        assert buf.latest(1)[0].event == "case.created"

    def test_ws_api_key_in_url(self) -> None:
        """WS EventClient passes api_key through to URL params."""
        client = EventClient(base_url="http://localhost:8000", transport="ws", api_key="mykey")

        mock_ws = MagicMock()
        mock_ws.__enter__ = MagicMock(return_value=mock_ws)
        mock_ws.__exit__ = MagicMock(return_value=False)
        mock_ws.__iter__ = MagicMock(return_value=iter([]))

        with patch("skills.shared.event_stream_client.ws_connect", return_value=mock_ws) as mock_connect:
            list(client.stream_events())
            called_url = mock_connect.call_args[0][0]
            assert "api_key=mykey" in called_url

    def test_sse_api_key_in_headers(self) -> None:
        """SSE EventClient passes api_key through to HTTP headers."""
        client = EventClient(base_url="http://localhost:8000", transport="sse", api_key="mykey")
        assert isinstance(client._inner, EventStreamClient)
        headers = client._inner._headers()
        assert headers["Authorization"] == "Bearer mykey"