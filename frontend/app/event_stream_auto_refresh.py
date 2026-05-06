"""Auto-refresh configuration helpers — pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.  The :class:`LiveEventFeed`
class in ``event_stream_live_feed`` uses these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Auto-refresh configuration — pure, fully testable
# ---------------------------------------------------------------------------


@dataclass
class AutoRefreshConfig:
    """Configuration for auto-refresh behaviour.

    Attributes:
        interval_seconds: Seconds between automatic refreshes.
            0 or negative means no auto-refresh.
        enabled: Whether auto-refresh is active.
        mode: How the interval was determined — ``"heuristic"``,
            ``"manual"``, or ``"disabled"``.
    """

    interval_seconds: int = 10
    enabled: bool = True
    mode: str = "heuristic"


# Heuristic interval brackets (seconds)
_FAST_INTERVAL: int = 5  # active work (running/pending jobs)
_MODERATE_INTERVAL: int = 15  # blocked jobs, idle with events
_IDLE_INTERVAL: int = 30  # no active work, no errors
_ERROR_BACKOFF_INTERVAL: int = 20  # connection errors, no active work

_ACTIVE_STATUSES: set[str] = {"running", "pending"}


def compute_auto_refresh_config(
    job_cards: list[dict] | None = None,
    has_connection_error: bool = False,
    total_events: int = 0,
    enabled: bool = True,
    interval_seconds: int | None = None,
) -> AutoRefreshConfig:
    """Compute the auto-refresh configuration from current system state.

    This is a **pure function** — it has no Streamlit dependency and is
    fully testable.  It examines the current dashboard state and returns
    an appropriate refresh interval:

    - **Active jobs** (running/pending) → fast refresh (5 s)
    - **Blocked jobs** → moderate refresh (15 s)
    - **Connection error, no active jobs** → back off (20 s)
    - **Idle (no jobs, no errors)** → slow refresh (30 s)

    An explicit *interval_seconds* overrides the heuristic.

    Args:
        job_cards: Job status card dicts (from derive_job_status_cards).
        has_connection_error: Whether the last poll failed.
        total_events: Total buffered event count (unused in heuristic
            but available for future logic).
        enabled: Master switch — pass ``False`` to disable auto-refresh.
        interval_seconds: Override the heuristic interval.

    Returns:
        An :class:`AutoRefreshConfig` with the computed settings.
    """
    if not enabled:
        return AutoRefreshConfig(interval_seconds=0, enabled=False, mode="disabled")

    if interval_seconds is not None:
        return AutoRefreshConfig(interval_seconds=interval_seconds, enabled=True, mode="manual")

    # Determine if any jobs are actively running or pending
    has_active_jobs = False
    has_blocked_jobs = False
    if job_cards:
        for card in job_cards:
            status = card.get("status", "")
            if status in _ACTIVE_STATUSES:
                has_active_jobs = True
            if status == "blocked":
                has_blocked_jobs = True

    # Priority 1: active jobs → fast
    if has_active_jobs:
        return AutoRefreshConfig(interval_seconds=_FAST_INTERVAL, enabled=True, mode="heuristic")

    # Priority 2: connection error without active jobs → backoff
    if has_connection_error:
        return AutoRefreshConfig(
            interval_seconds=_ERROR_BACKOFF_INTERVAL, enabled=True, mode="heuristic"
        )

    # Priority 3: blocked jobs → moderate
    if has_blocked_jobs:
        return AutoRefreshConfig(
            interval_seconds=_MODERATE_INTERVAL, enabled=True, mode="heuristic"
        )

    # Default: idle
    return AutoRefreshConfig(interval_seconds=_IDLE_INTERVAL, enabled=True, mode="heuristic")


def format_auto_refresh_mode_label(config: AutoRefreshConfig) -> str:
    """Return a human-readable label for the current auto-refresh mode.

    This is a **pure function** — testable without Streamlit.

    Examples::

        >>> format_auto_refresh_mode_label(AutoRefreshConfig(interval_seconds=0, enabled=False, mode="disabled"))
        'Auto-refresh: disabled'
        >>> format_auto_refresh_mode_label(AutoRefreshConfig(interval_seconds=30, enabled=True, mode="heuristic"))
        'Auto-refresh: heuristic (30s)'
        >>> format_auto_refresh_mode_label(AutoRefreshConfig(interval_seconds=42, enabled=True, mode="manual"))
        'Auto-refresh: manual override (42s)'

    Args:
        config: The auto-refresh configuration to label.

    Returns:
        A short operator-facing string describing the current mode.
    """
    if not config.enabled:
        return "Auto-refresh: disabled"
    mode_labels = {
        "heuristic": f"Auto-refresh: heuristic ({config.interval_seconds}s)",
        "manual": f"Auto-refresh: manual override ({config.interval_seconds}s)",
    }
    return mode_labels.get(config.mode, f"Auto-refresh: {config.mode} ({config.interval_seconds}s)")
