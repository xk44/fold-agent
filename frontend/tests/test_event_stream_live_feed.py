"""Tests for LiveEventFeed websocket-preferred / SSE-fallback behaviour.

These tests verify that:

1. LiveEventFeed uses WebSocket transport by default.
2. When WS is preferred and succeeds, events are delivered.
3. When WS fails, LiveEventFeed silently falls back to SSE snapshot.
4. When SSE also fails, the dashboard doesn't crash (graceful degradation).
5. Transport metadata is tracked in session state.
6. Explicit ``transport="sse"`` bypasses WS entirely.
7. Event deduplication works across both transports.
8. The ``_merge_events`` helper correctly merges and deduplicates.
9. The ``_build_ws_params`` and ``_build_sse_params`` helpers work.
10. ``_active_transport`` reflects what was actually used.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream_live_feed import LiveEventFeed
from skills.shared.event_stream_client import EventBuffer, SSEEvent

# ---------------------------------------------------------------------------
# Helpers — fake Streamlit and fake clients
# ---------------------------------------------------------------------------


def _make_fake_streamlit() -> SimpleNamespace:
    """Create a minimal fake streamlit with mutable session_state."""
    return SimpleNamespace(session_state={})


class _FakeSSEClient:
    """Fake EventStreamClient that returns canned responses on snapshot()."""

    def __init__(self, responses: list[list[SSEEvent]]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict | None]] = []

    def snapshot(self, path: str, params: dict | None = None):
        self.calls.append((path, params))
        if self._responses:
            return self._responses.pop(0)
        return []


class _FakeWSClient:
    """Fake WebSocketEventClient that yields canned events then raises or stops."""

    def __init__(self, responses: list[list[SSEEvent]] | None = None, fail: bool = False):
        self._responses = responses or []
        self._fail = fail
        self.calls: list[tuple[str, dict | None]] = []

    def stream_events(self, path: str = "/agent/events/ws", params: dict | None = None):
        self.calls.append((path, params))
        if self._fail:
            raise OSError("WebSocket connection refused")
        # Yield all events from the first canned response then stop
        if self._responses:
            for evt in self._responses[0]:
                yield evt


# ---------------------------------------------------------------------------
# Tests: parameter builders
# ---------------------------------------------------------------------------


class TestBuildParams:
    def test_default_api_url_matches_foldagent_local_api_port(self) -> None:
        feed = LiveEventFeed()

        assert feed.api_url == "http://localhost:8010"

    def test_build_ws_params_with_prefixes(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000", event_prefixes=("pipeline.", "case."))
        params = feed._build_ws_params()
        assert params == {"heartbeat": 1.0, "prefix": "pipeline.,case."}

    def test_build_ws_params_without_prefixes(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        params = feed._build_ws_params()
        assert params == {"heartbeat": 1.0}

    def test_build_sse_params_with_cursor(self) -> None:
        feed = LiveEventFeed(
            api_url="http://localhost:8000", poll_limit=25, event_prefixes=("pipeline.",)
        )
        params = feed._build_sse_params(last_event_id="evt-42")
        assert params == {
            "limit": 25,
            "prefix": "pipeline.",
            "after_event_id": "evt-42",
        }

    def test_build_sse_params_without_cursor(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=10)
        params = feed._build_sse_params()
        assert params == {"limit": 10}


# ---------------------------------------------------------------------------
# Tests: _merge_events helper
# ---------------------------------------------------------------------------


class TestMergeEvents:
    def test_merge_new_events_into_empty_buffer(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)
        events = [
            SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="e1"),
            SSEEvent(event="pipeline.completed", data={"ts": "t2"}, event_id="e2"),
        ]
        new_id = feed._merge_events(buf, events, None)
        assert buf.total_count == 2
        assert new_id == "e2"

    def test_merge_deduplicates_by_event_id(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)
        first = [SSEEvent(event="x", data={"ts": "t1"}, event_id="e1")]
        feed._merge_events(buf, first, None)
        # Re-add the same event_id — should be deduplicated
        second = [SSEEvent(event="x", data={"ts": "t1"}, event_id="e1")]
        new_id = feed._merge_events(buf, second, "e1")
        assert buf.total_count == 1
        assert new_id == "e1"

    def test_merge_deduplicates_by_composite_key_when_no_id(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)
        events1 = [SSEEvent(event="case.created", data={"timestamp": "t1"})]
        feed._merge_events(buf, events1, None)
        # Same composite key — should be deduplicated
        events2 = [SSEEvent(event="case.created", data={"timestamp": "t1"})]
        feed._merge_events(buf, events2, None)
        assert buf.total_count == 1

    def test_merge_updates_last_event_id(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)
        events = [
            SSEEvent(event="a", data={}, event_id="id-1"),
            SSEEvent(event="b", data={}, event_id="id-2"),
            SSEEvent(event="c", data={}, event_id="id-3"),
        ]
        new_id = feed._merge_events(buf, events, "id-0")
        assert new_id == "id-3"

    def test_merge_preserves_old_last_event_id_when_no_new_ids(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        buf = EventBuffer(max_events=100)
        events = [SSEEvent(event="x", data={"ts": "t1"})]  # no event_id
        new_id = feed._merge_events(buf, events, "old-id")
        assert new_id == "old-id"


# ---------------------------------------------------------------------------
# Tests: WS-preferred poll with SSE fallback
# ---------------------------------------------------------------------------


class TestPollWsPreferred:
    def test_ws_preferred_transport_default(self) -> None:
        """LiveEventFeed defaults to WS transport preference."""
        feed = LiveEventFeed(api_url="http://localhost:8000")
        assert feed._transport_preference == "ws"

    def test_explicit_sse_transport(self) -> None:
        """Explicit SSE transport preference."""
        feed = LiveEventFeed(api_url="http://localhost:8000", transport="sse")
        assert feed._transport_preference == "sse"

    def test_first_poll_bootstraps_with_sse_even_when_ws_is_preferred(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=10)
        fake_ws = _FakeWSClient(
            responses=[[SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="ws-1")]]
        )
        feed._ws_client = fake_ws

        fake_sse = _FakeSSEClient(
            responses=[[SSEEvent(event="case.created", data={"ts": "t0"}, event_id="sse-1")]]
        )
        feed._sse_client = fake_sse

        buf = feed.poll()
        assert buf.total_count == 1
        assert buf.latest(1)[0].event_id == "sse-1"
        assert not fake_ws.calls
        assert fake_sse.calls
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta["transport"] == "sse"

    def test_poll_uses_ws_after_cursor_exists_and_ws_succeeds(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=10)
        fake_ws = _FakeWSClient(
            responses=[[SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="ws-1")]]
        )
        feed._ws_client = fake_ws
        fake_sse = _FakeSSEClient(responses=[])
        feed._sse_client = fake_sse

        buf = feed.poll()
        assert buf.total_count == 1
        assert buf.latest(1)[0].event_id == "ws-1"
        assert fake_ws.calls
        assert not fake_sse.calls
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta["transport"] == "ws"

    def test_poll_falls_back_to_sse_when_ws_fails(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=5)
        fake_ws = _FakeWSClient(fail=True)
        feed._ws_client = fake_ws

        sse_events = [
            SSEEvent(event="case.created", data={"ts": "t1"}, event_id="sse-1"),
        ]
        fake_sse = _FakeSSEClient(responses=[sse_events])
        feed._sse_client = fake_sse

        buf = feed.poll()
        assert buf.total_count == 1
        assert buf.latest(1)[0].event_id == "sse-1"
        assert fake_ws.calls
        assert fake_sse.calls
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta["transport"] == "sse"

    def test_poll_sse_only_when_transport_is_sse(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", transport="sse", poll_limit=5)
        # SSE responses
        sse_events = [
            SSEEvent(event="case.created", data={"ts": "t1"}, event_id="sse-1"),
        ]
        fake_sse = _FakeSSEClient(responses=[sse_events])
        feed._sse_client = fake_sse

        buf = feed.poll()
        assert buf.total_count == 1
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta["transport"] == "sse"
        # WS client was never created
        assert feed._ws_client is None

    def test_poll_graceful_degradation_when_both_fail(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=5)
        # WS fails
        fake_ws = _FakeWSClient(fail=True)
        feed._ws_client = fake_ws

        # SSE also fails
        fake_sse = _FakeSSEClient(responses=[])
        fake_sse.snapshot = MagicMock(side_effect=ConnectionError("SSE server unreachable"))
        feed._sse_client = fake_sse

        buf = feed.poll()
        # Buffer should exist but be empty (no crash)
        assert buf.total_count == 0
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta.get("error") is True

    def test_poll_tracks_transport_in_active_transport_attribute(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=5)
        fake_ws = _FakeWSClient(responses=[[SSEEvent(event="x", data={}, event_id="w1")]])
        feed._ws_client = fake_ws
        feed._sse_client = _FakeSSEClient(responses=[])

        feed.poll()
        assert feed._active_transport == "ws"

    def test_poll_ws_fallback_sets_active_transport_to_sse(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=5)
        fake_ws = _FakeWSClient(fail=True)
        feed._ws_client = fake_ws
        feed._sse_client = _FakeSSEClient(responses=[[SSEEvent(event="y", data={}, event_id="s1")]])

        feed.poll()
        assert feed._active_transport == "sse"


# ---------------------------------------------------------------------------
# Tests: incremental cursor tracking (preserved from original)
# ---------------------------------------------------------------------------


class TestPollCursorTracking:
    def test_poll_tracks_last_event_id_with_ws(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(
            api_url="http://localhost:8000", poll_limit=5, event_prefixes=("pipeline.",)
        )
        first_events = [
            SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="evt-1"),
            SSEEvent(event="pipeline.completed", data={"ts": "t2"}, event_id="evt-2"),
        ]
        fake_ws = _FakeWSClient(responses=[first_events])
        feed._ws_client = fake_ws

        buf = feed.poll()
        assert buf.total_count == 2
        meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
        assert meta["last_event_id"] == "evt-2"
        assert meta["transport"] == "ws"

    def test_poll_deduplicates_across_ws_then_sse_fallback(self, monkeypatch) -> None:
        """When WS fails on second poll and SSE returns overlapping events,
        deduplication should prevent duplicates."""
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000", poll_limit=5)

        first_events = [
            SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="evt-1"),
        ]
        fake_ws = _FakeWSClient(responses=[first_events])
        feed._ws_client = fake_ws
        feed._sse_client = _FakeSSEClient(responses=[])

        feed.poll()
        assert fake_streamlit.session_state[feed.SESSION_KEY].total_count == 1

        fake_ws._fail = True
        overlapping_sse = [
            SSEEvent(event="pipeline.started", data={"ts": "t1"}, event_id="evt-1"),
            SSEEvent(event="pipeline.completed", data={"ts": "t2"}, event_id="evt-2"),
        ]
        feed._sse_client = _FakeSSEClient(responses=[overlapping_sse])

        feed.poll()
        buf = fake_streamlit.session_state[feed.SESSION_KEY]
        assert buf.total_count == 2
        assert [e.event_id for e in buf.latest(10)] == ["evt-1", "evt-2"]

    def test_poll_sse_cursor_incremental(self, monkeypatch) -> None:
        """Original SSE-only cursor behaviour still works with transport=sse."""
        fake_streamlit = _make_fake_streamlit()
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(
            api_url="http://localhost:8000",
            poll_limit=5,
            event_prefixes=("pipeline.",),
            transport="sse",
        )
        feed._sse_client = _FakeSSEClient(
            responses=[
                [
                    SSEEvent(event="pipeline.started", data={"timestamp": "t1"}, event_id="evt-1"),
                    SSEEvent(
                        event="pipeline.completed", data={"timestamp": "t2"}, event_id="evt-2"
                    ),
                ],
                [
                    SSEEvent(event="pipeline.failed", data={"timestamp": "t3"}, event_id="evt-3"),
                ],
            ]
        )

        first_buf = feed.poll()
        assert first_buf.total_count == 2
        assert fake_streamlit.session_state[feed.SESSION_META_KEY]["last_event_id"] == "evt-2"

        second_buf = feed.poll()
        assert second_buf.total_count == 3
        assert fake_streamlit.session_state[feed.SESSION_META_KEY]["last_event_id"] == "evt-3"

    def test_poll_sse_dedup_when_server_replays(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(
            api_url="http://localhost:8000",
            poll_limit=5,
            transport="sse",
        )
        # With the new code, SSE-only uses self._sse_client
        feed._sse_client = _FakeSSEClient(
            responses=[
                [SSEEvent(event="case.created", data={"timestamp": "t1"}, event_id="evt-1")],
                [SSEEvent(event="case.created", data={"timestamp": "t1"}, event_id="evt-1")],
            ]
        )

        feed.poll()
        buf = feed.poll()
        assert buf.total_count == 1


# ---------------------------------------------------------------------------
# Tests: lazy WS client initialization
# ---------------------------------------------------------------------------


class TestLazyWsClient:
    def test_ws_client_created_lazily(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        assert feed._ws_client is None
        client = feed._get_ws_client()
        assert client is not None
        # Second call returns same instance
        assert feed._get_ws_client() is client


# ---------------------------------------------------------------------------
# Tests: _active_transport state across polls
# ---------------------------------------------------------------------------


class TestActiveTransportTracking:
    def test_active_transport_starts_as_sse(self) -> None:
        feed = LiveEventFeed(api_url="http://localhost:8000")
        assert feed._active_transport == "sse"

    def test_active_transport_updates_after_successful_ws_poll(self, monkeypatch) -> None:
        fake_streamlit = _make_fake_streamlit()
        fake_streamlit.session_state[LiveEventFeed.SESSION_META_KEY] = {"last_event_id": "evt-0"}
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        feed = LiveEventFeed(api_url="http://localhost:8000")
        fake_ws = _FakeWSClient(responses=[[SSEEvent(event="test", data={}, event_id="t1")]])
        feed._ws_client = fake_ws
        feed._sse_client = _FakeSSEClient(responses=[])

        feed.poll()
        assert feed._active_transport == "ws"


# ---------------------------------------------------------------------------
# Legacy _FakeEventClient (kept for backward-compat test above)
# ---------------------------------------------------------------------------


class _FakeEventClient:
    """Replicates the original _FakeEventClient used in existing tests.
    This fake only supports .snapshot() for SSE transport."""

    def __init__(self, responses: list[list[SSEEvent]]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict | None]] = []

    def snapshot(self, path: str, params: dict | None = None):
        self.calls.append((path, params))
        if self._responses:
            return self._responses.pop(0)
        return []
