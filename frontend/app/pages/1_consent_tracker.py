"""Consent Status Tracker — Streamlit page.

A dedicated timeline view for tracking consent status across cases.
Add this page to the sidebar by placing it in ``frontend/app/pages/``.
"""

from __future__ import annotations

import os

import streamlit as st

from frontend.app.consent_tracker import (
    build_consent_case_table_row,
    build_consent_timeline,
    summarize_consent_state,
)
from skills.shared.foldagent_client import FoldAgentClient

DEFAULT_API_URL = os.environ.get("FOLDAGENT_API_URL", "http://127.0.0.1:8010")

st.set_page_config(page_title="Consent Tracker — FoldAgent", layout="wide")

st.title("Consent Status Tracker")
st.caption("Timeline view of consent status across all research cases")

api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
client = FoldAgentClient(base_url=api_url)


def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # pragma: no cover
        return None, str(exc)


# --- Fetch data ---
cases, cases_error = safe_call(client.list_cases)
if cases_error:
    st.error(f"Unable to load cases: {cases_error}")
    cases = []

if not cases:
    st.info("No cases found.")
    st.stop()

# Build per-case timelines
consent_rows = []
case_timelines = {}
for case in cases:
    case_id = case.get("id")
    audit_log, _ = safe_call(client.get_audit_log, case_id)
    audit_log = audit_log or []
    timeline = build_consent_timeline(case, audit_log)
    case_timelines[case_id] = timeline
    consent_rows.append(build_consent_case_table_row(case, timeline))

# --- Overview table ---
st.subheader("All cases")
st.dataframe(consent_rows, width="stretch", hide_index=True)

# --- Case selector ---
st.divider()
st.subheader("Case consent timeline")
case_options = {c.get("id", "unknown"): c for c in cases}
case_labels = {
    cid: f"{cid[:8]} — {case.get('species', '?')} — consent: {case.get('consent_status', '?')}"
    for cid, case in case_options.items()
}
selected_case_id = st.selectbox("Select case", options=list(case_labels.keys()), format_func=lambda x: case_labels[x])
selected_case = case_options[selected_case_id]
timeline = case_timelines[selected_case_id]

# --- Summary metrics ---
summary = summarize_consent_state(selected_case, timeline)
metric_cols = st.columns(4)
metric_cols[0].metric("Current status", f"{summary['status_icon']} {summary['current_status']}")
metric_cols[1].metric("Review status", summary["review_status"])
metric_cols[2].metric("Consent updates", summary["consent_update_count"])
metric_cols[3].metric(
    "Days since update",
    f"{summary['days_since_last_update']:.1f}" if summary["days_since_last_update"] is not None else "—",
)

if summary["needs_attention"]:
    st.warning("This case needs consent attention before review can proceed.")
if summary["is_redacted"]:
    st.error("This case has been redacted.")
if summary["is_deleted"]:
    st.error("This case has been deleted.")

# --- Timeline ---
st.divider()
for event in timeline:
    icon = {
        "case_created": "🆕",
        "consent_updated": "📝",
        "redacted": "🔒",
        "deleted": "🗑️",
        "ethics_report": "📋",
    }.get(event["event_type"], "•")
    with st.container():
        cols = st.columns([1, 4])
        with cols[0]:
            st.markdown(f"**{icon} {event['timestamp'] or '—'}**")
        with cols[1]:
            st.markdown(f"**{event['title']}**")
            st.caption(event["description"])
            if event.get("status_after"):
                st.markdown(f"`Status: {event['status_after']}`")
        st.markdown("---")

# --- Update consent action ---
st.divider()
st.subheader("Update consent status")
with st.form("update-consent"):
    new_status = st.selectbox(
        "New consent status",
        ["pending", "received", "withdrawn"],
        index=["pending", "received", "withdrawn"].index(summary["current_status"])
        if summary["current_status"] in ["pending", "received", "withdrawn"]
        else 0,
    )
    reason = st.text_area("Reason / notes", value="")
    submitted = st.form_submit_button("Update consent", width="stretch")

if submitted:
    updated, error = safe_call(client.update_case, selected_case_id, consent_status=new_status)
    if error:
        st.error(f"Update failed: {error}")
    else:
        st.success(f"Consent status updated to {new_status}")
        if reason:
            st.info(f"Reason recorded: {reason}")
        st.rerun()
