"""Operator context / focus restore helpers — pure functions, no Streamlit dependency.

Extracted from event_stream.py for modularity.
"""

from __future__ import annotations

from frontend.app.event_stream_filters import FILTER_ALL

# ---------------------------------------------------------------------------
# Well-known session-state keys used across the dashboard.  Keeping them
# as constants makes the surface explicit and testable without Streamlit.
# ---------------------------------------------------------------------------

_CTX_EVENT_KEY = "live_event_drilldown_select"
_CTX_JOB_KEY = "job_detail_select"
_CTX_PIPELINE_CASE_KEY = "pipeline-case-selector"
_CTX_INSPECT_CASE_KEY = "inspect-case-selector"
_CTX_REPORT_KEY_PREFIX = "report-detail-"
_CTX_STRUCTURE_JOB_KEY_PREFIX = "structure-job-"
_CTX_FILTER_STATUS_KEY = "filter_status"
_CTX_FILTER_JOB_TYPE_KEY = "filter_job_type"
_CTX_FILTER_CASE_ID_KEY = "filter_case_id"
_CTX_PREFOCUS_REPORT_KEY = "prefocus_report_id"
_CTX_PREFOCUS_CASE_KEY = "prefocus_case_id"
_CTX_PREFOCUS_ARTIFACT_KEY = "prefocus_artifact_path"
_CTX_PREFOCUS_AUTO_OPEN_KEY = "prefocus_auto_open_artifact"

# ---------------------------------------------------------------------------
# Persistent operator focus — restorable focus keys and helpers.
# Pure functions, no Streamlit dependency.  File I/O lives in
# operator_focus_store.py; these helpers only extract/apply focus
# from a plain dict, making them fully unit-testable.
# ---------------------------------------------------------------------------

# Keys that are safe to persist across sessions.  Prefocus keys are
# intentionally excluded because they are consumed-and-cleared on
# each render cycle (they are ephemeral navigation hints, not
# selections).
_RESTORABLE_FOCUS_KEYS: list[str] = [
    _CTX_EVENT_KEY,
    _CTX_JOB_KEY,
    _CTX_PIPELINE_CASE_KEY,
    _CTX_INSPECT_CASE_KEY,
    _CTX_FILTER_STATUS_KEY,
    _CTX_FILTER_JOB_TYPE_KEY,
    _CTX_FILTER_CASE_ID_KEY,
]

# Prefixes whose dynamic keys should also be captured (e.g.
# report-detail-{case_id}, structure-job-{case_id}).
_RESTORABLE_FOCUS_PREFIXES: list[tuple[str, str]] = [
    (_CTX_REPORT_KEY_PREFIX, "report_detail_keys"),
    (_CTX_STRUCTURE_JOB_KEY_PREFIX, "structure_job_keys"),
]


def extract_restorable_focus(session_state: dict) -> dict:
    """Extract a restorable focus snapshot from session state.

    Walks *session_state* and collects values for the well-known
    operator focus keys (case selectors, filter selectors, etc.)
    plus any dynamic keys matching the registered prefixes (e.g.
    ``report-detail-{case_id}``, ``structure-job-{case_id}``).

    Values that are empty strings, ``None``, or equal to
    ``FILTER_ALL`` (``"__all__"``) are omitted — they represent
    "no selection" and should not shadow a previously saved focus.

    The returned dict is JSON-serialisable (all values are strings
    or dicts of strings) and suitable for writing to disk via
    :func:`operator_focus_store.save_operator_focus`.

    This is a **pure function** — no Streamlit dependency.
    """
    focus: dict[str, str | dict[str, str]] = {}

    # --- Static keys ---
    for key in _RESTORABLE_FOCUS_KEYS:
        value = session_state.get(key)
        if value is None or value == "" or value == FILTER_ALL:
            continue
        focus[key] = str(value)

    # --- Dynamic prefixed keys ---
    # Collect all session_state keys that start with a known prefix
    # and have a truthy, non-FILTER_ALL value.
    for prefix, _bucket in _RESTORABLE_FOCUS_PREFIXES:
        dynamic: dict[str, str] = {}
        for skey, sval in session_state.items():
            if isinstance(skey, str) and skey.startswith(prefix):
                if sval is None or sval == "" or sval == FILTER_ALL:
                    continue
                # The part after the prefix is the case_id / identifier
                dynamic[skey[len(prefix) :]] = str(sval)
        if dynamic:
            focus[_bucket] = dynamic

    return focus


def apply_restored_focus(
    session_state: dict,
    saved_focus: dict,
) -> dict:
    """Apply a previously saved focus into session state.

    For each focus key present in *saved_focus*, the value is written
    into *session_state* **only if** that key is not already present
    or holds an empty/``None``/``FILTER_ALL`` value.  This ensures that
    an active operator selection in the current session is never
    overwritten by a stale persisted value.

    Dynamic prefixed keys (``report_detail_keys``,
    ``structure_job_keys``) are expanded back into their full
    session-state key form (e.g. ``report-detail-{case_id}``) and
    applied with the same non-destructive rule.

    Returns the *session_state* dict (mutated in-place for convenience).

    This is a **pure function** — no Streamlit dependency.
    """
    if not saved_focus:
        return session_state

    # Helper: decide whether a session-state slot is "empty" / "all"
    def _is_empty(val) -> bool:
        return val is None or val == "" or val == FILTER_ALL

    # --- Static keys ---
    for key in _RESTORABLE_FOCUS_KEYS:
        if key in saved_focus:
            current = session_state.get(key)
            if _is_empty(current):
                session_state[key] = saved_focus[key]

    # --- Dynamic prefixed keys ---
    for prefix, bucket in _RESTORABLE_FOCUS_PREFIXES:
        dynamic = saved_focus.get(bucket)
        if not isinstance(dynamic, dict):
            continue
        for suffix, value in dynamic.items():
            full_key = f"{prefix}{suffix}"
            current = session_state.get(full_key)
            if _is_empty(current):
                session_state[full_key] = value

    return session_state


def derive_operator_context(
    session_state: dict,
    *,
    job_cards: list[dict] | None = None,
) -> dict:
    """Derive a unified operator context summary from session state.

    Extracts the operator's current focus selections across event drilldown,
    job detail, case, report, and structure job surfaces into a single compact
    dict the dashboard can display as a context rail.

    **Parameters:**

    - ``session_state``: A dict mirroring ``st.session_state``.  In production
      this is ``dict(st.session_state)``; in tests it can be a plain dict.
    - ``job_cards``: Optional list of job card dicts (as produced by
      :func:`derive_job_status_cards`).  When provided, the selected job
      label is enriched with type and status information.

    **Returns a dict with these keys:**

    - ``event_label``: The label of the selected live event (empty string if
      none selected).
    - ``job_label``: The label of the selected job detail (empty string if
      none selected).  May be enriched with ``job_id``, ``job_type``,
      ``job_status`` from *job_cards*.
    - ``case_id``: The currently selected case ID (from pipeline-case-selector
      or inspect-case-selector — pipeline preferred).
    - ``report_id``: The selected report ID for the active case, if any.
    - ``structure_job_id``: The selected structure job ID for the active
      case, if any.
    - ``filters``: Dict of active filter values (status, job_type, case_id).
      Values of ``FILTER_ALL`` are omitted.
    - ``prefocus``: Dict of active prefocus keys (report_id, case_id,
      artifact_path) that have not yet been consumed.
    - ``summary_line``: A human-readable one-line summary string.

    This is a **pure function** — no Streamlit dependency.
    """
    event_label = session_state.get(_CTX_EVENT_KEY, "") or ""

    job_label = session_state.get(_CTX_JOB_KEY, "") or ""

    case_id = (
        session_state.get(_CTX_PIPELINE_CASE_KEY, "")
        or ""
        or session_state.get(_CTX_INSPECT_CASE_KEY, "")
        or ""
    )

    # Report ID is keyed per-case: report-detail-{case_id}
    report_id = ""
    if case_id:
        report_id = session_state.get(f"{_CTX_REPORT_KEY_PREFIX}{case_id}", "") or ""

    # Structure job ID is also keyed per-case: structure-job-{case_id}
    structure_job_id = ""
    if case_id:
        structure_job_id = session_state.get(f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{case_id}", "") or ""

    # Active filters — suppress the "all" sentinel
    active_filters: dict[str, str] = {}
    for key, label in [
        (_CTX_FILTER_STATUS_KEY, "status"),
        (_CTX_FILTER_JOB_TYPE_KEY, "job_type"),
        (_CTX_FILTER_CASE_ID_KEY, "case_id"),
    ]:
        val = session_state.get(key, "")
        if val and val != FILTER_ALL:
            active_filters[label] = val

    # Prefocus keys that haven't been consumed yet
    prefocus: dict[str, str] = {}
    prefocus_report = session_state.get(_CTX_PREFOCUS_REPORT_KEY)
    prefocus_case = session_state.get(_CTX_PREFOCUS_CASE_KEY)
    prefocus_artifact = session_state.get(_CTX_PREFOCUS_ARTIFACT_KEY)
    if prefocus_report:
        prefocus["report_id"] = prefocus_report
    if prefocus_case:
        prefocus["case_id"] = prefocus_case
    if prefocus_artifact:
        prefocus["artifact_path"] = prefocus_artifact

    # Enrich job_label from job_cards if possible
    enriched_job = ""
    job_id = ""
    job_type = ""
    job_status = ""
    if job_label and job_cards:
        # The job_label is the selectbox label; look it up in card data.
        # Cards store job_id, job_type, status.
        for card in job_cards:
            card_label = (
                f"{card.get('job_type', '?')} — "
                f"{card.get('status', '?')} "
                f"({(card.get('job_id') or '')[:8]})"
            )
            if card_label == job_label:
                job_id = card.get("job_id") or ""
                job_type = card.get("job_type") or ""
                job_status = card.get("status") or ""
                enriched_job = (
                    f"{card.get('job_type', '?')} · {card.get('status', '?')} · {job_id[:8]}"
                )
                break
        if not enriched_job:
            enriched_job = job_label
    elif job_label:
        enriched_job = job_label

    # Build summary line
    parts: list[str] = []
    if event_label:
        # Truncate very long event labels
        display_label = event_label if len(event_label) <= 60 else event_label[:57] + "..."
        parts.append(f"event: {display_label}")
    if enriched_job:
        parts.append(f"job: {enriched_job}")
    if case_id:
        short_case = case_id[:8] if len(case_id) >= 8 else case_id
        parts.append(f"case: {short_case}")
    if report_id:
        short_report = report_id[:8] if len(report_id) >= 8 else report_id
        parts.append(f"report: {short_report}")
    if structure_job_id:
        short_sj = structure_job_id[:8] if len(structure_job_id) >= 8 else structure_job_id
        parts.append(f"struct: {short_sj}")
    if active_filters:
        filter_parts = [f"{k}={v}" for k, v in sorted(active_filters.items())]
        parts.append(f"filter: {', '.join(filter_parts)}")
    if prefocus:
        prefocus_parts = [f"{k}={v[:8]}" for k, v in sorted(prefocus.items())]
        parts.append(f"prefocus: {', '.join(prefocus_parts)}")

    summary_line = " | ".join(parts) if parts else "No active selections"

    return {
        "event_label": event_label,
        "job_label": job_label,
        "job_id": job_id,
        "job_type": job_type,
        "job_status": job_status,
        "case_id": case_id,
        "report_id": report_id,
        "structure_job_id": structure_job_id,
        "filters": active_filters,
        "prefocus": prefocus,
        "summary_line": summary_line,
    }


def format_operator_context(context: dict) -> str:
    """Render a unified operator context as a compact text block.

    Produces a multi-line block suitable for ``st.code()`` or
    ``st.caption()`` that the dashboard can display as a context rail.

    Example output::

        Operator context
          event:   case.created @ 2025-04-20T08:00:00 | case=c1
          job:     pipeline_run · running · abc12345
          case:    7f3a9c01
          report:  rep-99ab
          struct:  sj-42b1
          filters: status=running, case_id=c1
          prefocus: report_id=rep-99ab

    This is a **pure function** — no Streamlit dependency.
    """
    if not context:
        return "No operator context available."

    lines = ["Operator context"]

    event_label = context.get("event_label", "")
    if event_label:
        display = event_label if len(event_label) <= 60 else event_label[:57] + "..."
        lines.append(f"  event:   {display}")

    job_id = context.get("job_id", "")
    job_type = context.get("job_type", "")
    job_status = context.get("job_status", "")
    job_label = context.get("job_label", "")
    if job_id and job_type and job_status:
        lines.append(f"  job:     {job_type} · {job_status} · {job_id[:8]}")
    elif job_label:
        display = job_label if len(job_label) <= 60 else job_label[:57] + "..."
        lines.append(f"  job:     {display}")

    case_id = context.get("case_id", "")
    if case_id:
        short = case_id[:8] if len(case_id) >= 8 else case_id
        lines.append(f"  case:    {short}")

    report_id = context.get("report_id", "")
    if report_id:
        short = report_id[:8] if len(report_id) >= 8 else report_id
        lines.append(f"  report:  {short}")

    structure_job_id = context.get("structure_job_id", "")
    if structure_job_id:
        short = structure_job_id[:8] if len(structure_job_id) >= 8 else structure_job_id
        lines.append(f"  struct:  {short}")

    filters = context.get("filters") or {}
    if filters:
        filter_parts = [f"{k}={v}" for k, v in sorted(filters.items())]
        lines.append(f"  filters: {', '.join(filter_parts)}")

    prefocus = context.get("prefocus") or {}
    if prefocus:
        prefocus_parts = [f"{k}={v[:8]}" for k, v in sorted(prefocus.items())]
        lines.append(f"  prefocus: {', '.join(prefocus_parts)}")

    if len(lines) == 1:
        lines.append("  (no active selections)")

    return "\n".join(lines)
