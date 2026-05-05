"""Operator timeline — concise synthesized timeline from job detail, lifecycle,
structure linkback, and terminal state. Pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.
"""
from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent

from frontend.app.event_stream_job_detail import (
    derive_job_detail,
    _format_payload_preview,
)
from frontend.app.event_stream_job_status import _severity_for_status


# ---------------------------------------------------------------------------
# Timeline row types
# ---------------------------------------------------------------------------

_TL_CREATED = "created"
_TL_STATUS = "status"
_TL_LIFECYCLE = "lifecycle"
_TL_LINKBACK = "linkback"
_TL_RETRY = "retry"
_TL_RESULT = "result"
_TL_ERROR = "error"

# Concise labels for timeline entry types
_TL_TYPE_LABELS: dict[str, str] = {
    _TL_CREATED: "Created",
    _TL_STATUS: "Status",
    _TL_LIFECYCLE: "Event",
    _TL_LINKBACK: "Structure",
    _TL_RETRY: "Retry",
    _TL_RESULT: "Result",
    _TL_ERROR: "Error",
}


def derive_operator_timeline(
    job_card: dict,
    api_job: dict | None = None,
    events: list[SSEEvent] | None = None,
) -> list[dict]:
    """Derive a concise operator timeline from job detail, lifecycle events,
    structure linkback, and terminal state.

    Returns a chronologically-sorted list of timeline row dicts, each with:
      - ``type``: one of the ``_TL_*`` constants (created, status, lifecycle,
        linkback, retry, result, error)
      - ``timestamp``: ISO timestamp or empty string
      - ``label``: concise human-readable one-liner
      - ``detail``: optional extra detail string (empty string if none)
      - ``severity``: one of ``"ok"``, ``"running"``, ``"warning"``, ``"error"``,
        ``"info"``

    The timeline synthesizes:
    1. Job creation (from card/api_job)
    2. Initial/pending status transitions (from lifecycle events)
    3. Retry attempts (attempt > 1)
    4. Structure linkback milestone (when applicable)
    5. Result / error terminal state

    This is a **pure function** — no Streamlit dependency.
    """
    detail = derive_job_detail(job_card, api_job=api_job, events=events)
    timeline: list[dict] = []

    # --- 1. Job creation ---
    created_at = detail.get("created_at") or ""
    job_type = detail.get("job_type", "unknown")
    job_id = detail.get("job_id") or "?"
    short_id = job_id[:8] if len(job_id) >= 8 else job_id
    case_id = detail.get("case_id") or ""
    timeline.append({
        "type": _TL_CREATED,
        "timestamp": created_at,
        "label": f"{job_type} {short_id} created",
        "detail": f"case={case_id}" if case_id else "",
        "severity": "info",
    })

    # --- 2. Status + lifecycle events (merged into timeline) ---
    lifecycle_events = detail.get("lifecycle_events") or []
    for entry in lifecycle_events:
        ts = entry.get("timestamp", "")
        action = entry.get("action", "")
        ev_detail = entry.get("detail", "")
        # Infer severity from the event's status field or its action name
        entry_status = entry.get("status", "")
        if entry_status:
            ev_severity = _severity_for_status(entry_status)
        else:
            ev_severity = _severity_from_event_action(action)
        # Skip creation-duplicate events (the 'created' row already covers it)
        if action.endswith(".created") or action == "job_created":
            continue
        timeline.append({
            "type": _TL_LIFECYCLE,
            "timestamp": ts,
            "label": action,
            "detail": ev_detail,
            "severity": ev_severity,
        })

    # --- 3. Retry milestone ---
    attempt = detail.get("attempt")
    max_retries = detail.get("max_retries")
    if attempt is not None and attempt > 1:
        limit = (max_retries + 1) if max_retries is not None else "?"
        timeline.append({
            "type": _TL_RETRY,
            "timestamp": "",
            "label": f"Attempt {attempt}/{limit}",
            "detail": f"max_retries={max_retries}" if max_retries is not None else "",
            "severity": "warning",
        })

    # --- 4. Structure linkback milestone ---
    linkback = detail.get("structure_linkback")
    if linkback:
        lbl = linkback.get("label", "View structure job")
        link_parts: list[str] = []
        if linkback.get("case_id"):
            link_parts.append(f"case={linkback['case_id']}")
        if linkback.get("structure_job_id"):
            link_parts.append(f"struct={linkback['structure_job_id'][:8]}")
        timeline.append({
            "type": _TL_LINKBACK,
            "timestamp": "",
            "label": lbl,
            "detail": " | ".join(link_parts),
            "severity": "info",
        })

    # --- 5. Result / error terminal state ---
    error = detail.get("error")
    result = detail.get("result")
    status = detail.get("status", "unknown")
    if error:
        error_str = str(error)
        if len(error_str) > 200:
            error_str = error_str[:197] + "..."
        timeline.append({
            "type": _TL_ERROR,
            "timestamp": "",
            "label": f"Failed: {status}",
            "detail": error_str,
            "severity": "error",
        })
    elif result and isinstance(result, dict):
        result_status = result.get("status", "")
        result_preview = _format_payload_preview(result, max_len=140)
        timeline.append({
            "type": _TL_RESULT,
            "timestamp": "",
            "label": f"Result: {result_status or status}",
            "detail": result_preview,
            "severity": "ok" if result_status in ("completed", "ok") else "info",
        })

    # Sort by timestamp (empty strings sort last to keep order stable for
    # synthetic entries without timestamps)
    def _sort_key(row: dict) -> str:
        ts = row.get("timestamp", "")
        # Empty timestamps go at the end
        return ts if ts else "zzz"

    timeline.sort(key=_sort_key)

    return timeline


def _severity_from_event_action(action: str) -> str:
    """Infer a severity from an event action string."""
    action_lower = action.lower()
    if any(kw in action_lower for kw in ("fail", "error", "timeout", "abort")):
        return "error"
    if any(kw in action_lower for kw in ("block", "retry", "pending")):
        return "warning"
    if any(kw in action_lower for kw in ("complet", "success", "ok", "pass")):
        return "ok"
    if any(kw in action_lower for kw in ("run", "start", "submit", "dispatch")):
        return "running"
    return "info"


def format_operator_timeline(timeline: list[dict]) -> str:
    """Render an operator timeline as a concise, operator-oriented text block.

    Each row is formatted as::

        [SEVERITY] TIMESTAMP  TYPE  label  |  detail

    Pure function — no Streamlit dependency.
    """
    if not timeline:
        return "No timeline entries."

    lines = [f"Operator timeline — {len(timeline)} entry/entries"]
    for row in timeline:
        severity = row.get("severity", "info").upper()
        ts = row.get("timestamp", "") or "—"
        rtype = row.get("type", "info")
        type_label = _TL_TYPE_LABELS.get(rtype, rtype)
        label = row.get("label", "")
        detail = row.get("detail", "")
        line = f"  [{severity:>7}] {ts}  {type_label:<10} {label}"
        if detail:
            line += f"  |  {detail}"
        lines.append(line)

    return "\n".join(lines)


def build_operator_timeline_rows(timeline: list[dict]) -> list[dict]:
    """Convert an operator timeline into flat row dicts for tabular display.

    Each row includes: type, type_label, timestamp, label, detail, severity.
    """
    rows: list[dict] = []
    for row in timeline:
        rtype = row.get("type", "info")
        rows.append({
            "type": rtype,
            "type_label": _TL_TYPE_LABELS.get(rtype, rtype),
            "timestamp": row.get("timestamp", ""),
            "label": row.get("label", ""),
            "detail": row.get("detail", ""),
            "severity": row.get("severity", "info"),
        })
    return rows