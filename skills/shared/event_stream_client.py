"""SSE Event Stream Client for FoldAgent.

Provides SSE wire-format parsing, a thread-safe event buffer, and
HTTP/WebSocket streaming clients that connect to event endpoints
and yield parsed events in real time.

A transport-agnostic facade (:class:`EventClient`) lets consumers
pick SSE or WebSocket without changing their event-handling code.

This module is the live-event foundation — it contains no Streamlit
dependencies and is fully testable in isolation.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

import httpx

from skills.shared.foldagent_client import DEFAULT_BASE_URL

try:
    from websockets.sync.client import connect as ws_connect
except ImportError:  # pragma: no cover — websockets is a required dep in this project
    ws_connect = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSEEvent — structured representation of one SSE event
# ---------------------------------------------------------------------------


@dataclass(eq=True)
class SSEEvent:
    """A single parsed Server-Sent Event."""

    event: str | None
    data: dict
    event_id: str | None = field(default=None, compare=False)


# ---------------------------------------------------------------------------
# parse_sse_lines — core wire-format parser
# ---------------------------------------------------------------------------


def parse_sse_lines(lines: list[str]) -> Generator[SSEEvent, None, None]:
    """Parse SSE wire-format lines and yield :class:`SSEEvent` objects.

    Follows the SSE specification:
    - ``event: <name>`` sets the event type for the current message.
    - ``data: <payload>`` appends to the data buffer (multiple ``data:``
      lines are joined with newlines before JSON parsing).
    - ``id: <value>`` sets the last event ID.
    - ``retry: <ms>`` is acknowledged but not stored.
    - Lines beginning with ``:`` are comments and ignored.
    - An empty line dispatches the current message.
    """
    current_event: str | None = None
    data_fragments: list[str] = []
    current_id: str | None = None

    for line in lines:
        stripped = line.rstrip("\n").rstrip("\r")

        # Comment line — ignore
        if stripped.startswith(":"):
            continue

        # Empty line — dispatch current message
        if stripped == "":
            if data_fragments:
                raw_data = "\n".join(data_fragments)
                try:
                    payload = json.loads(raw_data)
                except (json.JSONDecodeError, ValueError):
                    payload = {"raw": raw_data}
                yield SSEEvent(event=current_event, data=payload, event_id=current_id)
            # Reset per-message state
            current_event = None
            data_fragments = []
            current_id = None
            continue

        # Field parsing
        if stripped.startswith("event: "):
            current_event = stripped[len("event: ") :]
        elif stripped.startswith("data: "):
            data_fragments.append(stripped[len("data: ") :])
        elif stripped.startswith("data:"):
            # "data:" with no space — treat as empty data fragment
            data_fragments.append(stripped[len("data:") :])
        elif stripped.startswith("id: "):
            current_id = stripped[len("id: ") :]
        elif stripped.startswith("id:"):
            current_id = stripped[len("id:") :].strip()
        elif stripped.startswith("retry: "):
            pass  # acknowledged but not stored


def parse_sse_snapshot(text: str) -> list[SSEEvent]:
    """Parse a complete SSE response text (snapshot) into events.

    Convenience wrapper around :func:`parse_sse_lines` for one-shot
    HTTP GET responses.
    """
    return list(parse_sse_lines(text.splitlines()))


# ---------------------------------------------------------------------------
# EventBuffer — thread-safe event accumulator
# ---------------------------------------------------------------------------


class EventBuffer:
    """Thread-safe, bounded buffer that accumulates :class:`SSEEvent` objects.

    When the buffer exceeds *max_events*, the oldest events are pruned.
    """

    def __init__(self, max_events: int = 200) -> None:
        self._max = max_events
        self._events: deque[SSEEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._events)

    def append(self, event: SSEEvent) -> None:
        with self._lock:
            self._events.append(event)

    def latest(self, n: int = 20) -> list[SSEEvent]:
        """Return the *n* most recent events (oldest first)."""
        with self._lock:
            items = list(self._events)
            return items[-n:] if n < len(items) else items

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def family_counts(self) -> dict[str, int]:
        """Count events by their family (prefix before first dot)."""
        counts: dict[str, int] = {}
        with self._lock:
            for evt in self._events:
                name = evt.event or "unknown"
                family = name.split(".", 1)[0]
                counts[family] = counts.get(family, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# EventStreamClient — HTTP SSE streaming with parsing
# ---------------------------------------------------------------------------


class EventStreamClient:
    """HTTP client that connects to SSE endpoints and yields parsed events.

    Two consumption modes:
    - **Streaming**: :meth:`stream_events` opens a long-lived HTTP stream
      and yields events as they arrive (generator).
    - **Snapshot**: :meth:`snapshot` does a one-shot GET and parses the
      complete response text.
    - **Collect**: :meth:`collect_into` streams events into an
      :class:`EventBuffer` (blocking call).

    Args:
        base_url: API base URL (e.g. ``http://localhost:8010``).
        api_key: Optional bearer-token API key.
        timeout: HTTP connection/read timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def stream_events(
        self,
        path: str,
        params: dict | None = None,
    ) -> Generator[SSEEvent, None, None]:
        """Open an SSE stream and yield parsed events live.

        This is a **blocking generator** — iterate it to consume events
        as they arrive.  Break out of the iteration to close the stream.
        """
        with self._client.stream(
            "GET",
            path,
            params=params,
            headers=self._headers(),
        ) as response:
            response.raise_for_status()
            current_event: str | None = None
            data_fragments: list[str] = []
            current_id: str | None = None

            for line in response.iter_lines():
                if line.startswith(":"):
                    continue
                if line == "":
                    if data_fragments:
                        raw_data = "\n".join(data_fragments)
                        try:
                            payload = json.loads(raw_data)
                        except (json.JSONDecodeError, ValueError):
                            payload = {"raw": raw_data}
                        yield SSEEvent(
                            event=current_event,
                            data=payload,
                            event_id=current_id,
                        )
                    current_event = None
                    data_fragments = []
                    current_id = None
                    continue
                if line.startswith("event: "):
                    current_event = line[len("event: ") :]
                elif line.startswith("data: "):
                    data_fragments.append(line[len("data: ") :])
                elif line.startswith("data:"):
                    data_fragments.append(line[len("data:") :])
                elif line.startswith("id: "):
                    current_id = line[len("id: ") :]
                elif line.startswith("id:"):
                    current_id = line[len("id:") :].strip()
                elif line.startswith("retry: "):
                    pass

    def collect_into(
        self,
        buffer: EventBuffer,
        path: str,
        params: dict | None = None,
    ) -> None:
        """Stream events from *path* and append each into *buffer*.

        Blocks until the stream ends (server closes connection) or an
        error occurs.
        """
        for event in self.stream_events(path, params=params):
            buffer.append(event)

    def snapshot(
        self,
        path: str,
        params: dict | None = None,
    ) -> list[SSEEvent]:
        """One-shot GET that parses the full SSE response text."""
        response = self._client.get(path, params=params, headers=self._headers())
        response.raise_for_status()
        return parse_sse_snapshot(response.text)


# ---------------------------------------------------------------------------
# WebSocketEventClient — WebSocket transport that yields SSEEvent objects
# ---------------------------------------------------------------------------


class WebSocketEventClient:
    """WebSocket client that connects to a FoldAgent event endpoint and
    yields parsed :class:`SSEEvent` objects.

    The server sends JSON messages of the form::

        {"event": "...", "id": "...", "data": {...}}

    Heartbeat messages ``{"type": "ping"}`` are silently ignored by
    :meth:`stream_events` and treated as an idle boundary by
    :meth:`drain_events`.

    Two consumption modes:
    - **Streaming**: :meth:`stream_events` opens a WebSocket connection
      and yields events as they arrive (blocking generator).
    - **Collect**: :meth:`collect_into` streams events into an
      :class:`EventBuffer` (blocking call).

    Args:
        base_url: API base URL (e.g. ``http://localhost:8010``).
            The scheme is converted to ``ws://`` or ``wss://`` automatically.
        api_key: Optional bearer-token API key (sent as a query parameter
            because WebSocket does not support custom headers during
            the handshake in all clients).
        ping_interval: Interval in seconds between automatic keep-alive
            pings sent by the underlying websocket library.
        close_timeout: Timeout in seconds for the WebSocket close handshake.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        ping_interval: float = 20.0,
        close_timeout: float = 10.0,
    ) -> None:
        # Derive WS URL from HTTP URL
        ws_base = base_url.rstrip("/")
        if ws_base.startswith("https://"):
            ws_base = "wss://" + ws_base[len("https://") :]
        elif ws_base.startswith("http://"):
            ws_base = "ws://" + ws_base[len("http://") :]
        self._ws_url_base = ws_base
        self._api_key = api_key
        self._ping_interval = ping_interval
        self._close_timeout = close_timeout

    def _build_url(self, path: str, params: dict | None = None) -> str:
        """Build the full WebSocket URL with optional query parameters."""
        url = f"{self._ws_url_base}{path}"
        query: list[tuple[str, str]] = []
        if self._api_key:
            query.append(("api_key", self._api_key))
        if params:
            for k, v in params.items():
                query.append((str(k), str(v)))
        if query:
            url += "?" + urlencode(query)
        return url

    @staticmethod
    def _parse_ws_message(raw: str) -> SSEEvent | None:
        """Parse a single WebSocket JSON message into an SSEEvent.

        Returns ``None`` for heartbeat pings (``{"type": "ping"}``) and
        for unrecognised message shapes.
        """
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.debug("WS: ignoring non-JSON message")
            return None

        # Heartbeat ping — skip
        if isinstance(msg, dict) and msg.get("type") == "ping":
            return None

        # Event message: {"event": ..., "id": ..., "data": {...}}
        if isinstance(msg, dict) and "event" in msg and "data" in msg:
            return SSEEvent(
                event=msg.get("event"),
                data=msg["data"] if isinstance(msg["data"], dict) else {"raw": msg["data"]},
                event_id=msg.get("id"),
            )

        logger.debug(
            "WS: ignoring unrecognised message shape: %s",
            list(msg.keys()) if isinstance(msg, dict) else type(msg).__name__,
        )
        return None

    def stream_events(
        self,
        path: str = "/agent/events/ws",
        params: dict | None = None,
    ) -> Generator[SSEEvent, None, None]:
        """Open a WebSocket connection and yield parsed events live.

        This is a **blocking generator** — iterate it to consume events
        as they arrive.  Break out of the iteration to close the
        connection.
        """
        if ws_connect is None:
            raise ImportError("websockets package is required for WebSocket transport")

        url = self._build_url(path, params)

        with ws_connect(
            url,
            ping_interval=self._ping_interval,
            close_timeout=self._close_timeout,
        ) as ws:
            for raw in ws:
                event = self._parse_ws_message(raw)
                if event is not None:
                    yield event

    def drain_events(
        self,
        path: str = "/agent/events/ws",
        params: dict | None = None,
        *,
        max_events: int = 25,
        idle_timeout: float = 1.5,
    ) -> list[SSEEvent]:
        """Collect a bounded batch of WS events until idle or limit reached.

        This is useful for snapshot-like UI polling over a live WebSocket.
        The method stops when:
        - ``max_events`` have been collected,
        - the socket is idle for ``idle_timeout`` seconds, or
        - the server sends a heartbeat ping.
        """
        if ws_connect is None:
            raise ImportError("websockets package is required for WebSocket transport")

        url = self._build_url(path, params)
        events: list[SSEEvent] = []
        with ws_connect(
            url,
            ping_interval=self._ping_interval,
            close_timeout=self._close_timeout,
        ) as ws:
            while len(events) < max_events:
                try:
                    raw = ws.recv(timeout=idle_timeout)
                except TimeoutError:
                    break
                try:
                    message = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    logger.debug("WS: ignoring non-JSON message during drain")
                    continue
                if isinstance(message, dict) and message.get("type") == "ping":
                    break
                event = self._parse_ws_message(raw)
                if event is not None:
                    events.append(event)
        return events

    def collect_into(
        self,
        buffer: EventBuffer,
        path: str = "/agent/events/ws",
        params: dict | None = None,
    ) -> None:
        """Stream events from the WebSocket endpoint into *buffer*.

        Blocks until the connection closes or an error occurs.
        """
        for event in self.stream_events(path, params=params):
            buffer.append(event)


# ---------------------------------------------------------------------------
# EventClient — transport-agnostic facade
# ---------------------------------------------------------------------------


class EventClient:
    """Transport-agnostic event client that delegates to SSE or WebSocket.

    Provides a uniform interface for fetching and streaming events
    regardless of the underlying transport.  Consumers choose the
    transport at construction time and then use a single API surface.

    Args:
        base_url: API base URL (e.g. ``http://localhost:8010``).
        transport: ``"sse"`` (default) or ``"ws"``.
        api_key: Optional bearer-token API key.
        timeout: HTTP connection/read timeout in seconds (SSE only).
        ping_interval: WebSocket keep-alive ping interval in seconds
            (WS only).
        close_timeout: WebSocket close handshake timeout in seconds
            (WS only).

    Example::

        # SSE mode — one-shot snapshot
        client = EventClient(base_url="http://localhost:8010")
        events = client.snapshot("/agent/events", params={"limit": 10})

        # WS mode — live streaming
        client = EventClient(base_url="http://localhost:8010", transport="ws")
        for event in client.stream_events():
            print(event)
    """

    _TRANSPORTS = ("sse", "ws")

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: Literal["sse", "ws"] = "sse",
        api_key: str | None = None,
        timeout: float = 30.0,
        ping_interval: float = 20.0,
        close_timeout: float = 10.0,
    ) -> None:
        if transport not in self._TRANSPORTS:
            raise ValueError(f"transport must be one of {self._TRANSPORTS}, got {transport!r}")
        self._transport = transport
        if transport == "sse":
            self._inner: EventStreamClient | WebSocketEventClient = EventStreamClient(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
        else:
            self._inner = WebSocketEventClient(
                base_url=base_url,
                api_key=api_key,
                ping_interval=ping_interval,
                close_timeout=close_timeout,
            )

    @property
    def transport(self) -> str:
        """The active transport name (``'sse'`` or ``'ws'``)."""
        return self._transport

    def stream_events(
        self,
        path: str | None = None,
        params: dict | None = None,
    ) -> Generator[SSEEvent, None, None]:
        """Open a connection and yield parsed events live.

        For SSE transport, *path* defaults to ``None`` (must be provided).
        For WS transport, *path* defaults to ``/agent/events/ws``.
        """
        # Determine the default path based on transport
        if path is None:
            path = "/agent/events/ws" if self._transport == "ws" else "/agent/events"
        yield from self._inner.stream_events(path, params=params)

    def collect_into(
        self,
        buffer: EventBuffer,
        path: str | None = None,
        params: dict | None = None,
    ) -> None:
        """Stream events into *buffer* until the connection closes.

        For SSE transport, *path* defaults to ``None`` (must be provided).
        For WS transport, *path* defaults to ``/agent/events/ws``.
        """
        if path is None:
            path = "/agent/events/ws" if self._transport == "ws" else "/agent/events"
        self._inner.collect_into(buffer, path, params=params)

    def snapshot(
        self,
        path: str = "/agent/events",
        params: dict | None = None,
    ) -> list[SSEEvent]:
        """One-shot fetch: SSE snapshot or WS collect-then-close.

        For the SSE transport this directly calls
        :meth:`EventStreamClient.snapshot`.  For the WS transport it
        opens a connection, collects whatever events arrive until the
        server closes the connection, and returns them as a list.

        .. note::

            WebSocket is inherently a streaming protocol and has no
            native snapshot mode.  The WS snapshot collects events until
            the server closes the connection — use
            :meth:`stream_events` for real-time consumption instead.
        """
        if self._transport == "sse":
            return self._inner.snapshot(path, params=params)  # type: ignore[union-attr]

        # WS: collect events until the connection closes
        buf = EventBuffer(max_events=10_000)
        self.collect_into(buf, path=path, params=params)
        return buf.latest(buf.total_count)
