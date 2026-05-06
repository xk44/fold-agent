"""Data loading and validation panels for the Streamlit dashboard.

Renders file validation, sample role detection, missing-data checklist,
and data inventory for a case.
"""

from __future__ import annotations

from typing import Any


def render_data_loading_section(
    api_base: str,
    case_id: str | None,
    http_get: Any,
    http_post: Any,
    st: Any,
) -> None:
    st.header("Data Loading & Validation")

    if case_id is None:
        st.info("Select a case to manage data.")
        return

    tab_checklist, tab_validate, tab_inventory = st.tabs(
        ["Missing Data Checklist", "File Validation", "Data Inventory"]
    )

    with tab_checklist:
        _render_missing_data(api_base, case_id, http_get, st)

    with tab_validate:
        _render_file_validation(api_base, http_post, st)

    with tab_inventory:
        _render_data_report(api_base, case_id, http_get, st)


def _render_missing_data(api_base: str, case_id: str, http_get: Any, st: Any) -> None:
    st.subheader("Missing Data Checklist")

    checklist = http_get(f"{api_base}/cases/{case_id}/data/checklist").json()

    for item in checklist:
        icon = "✅" if item["done"] else ("🔴" if item["priority"] == "high" else "🟡")
        st.write(
            f"{icon} {'~~' if item['done'] else ''}{item['item']}{'~~' if item['done'] else ''}"
        )

    report = http_get(f"{api_base}/cases/{case_id}/data/missing").json()

    if report.get("issues"):
        st.error("**Issues:**")
        for issue in report["issues"]:
            st.write(f"- {issue}")

    if report.get("warnings"):
        st.warning("**Warnings:**")
        for warning in report["warnings"]:
            st.write(f"- {warning}")

    if report.get("data_completeness") == "complete":
        st.success("All required data is present.")


def _render_file_validation(api_base: str, http_post: Any, st: Any) -> None:
    st.subheader("File Validation")

    filename = st.text_input("Filename to validate", placeholder="e.g. tumor_R1.fastq.gz")

    if st.button("Validate") and filename:
        result = http_post(f"{api_base}/data/validate-file", json={"filename": filename}).json()
        if result["valid"]:
            st.success(f"Valid **{result['detected_format']}** file")
        else:
            st.error(result["error"])

    role_filename = st.text_input(
        "Detect sample role from filename", placeholder="e.g. matched_normal.bam", key="role_input"
    )
    if st.button("Detect Role") and role_filename:
        result = http_post(f"{api_base}/data/detect-role", json={"filename": role_filename}).json()
        st.info(f"Detected role: **{result['detected_role']}**")


def _render_data_report(api_base: str, case_id: str, http_get: Any, st: Any) -> None:
    st.subheader("Data Inventory")

    report = http_get(f"{api_base}/cases/{case_id}/data/missing").json()

    cols = st.columns(4)
    cols[0].metric("Samples", report.get("sample_count", 0))
    cols[1].metric("Variants", report.get("variant_count", 0))
    cols[2].metric("Candidates", report.get("candidate_count", 0))
    cols[3].metric("Structure Jobs", report.get("structure_job_count", 0))

    sample_types = report.get("sample_types", [])
    if sample_types:
        st.write(f"**Sample types:** {', '.join(sample_types)}")

    status = report.get("data_completeness", "unknown")
    if status == "complete":
        st.success("Data completeness: Complete")
    else:
        st.warning("Data completeness: Incomplete — see checklist above")
