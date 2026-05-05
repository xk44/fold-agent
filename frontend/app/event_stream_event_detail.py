"""Event detail drilldown helpers — pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.
"""
from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent


def derive_event_detail(event: SSEEvent) -> dict:
    """Derive a detailed drilldown dict for a selected SSE event.

    Returns a dict with:
      - event: the event name
      - event_id: the event ID (if any)
      - timestamp: from event data
      - action: from event data (falls back to event name)
      - case_id: from event data (or None)
      - job_id: from event data (or None)
      - family: event family (part before first dot)
      - action_type: event action after dot (or full event)
      - data: the full event data dict
      - summary: a human-readable one-line summary
      - shortcuts: related shortcuts (from derive_event_shortcuts)

    This is a **pure function** — no Streamlit dependency.
    """
    data = event.data or {}
    event_name = event.event or "message"
    family = event_name.split(".", 1)[0] if "." in event_name else event_name
    action_type = event_name.split(".", 1)[-1] if "." in event_name else event_name

    # Build summary
    action = data.get("action", event_name)
    case_id = data.get("case_id", "")
    status = data.get("status", "")
    safety_gate = data.get("safety_gate_result", "")

    summary_parts = [f"[{data.get('timestamp', 'n/a')}] {action}"]
    if case_id:
        summary_parts.append(f"case={case_id}")
    if status:
        summary_parts.append(f"status={status}")
    if safety_gate:
        summary_parts.append(f"safety_gate={safety_gate}")
    summary = " | ".join(summary_parts) if len(summary_parts) > 1 else summary_parts[0]

    shortcuts = derive_event_shortcuts(event)

    return {
        "event": event_name,
        "event_id": event.event_id,
        "timestamp": data.get("timestamp", ""),
        "action": action,
        "case_id": case_id or None,
        "job_id": data.get("job_id") or None,
        "family": family,
        "action_type": action_type,
        "data": data,
        "summary": summary,
        "shortcuts": shortcuts,
    }


def derive_event_shortcuts(event: SSEEvent) -> dict | None:
    """Derive shortcut metadata for navigating from an event to related views.

    Returns a dict with (when derivable):
      - case_id: if the event has a case_id
      - job_id: if the event has a job_id
      - job_type_hint: inferred from event family
      - case_shortcut: True if case_id is present
      - job_shortcut: True if job_id is present
      - pipeline_shortcut: True if event family is 'pipeline'
      - safety_shortcut: True if event family is 'safety'

    Returns None if no shortcuts can be derived (no case_id, no job_id,
    no recognizable family).
    """
    data = event.data or {}
    event_name = event.event or ""
    family = event_name.split(".", 1)[0] if "." in event_name else event_name

    case_id = data.get("case_id") or None
    job_id = data.get("job_id") or None

    has_case = case_id is not None
    has_job = job_id is not None
    has_pipeline = family == "pipeline"
    has_safety = family == "safety"

    if not (has_case or has_job or has_pipeline or has_safety):
        return None

    shortcuts: dict = {}
    if case_id:
        shortcuts["case_id"] = case_id
        shortcuts["case_shortcut"] = True
    if job_id:
        shortcuts["job_id"] = job_id
        shortcuts["job_shortcut"] = True
    if family:
        shortcuts["job_type_hint"] = family
        shortcuts["pipeline_shortcut"] = has_pipeline
        shortcuts["safety_shortcut"] = has_safety

    return shortcuts


def format_event_detail(detail: dict) -> str:
    """Render an event detail dict as a compact, operator-oriented text block.

    Pure function — no Streamlit dependency.
    """
    if not detail:
        return "No event detail available."

    event_name = detail.get("event", "?")
    timestamp = detail.get("timestamp", "n/a")
    action = detail.get("action", "?")
    family = detail.get("family", "?")
    action_type = detail.get("action_type", "?")
    case_id = detail.get("case_id") or "n/a"
    job_id = detail.get("job_id") or "n/a"

    lines = [
        f"Event detail — {event_name}",
        f"  timestamp:   {timestamp}",
        f"  action:       {action}",
        f"  family:       {family}",
        f"  action_type:  {action_type}",
        f"  case:         {case_id}",
        f"  job:          {job_id}",
    ]

    # Summary
    summary = detail.get("summary", "")
    if summary:
        lines.append(f"  summary:      {summary}")

    # Shortcuts
    shortcuts = detail.get("shortcuts") or {}
    if shortcuts:
        shortcut_parts = []
        if shortcuts.get("case_shortcut"):
            shortcut_parts.append(f"case={shortcuts.get('case_id', '?')}")
        if shortcuts.get("job_shortcut"):
            shortcut_parts.append(f"job={shortcuts.get('job_id', '?')}")
        if shortcuts.get("pipeline_shortcut"):
            shortcut_parts.append("pipeline")
        if shortcuts.get("safety_shortcut"):
            shortcut_parts.append("safety")
        if shortcut_parts:
            lines.append(f"  shortcuts:    {' | '.join(shortcut_parts)}")

    # Key data fields (select most useful ones for readability)
    data = detail.get("data") or {}
    detail_keys = [k for k in (
        "status", "safety_gate_result", "actor", "details",
        "message", "error", "step", "total_steps", "completed_steps",
    ) if k in data and data[k]]
    for k in detail_keys:
        val = data[k]
        # Truncate long values
        val_str = str(val)
        if len(val_str) > 200:
            val_str = val_str[:197] + "..."
        lines.append(f"  {k + ':':<14}{val_str}")

    return "\n".join(lines)


def format_event_payload_json(event: SSEEvent) -> str:
    """Format the raw event data payload as pretty-printed JSON for display.

    Pure function — no Streamlit dependency.
    """
    import json

    data = event.data or {}
    if not data:
        return "{}"
    try:
        return json.dumps(data, indent=2, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(data)