from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from backend.tests.test_event_stream_redis_live_smoke import (
    RUN_FLAG,
    _ComposeRedis,
    _UvicornServer,
    _publish_remote,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if os.getenv(RUN_FLAG) != "1":
    pytest.skip(
        f"set {RUN_FLAG}=1 to run live Redis client smoke tests",
        allow_module_level=True,
    )

sys.path.insert(0, str(PROJECT_ROOT))

from frontend.app.event_stream_live_feed import LiveEventFeed
from skills.shared.event_stream_client import EventClient, EventStreamClient, WebSocketEventClient


def _publish_remote_later(redis_url: str, event_name: str, payload: dict, delay: float = 0.5) -> Thread:
    def _runner() -> None:
        time.sleep(delay)
        _publish_remote(redis_url, "neovax:events", event_name, payload)

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    return thread


def _make_fake_streamlit() -> SimpleNamespace:
    return SimpleNamespace(session_state={})


def test_live_websocket_event_client_receives_remote_redis_event() -> None:
    with _ComposeRedis() as redis_url:
        with _UvicornServer(redis_url) as base_url:
            publisher = _publish_remote_later(redis_url, "smoke.client_ws", {"marker": "ws-client"})
            client = WebSocketEventClient(base_url=base_url)
            stream = client.stream_events("/agent/events/ws", params={"prefix": "smoke.", "heartbeat": 1})
            try:
                event = next(stream)
            finally:
                stream.close()
            publisher.join(timeout=5)
            assert event.event == "smoke.client_ws"
            assert event.data == {"marker": "ws-client"}
            assert event.event_id is None


def test_live_sse_event_stream_client_receives_remote_redis_event() -> None:
    with _ComposeRedis() as redis_url:
        with _UvicornServer(redis_url) as base_url:
            publisher = _publish_remote_later(redis_url, "smoke.client_sse", {"marker": "sse-client"})
            client = EventStreamClient(base_url=base_url, timeout=20.0)
            stream = client.stream_events(
                "/agent/events",
                params={"follow": True, "prefix": "smoke.", "limit": 1},
            )
            try:
                event = next(stream)
            finally:
                stream.close()
            publisher.join(timeout=5)
            assert event.event == "smoke.client_sse"
            assert event.data == {"marker": "sse-client"}
            assert event.event_id is None


def test_live_event_client_ws_facade_receives_remote_redis_event() -> None:
    with _ComposeRedis() as redis_url:
        with _UvicornServer(redis_url) as base_url:
            publisher = _publish_remote_later(redis_url, "smoke.client_facade", {"marker": "ws-facade"})
            client = EventClient(base_url=base_url, transport="ws")
            stream = client.stream_events(params={"prefix": "smoke.", "heartbeat": 1})
            try:
                event = next(stream)
            finally:
                stream.close()
            publisher.join(timeout=5)
            assert event.event == "smoke.client_facade"
            assert event.data == {"marker": "ws-facade"}


def test_live_event_feed_bootstraps_sse_then_uses_ws_against_redis_server(monkeypatch) -> None:
    fake_streamlit = _make_fake_streamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    with _ComposeRedis() as redis_url:
        with _UvicornServer(redis_url) as base_url:
            response = httpx.post(
                f"{base_url}/cases",
                json={"species": "demo", "diagnosis_summary": "live feed smoke"},
                timeout=20.0,
            )
            assert response.status_code == 201

            feed = LiveEventFeed(
                api_url=base_url,
                poll_limit=5,
                event_prefixes=("case.", "smoke."),
                ws_heartbeat=1.0,
            )

            first_buf = feed.poll()
            assert first_buf.total_count >= 1
            first_meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
            assert first_meta["transport"] == "sse"
            assert first_meta.get("last_event_id")

            publisher = _publish_remote_later(redis_url, "smoke.live_feed", {"marker": "live-feed"})
            second_buf = feed.poll()
            publisher.join(timeout=5)

            events = second_buf.latest(second_buf.total_count)
            assert any(evt.event == "smoke.live_feed" and evt.data == {"marker": "live-feed"} for evt in events)
            second_meta = fake_streamlit.session_state[feed.SESSION_META_KEY]
            assert second_meta["transport"] == "ws"
