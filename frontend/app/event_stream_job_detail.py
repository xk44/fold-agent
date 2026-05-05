"""Job-detail drilldown, linkback, and diagnosis helpers — pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.  This module depends on
:mod:`event_stream_job_status` (for ``_severity_for_status``) and
:mod:`event_stream_job_retry` (for ``is_retry_eligible``).
"""
from __future__ import annotations

from skills.shared.event_stream_client import SSEEvent

from frontend.app.event_stream_job_status import _severity_for_status


# ---------------------------------------------------------------------------
# Structure-job / AlphaFold linkback helpers — pure, no Streamlit dependency
# ---------------------------------------------------------------------------

# Job types that map to the structure-job surface
_STRUCTURE_JOB_TYPES = frozenset({"alphafold_backend", "alphafold_structure"})


def derive_structure_linkback(
    job_card: dict,
    api_job: dict | None = None,
) -> dict | None:
    """Derive a linkback from a background job detail to a structure-job surface.

    When a background job is an AlphaFold/structure job (or has a result that
    includes structure-job metadata), this helper returns a dict with enough
    information for the dashboard to navigate the user to the relevant
    structure-job explorer.

    Returns ``None`` if no linkback can be derived.

    The returned dict, when present, contains at minimum:
      - ``structure_job_id``: ID of the related StructureJob, if available
      - ``case_id``: case ID to scope the structure-job explorer
      - ``label``: human-readable action text (e.g. "View AlphaFold structure")
      - ``surface``: hint for which dashboard section to focus (always
        ``"structure_job_explorer"`` for now)
    """
    detail = api_job or job_card
    job_type = detail.get("job_type", "")
    case_id = detail.get("case_id") or job_card.get("case_id")

    # Only derive for structure-related job types
    if job_type not in _STRUCTURE_JOB_TYPES:
        return None

    # Try to extract structure_job_id from several possible sources:
    # 1. Explicit structure_job_id in result (future-proof)
    result = detail.get("result") or {}
    structure_job_id = result.get("structure_job_id")

    # 2. From result.structure.job_id or result.job_id
    if not structure_job_id:
        structure_block = result.get("structure") or {}
        if isinstance(structure_block, dict):
            structure_job_id = structure_block.get("job_id") or structure_block.get("structure_job_id")

    # 3. From payload.candidate_id (enables lookup by case_id in the explorer)
    payload = detail.get("payload") or {}
    candidate_id = payload.get("candidate_id")

    # Derive a friendly label based on job type
    label_map = {
        "alphafold_backend": "View AlphaFold structure",
        "alphafold_structure": "View structure job",
    }
    label = label_map.get(job_type, "View structure job")

    # Determine status from the result for context
    result_status = result.get("status") if isinstance(result, dict) else None

    linkback: dict = {
        "structure_job_id": structure_job_id or None,
        "case_id": case_id,
        "candidate_id": candidate_id or None,
        "label": label,
        "surface": "structure_job_explorer",
        "job_type": job_type,
        "result_status": result_status,
    }

    # Only return linkback if we have at least a case_id or structure_job_id
    if not linkback["case_id"] and not linkback["structure_job_id"]:
        return None

    return linkback


# ---------------------------------------------------------------------------
# Blocked/failed diagnosis — concise summary combining status, error,
# latest lifecycle events, and retry budget. Pure, no Streamlit dependency.
# ---------------------------------------------------------------------------

# Statuses that merit a diagnosis
_DIAGNOSIS_STATUSES = frozenset({"blocked", "failed", "timed_out"})


def derive_blocked_failed_diagnosis(
    job_card: dict,
    api_job: dict | None = None,
    events: list[SSEEvent] | None = None,
    detail: dict | None = None,
) -> str:
    """Derive a concise diagnosis summary for a blocked/failed job.

    Combines, when available:
      - job status
      - explicit error message
      - latest lifecycle event(s)
      - retry budget / eligibility

    Returns a terse, operator-oriented one-line diagnosis string.
    Returns an empty string when the job is not in a diagnosis-worthy state
    (i.e. not blocked, failed, or timed_out).

    This is a **pure function** — no Streamlit dependency.
    """
    source = api_job or job_card
    status = source.get("status", job_card.get("status", ""))

    if status not in _DIAGNOSIS_STATUSES:
        return ""

    # Use pre-computed detail if available, otherwise derive minimally
    if detail is None:
        detail = derive_job_detail(job_card, api_job=api_job, events=events)

    parts: list[str] = []

    # 1. Status headline
    status_headline = {
        "blocked": "BLOCKED",
        "failed": "FAILED",
        "timed_out": "TIMED_OUT",
    }.get(status, status.upper())
    parts.append(status_headline)

    # 2. Error message (truncated)
    error = detail.get("error")
    if error:
        error_str = str(error)
        if len(error_str) > 120:
            error_str = error_str[:117] + "..."
        parts.append(f"err={error_str}")

    # 3. Latest lifecycle event detail (most recent relevant one)
    lifecycle = detail.get("lifecycle_events") or []
    if lifecycle:
        # Pick the last lifecycle entry that has meaningful detail
        for entry in reversed(lifecycle):
            ev_detail = entry.get("detail", "")
            action = entry.get("action", "")
            if ev_detail:
                # Truncate long detail
                if len(ev_detail) > 100:
                    ev_detail = ev_detail[:97] + "..."
                parts.append(f"last={action}: {ev_detail}")
                break
        else:
            # No entry with detail — just note the latest action
            latest = lifecycle[-1]
            parts.append(f"last={latest.get('action', '?')}")

    # 4. Retry budget
    attempt = detail.get("attempt")
    max_retries = detail.get("max_retries")
    if attempt is not None and max_retries is not None:
        limit = max_retries + 1
        if attempt > limit:
            parts.append(f"retries=EXHAUSTED({attempt}/{limit})")
        else:
            retries_remaining = limit - attempt
            parts.append(f"retries={retries_remaining} left ({attempt}/{limit})")

    # 5. Timed-out flag
    timed_out = detail.get("timed_out")
    if timed_out:
        parts.append("timeout=yes")

    return " | ".join(parts)


def format_blocked_failed_diagnosis(diagnosis: str) -> str:
    """Render a diagnosis string as a compact, operator-oriented label.

    Returns a styled one-liner suitable for dashboards.  Returns
    ``""`` when *diagnosis* is empty (job not in a diagnosis-worthy state).

    This is a **pure function** — no Streamlit dependency.
    """
    if not diagnosis:
        return ""
    return f"Diagnosis: {diagnosis}"


# ---------------------------------------------------------------------------
# Lifecycle event helpers (internal)
# ---------------------------------------------------------------------------

def _derive_lifecycle_events(
    events: list[SSEEvent],
    job_id: str | None = None,
    case_id: str | None = None,
    job_type: str | None = None,
) -> list[dict]:
    """Filter and format SSE events relevant to a specific job/case.

    Matches events by:
    1. Explicit job_id reference in event data (exact match)
    2. case_id + event family matching the job_type
    3. case_id match alone (if job_type is generic like 'pipeline' → 'pipeline_run')

    Returns a list of dicts, each with keys: event, timestamp, action, detail.
    """
    lifecycle: list[dict] = []
    # Normalize job_type for matching: 'pipeline_run' → 'pipeline', etc.
    normalized_family = (job_type or "").rsplit("_", 1)[0] if job_type else None
    # Also try direct match
    job_type_variants = {job_type} if job_type else set()
    if normalized_family and normalized_family != job_type:
        job_type_variants.add(normalized_family)

    for evt in events:
        data = evt.data or {}
        evt_family = (evt.event or "").split(".", 1)[0]
        evt_case = data.get("case_id", "")

        # Match by explicit job_id in event data
        if job_id and data.get("job_id") == job_id:
            lifecycle.append(_format_lifecycle_entry(evt))
            continue

        # Match by case_id + family
        if case_id and evt_case == case_id:
            if not job_type_variants:
                # No type filter — include all events for this case
                lifecycle.append(_format_lifecycle_entry(evt))
            elif evt_family in job_type_variants:
                lifecycle.append(_format_lifecycle_entry(evt))

    return lifecycle


def _format_lifecycle_entry(evt: SSEEvent) -> dict:
    """Convert an SSEEvent into a flat lifecycle entry dict."""
    data = evt.data or {}
    detail_keys = [k for k in ("status", "safety_gate_result", "details", "message", "error") if data.get(k)]
    detail_parts = [f"{k}={data[k]}" for k in detail_keys]
    return {
        "event": evt.event or "message",
        "timestamp": data.get("timestamp", ""),
        "action": data.get("action", evt.event or ""),
        "detail": " | ".join(detail_parts),
    }


def _format_payload_preview(payload, max_len: int = 200) -> str:
    """Format a result/payload dict as a compact preview string."""
    import json

    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload[:max_len] + ("..." if len(payload) > max_len else "")
    try:
        s = json.dumps(payload, default=str, separators=(",", ":"))
        if len(s) > max_len:
            return s[:max_len - 3] + "..."
        return s
    except (TypeError, ValueError):
        return str(payload)[:max_len]


# ---------------------------------------------------------------------------
# Job detail derivation (primary entry point)
# ---------------------------------------------------------------------------

def derive_job_detail(
    job_card: dict,
    api_job: dict | None = None,
    events: list[SSEEvent] | None = None,
) -> dict:
    """Derive a detailed drilldown dict for a selected job card.

    Merges information from the job status card, the full API job payload
    (if available), and any SSE lifecycle events associated with the
    job's case/type.

    Returns a dict with at minimum:
      - job_id, job_type, status, case_id (from the card)
      - attempt, max_retries, timed_out (from api_job if present)
      - result (from api_job if present)
      - error (from card or api_job, merged)
      - lifecycle_events: list of dicts with event/ts/action/detail
      - created_at (from card or api_job)
      - diagnosis: concise blocked/failed diagnosis string (from
        :func:`derive_blocked_failed_diagnosis`)

    This is a **pure function** — no Streamlit dependency.
    """
    # Import at function level to avoid circular imports at module load time.
    # derive_job_detail_actions (in event_stream_action_chips) calls back into
    # derive_structure_linkback and is_retry_eligible, but does NOT call
    # derive_job_detail, so the cycle is only one level deep.
    from frontend.app.event_stream_action_chips import derive_job_detail_actions  # noqa: F401

    detail: dict = {
        "job_id": job_card.get("job_id") or "",
        "job_type": job_card.get("job_type", "unknown"),
        "status": job_card.get("status", "unknown"),
        "case_id": job_card.get("case_id") or "",
        "created_at": job_card.get("created_at") or "",
        "attempt": None,
        "max_retries": None,
        "timed_out": None,
        "result": None,
        "error": None,
        "lifecycle_events": [],
    }

    # Merge in API job payload (richer detail)
    if api_job:
        detail["attempt"] = api_job.get("attempt")
        detail["max_retries"] = api_job.get("max_retries")
        detail["timed_out"] = api_job.get("timed_out")
        detail["result"] = api_job.get("result")
        detail["error"] = api_job.get("error") or job_card.get("error")
        detail["created_at"] = api_job.get("created_at") or detail["created_at"]
        # Use API job type/status as more authoritative
        if api_job.get("job_type"):
            detail["job_type"] = api_job["job_type"]
        if api_job.get("status"):
            detail["status"] = api_job["status"]
        if api_job.get("case_id") is not None:
            detail["case_id"] = api_job["case_id"]
        # Also carry payload for preview
        detail["payload"] = api_job.get("payload")
    else:
        # Fall back to card fields
        detail["error"] = job_card.get("error")

    # Derive lifecycle events from SSE stream
    if events:
        detail["lifecycle_events"] = _derive_lifecycle_events(
            events,
            job_id=detail.get("job_id") or None,
            case_id=detail.get("case_id") or None,
            job_type=detail.get("job_type"),
        )

    detail["structure_linkback"] = derive_structure_linkback(
        job_card,
        api_job=api_job,
    )

    detail["action_chips"] = derive_job_detail_actions(
        job_card,
        api_job=api_job,
    )

    detail["diagnosis"] = derive_blocked_failed_diagnosis(
        job_card,
        api_job=api_job,
        events=events,
        detail=detail,
    )

    return detail


def format_job_detail(detail: dict) -> str:
    """Render a job detail dict as a compact, operator-oriented text block.

    Pure function — no Streamlit dependency.
    """
    if not detail:
        return "No job detail available."

    # Import at function level to avoid circular imports
    from frontend.app.event_stream_action_chips import format_action_chips

    job_id = detail.get("job_id") or "?"
    short_id = job_id[:8] if len(job_id) >= 8 else job_id
    job_type = detail.get("job_type", "unknown")
    status = detail.get("status", "unknown")
    case_id = detail.get("case_id") or "n/a"
    created_at = detail.get("created_at") or "n/a"

    lines = [
        f"Job detail — {job_type} [{short_id}]",
        f"  status:     {status}",
        f"  case:       {case_id}",
        f"  created:    {created_at}",
    ]

    # Attempt/retry info
    attempt = detail.get("attempt")
    max_retries = detail.get("max_retries")
    if attempt is not None:
        attempt_line = f"  attempt:    {attempt}"
        if max_retries is not None:
            attempt_line += f"/{max_retries + 1}"
        lines.append(attempt_line)

    timed_out = detail.get("timed_out")
    if timed_out is not None:
        lines.append(f"  timed_out:  {timed_out}")

    # Error
    error = detail.get("error")
    if error:
        error_str = str(error)
        # Truncate very long errors for readability
        if len(error_str) > 500:
            error_str = error_str[:497] + "..."
        lines.append(f"  error:      {error_str}")

    # Result payload
    result = detail.get("result")
    if result:
        result_str = _format_payload_preview(result)
        lines.append(f"  result:     {result_str}")

    # Payload (input)
    payload = detail.get("payload")
    if payload:
        payload_str = _format_payload_preview(payload)
        lines.append(f"  payload:    {payload_str}")

    # Structure / AlphaFold linkback
    linkback = detail.get("structure_linkback")
    if linkback:
        lines.append(f"  linkback:   {linkback.get('label', 'View structure job')}")
        if linkback.get("case_id"):
            lines.append(f"  focus_case: {linkback['case_id']}")
        if linkback.get("structure_job_id"):
            lines.append(f"  struct_job: {linkback['structure_job_id']}")
        if linkback.get("candidate_id"):
            lines.append(f"  candidate:  {linkback['candidate_id']}")

    # Action chips
    action_chips = detail.get("action_chips") or []
    if action_chips:
        lines.append(f"  actions:    {format_action_chips(action_chips)}")

    # Diagnosis (concise blocked/failed summary)
    diagnosis = detail.get("diagnosis")
    if diagnosis:
        lines.append(f"  diagnosis:  {diagnosis}")

    # Lifecycle events
    lifecycle = detail.get("lifecycle_events") or []
    if lifecycle:
        lines.append(f"  lifecycle:  {len(lifecycle)} event(s)")
        for entry in lifecycle[-10:]:  # Show last 10
            ts = entry.get("timestamp", "?")
            action = entry.get("action", "?")
            detail_str = entry.get("detail", "")
            line = f"    [{ts}] {action}"
            if detail_str:
                line += f" — {detail_str}"
            lines.append(line)
    else:
        lines.append("  lifecycle:  no events found")

    return "\n".join(lines)


def build_job_detail_table(detail: dict) -> list[dict]:
    """Convert a job detail dict into flat row dicts for tabular display.

    Produces one row per lifecycle event plus a summary row for the job itself.
    """
    rows: list[dict] = []
    if not detail:
        return rows

    job_id = detail.get("job_id") or ""
    job_type = detail.get("job_type", "unknown")
    status = detail.get("status", "unknown")
    case_id = detail.get("case_id") or ""

    # Summary row
    summary_row = {
        "type": "summary",
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "case_id": case_id,
        "event": "—",
        "timestamp": detail.get("created_at") or "",
        "action": "job_created",
        "detail": "",
    }
    rows.append(summary_row)

    # Lifecycle event rows
    for entry in detail.get("lifecycle_events") or []:
        rows.append({
            "type": "lifecycle",
            "job_id": job_id,
            "job_type": job_type,
            "status": status,
            "case_id": case_id,
            "event": entry.get("event", ""),
            "timestamp": entry.get("timestamp", ""),
            "action": entry.get("action", ""),
            "detail": entry.get("detail", ""),
        })

    return rows