"""LiveEventFeed — Streamlit-compatible event accumulator and renderer.

Extracted from event_stream.py for modularity.  This module depends on
:mod:`event_stream_auto_refresh` and :mod:`event_stream_format`.

**Transport preference**: By default the feed now prefers WebSocket when
available and falls back to SSE snapshot polling if the WebSocket connection
fails or is unavailable.  The active transport is tracked in session-state
metadata so the dashboard can display it.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from skills.shared.event_stream_client import (
    EventBuffer,
    EventStreamClient,
    SSEEvent,
    WebSocketEventClient,
)
from skills.shared.neovax_client import DEFAULT_BASE_URL

from frontend.app.event_stream_auto_refresh import (
    AutoRefreshConfig,
    compute_auto_refresh_config,
)
from frontend.app.event_stream_format import (
    format_sse_event_feed,
    format_sse_event_table_rows,
)

logger = logging.getLogger(__name__)


class LiveEventFeed:
    """Manages live event accumulation for Streamlit dashboards.

    Usage in Streamlit::

        feed = LiveEventFeed(api_url="http://localhost:8010")
        feed.poll()                      # fetch latest events
        feed.render(st_container)        # render into a container

    The feed stores events in ``st.session_state`` so they persist across
    reruns.  By default it prefers the WebSocket transport and falls back
    to SSE snapshot polling if WebSocket is unavailable.

    Transport preference can be set explicitly via *transport*:

    - ``"ws"`` — WebSocket preferred, SSE fallback (default)
    - ``"sse"`` — SSE snapshot polling only (original behaviour)
    """

    SESSION_KEY = "neovax_live_events"
    SESSION_META_KEY = "neovax_live_events_meta"

    def __init__(
        self,
        api_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        max_buffer: int = 200,
        poll_limit: int = 25,
        event_prefixes: tuple[str, ...] | None = None,
        transport: Literal["ws", "sse"] = "ws",
        ws_heartbeat: float = 1.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.max_buffer = max_buffer
        self.poll_limit = poll_limit
        self.event_prefixes = event_prefixes
        self._transport_preference = transport
        self._ws_heartbeat = ws_heartbeat
        # SSE client is always available as fallback
        self._sse_client = EventStreamClient(
            base_url=self.api_url,
            api_key=self.api_key,
        )
        # Lazy-initialised: created on first ws poll attempt
        self._ws_client: WebSocketEventClient | None = None
        # Track actual transport in use (mutable per-poll)
        self._active_transport: str = "sse"  # safe default

    # ------------------------------------------------------------------
    # Transport helpers — thin glue
    # ------------------------------------------------------------------

    def _build_ws_params(self) -> dict[str, object]:
        """Build query params for the WebSocket path."""
        params: dict[str, object] = {"heartbeat": self._ws_heartbeat}
        if self.event_prefixes:
            params["prefix"] = ",".join(self.event_prefixes)
        return params

    def _build_sse_params(self, last_event_id: str | None = None) -> dict[str, object]:
        """Build query params for the SSE snapshot path."""
        params: dict[str, object] = {"limit": self.poll_limit}
        if self.event_prefixes:
            params["prefix"] = ",".join(self.event_prefixes)
        if last_event_id:
            params["after_event_id"] = last_event_id
        return params

    def _get_ws_client(self) -> WebSocketEventClient:
        """Lazily create the WebSocket client."""
        if self._ws_client is None:
            self._ws_client = WebSocketEventClient(
                base_url=self.api_url,
                api_key=self.api_key,
            )
        return self._ws_client

    def _poll_via_ws(self, params: dict[str, object]) -> list[SSEEvent]:
        """Attempt a short WebSocket live drain.

        This is intentionally not a historical snapshot: the current WS backend
        is live-only. We use it to pick up fresh events quickly, then rely on
        SSE snapshot/cursor mode for bootstrap and replay safety.
        """
        ws_client = self._get_ws_client()
        try:
            if hasattr(ws_client, "drain_events"):
                return ws_client.drain_events(
                    path="/agent/events/ws",
                    params=params,
                    max_events=self.poll_limit,
                    idle_timeout=max(self._ws_heartbeat + 0.25, 1.25),
                )

            buf = EventBuffer(max_events=self.max_buffer)
            for event in ws_client.stream_events(
                path="/agent/events/ws",
                params=params,
            ):
                buf.append(event)
                if buf.total_count >= self.poll_limit:
                    break
            return buf.latest(buf.total_count)
        except Exception as exc:
            logger.debug("WS poll failed, will fall back to SSE: %s", exc)
            raise

    def _poll_via_sse(
        self, params: dict[str, object], last_event_id: str | None = None
    ) -> list[SSEEvent]:
        """SSE snapshot poll — the original polling method."""
        return self._sse_client.snapshot("/agent/events", params=params)

    def _merge_events(
        self,
        buf: EventBuffer,
        new_events: list[SSEEvent],
        last_event_id: str | None,
    ) -> str | None:
        """Merge *new_events* into *buf*, deduplicating.

        Returns the new ``last_event_id`` (or the previous one if no
        events had an ID).
        """
        existing_keys: set[object] = set()
        for existing in buf.latest(buf.total_count):
            key = existing.event_id or (existing.event, existing.data.get("timestamp"))
            existing_keys.add(key)

        new_last_id = last_event_id
        for evt in new_events:
            key = evt.event_id or (evt.event, evt.data.get("timestamp"))
            if key not in existing_keys:
                buf.append(evt)
                existing_keys.add(key)
            if evt.event_id:
                new_last_id = evt.event_id
        return new_last_id

    # ------------------------------------------------------------------
    # Session-state helpers
    # ------------------------------------------------------------------

    def _get_buffer(self) -> EventBuffer:
        """Retrieve or create the EventBuffer from session state."""
        import streamlit as st

        if self.SESSION_KEY not in st.session_state:
            st.session_state[self.SESSION_KEY] = EventBuffer(max_events=self.max_buffer)
        buf = st.session_state[self.SESSION_KEY]
        if not isinstance(buf, EventBuffer):
            st.session_state[self.SESSION_KEY] = EventBuffer(max_events=self.max_buffer)
            buf = st.session_state[self.SESSION_KEY]
        return buf

    def poll(self) -> EventBuffer:
        """Fetch latest events via the preferred transport and merge into the buffer.

        Strategy:
        - bootstrap with SSE snapshot when there is no cursor yet
        - once bootstrapped, prefer a short WebSocket live drain for freshness
        - always fall back to SSE incremental replay on WS failure or when WS
          yields no events, so historical correctness is preserved
        """
        import streamlit as st

        buf = self._get_buffer()
        meta = st.session_state.get(self.SESSION_META_KEY, {})
        last_event_id: str | None = meta.get("last_event_id")

        events: list[SSEEvent] = []
        used_transport = "sse"

        if self._transport_preference == "ws" and last_event_id is not None:
            ws_params = self._build_ws_params()
            try:
                events = self._poll_via_ws(ws_params)
                if events:
                    used_transport = "ws"
            except Exception:
                logger.info("WebSocket poll failed; falling back to SSE snapshot")
                events = []

        if self._transport_preference == "sse" or last_event_id is None or not events:
            sse_params = self._build_sse_params(last_event_id)
            try:
                sse_events = self._poll_via_sse(sse_params, last_event_id)
                if sse_events:
                    events = sse_events
                    used_transport = "sse"
                elif last_event_id is None or self._transport_preference == "sse":
                    used_transport = "sse"
            except Exception:
                if not events:
                    st.session_state[self.SESSION_META_KEY] = {
                        "last_poll": datetime.now().isoformat(),
                        "fetched_count": 0,
                        "error": True,
                        "last_event_id": last_event_id,
                        "prefix": self.event_prefixes and ",".join(self.event_prefixes),
                        "transport": used_transport,
                    }
                    return buf

        new_last_id = self._merge_events(buf, events, last_event_id)
        self._active_transport = used_transport

        st.session_state[self.SESSION_META_KEY] = {
            "last_poll": datetime.now().isoformat(),
            "fetched_count": len(events),
            "last_event_id": new_last_id,
            "prefix": self.event_prefixes and ",".join(self.event_prefixes),
            "transport": used_transport,
        }
        return buf

    # ------------------------------------------------------------------
    # Auto-refresh configuration
    # ------------------------------------------------------------------

    def get_auto_refresh_config(
        self,
        job_cards: list[dict] | None = None,
        enabled: bool = True,
        interval_seconds: int | None = None,
    ) -> AutoRefreshConfig:
        """Compute auto-refresh config from the current event buffer state.

        Convenience method that examines the buffer's session state metadata
        (e.g. connection errors) and delegates to the pure
        :func:`compute_auto_refresh_config` helper.

        Args:
            job_cards: Job status cards for heuristic interval selection.
            enabled: Master switch — ``False`` disables auto-refresh.
            interval_seconds: Override the heuristic interval.

        Returns:
            An :class:`AutoRefreshConfig` ready for :func:`render_auto_refresh`.
        """
        import streamlit as st

        meta = st.session_state.get(self.SESSION_META_KEY, {})
        has_error = bool(meta.get("error"))
        buf = self._get_buffer()
        total_events = buf.total_count

        return compute_auto_refresh_config(
            job_cards=job_cards,
            has_connection_error=has_error,
            total_events=total_events,
            enabled=enabled,
            interval_seconds=interval_seconds,
        )

    def auto_refresh(
        self,
        config: AutoRefreshConfig | None = None,
        *,
        job_cards: list[dict] | None = None,
        enabled: bool = True,
        interval_seconds: int | None = None,
        key: str = "live_feed_autorefresh",
    ) -> AutoRefreshConfig:
        """Poll for new events and render auto-refresh logic.

        This is the primary entry point for auto-refresh mode.  It:

        1. Computes an :class:`AutoRefreshConfig` from current state (unless
           one is provided).
        2. Calls :meth:`poll` to fetch latest events.
        3. Renders the auto-refresh timer so the page will rerun automatically.

        Usage::

            feed = LiveEventFeed(api_url=api_url)
            config = feed.auto_refresh(job_cards=job_cards)
            feed.render(live_container)

        Args:
            config: Pre-computed config (overrides heuristic). If ``None``,
                the config is computed from *job_cards*, *enabled*, and
                *interval_seconds*.
            job_cards: Job status cards for heuristic interval selection.
            enabled: Master switch — ``False`` disables auto-refresh.
            interval_seconds: Override the heuristic interval.
            key: Unique Streamlit component key for the auto-refresh HTML.

        Returns:
            The :class:`AutoRefreshConfig` used (useful for display).
        """
        import streamlit as st

        if config is None:
            config = self.get_auto_refresh_config(
                job_cards=job_cards,
                enabled=enabled,
                interval_seconds=interval_seconds,
            )

        # Always poll — auto-refresh means we should fetch on every rerun
        self.poll()

        # Render the auto-refresh timer if enabled
        if config.enabled and config.interval_seconds > 0:
            render_auto_refresh(config.interval_seconds, key=key)
            st.session_state[f"{key}_interval"] = config.interval_seconds
        else:
            st.session_state[f"{key}_interval"] = 0

        # Always store mode so render() can display it
        st.session_state[f"{key}_mode"] = config.mode

        return config

    def render(self, container=None, show_count: int = 10) -> list:
        """Render the live event feed into a Streamlit container.

        Args:
            container: A Streamlit container (e.g. ``st.container()``).
                If ``None``, renders directly.
            show_count: Number of recent events to show.

        Returns:
            List of recent SSEEvents for further processing.
        """
        import streamlit as st

        target = container or st
        buf = self._get_buffer()
        events = buf.latest(show_count)

        meta = st.session_state.get(self.SESSION_META_KEY, {})
        family_counts = buf.family_counts()
        family_line = ", ".join(f"{k}:{v}" for k, v in sorted(family_counts.items())) or "none"

        auto_interval = st.session_state.get("live_feed_autorefresh_interval")
        auto_mode = st.session_state.get("live_feed_autorefresh_mode")

        target.subheader("Live event feed")
        status_parts = [f"Buffered: {buf.total_count} events", f"Families: {family_line}"]

        # Show active transport
        transport_label = meta.get("transport", "sse")
        status_parts.append(f"Transport: {transport_label.upper()}")

        if auto_mode == "disabled":
            status_parts.append("Auto-refresh: disabled")
        elif auto_interval and auto_mode:
            mode_label = {
                "heuristic": f"Auto-refresh: heuristic ({auto_interval}s)",
                "manual": f"Auto-refresh: manual override ({auto_interval}s)",
            }.get(auto_mode, f"Auto-refresh: {auto_mode} ({auto_interval}s)")
            status_parts.append(mode_label)
        elif auto_interval:
            status_parts.append(f"Auto-refresh: {auto_interval}s")
        target.caption(" · ".join(status_parts))

        if meta.get("error"):
            target.warning("Last poll encountered a connection error.")
        elif meta.get("last_poll"):
            target.caption(f"Last poll: {meta['last_poll']} ({meta.get('fetched_count', 0)} fetched)")

        if events:
            target.code(format_sse_event_feed(events, limit=show_count))
            with target.expander("Event table"):
                rows = format_sse_event_table_rows(events)
                target.dataframe(rows, width="stretch", hide_index=True)
        else:
            target.info("No live events received yet. Auto-refresh will populate events when available.")

        return events


# ---------------------------------------------------------------------------
# Auto-refresh renderer — thin Streamlit bridge
# ---------------------------------------------------------------------------

def render_auto_refresh(interval_seconds: int, key: str = "auto_refresh") -> None:
    """Render a lightweight auto-refresh timer using a hidden HTML component.

    This injects a small JavaScript snippet that triggers a Streamlit page
    rerun after *interval_seconds*.  It works by sending a ``streamlit:setConfig``
    message via ``postMessage`` which Streamlit's frontend reacts to by
    scheduling a rerun.

    The approach is equivalent to the ``streamlit-autorefresh`` package but
    requires no external dependency.

    Args:
        interval_seconds: Seconds between automatic page reruns.
            Must be > 0; values <= 0 are silently ignored.
        key: Unique key for the Streamlit HTML component (prevents
            duplicate-component warnings when multiple auto-refresh widgets
            appear on the same page).

    .. note::

        This function has a **Streamlit dependency** and should only be called
        from within a Streamlit app.  It is intentionally thin — all
        interval-selection logic lives in the pure
        :func:`compute_auto_refresh_config` helper.
    """
    if interval_seconds <= 0:
        return

    import streamlit as st

    # The JS opens an iframe at height=0 (invisible) and sets a timer that
    # triggers a page reload via window.parent.location.reload() which causes
    # Streamlit to re-execute the entire script, effectively refreshing data.
    # We use location.reload() because it is the most reliable cross-version
    # mechanism — it works with all Streamlit versions >= 1.0.
    interval_ms = interval_seconds * 1000
    st.iframe(
        f"""
        <script>
        setTimeout(function() {{
            window.parent.location.reload();
        }}, {interval_ms});
        </script>
        """,
        height=1,
    )
