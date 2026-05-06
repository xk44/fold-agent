"""Job status card helpers — derive, format, and tabulate operator status.

Extracted from event_stream.py for modularity.  Pure functions, no
Streamlit dependency.
"""

from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent


def derive_job_status_cards(
    events: list[SSEEvent],
    api_jobs: list[dict],
    dedup: bool = False,
) -> list[dict]:
    """Derive operator-oriented job status cards from SSE events and /jobs API data.

    Each card represents a logical grouping of background work:
    - From events: grouped by (event_family, case_id) with latest status and count.
    - From API jobs: one card per job with id, type, status, and error.

    When *dedup* is True, if an event-sourced card and an API-sourced card share
    the same (job_type, case_id), the API-sourced card is kept (more authoritative).

    Returns a list of card dicts suitable for ``format_job_status_cards`` and
    ``build_job_status_table_rows``.
    """
    cards: list[dict] = []

    # --- Event-sourced cards: group events by (family, case_id) ---
    event_groups: dict[tuple[str, str], list[SSEEvent]] = {}
    for evt in events:
        family = (evt.event or "unknown").split(".", 1)[0]
        case_id = evt.data.get("case_id", "") if evt.data else ""
        key = (family, case_id)
        event_groups.setdefault(key, []).append(evt)

    for (family, case_id), group in sorted(event_groups.items()):
        # Sort by timestamp to find the latest status
        latest_evt = group[-1]  # already in insertion order; pick last by convention
        for evt in reversed(group):
            ts = (evt.data or {}).get("timestamp", "")
            if ts:
                latest_evt = evt
                break

        status = ""
        data = latest_evt.data or {}
        # Derive status from event data
        if data.get("status"):
            status = data.get("status")
        elif data.get("safety_gate_result"):
            status = data.get("safety_gate_result")
        else:
            status = (latest_evt.event or "unknown").split(".", 1)[-1]

        cards.append(
            {
                "source": "event",
                "job_id": None,
                "job_type": family,
                "case_id": case_id or None,
                "status": status,
                "latest_status": status,
                "event_count": len(group),
                "error": None,
                "created_at": data.get("timestamp"),
            }
        )

    # --- API-sourced cards: one per background job ---
    for job in api_jobs:
        cards.append(
            {
                "source": "api",
                "job_id": job.get("id"),
                "job_type": job.get("job_type", "unknown"),
                "case_id": job.get("case_id"),
                "status": job.get("status", "unknown"),
                "latest_status": job.get("status", "unknown"),
                "event_count": 0,
                "error": job.get("error"),
                "created_at": job.get("created_at"),
                "attempt": job.get("attempt", 1),
                "max_retries": job.get("max_retries", 0),
            }
        )

    # --- Dedup: prefer API card when (job_type, case_id) collides ---
    if dedup:
        seen: dict[tuple[str, str | None], dict] = {}
        for card in cards:
            key = (card["job_type"], card.get("case_id"))
            if key not in seen:
                seen[key] = card
            else:
                existing = seen[key]
                # Prefer API over event when same key
                if card["source"] == "api" and existing["source"] == "event":
                    seen[key] = card
                # Otherwise keep first (event if both event, api if both api)
        cards = list(seen.values())

    # Sort: running/pending first, then failed, then completed; within groups by created_at desc
    def _sort_key(c: dict) -> tuple:
        status_priority = {"running": 0, "pending": 0, "blocked": 1, "failed": 2, "completed": 3}
        s = c.get("status", "unknown")
        priority = status_priority.get(s, 1)
        ts = c.get("created_at") or ""
        return (priority, ts)

    cards.sort(key=_sort_key)
    return cards


_SEVERITY_MAP: dict[str, str] = {
    "completed": "ok",
    "running": "running",
    "pending": "running",
    "failed": "error",
    "timed_out": "error",
    "cancelled": "info",
    "blocked": "warning",
}


def _severity_for_status(status: str) -> str:
    return _SEVERITY_MAP.get(status, "info")


def format_job_status_cards(cards: list[dict]) -> str:
    """Render job status cards as a human-readable text block.

    Pure function — no Streamlit dependency.
    """
    if not cards:
        return "No job status cards."

    lines: list[str] = [f"Job status cards — {len(cards)} card(s)"]

    for card in cards:
        source = card.get("source", "?")
        job_id = card.get("job_id") or ""
        job_type = card.get("job_type", "unknown")
        case_id = card.get("case_id") or "n/a"
        status = card.get("status", "unknown")
        event_count = card.get("event_count", 0)
        error = card.get("error")
        severity = _severity_for_status(status)

        id_part = f"id={job_id[:8]}" if job_id else "no-id"
        header = (
            f"  [{severity.upper()}] {job_type} | {status} "
            f"| src={source} | {id_part} | case={case_id}"
        )
        lines.append(header)

        if event_count:
            lines.append(f"    events: {event_count}")
        if error:
            lines.append(f"    error: {error}")

    return "\n".join(lines)


def build_job_status_table_rows(cards: list[dict]) -> list[dict]:
    """Convert job status cards into flat row dicts for tabular display.

    Each row includes a derived ``severity`` field based on status.
    If the card has ``retry_eligible`` / ``retry_badge`` fields (from
    :func:`enrich_cards_with_retry_info`), those are carried forward into
    the row dict.
    """
    rows: list[dict] = []
    for card in cards:
        row = {
            "source": card.get("source", ""),
            "job_id": card.get("job_id") or "",
            "job_type": card.get("job_type") or "unknown",
            "case_id": card.get("case_id") or "",
            "status": card.get("status") or "unknown",
            "severity": _severity_for_status(card.get("status", "unknown")),
            "event_count": card.get("event_count", 0),
            "error": card.get("error") or "",
            "created_at": card.get("created_at") or "",
        }
        if "retry_eligible" in card:
            row["retry_eligible"] = card["retry_eligible"]
        if "retry_reason" in card:
            row["retry_reason"] = card["retry_reason"]
        if "retry_badge" in card:
            row["retry_badge"] = card["retry_badge"]
        rows.append(row)
    return rows
