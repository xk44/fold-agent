"""Lab Coordination panels for the FoldAgent Streamlit dashboard.

Renders contact log, cost tracker, timeline, document requests,
outreach templates, and checklists.
"""

from __future__ import annotations

from typing import Any


def render_lab_coordination_section(
    api_base: str,
    case_id: str | None,
    http_get: Any,
    http_post: Any,
    st: Any,
) -> None:
    st.header("Lab Coordination")

    if case_id is None:
        st.info("Select a case to manage lab coordination.")
        return

    tab_contacts, tab_costs, tab_timeline, tab_docs, tab_templates = st.tabs(
        ["Contacts", "Costs", "Timeline", "Documents", "Templates & Checklists"]
    )

    with tab_contacts:
        _render_contacts(api_base, case_id, http_get, http_post, st)

    with tab_costs:
        _render_costs(api_base, case_id, http_get, http_post, st)

    with tab_timeline:
        _render_timeline(api_base, case_id, http_get, http_post, st)

    with tab_docs:
        _render_document_requests(api_base, case_id, http_get, http_post, st)

    with tab_templates:
        _render_templates_and_checklists(api_base, http_get, st)


def _render_contacts(api_base: str, case_id: str, http_get: Any, http_post: Any, st: Any) -> None:
    st.subheader("Contact Log")

    with st.expander("Add Contact"):
        name = st.text_input("Name", key="contact_name")
        role = st.selectbox("Role", [
            "Veterinary Oncologist", "Medical Oncologist", "Sequencing Provider",
            "RNA Manufacturing Lab", "University Researcher", "Immunologist",
            "Pathologist", "Other",
        ], key="contact_role")
        org = st.text_input("Organization", key="contact_org")
        email = st.text_input("Email", key="contact_email")
        notes = st.text_area("Notes", key="contact_notes")

        if st.button("Add Contact") and name:
            http_post(f"{api_base}/cases/{case_id}/lab/contacts", json={
                "name": name, "role": role, "organization": org,
                "email": email, "notes": notes,
            })
            st.rerun()

    contacts = http_get(f"{api_base}/cases/{case_id}/lab/contacts").json()
    if contacts:
        for c in contacts:
            cols = st.columns([3, 2, 2, 3])
            cols[0].write(f"**{c['name']}**")
            cols[1].write(c.get("role", ""))
            cols[2].write(c.get("organization", ""))
            cols[3].write(c.get("email", ""))
    else:
        st.caption("No contacts yet.")


def _render_costs(api_base: str, case_id: str, http_get: Any, http_post: Any, st: Any) -> None:
    st.subheader("Cost Tracker")

    with st.expander("Add Cost Entry"):
        category = st.selectbox("Category", [
            "Sequencing", "Structure Prediction", "RNA Synthesis",
            "Lab Services", "Consultation", "Other",
        ], key="cost_category")
        desc = st.text_input("Description", key="cost_desc")
        amount = st.number_input("Amount ($)", min_value=0.0, step=10.0, key="cost_amount")
        status = st.selectbox("Status", ["estimated", "quoted", "invoiced", "paid"], key="cost_status")

        if st.button("Add Cost") and desc:
            http_post(f"{api_base}/cases/{case_id}/lab/costs", json={
                "category": category, "description": desc,
                "amount_cents": int(amount * 100), "status": status,
            })
            st.rerun()

    summary = http_get(f"{api_base}/cases/{case_id}/lab/costs").json()
    if summary.get("entry_count", 0) > 0:
        st.metric("Total Estimated Cost", summary.get("total_display", "$0.00"))
        for cat, amount_str in (summary.get("by_category") or {}).items():
            st.write(f"- **{cat}**: {amount_str}")
    else:
        st.caption("No cost entries yet.")


def _render_timeline(api_base: str, case_id: str, http_get: Any, http_post: Any, st: Any) -> None:
    st.subheader("Timeline")

    with st.expander("Add Timeline Entry"):
        title = st.text_input("Title", key="tl_title")
        owner = st.text_input("Owner", key="tl_owner")
        status = st.selectbox("Status", ["pending", "in_progress", "completed", "blocked"], key="tl_status")

        if st.button("Add Entry") and title:
            http_post(f"{api_base}/cases/{case_id}/lab/timeline", json={
                "title": title, "owner": owner, "status": status,
            })
            st.rerun()

    entries = http_get(f"{api_base}/cases/{case_id}/lab/timeline").json()
    if entries:
        for e in entries:
            status_icon = {"pending": "⏳", "in_progress": "🔄", "completed": "✅", "blocked": "🚫"}.get(e["status"], "❓")
            cols = st.columns([1, 4, 2, 2])
            cols[0].write(status_icon)
            cols[1].write(e["title"])
            cols[2].write(e.get("owner", "—"))
            cols[3].write(e.get("due_date", "—"))
    else:
        st.caption("No timeline entries yet.")


def _render_document_requests(api_base: str, case_id: str, http_get: Any, http_post: Any, st: Any) -> None:
    st.subheader("Document Requests")

    with st.expander("New Request"):
        doc_type = st.selectbox("Document Type", [
            "Veterinary consent form", "IRB approval", "Ethics review",
            "Sequencing report", "Pathology report", "MTA/Data use agreement",
            "Quality control documentation", "Other",
        ], key="doc_type")
        requested_from = st.text_input("Requested From", key="doc_from")
        notes = st.text_area("Notes", key="doc_notes")

        if st.button("Submit Request") and doc_type:
            http_post(f"{api_base}/cases/{case_id}/lab/document-requests", json={
                "document_type": doc_type, "requested_from": requested_from, "notes": notes,
            })
            st.rerun()

    requests = http_get(f"{api_base}/cases/{case_id}/lab/document-requests").json()
    if requests:
        for r in requests:
            status_color = {"pending": "🟡", "received": "🟢", "overdue": "🔴"}.get(r["status"], "⚪")
            cols = st.columns([1, 3, 2, 2])
            cols[0].write(status_color)
            cols[1].write(r["document_type"])
            cols[2].write(r.get("requested_from", "—"))
            cols[3].write(r["status"])
    else:
        st.caption("No document requests yet.")


def _render_templates_and_checklists(api_base: str, http_get: Any, st: Any) -> None:
    st.subheader("Templates & Checklists")

    checklists = http_get(f"{api_base}/lab/checklists").json()

    st.warning(checklists.get("email_privacy_warning", ""))

    with st.expander("Sequencing Provider Checklist"):
        for item in checklists.get("sequencing_provider", []):
            st.checkbox(item, key=f"seq_{item[:20]}")

    with st.expander("RNA Manufacturing Checklist"):
        for item in checklists.get("rna_manufacturing", []):
            st.checkbox(item, key=f"rna_{item[:20]}")

    with st.expander("Secure Handoff Checklist"):
        for item in checklists.get("secure_handoff", []):
            st.checkbox(item, key=f"handoff_{item[:20]}")

    with st.expander("University Outreach Template"):
        template = http_get(f"{api_base}/lab/templates/university-outreach").json()
        st.code(template.get("template", ""), language="text")
