"""Focused render helpers for FoldAgent dashboard operator surfaces.

This module extracts the large operator UI surfaces from dashboard.py into
reusable render functions.  Each function encapsulates one logical panel:

- ``render_operator_context_rail``  — the unified operator context rail
- ``render_live_event_drilldown``    — live event select + detail + shortcuts
- ``render_job_status_summary``     — status cards, metrics, table
- ``render_job_retry_panel``        — retry / re-dispatch for eligible jobs
- ``render_job_detail_drilldown``   — job detail + timeline + action chips + linkback

All functions accept their data as arguments (no hidden ``st.session_state``
reads except where the original dashboard code already did).  The goal is
to keep behaviour identical while making dashboard.py shorter and each
surface independently testable / reusable.

Only Streamlit render helpers — pure logic stays in event_stream.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from frontend.app.event_stream import (
    _CTX_EVENT_KEY,
    _CTX_FILTER_CASE_ID_KEY,
    _CTX_JOB_KEY,
    _CTX_PIPELINE_CASE_KEY,
    _CTX_STRUCTURE_JOB_KEY_PREFIX,
    build_job_detail_table,
    build_job_status_table_rows,
    build_operator_timeline_rows,
    derive_chip_prefocus,
    derive_event_detail,
    derive_job_detail,
    derive_job_detail_actions,
    derive_macro_focus_prefocus,
    derive_operator_timeline,
    derive_structure_linkback,
    format_action_chip_summary,
    format_action_chips,
    format_blocked_failed_diagnosis,
    format_cancel_action_summary,
    format_event_detail,
    format_event_payload_json,
    format_job_detail,
    format_job_status_cards,
    format_operator_context,
    format_operator_timeline,
    format_retry_action_summary,
)
from frontend.app.dashboard_helpers import normalize_table_rows

if TYPE_CHECKING:
    from skills.shared.event_stream_client import SSEEvent
    from skills.shared.foldagent_client import FoldAgentClient


# ---------------------------------------------------------------------------
# Operator context rail
# ---------------------------------------------------------------------------

def render_operator_context_rail(
    op_ctx: dict,
) -> None:
    """Render the unified operator context rail expander.

    Args:
        op_ctx: Context dict as returned by
            :func:`event_stream.derive_operator_context`.
    """
    with st.expander(
        "Operator context",
        expanded=bool(
            op_ctx.get("summary_line")
            and op_ctx["summary_line"] != "No active selections"
        ),
    ):
        st.code(format_operator_context(op_ctx))


# ---------------------------------------------------------------------------
# Live event drilldown
# ---------------------------------------------------------------------------

def render_live_event_drilldown(
    filtered_events: list[SSEEvent],
) -> None:
    """Render the live event drilldown selector + detail + shortcuts.

    Args:
        filtered_events: Already-filtered list of SSEEvent objects.
    """
    if not filtered_events:
        return

    st.markdown("#### Live event drilldown")
    event_options = {
        f"{(e.event or 'message')} @ {(e.data or {}).get('timestamp', '?')} | case={((e.data or {}).get('case_id') or '?')}": e
        for e in filtered_events
    }
    selected_event_label = st.selectbox(
        "Select a live event to inspect",
        options=list(event_options.keys()),
        key=_CTX_EVENT_KEY,
    )
    selected_event = event_options.get(selected_event_label)
    if selected_event:
        event_detail = derive_event_detail(selected_event)
        st.code(format_event_detail(event_detail))

        # Shortcuts — jump to case/job filter
        shortcuts = event_detail.get("shortcuts")
        if shortcuts:
            shortcut_col1, shortcut_col2 = st.columns(2)
            if shortcuts.get("case_shortcut"):
                with shortcut_col1:
                    shortcut_case = shortcuts.get("case_id", "")
                    if st.button(
                        f"Filter to case {shortcut_case}",
                        key=f"event-drilldown-case-{shortcut_case}",
                        width="stretch",
                    ):
                        st.session_state[_CTX_FILTER_CASE_ID_KEY] = shortcut_case
                        st.rerun()
            if shortcuts.get("job_shortcut"):
                with shortcut_col2:
                    shortcut_job = shortcuts.get("job_id", "")
                    st.caption(f"Related job: {shortcut_job}")

        # Raw payload in expander
        with st.expander("Raw event payload"):
            st.code(format_event_payload_json(selected_event))


# ---------------------------------------------------------------------------
# Job status summary (cards + metrics + table)
# ---------------------------------------------------------------------------

def render_job_status_summary(
    filtered_cards: list[dict],
    enriched_cards: list[dict],
) -> None:
    """Render job status summary metrics, compact text, and detail table.

    Args:
        filtered_cards: Filtered job cards (not yet enriched).
        enriched_cards: Same cards after :func:`enrich_cards_with_retry_info`.
    """
    # Summary metrics row (based on filtered cards)
    status_counts: dict[str, int] = {}
    for card in filtered_cards:
        s = card.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    card_cols = st.columns(min(len(status_counts), 6))
    for idx, (status_label, count) in enumerate(sorted(status_counts.items())):
        if idx < len(card_cols):
            card_cols[idx].metric(status_label.replace("_", " ").title(), count)

    # Severity-aware compact summary
    st.caption("Operator card summary")
    st.code(format_job_status_cards(filtered_cards))

    # Detailed table
    with st.expander("Job status detail"):
        job_rows = build_job_status_table_rows(enriched_cards)
        st.dataframe(normalize_table_rows(job_rows), width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Retry / re-dispatch panel
# ---------------------------------------------------------------------------

def render_job_retry_panel(
    enriched_cards: list[dict],
    client: FoldAgentClient,
    safe_call,
    render_api_error,
) -> None:
    """Render retry / cancel actions for background jobs.

    Args:
        enriched_cards: Job cards enriched with retry/cancel info.
        client: FoldAgentClient instance for API calls.
        safe_call: The dashboard's ``safe_call`` wrapper.
        render_api_error: The dashboard's ``render_api_error`` helper.
    """
    eligible_retry_cards = [c for c in enriched_cards if c.get("retry_eligible")]
    eligible_cancel_cards = [c for c in enriched_cards if c.get("cancel_eligible")]

    if eligible_retry_cards:
        st.markdown("#### Retry / re-dispatch")
        st.caption(f"{len(eligible_retry_cards)} job(s) eligible for retry")
        st.code(format_retry_action_summary(enriched_cards))

        for card in eligible_retry_cards:
            job_id = card.get("job_id") or ""
            short_id = job_id[:8] if len(job_id) >= 8 else job_id
            job_type = card.get("job_type", "unknown")
            status = card.get("status", "unknown")
            badge = card.get("retry_badge", "")
            retry_col1, retry_col2 = st.columns([3, 1])
            with retry_col1:
                st.markdown(
                    f"**{job_type}** ({status}) — `{short_id}` — {badge}"
                )
            with retry_col2:
                if st.button(
                    f"Retry {short_id}",
                    key=f"retry-job-{job_id}",
                    width="stretch",
                ):
                    retry_result, retry_error = safe_call(client.retry_background_job, job_id)
                    if retry_error:
                        render_api_error(retry_error, fallback_title=f"Retry failed for job {short_id}")
                    else:
                        st.success(f"Job {short_id} re-dispatched (attempt {retry_result.get('attempt', '?')})")
                        st.rerun()
    else:
        with st.expander("Retry / re-dispatch"):
            st.info("No jobs currently eligible for retry (only failed/timed_out jobs with remaining retry budget).")

    if eligible_cancel_cards:
        st.markdown("#### Cancel running / pending jobs")
        st.caption(f"{len(eligible_cancel_cards)} job(s) eligible for cancellation")
        st.code(format_cancel_action_summary(enriched_cards))

        for card in eligible_cancel_cards:
            job_id = card.get("job_id") or ""
            short_id = job_id[:8] if len(job_id) >= 8 else job_id
            job_type = card.get("job_type", "unknown")
            status = card.get("status", "unknown")
            badge = card.get("cancel_badge", "")
            cancel_col1, cancel_col2 = st.columns([3, 1])
            with cancel_col1:
                st.markdown(f"**{job_type}** ({status}) — `{short_id}` — {badge}")
            with cancel_col2:
                if st.button(
                    f"Cancel {short_id}",
                    key=f"cancel-job-{job_id}",
                    width="stretch",
                ):
                    cancel_result, cancel_error = safe_call(client.cancel_background_job, job_id)
                    if cancel_error:
                        render_api_error(cancel_error, fallback_title=f"Cancel failed for job {short_id}")
                    else:
                        st.success(f"Job {short_id} cancellation requested ({cancel_result.get('status', '?')})")
                        st.rerun()
    else:
        with st.expander("Cancel running / pending jobs"):
            st.info("No jobs currently eligible for cancellation (only pending/running jobs).")


# ---------------------------------------------------------------------------
# Job detail drilldown (detail + timeline + action chips + linkback)
# ---------------------------------------------------------------------------

def render_job_detail_drilldown(
    enriched_cards: list[dict],
    live_events: list[SSEEvent],
    client: FoldAgentClient,
    safe_call,
    render_api_error,
) -> None:
    """Render job detail drilldown panel with timeline, action chips, and linkback.

    Args:
        enriched_cards: Enriched job cards (with retry info).
        live_events: Current live events from the feed buffer.
        client: FoldAgentClient instance for API calls.
        safe_call: The dashboard's ``safe_call`` wrapper.
        render_api_error: The dashboard's ``render_api_error`` helper.
    """
    # Select an API-sourced job to inspect in detail
    api_cards = [c for c in enriched_cards if c.get("job_id")]
    if not api_cards:
        return

    job_options = {
        f"{c.get('job_type', '?')} — {c.get('status', '?')} ({(c.get('job_id') or '')[:8]})": c
        for c in api_cards
    }
    st.markdown("#### Job detail drilldown")
    selected_job_label = st.selectbox(
        "Select a background job to inspect",
        options=list(job_options.keys()),
        key=_CTX_JOB_KEY,
    )
    selected_card = job_options.get(selected_job_label)

    if not selected_card:
        return

    selected_job_id = selected_card.get("job_id")
    # Fetch full job detail from API for richer info
    job_detail_api, job_detail_error = safe_call(client.get_background_job, selected_job_id)
    api_job_data = None
    if job_detail_error:
        st.caption(f"Could not fetch full job detail: {job_detail_error}")
    elif job_detail_api:
        api_job_data = job_detail_api

    # Derive structured detail from card + API data + live events
    job_detail = derive_job_detail(
        job_card=selected_card,
        api_job=api_job_data,
        events=live_events,
    )

    # Compact text detail
    st.code(format_job_detail(job_detail))

    # --- Diagnosis: concise blocked/failed summary ---
    diagnosis = job_detail.get("diagnosis", "")
    if diagnosis:
        st.error(format_blocked_failed_diagnosis(diagnosis))

    # --- Operator timeline: concise synthesized view ---
    timeline = derive_operator_timeline(
        job_card=selected_card,
        api_job=api_job_data,
        events=live_events,
    )
    if timeline:
        st.caption("Operator timeline")
        st.code(format_operator_timeline(timeline))
        with st.expander("Timeline table"):
            timeline_rows = build_operator_timeline_rows(timeline)
            st.dataframe(normalize_table_rows(timeline_rows), width="stretch", hide_index=True)

    # --- Action chips: compact action affordances ---
    action_chips = job_detail.get("action_chips") or derive_job_detail_actions(
        selected_card, api_job=api_job_data,
    )
    if action_chips:
        _render_action_chips(action_chips, selected_job_id, client, safe_call, render_api_error)

    structure_linkback = job_detail.get("structure_linkback") or derive_structure_linkback(
        selected_card,
        api_job=api_job_data,
    )
    if structure_linkback:
        _render_structure_linkback(structure_linkback, selected_job_id)

    # Lifecycle events in expandable table
    lifecycle_events = job_detail.get("lifecycle_events") or []
    if lifecycle_events:
        with st.expander("Job lifecycle events"):
            detail_rows = build_job_detail_table(job_detail)
            st.dataframe(normalize_table_rows(detail_rows), width="stretch", hide_index=True)
    else:
        st.caption("No lifecycle events found for this job/case.")

    # Raw result/error payloads in expanders
    if job_detail.get("result"):
        with st.expander("Result payload"):
            st.json(job_detail["result"])
    if job_detail.get("error"):
        with st.expander("Error detail"):
            st.code(str(job_detail["error"]))
    if job_detail.get("payload"):
        with st.expander("Input payload"):
            st.json(job_detail["payload"])


# ---------------------------------------------------------------------------
# Private: action chips sub-panel
# ---------------------------------------------------------------------------

def _render_action_chips(
    action_chips: list[dict],
    selected_job_id: str,
    client: FoldAgentClient,
    safe_call,
    render_api_error,
) -> None:
    """Render actionable chip buttons for a selected job."""
    st.caption("Available actions")
    chip_summary = format_action_chips(action_chips)
    st.info(chip_summary)
    # Render actionable chip buttons
    chip_columns = st.columns(min(len(action_chips), 5))
    for idx, chip in enumerate(action_chips[:5]):
        with chip_columns[idx]:
            chip_action = chip.get("action", "")
            chip_data = chip.get("data") or {}
            chip_label = chip.get("label", chip_action)
            chip_enabled = chip.get("enabled", True)

            if chip_action == "retry" and chip_enabled:
                if st.button(
                    f"↻ {chip_label}",
                    key=f"chip-retry-{selected_job_id}",
                    width="stretch",
                ):
                    retry_result, retry_error = safe_call(
                        client.retry_background_job, chip_data.get("job_id", selected_job_id),
                    )
                    if retry_error:
                        render_api_error(retry_error, fallback_title=f"Retry failed for job {selected_job_id[:8]}")
                    else:
                        st.success(f"Job {selected_job_id[:8]} re-dispatched (attempt {retry_result.get('attempt', '?')})")
                        st.rerun()

            elif chip_action == "view_structure" and chip_enabled:
                if st.button(
                    f"🔬 {chip_label}",
                    key=f"chip-structure-{selected_job_id}",
                    width="stretch",
                ):
                    focus_case_id = chip_data.get("case_id")
                    structure_job_id = chip_data.get("structure_job_id")
                    if focus_case_id:
                        st.session_state[_CTX_PIPELINE_CASE_KEY] = focus_case_id
                    if focus_case_id and structure_job_id:
                        st.session_state[f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{focus_case_id}"] = structure_job_id
                    st.rerun()

            elif chip_action == "view_report" and chip_enabled:
                # Show report shortcut: select case and prefocus specific report
                if st.button(
                    f"📄 {chip_label}",
                    key=f"chip-report-{selected_job_id}",
                    width="stretch",
                ):
                    prefocus = derive_chip_prefocus(chip)
                    if prefocus:
                        for k, v in prefocus.items():
                            st.session_state[k] = v
                    else:
                        chip_case_id = chip_data.get("case_id")
                        if chip_case_id:
                            st.session_state[_CTX_PIPELINE_CASE_KEY] = chip_case_id
                    st.rerun()

            elif chip_action == "view_artifacts" and chip_enabled:
                # Show artifacts shortcut: select case and prefocus specific artifact
                if st.button(
                    f"📦 {chip_label}",
                    key=f"chip-artifacts-{selected_job_id}",
                    width="stretch",
                ):
                    prefocus = derive_chip_prefocus(chip)
                    if prefocus:
                        for k, v in prefocus.items():
                            st.session_state[k] = v
                    else:
                        chip_case_id = chip_data.get("case_id")
                        if chip_case_id:
                            st.session_state[_CTX_PIPELINE_CASE_KEY] = chip_case_id
                    st.rerun()

            elif chip_action == "macro_focus" and chip_enabled:
                # One-click macro focus: set all derivable preselect keys
                if st.button(
                    f"🎯 {chip_label}",
                    key=f"chip-macro-focus-{selected_job_id}",
                    width="stretch",
                ):
                    prefocus = derive_macro_focus_prefocus(chip_data)
                    if prefocus:
                        for k, v in prefocus.items():
                            st.session_state[k] = v
                    else:
                        chip_case_id = chip_data.get("case_id")
                        if chip_case_id:
                            st.session_state[_CTX_PIPELINE_CASE_KEY] = chip_case_id
                    st.rerun()

            else:
                st.caption(f"{chip_label}" if not chip_enabled else f"{chip_label}")

    # Compact text summary of all actions
    with st.expander("Action details"):
        st.code(format_action_chip_summary(action_chips))


# ---------------------------------------------------------------------------
# Private: structure linkback sub-panel
# ---------------------------------------------------------------------------

def _render_structure_linkback(
    structure_linkback: dict,
    selected_job_id: str,
) -> None:
    """Render structure / AlphaFold linkback info + focus button."""
    st.caption("Structure / AlphaFold linkback")
    link_col1, link_col2 = st.columns([3, 1])
    with link_col1:
        link_parts = [structure_linkback.get("label") or "View structure job"]
        if structure_linkback.get("case_id"):
            link_parts.append(f"case={structure_linkback['case_id']}")
        if structure_linkback.get("structure_job_id"):
            link_parts.append(f"structure_job={structure_linkback['structure_job_id'][:8]}")
        st.info(" · ".join(link_parts))
    with link_col2:
        if st.button(
            "Focus structure",
            key=f"focus-structure-from-job-{selected_job_id}",
            width="stretch",
        ):
            focus_case_id = structure_linkback.get("case_id")
            structure_job_id = structure_linkback.get("structure_job_id")
            if focus_case_id:
                st.session_state[_CTX_PIPELINE_CASE_KEY] = focus_case_id
            if focus_case_id and structure_job_id:
                st.session_state[f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}{focus_case_id}"] = structure_job_id
            st.rerun()
