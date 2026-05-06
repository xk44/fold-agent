"""Filter helpers — derive options and apply filters, pure and testable.

Extracted from event_stream.py for modularity.
"""

from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent

# Canonical status values used across the dashboard
_ALL_STATUSES: list[str] = [
    "running",
    "pending",
    "blocked",
    "failed",
    "timed_out",
    "cancelled",
    "completed",
]

# Sentinel for "show all" in filter selection
FILTER_ALL = "__all__"


def derive_filter_options(
    job_cards: list[dict],
    events: list[SSEEvent],
) -> dict[str, list[str]]:
    """Derive available filter options from current job cards and events.

    Returns a dict with keys ``status``, ``job_type``, and ``case_id``,
    each containing a sorted list of unique values present in the data.
    The ``status`` list always includes the canonical statuses above even
    if none of the current data uses them (so operators can pre-select).

    This is a **pure function** — no Streamlit dependency.
    """
    statuses: set[str] = set()
    job_types: set[str] = set()
    case_ids: set[str] = set()

    for card in job_cards:
        s = card.get("status")
        if s:
            statuses.add(s)
        jt = card.get("job_type")
        if jt:
            job_types.add(jt)
        ci = card.get("case_id")
        if ci:
            case_ids.add(ci)

    for evt in events:
        family = (evt.event or "").split(".", 1)[0]
        if family and family != "unknown":
            job_types.add(family)
        data = evt.data or {}
        ci = data.get("case_id")
        if ci:
            case_ids.add(ci)

    # Always include canonical statuses so the selector isn't empty
    for s in _ALL_STATUSES:
        statuses.add(s)

    return {
        "status": sorted(statuses),
        "job_type": sorted(job_types),
        "case_id": sorted(case_ids),
    }


def apply_filters(
    job_cards: list[dict],
    events: list[SSEEvent],
    *,
    status: str = FILTER_ALL,
    job_type: str = FILTER_ALL,
    case_id: str = FILTER_ALL,
) -> tuple[list[dict], list[SSEEvent]]:
    """Apply filter selections to job cards and events.

    Each filter value uses the ``FILTER_ALL`` sentinel (``"__all__"``) to
    mean "no filter / show everything".  Any other value restricts the
    output to items whose corresponding field matches exactly.

    For event filtering:
    - ``status`` is not applied to events (they lack a top-level status)
    - ``job_type`` matches the event family (the part before ``"."``).
    - ``case_id`` matches ``event.data["case_id"]``.

    For job card filtering:
    - ``status`` matches ``card["status"]``.
    - ``job_type`` matches ``card["job_type"]``.
    - ``case_id`` matches ``card["case_id"]``.

    Returns a tuple of ``(filtered_cards, filtered_events)``.

    This is a **pure function** — no Streamlit dependency.
    """
    filtered_cards = job_cards
    filtered_events = events

    # Filter job cards
    if status != FILTER_ALL:
        filtered_cards = [c for c in filtered_cards if c.get("status") == status]
    if job_type != FILTER_ALL:
        filtered_cards = [c for c in filtered_cards if c.get("job_type") == job_type]
    if case_id != FILTER_ALL:
        filtered_cards = [c for c in filtered_cards if c.get("case_id") == case_id]

    # Filter events (status not applicable to events)
    if job_type != FILTER_ALL or case_id != FILTER_ALL:

        def _event_matches(evt: SSEEvent) -> bool:
            if job_type != FILTER_ALL:
                family = (evt.event or "").split(".", 1)[0]
                if family != job_type:
                    return False
            if case_id != FILTER_ALL:
                ci = (evt.data or {}).get("case_id", "")
                if ci != case_id:
                    return False
            return True

        filtered_events = [e for e in filtered_events if _event_matches(evt=e)]

    return filtered_cards, filtered_events
