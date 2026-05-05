"""Pure formatting functions for SSE event feeds — fully testable without Streamlit.

Extracted from event_stream.py for modularity.
"""
from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent


def format_sse_event_summary(events: list[SSEEvent]) -> dict[str, int | dict[str, int]]:
    """Compute summary statistics from a list of SSE events."""
    family_counts: dict[str, int] = {}
    for evt in events:
        family = (evt.event or "unknown").split(".", 1)[0]
        family_counts[family] = family_counts.get(family, 0) + 1
    return {"total_events": len(events), "event_family_counts": family_counts}


def format_sse_event_feed(events: list[SSEEvent], limit: int = 10) -> str:
    """Render a human-readable text preview of recent SSE events.

    This is a pure function — no Streamlit dependency.
    """
    if not events:
        return "No live events."

    recent = events[-limit:] if len(events) > limit else events
    summary = format_sse_event_summary(events)

    family_lines = ", ".join(
        f"{k}:{v}" for k, v in sorted(summary["event_family_counts"].items())
    ) or "none"

    lines = [
        f"Live event feed — {summary['total_events']} events",
        f"Family counts: {family_lines}",
        "",
    ]

    for evt in recent:
        event_name = evt.event or "message"
        data = evt.data or {}
        ts = data.get("timestamp", "n/a")
        case_id = data.get("case_id", "n/a")
        action = data.get("action", event_name)
        lines.append(f"  [{ts}] {action} (case={case_id})")

        # Show key detail fields
        detail_keys = [k for k in ("status", "safety_gate_result", "details") if k in data and data[k]]
        if detail_keys:
            detail_parts = [f"{k}={data[k]}" for k in detail_keys]
            lines.append(f"    {' | '.join(detail_parts)}")

    return "\n".join(lines)


def format_sse_event_table_rows(events: list[SSEEvent]) -> list[dict]:
    """Convert SSE events to a flat list of row dicts for tabular display."""
    rows = []
    for evt in events:
        data = evt.data or {}
        rows.append({
            "event": evt.event or "message",
            "timestamp": data.get("timestamp", ""),
            "case_id": data.get("case_id", ""),
            "action": data.get("action", evt.event or ""),
            "actor": data.get("actor", ""),
            "safety_gate_result": data.get("safety_gate_result", ""),
        })
    return rows