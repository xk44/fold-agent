"""Focused render helpers for the FoldAgent case inspection panels.

This module extracts the large case inspection UI from dashboard.py into
reusable render functions:

- ``render_create_case_panel``         — case creation form
- ``render_case_inspection``           — full case inspection section

All functions accept their data as explicit arguments.  Behaviour and
``st.session_state`` keys are kept identical to the original dashboard code.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from frontend.app.audit_viewer import build_audit_action_options, filter_audit_entries, format_audit_entry_preview
from frontend.app.candidate_review_table import (
    apply_candidate_column_preset,
    build_candidate_column_presets,
    build_candidate_detail,
    build_candidate_linkout_targets,
    build_candidate_review_summary,
    filter_candidates,
    format_candidate_option,
    sort_candidates,
)
from frontend.app.data_inventory import build_case_inventory_summary, build_inventory_rows
from frontend.app.case_governance_actions import (
    build_case_delete_preview,
    build_case_redaction_preview,
    build_subject_redaction_preview,
    format_case_delete_preview,
    format_case_redaction_preview,
    format_subject_redaction_preview,
)
from frontend.app.dashboard_helpers import (
    build_case_governance_summary,
    build_provenance_summary,
    build_subject_governance_rows,
    flatten_candidate_rows,
    is_task_overdue,
    normalize_table_rows,
    parse_due_date,
    task_sort_key,
)
from frontend.app.event_stream import (
    _CTX_PREFOCUS_ARTIFACT_KEY,
    _CTX_PREFOCUS_AUTO_OPEN_KEY,
    _CTX_PREFOCUS_REPORT_KEY,
)
from frontend.app.report_preview import (
    format_bundle_preview,
    format_candidate_review_operator_summary,
    format_report_preview,
    format_structure_job_preview,
    summarize_candidate_review_operator_state,
    summarize_ethics_package_operator_state,
)
from frontend.app.structure_viewer import (
    build_compare_structure_viewer_html,
    build_structure_viewer_html,
    choose_compare_artifact,
    format_structure_artifact_option,
    format_structure_confidence_summary,
    list_structure_artifacts,
    select_structure_artifact,
    viewer_format_for_artifact,
)
from frontend.app.upload_wizard import (
    build_sample_registration_payload,
    build_subject_creation_payload,
    stage_uploaded_sample,
)
from frontend.app.variant_explorer import (
    apply_variant_column_preset,
    build_variant_column_presets,
    build_variant_detail,
    build_variant_linkout_targets,
    build_variant_review_status_options,
    filter_variants,
    flatten_variant_rows,
    format_variant_option,
    sort_variants,
)

if TYPE_CHECKING:
    from pathlib import Path

    from skills.shared.foldagent_client import FoldAgentClient


# ---------------------------------------------------------------------------
# Create case
# ---------------------------------------------------------------------------

def render_create_case_panel(
    *,
    client: FoldAgentClient,
    safe_call,
) -> None:
    """Render the case creation form."""
    st.subheader("Create case")
    with st.form("create-case"):
        species = st.selectbox("Species mode", ["demo", "dog", "human"], index=0)
        diagnosis_summary = st.text_area("Diagnosis summary", value="Synthetic demo research case")
        supervising_professional = st.text_input("Supervising professional", value="")
        create_submitted = st.form_submit_button("Create case", width="stretch")
    if create_submitted:
        created, error = safe_call(
            client.create_case,
            species=species,
            diagnosis_summary=diagnosis_summary,
            supervising_professional=supervising_professional or None,
        )
        if error:
            st.error(error)
        else:
            st.success(f"Created case {created['id']}")
            st.rerun()


# ---------------------------------------------------------------------------
# Task card renderer
# ---------------------------------------------------------------------------

def render_task_card(task: dict) -> None:
    """Render a compact task card with overdue highlight."""
    due = parse_due_date(task.get("due_date"))
    overdue = is_task_overdue(task)
    title = task.get("title") or "Untitled task"
    owner = task.get("owner") or "unassigned"
    notes = task.get("notes") or ""
    due_label = due.isoformat() if due else "none"
    prefix = "🔴 OVERDUE · " if overdue else ""
    st.markdown(
        "\n".join(
            [
                f"**{prefix}{title}**",
                f"owner: {owner}",
                f"due: {due_label}",
                f"notes: {notes or '—'}",
            ]
        )
    )
    st.caption(task["id"][:8])


# ---------------------------------------------------------------------------
# Provenance summary
# ---------------------------------------------------------------------------

def render_provenance_summary(
    client: FoldAgentClient,
    api_url: str,
    variants: list[dict] | None,
    candidates: list[dict] | None,
    safe_call,
    report_payload: dict | None = None,
    execution_select_key: str | None = None,
    execution_history: list[dict] | None = None,
) -> None:
    """Render parsed provenance metrics, scores, and traceability shortcuts."""
    from frontend.app.report_preview import format_safety_enforcement_error

    provenance = build_provenance_summary(variants, candidates)
    variant_sources = provenance["variant_sources"]
    candidate_sources = provenance["candidate_sources"]
    structure_backends = provenance["structure_backends"]
    structure_statuses = provenance["structure_statuses"]
    variant_execution_ids = provenance["variant_execution_ids"]
    candidate_execution_ids = provenance["candidate_execution_ids"]

    st.markdown("### Parsed provenance")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Variant parsed_from", ", ".join(variant_sources) if variant_sources else "mock_only")
    col2.metric("Candidate parsed_from", ", ".join(candidate_sources) if candidate_sources else "mock_only")
    col3.metric("Structure backend", ", ".join(structure_backends) if structure_backends else "mock_only")
    col4.metric("Structure status", ", ".join(structure_statuses) if structure_statuses else "mock_only")

    score_col1, score_col2, score_col3 = st.columns(3)
    score_col1.metric("Best ranking_score", provenance["best_ranking_score"])
    score_col2.metric("Best pTM", provenance["best_ptm"])
    score_col3.metric("Best ipTM", provenance["best_iptm"])

    trace_col1, trace_col2 = st.columns(2)
    trace_col1.caption("Variant parsed execution IDs")
    trace_col1.code("\n".join(variant_execution_ids) if variant_execution_ids else "none")
    trace_col2.caption("Candidate parsed execution IDs")
    trace_col2.code("\n".join(candidate_execution_ids) if candidate_execution_ids else "none")

    combined_execution_ids = provenance["combined_execution_ids"]
    if execution_select_key and combined_execution_ids:
        st.caption("Traceability shortcuts")
        shortcut_cols = st.columns(min(len(combined_execution_ids), 4))
        for idx, execution_id in enumerate(combined_execution_ids[:4]):
            with shortcut_cols[idx]:
                if st.button(f"Focus {execution_id[:8]}", key=f"focus-{execution_select_key}-{execution_id}", width="stretch"):
                    st.session_state[execution_select_key] = execution_id
                    st.rerun()

        if execution_history:
            selected_execution_id = st.session_state.get(execution_select_key) or combined_execution_ids[0]
            selected_execution = next((item for item in execution_history if item["id"] == selected_execution_id), None)
            if selected_execution and selected_execution.get("artifacts"):
                primary_artifact = selected_execution["artifacts"][0]
                st.caption("Focused execution shortcut")
                shortcut_action_col1, shortcut_action_col2 = st.columns(2)
                with shortcut_action_col1:
                    st.link_button(
                        f"Open artifact {primary_artifact['filename']}",
                        api_url.rstrip("/") + primary_artifact["download_url"],
                        width="stretch",
                    )
                with shortcut_action_col2:
                    if st.button(
                        f"Load artifact {primary_artifact['filename']}",
                        key=f"load-focused-{execution_select_key}-{selected_execution_id}",
                        width="stretch",
                    ):
                        artifact_file, artifact_file_error = safe_call(client.download_artifact, primary_artifact["path"])
                        if artifact_file_error:
                            st.error(artifact_file_error)
                        else:
                            try:
                                st.session_state[f"focused-artifact-{execution_select_key}"] = artifact_file.decode("utf-8")
                            except UnicodeDecodeError:
                                st.session_state[f"focused-artifact-{execution_select_key}"] = f"Binary artifact: {len(artifact_file)} bytes"
                cached_focused_artifact = st.session_state.get(f"focused-artifact-{execution_select_key}")
                if cached_focused_artifact is not None:
                    st.caption("Focused execution artifact content")
                    st.code(cached_focused_artifact)

    if report_payload:
        content_json = report_payload.get("content_json") or {}
        report_col1, report_col2, report_col3 = st.columns(3)
        report_col1.metric("Report top candidate", content_json.get("top_candidate_gene") or "n/a")
        report_col2.metric(
            "Report structure provenance",
            " / ".join(
                part for part in [content_json.get("structure_backend"), content_json.get("structure_status")] if part
            ) or "n/a",
        )
        report_score_parts = [
            f"rank={content_json.get('ranking_score')}" if content_json.get("ranking_score") is not None else None,
            f"pTM={content_json.get('ptm')}" if content_json.get("ptm") is not None else None,
            f"ipTM={content_json.get('iptm')}" if content_json.get("iptm") is not None else None,
        ]
        report_col3.metric("Report structure scores", " · ".join(part for part in report_score_parts if part) or "n/a")


# ---------------------------------------------------------------------------
# Main case inspection
# ---------------------------------------------------------------------------

def render_case_inspection(
    *,
    client: FoldAgentClient,
    api_url: str,
    root_dir: Path,
    cases: list[dict],
    safe_call,
    render_api_error,
    execution_history: list[dict] | None = None,
) -> None:
    """Render the full case inspection section (data inventory, tasks,
    samples, audit, variants, candidates, structure jobs, reports, artifacts).

    Args:
        client: FoldAgentClient instance.
        api_url: Base API URL for artifact link buttons.
        root_dir: Project ROOT path for upload staging.
        cases: List of case dicts from the API.
        safe_call: The dashboard's ``safe_call`` wrapper.
        render_api_error: The dashboard's ``render_api_error`` helper.
        execution_history: Execution history from pipeline section (may be None).
    """
    pipeline_case_id = st.session_state.get("pipeline-case-selector")

    with st.container():
        st.subheader("Cases")
        if not cases:
            st.info("No cases yet. Create one from the form on the left.")
        else:
            case_labels = {
                case["id"]: f"{case['species']} · {case['id'][:8]} · {case.get('diagnosis_summary') or 'no summary'}"
                for case in cases
            }
            selected_case_id = st.selectbox(
                "Select case",
                options=list(case_labels.keys()),
                format_func=lambda case_id: case_labels[case_id],
                key="inspect-case-selector",
            )
            case_detail, case_error = safe_call(client.get_case, selected_case_id)
            if case_error:
                st.error(case_error)
            else:
                _render_case_governance_panel(
                    client=client,
                    selected_case_id=selected_case_id,
                    case_detail=case_detail,
                    safe_call=safe_call,
                )

            # --- Data inventory ---
            _render_data_inventory(
                client=client,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
            )

            # --- Case tasks ---
            _render_case_tasks(
                client=client,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
            )

            # --- Sample intake ---
            _render_sample_intake(
                client=client,
                selected_case_id=selected_case_id,
                case_detail=case_detail,
                root_dir=root_dir,
                safe_call=safe_call,
            )

            # --- Audit log ---
            _render_audit_log(
                client=client,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
                inventory_data=st.session_state.get("_inv_data") or {},
                inventory_errors=st.session_state.get("_inv_errors") or {},
            )

            # --- Report generation buttons ---
            _render_report_generation(
                client=client,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
                render_api_error=render_api_error,
            )

            # --- Candidate review table + provenance ---
            _render_candidate_review(
                client=client,
                api_url=api_url,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
                execution_history=execution_history,
                pipeline_case_id=pipeline_case_id,
            )

            # --- Structure job explorer ---
            _render_structure_job_explorer(
                client=client,
                api_url=api_url,
                selected_case_id=selected_case_id,
                safe_call=safe_call,
                execution_history=execution_history,
            )

            # --- Report detail / export / artifacts ---
            _render_report_detail(
                client=client,
                api_url=api_url,
                selected_case_id=selected_case_id,
                case_detail=case_detail,
                safe_call=safe_call,
                render_api_error=render_api_error,
                execution_history=execution_history,
                pipeline_case_id=pipeline_case_id,
            )


# ---------------------------------------------------------------------------
# Data inventory
# ---------------------------------------------------------------------------

def _render_data_inventory(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    safe_call,
) -> None:
    st.markdown("### Data inventory")
    inventory_fetches = {
        "subjects": safe_call(client.list_subjects, selected_case_id),
        "samples": safe_call(client.list_samples, selected_case_id),
        "variants": safe_call(client.list_variants, selected_case_id),
        "candidates": safe_call(client.list_candidates, selected_case_id),
        "reports": safe_call(client.list_reports, selected_case_id),
        "structure_jobs": safe_call(client.list_structure_jobs, selected_case_id),
        "artifacts": safe_call(client.list_case_artifacts, selected_case_id),
        "executions": safe_call(client.list_execution_history, selected_case_id),
        "audit_entries": safe_call(client.get_audit_log, selected_case_id),
    }
    inventory_errors = {
        name: error
        for name, (_, error) in inventory_fetches.items()
        if error
    }
    if inventory_errors:
        st.error("Some inventory sources failed to load.")
        for name, error in inventory_errors.items():
            st.caption(f"{name}: {error}")
    inventory_data = {
        name: payload or []
        for name, (payload, _) in inventory_fetches.items()
    }
    # Stash for audit log (avoids double-fetch)
    st.session_state["_inv_data"] = inventory_data
    st.session_state["_inv_errors"] = inventory_errors

    inventory_summary = build_case_inventory_summary(**inventory_data)
    summary_cols = st.columns(5)
    summary_keys = [
        "subjects",
        "samples",
        "variants",
        "candidates",
        "reports",
        "artifacts",
        "structure_jobs",
        "executions",
        "audit_entries",
        "total_records",
    ]
    for idx, key in enumerate(summary_keys):
        with summary_cols[idx % len(summary_cols)]:
            st.metric(key.replace("_", " ").title(), inventory_summary[key])
    inventory_rows = build_inventory_rows(
        subjects=inventory_data["subjects"],
        samples=inventory_data["samples"],
        variants=inventory_data["variants"],
        candidates=inventory_data["candidates"],
        reports=inventory_data["reports"],
        structure_jobs=inventory_data["structure_jobs"],
        artifacts=inventory_data["artifacts"],
        executions=inventory_data["executions"],
    )
    if inventory_rows:
        st.dataframe(normalize_table_rows(inventory_rows), width="stretch")
    else:
        st.info("No inventory records for this case yet.")

    with st.expander("Inventory raw groups"):
        for key in ["subjects", "samples", "variants", "candidates", "reports", "structure_jobs", "artifacts", "executions"]:
            st.markdown(f"#### {key.replace('_', ' ').title()}")
            if inventory_data[key]:
                st.dataframe(normalize_table_rows(inventory_data[key]), width="stretch")
            else:
                st.caption("No records")


# ---------------------------------------------------------------------------
# Case governance / consent workflow
# ---------------------------------------------------------------------------

def _render_case_governance_panel(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    case_detail: dict,
    safe_call,
) -> None:
    st.markdown("### Case governance")
    subjects, subjects_error = safe_call(client.list_subjects, selected_case_id)
    if subjects_error:
        st.caption(f"subject inventory unavailable: {subjects_error}")
        subjects = []
    samples, samples_error = safe_call(client.list_samples, selected_case_id)
    if samples_error:
        st.caption(f"sample linkage unavailable: {samples_error}")
        samples = []

    summary = build_case_governance_summary(case_detail, subjects=subjects, samples=samples)
    metric_cols = st.columns(7)
    metric_cols[0].metric("Species", summary["species"])
    metric_cols[1].metric("Consent", summary["consent_status"])
    metric_cols[2].metric("Case review", summary["review_status"])
    metric_cols[3].metric("Redaction", summary["redaction_level"])
    metric_cols[4].metric("Subjects", summary["subject_count"])
    metric_cols[5].metric("Linked samples", summary["linked_sample_count"])
    metric_cols[6].metric("Redacted subjects", summary["redacted_subject_count"])

    left, right = st.columns([1.2, 1])
    with left:
        st.caption("Current case detail")
        st.json(case_detail)
        if subjects:
            subject_rows = build_subject_governance_rows(subjects, samples=samples)
            st.caption("Subject governance overview")
            st.dataframe(normalize_table_rows(subject_rows), width="stretch")
            selected_subject_id = st.selectbox(
                "Subject detail",
                options=[row["id"] for row in subject_rows],
                format_func=lambda subject_id: next(
                    (
                        f"{row['display_name']} · {row['privacy_mode']} · {row['linked_samples']} samples"
                        for row in subject_rows
                        if row["id"] == subject_id
                    ),
                    subject_id,
                ),
                key=f"subject-governance-detail-{selected_case_id}",
            )
            selected_subject_row = next((row for row in subject_rows if row["id"] == selected_subject_id), None)
            selected_subject_payload = next((subject for subject in subjects if subject.get("id") == selected_subject_id), None)
            if selected_subject_row:
                detail_metric1, detail_metric2, detail_metric3 = st.columns(3)
                detail_metric1.metric("Privacy mode", selected_subject_row["privacy_mode"])
                detail_metric2.metric("Linked samples", selected_subject_row["linked_samples"])
                detail_metric3.metric("Sample types", selected_subject_row["sample_types"] or "none")
                st.code(
                    "\n".join(
                        [
                            f"display_name: {selected_subject_row['display_name']}",
                            f"species: {selected_subject_row['species'] or 'n/a'}",
                            f"intake_notes: {selected_subject_row['intake_notes'] or 'n/a'}",
                            f"created_at: {selected_subject_row['created_at'] or 'n/a'}",
                        ]
                    )
                )
                with st.expander("Raw subject payload"):
                    st.json(selected_subject_payload or {})

                subject_redaction_options = ["full", "deidentify", "anonymous"]
                subject_current_redaction = str((selected_subject_payload or {}).get("redaction_level") or "full")
                with st.expander("Subject redaction", expanded=False):
                    with st.form(f"subject-redaction-{selected_case_id}-{selected_subject_id}"):
                        subject_redaction_level = st.selectbox(
                            "Target subject redaction level",
                            options=subject_redaction_options,
                            index=(
                                subject_redaction_options.index(subject_current_redaction)
                                if subject_current_redaction in subject_redaction_options
                                else 0
                            ),
                        )
                        subject_redaction_reason = st.text_area("Subject redaction reason", value="")
                        subject_redaction_confirm = st.checkbox(
                            "I understand this changes subject privacy state",
                            value=False,
                        )
                        subject_redaction_submit = st.form_submit_button("Apply subject redaction", width="stretch")
                    subject_redaction_preview = build_subject_redaction_preview(
                        selected_subject_payload or {},
                        redaction_level=subject_redaction_level,
                        confirm=subject_redaction_confirm,
                        reason=subject_redaction_reason,
                    )
                    st.code(format_subject_redaction_preview(subject_redaction_preview))
                    if subject_redaction_submit:
                        subject_redact_result, subject_redact_error = safe_call(
                            client.redact_subject,
                            selected_case_id,
                            selected_subject_id,
                            redaction_level=subject_redaction_level,
                            confirm=subject_redaction_confirm,
                            reason=subject_redaction_reason or None,
                        )
                        if subject_redact_error:
                            st.error(subject_redact_error)
                        else:
                            st.success(subject_redact_result.get("message") or f"Redacted subject {selected_subject_id}")
                            st.rerun()
        else:
            st.info("No subjects linked to this case yet.")

    with right:
        consent_options = ["pending", "received", "waived", "revoked", "demo"]
        review_options = ["unreviewed", "in_review", "approved", "rejected"]
        redaction_options = ["full", "deidentify", "anonymous"]
        current_consent = summary["consent_status"] if summary["consent_status"] in consent_options else "pending"
        current_review = summary["review_status"] if summary["review_status"] in review_options else "unreviewed"
        current_redaction = summary["redaction_level"] if summary["redaction_level"] in [*redaction_options, "deleted"] else "full"
        with st.form(f"case-governance-{selected_case_id}"):
            consent_status = st.selectbox(
                "Consent status",
                options=consent_options,
                index=consent_options.index(current_consent),
            )
            review_status = st.selectbox(
                "Case review status",
                options=review_options,
                index=review_options.index(current_review),
            )
            supervising_professional = st.text_input(
                "Supervising professional",
                value=summary["supervising_professional"],
            )
            diagnosis_summary = st.text_area(
                "Diagnosis summary",
                value=summary["diagnosis_summary"],
            )
            submitted = st.form_submit_button("Update case governance", width="stretch")
        if submitted:
            update_result, update_error = safe_call(
                client.update_case,
                selected_case_id,
                consent_status=consent_status,
                review_status=review_status,
                supervising_professional=supervising_professional or None,
                diagnosis_summary=diagnosis_summary or None,
            )
            if update_error:
                st.error(update_error)
            else:
                st.success(f"Updated case {update_result['id']}")
                st.rerun()

        st.divider()
        st.caption("Privacy controls")
        redaction_preview = build_case_redaction_preview(
            case_detail,
            redaction_level=current_redaction if current_redaction in redaction_options else "anonymous",
            confirm=False,
            reason="",
        )
        with st.expander("Case redaction", expanded=False):
            with st.form(f"case-redaction-{selected_case_id}"):
                redaction_level = st.selectbox(
                    "Target redaction level",
                    options=redaction_options,
                    index=redaction_options.index(current_redaction) if current_redaction in redaction_options else 0,
                )
                redaction_reason = st.text_area("Redaction reason", value="")
                redaction_confirm = st.checkbox(
                    "I understand this changes case/subject privacy state",
                    value=False,
                )
                redact_submit = st.form_submit_button("Apply case redaction", width="stretch")
            redaction_preview = build_case_redaction_preview(
                case_detail,
                redaction_level=redaction_level,
                confirm=redaction_confirm,
                reason=redaction_reason,
            )
            st.code(format_case_redaction_preview(redaction_preview))
            if redact_submit:
                redact_result, redact_error = safe_call(
                    client.redact_case,
                    selected_case_id,
                    redaction_level=redaction_level,
                    confirm=redaction_confirm,
                    reason=redaction_reason or None,
                )
                if redact_error:
                    st.error(redact_error)
                else:
                    st.success(redact_result.get("message") or f"Redacted case {selected_case_id}")
                    st.rerun()

        with st.expander("Case deletion", expanded=False):
            with st.form(f"case-delete-{selected_case_id}"):
                hard_delete = st.checkbox("Hard delete permanently removes the case", value=False)
                delete_reason = st.text_area("Deletion reason", value="")
                delete_confirm = st.checkbox(
                    "I understand this delete action is destructive",
                    value=False,
                )
                delete_submit = st.form_submit_button("Delete case", width="stretch")
            delete_preview = build_case_delete_preview(
                case_detail,
                hard_delete=hard_delete,
                confirm=delete_confirm,
                reason=delete_reason,
            )
            st.code(format_case_delete_preview(delete_preview))
            if delete_submit:
                delete_result, delete_error = safe_call(
                    client.delete_case,
                    selected_case_id,
                    confirm=delete_confirm,
                    hard_delete=hard_delete,
                    reason=delete_reason or None,
                )
                if delete_error:
                    st.error(delete_error)
                else:
                    st.success(delete_result.get("message") or f"Deleted case {selected_case_id}")
                    st.rerun()


# ---------------------------------------------------------------------------
# Case tasks
# ---------------------------------------------------------------------------

def _render_case_tasks(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    safe_call,
) -> None:
    from datetime import datetime, timezone

    st.markdown("### Case tasks")
    task_left, task_right = st.columns(2)
    with task_left:
        with st.form(f"create-task-{selected_case_id}"):
            task_title = st.text_input("Task title", value="")
            task_status = st.selectbox("Task status", ["todo", "in_progress", "done", "blocked"], index=0)
            task_owner = st.text_input("Task owner", value="")
            task_due_date = st.text_input("Task due date (ISO)", value="")
            task_notes = st.text_area("Task notes", value="")
            task_submit = st.form_submit_button("Create task", width="stretch")
        if task_submit and task_title.strip():
            payload = {
                "title": task_title,
                "status": task_status,
                "owner": task_owner or None,
                "due_date": task_due_date or None,
                "notes": task_notes or None,
            }
            task_result, task_error = safe_call(client.create_case_task, selected_case_id, **payload)
            if task_error:
                st.error(task_error)
            else:
                st.success(f"Created task {task_result['id']}")
                st.rerun()

    with task_right:
        tasks, tasks_error = safe_call(client.list_case_tasks, selected_case_id)
        if tasks_error:
            st.error(tasks_error)
        elif not tasks:
            st.info("No tasks for this case yet.")
        else:
            sorted_tasks = sorted(tasks, key=task_sort_key)
            overdue_count = sum(
                1
                for task in sorted_tasks
                if parse_due_date(task.get("due_date"))
                and parse_due_date(task.get("due_date")) < datetime.now(timezone.utc)
                and task.get("status") != "done"
            )
            task_metric1, task_metric2, task_metric3 = st.columns(3)
            task_metric1.metric("Total tasks", len(sorted_tasks))
            task_metric2.metric("Overdue", overdue_count)
            task_metric3.metric("Done", sum(1 for task in sorted_tasks if task.get("status") == "done"))

            lane_order = ["todo", "in_progress", "blocked", "done"]
            lane_columns = st.columns(len(lane_order))
            for lane, lane_col in zip(lane_order, lane_columns):
                with lane_col:
                    lane_tasks = [task for task in sorted_tasks if task.get("status") == lane]
                    st.markdown(f"#### {lane.replace('_', ' ').title()} ({len(lane_tasks)})")
                    if not lane_tasks:
                        st.caption("No tasks")
                    for task in lane_tasks:
                        render_task_card(task)
                        st.divider()

            st.markdown("#### Timeline / table")
            st.dataframe(normalize_table_rows(sorted_tasks), width="stretch")
            selected_task_id = st.selectbox(
                "Task update target",
                options=[task["id"] for task in sorted_tasks],
                format_func=lambda task_id: next((f"{task['status']} · {task['title']}" for task in sorted_tasks if task["id"] == task_id), task_id),
                key=f"task-target-{selected_case_id}",
            )
            with st.form(f"update-task-{selected_case_id}"):
                update_task_status = st.selectbox("Update task status", ["todo", "in_progress", "done", "blocked"], index=0)
                update_task_notes = st.text_area("Update task notes", value="")
                update_task_submit = st.form_submit_button("Update task", width="stretch")
            if update_task_submit:
                task_update_result, task_update_error = safe_call(
                    client.update_case_task,
                    selected_task_id,
                    status=update_task_status,
                    notes=update_task_notes or None,
                )
                if task_update_error:
                    st.error(task_update_error)
                else:
                    st.success(f"Updated task {task_update_result['id']}")
                    st.rerun()


# ---------------------------------------------------------------------------
# Sample intake
# ---------------------------------------------------------------------------

def _render_sample_intake(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    case_detail: dict | None,
    root_dir: Path,
    safe_call,
) -> None:
    sample_left, sample_right = st.columns(2)
    with sample_left:
        st.markdown("### Sample intake")
        upload_tab, manual_tab = st.tabs(["Upload wizard", "Manual path register"])

        with upload_tab:
            st.warning(
                "Upload wizard stages files locally only. Review metadata before registering. "
                "Research coordination only — not treatment use."
            )
            subjects, subjects_error = safe_call(client.list_subjects, selected_case_id)
            if subjects_error:
                st.error(subjects_error)
                subjects = []
            subject_options = ["create_new"] + [subject["id"] for subject in subjects or []]
            subject_labels = {
                "create_new": "Create new subject during intake",
                **{
                    subject["id"]: (
                        f"{subject.get('anonymized_display_name') or subject['id']} · "
                        f"{('redacted' if (subject.get('privacy_flags') or {}).get('redacted') else 'standard')} · "
                        f"{subject['id'][:8]}"
                    )
                    for subject in subjects or []
                },
            }
            with st.form(f"upload-sample-{selected_case_id}"):
                upload_sample_type = st.selectbox("Sample type", ["tumor", "normal", "rna", "other"], index=0, key=f"upload-sample-type-{selected_case_id}")
                upload_subject_mode = st.selectbox(
                    "Subject linkage",
                    options=subject_options,
                    format_func=lambda option: subject_labels.get(option, option),
                    key=f"upload-subject-mode-{selected_case_id}",
                )
                new_subject_name = st.text_input("New subject display name", value="", key=f"upload-subject-name-{selected_case_id}")
                new_subject_species = st.text_input("Subject species / note", value=case_detail.get("species") if case_detail else "", key=f"upload-subject-species-{selected_case_id}")
                privacy_mode = st.selectbox("Subject privacy mode", ["redacted", "open"], index=0, key=f"upload-privacy-mode-{selected_case_id}")
                upload_source_lab = st.text_input("Source lab", value="", key=f"upload-source-lab-{selected_case_id}")
                upload_notes = st.text_area(
                    "Chain-of-custody / intake notes",
                    value="",
                    help="Optional intake notes stored in custody metadata.",
                    key=f"upload-notes-{selected_case_id}",
                )
                uploaded_file = st.file_uploader(
                    "Upload sequencing or analysis file",
                    type=None,
                    accept_multiple_files=False,
                    key=f"upload-file-{selected_case_id}",
                )
                upload_submit = st.form_submit_button("Stage locally and register sample", width="stretch")
            if upload_submit:
                if uploaded_file is None:
                    st.error("Choose a file before registering the sample.")
                else:
                    subject_id = None
                    if upload_subject_mode == "create_new":
                        if not new_subject_name.strip():
                            st.error("Enter a subject display name or choose an existing subject.")
                            st.stop()
                        subject_payload = build_subject_creation_payload(
                            display_name=new_subject_name.strip(),
                            species=new_subject_species or None,
                            notes=upload_notes or None,
                            privacy_mode=privacy_mode,
                        )
                        subject_result, subject_error = safe_call(client.create_subject, selected_case_id, **subject_payload)
                        if subject_error:
                            st.error(subject_error)
                            st.stop()
                        subject_id = subject_result["id"]
                    else:
                        subject_id = upload_subject_mode

                    staged_upload = stage_uploaded_sample(
                        uploaded_file.getvalue(),
                        uploaded_file.name,
                        case_id=selected_case_id,
                        sample_type=upload_sample_type,
                        root_dir=root_dir / "artifacts" / "uploads",
                    )
                    payload = build_sample_registration_payload(
                        sample_type=upload_sample_type,
                        staged_upload=staged_upload,
                        source_lab=upload_source_lab or None,
                        notes=upload_notes or None,
                        subject_id=subject_id,
                    )
                    sample_result, sample_error = safe_call(client.register_sample, selected_case_id, **payload)
                    if sample_error:
                        st.error(sample_error)
                    else:
                        st.success(f"Registered sample {sample_result['id']}")
                        st.code(
                            "\n".join(
                                [
                                    f"subject_id: {subject_id or 'none'}",
                                    f"staged_path: {staged_upload['path']}",
                                    f"sha256: {staged_upload['checksum']}",
                                    f"size_bytes: {staged_upload['size_bytes']}",
                                ]
                            )
                        )
                        st.rerun()

        with manual_tab:
            with st.form(f"register-sample-{selected_case_id}"):
                sample_type = st.selectbox("Sample type", ["tumor", "normal", "rna", "other"], index=0)
                file_path = st.text_input("Primary file path", value="/tmp/demo.vcf")
                checksum = st.text_input("Checksum", value="")
                source_lab = st.text_input("Source lab", value="")
                sample_submit = st.form_submit_button("Register sample", width="stretch")
            if sample_submit:
                payload = {
                    "sample_type": sample_type,
                    "file_paths": {"primary": file_path} if file_path else None,
                    "checksum": checksum or None,
                    "source_lab": source_lab or None,
                }
                sample_result, sample_error = safe_call(client.register_sample, selected_case_id, **payload)
                if sample_error:
                    st.error(sample_error)
                else:
                    st.success(f"Registered sample {sample_result['id']}")
                    st.rerun()

    with sample_right:
        st.markdown("### Samples")
        samples, samples_error = safe_call(client.list_samples, selected_case_id)
        if samples_error:
            st.error(samples_error)
        elif not samples:
            st.info("No samples registered for this case yet.")
        else:
            st.dataframe(normalize_table_rows(samples), width="stretch")
            sample_ids = [sample["id"] for sample in samples]
            selected_sample_id = st.selectbox(
                "Sample checksum lookup",
                options=sample_ids,
                format_func=lambda sample_id: next(
                    (
                        f"{sample['sample_type']} · {sample_id[:8]} · {sample.get('source_lab') or 'unknown source'}"
                        for sample in samples
                        if sample["id"] == sample_id
                    ),
                    sample_id,
                ),
            )
            checksum_result, checksum_error = safe_call(client.get_sample_checksum, selected_sample_id)
            if checksum_error:
                st.error(checksum_error)
            else:
                st.json(checksum_result)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _render_audit_log(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    safe_call,
    inventory_data: dict,
    inventory_errors: dict,
) -> None:
    st.markdown("### Audit log")
    audit_entries = inventory_data.get("audit_entries") or []
    audit_error = inventory_errors.get("audit_entries")
    if audit_error:
        st.error(audit_error)
    elif not audit_entries:
        st.info("No audit entries for this case yet.")
    else:
        audit_filter_col1, audit_filter_col2 = st.columns([1, 1])
        with audit_filter_col1:
            selected_audit_action = st.selectbox(
                "Audit action filter",
                options=build_audit_action_options(audit_entries),
                key=f"audit-action-filter-{selected_case_id}",
            )
        with audit_filter_col2:
            audit_query = st.text_input(
                "Audit search",
                value="",
                placeholder="Search action, actor, or detail text",
                key=f"audit-query-{selected_case_id}",
            )

        filtered_audit_entries = filter_audit_entries(
            audit_entries,
            selected_action=selected_audit_action,
            query=audit_query,
        )
        audit_metric1, audit_metric2, audit_metric3 = st.columns(3)
        audit_metric1.metric("Visible entries", len(filtered_audit_entries))
        audit_metric2.metric(
            "Requires approval",
            sum(1 for entry in filtered_audit_entries if entry.get("safety_gate_result") == "requires_approval"),
        )
        audit_metric3.metric(
            "Blocked",
            sum(1 for entry in filtered_audit_entries if entry.get("safety_gate_result") == "block"),
        )

        if filtered_audit_entries:
            st.dataframe(normalize_table_rows(filtered_audit_entries), width="stretch")
            preview_target = st.selectbox(
                "Audit preview target",
                options=[entry["id"] for entry in filtered_audit_entries],
                format_func=lambda entry_id: next(
                    (
                        f"{entry.get('action')} · {entry.get('timestamp')}"
                        for entry in filtered_audit_entries
                        if entry.get("id") == entry_id
                    ),
                    entry_id,
                ),
                key=f"audit-preview-target-{selected_case_id}",
            )
            preview_entry = next((entry for entry in filtered_audit_entries if entry.get("id") == preview_target), None)
            if preview_entry:
                st.code(format_audit_entry_preview(preview_entry))
                with st.expander("Audit entry raw payload"):
                    st.json(preview_entry)
        else:
            st.info("No audit entries match the current filters.")


# ---------------------------------------------------------------------------
# Report generation buttons
# ---------------------------------------------------------------------------

def _render_report_generation(
    *,
    client: FoldAgentClient,
    selected_case_id: str,
    safe_call,
    render_api_error,
) -> None:
    st.markdown("### Reports")
    report_col1, report_col2 = st.columns(2)
    with report_col1:
        if st.button("Generate candidate review", width="stretch"):
            report_result, report_error = safe_call(client.generate_candidate_review_report, selected_case_id)
            if report_error:
                render_api_error(report_error, fallback_title="Candidate review generation blocked by safety enforcement.")
            else:
                st.success(f"Generated report {report_result['id']}")
                st.session_state["last_report_id"] = report_result["id"]
                st.rerun()
    with report_col2:
        if st.button("Generate ethics package", width="stretch"):
            report_result, report_error = safe_call(client.generate_ethics_package, selected_case_id)
            if report_error:
                render_api_error(report_error, fallback_title="Ethics package generation blocked by safety enforcement.")
            else:
                st.success(f"Generated report {report_result['id']}")
                st.session_state["last_report_id"] = report_result["id"]
                st.rerun()


# ---------------------------------------------------------------------------
# Candidate review table + provenance
# ---------------------------------------------------------------------------

def _render_candidate_review(
    *,
    client: FoldAgentClient,
    api_url: str,
    selected_case_id: str,
    safe_call,
    execution_history: list[dict] | None,
    pipeline_case_id: str | None,
) -> None:
    st.markdown("### Candidate review table")
    review_status_options = build_variant_review_status_options()
    variants, variants_error = safe_call(client.list_variants, selected_case_id)
    candidates, candidates_error = safe_call(client.list_candidates, selected_case_id)
    if not variants_error and not candidates_error:
        render_provenance_summary(
            client=client,
            api_url=api_url,
            variants=variants or [],
            candidates=candidates or [],
            safe_call=safe_call,
            execution_select_key=f"execution-viewer-{pipeline_case_id}" if pipeline_case_id else None,
            execution_history=execution_history or [],
        )
    reports_for_linkouts, _ = safe_call(client.list_reports, selected_case_id)
    artifacts_for_linkouts, _ = safe_call(client.list_case_artifacts, selected_case_id)
    structure_jobs_for_linkouts, _ = safe_call(client.list_structure_jobs, selected_case_id)
    if variants_error:
        st.error(variants_error)
    elif variants:
        st.caption("Variant explorer")
        variant_presets = build_variant_column_presets()
        variant_filter_col1, variant_filter_col2, variant_filter_col3 = st.columns(3)
        variant_filter_col4, variant_filter_col5, variant_filter_col6 = st.columns(3)
        with variant_filter_col1:
            variant_filter_status = st.selectbox(
                "Variant filter status",
                options=["all", *review_status_options],
                key=f"variant-filter-status-{selected_case_id}",
            )
        with variant_filter_col2:
            variant_gene_query = st.text_input(
                "Variant gene search",
                value="",
                key=f"variant-gene-query-{selected_case_id}",
            )
        with variant_filter_col3:
            variant_sort_key = st.selectbox(
                "Variant sort",
                options=["created_at", "gene", "protein_change", "review_status"],
                key=f"variant-sort-{selected_case_id}",
            )
        with variant_filter_col4:
            variant_vaf_min = st.number_input(
                "Variant VAF min",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.01,
                key=f"variant-vaf-min-{selected_case_id}",
            )
        with variant_filter_col5:
            variant_vaf_max = st.number_input(
                "Variant VAF max",
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.01,
                key=f"variant-vaf-max-{selected_case_id}",
            )
        with variant_filter_col6:
            variant_column_preset = st.selectbox(
                "Variant columns",
                options=list(variant_presets.keys()),
                key=f"variant-columns-{selected_case_id}",
            )
        filtered_variants = sort_variants(
            filter_variants(
                variants,
                review_status=variant_filter_status,
                gene_query=variant_gene_query,
                vaf_min=variant_vaf_min if variant_vaf_min > 0 else None,
                vaf_max=variant_vaf_max if variant_vaf_max < 1 else None,
            ),
            key=variant_sort_key,
            reverse=variant_sort_key == "created_at",
        )
        variant_rows = apply_variant_column_preset(
            flatten_variant_rows(filtered_variants),
            variant_column_preset,
        )
        if variant_rows:
            st.dataframe(normalize_table_rows(variant_rows), width="stretch")
            variant_lookup = {str(variant["id"]): variant for variant in filtered_variants}
            selected_variant_id = st.selectbox(
                "Variant review target",
                options=list(variant_lookup.keys()),
                format_func=lambda variant_id: format_variant_option(variant_lookup[variant_id]),
                key=f"variant-review-{selected_case_id}",
            )
            selected_variant = variant_lookup[selected_variant_id]
            variant_linkouts = build_variant_linkout_targets(
                selected_variant,
                candidates=candidates or [],
                reports=reports_for_linkouts or [],
                artifacts=artifacts_for_linkouts or [],
                structure_jobs=structure_jobs_for_linkouts or [],
            )
            with st.expander("Variant detail preview", expanded=False):
                st.json(build_variant_detail(selected_variant))
                link_col1, link_col2, link_col3 = st.columns(3)
                with link_col1:
                    if variant_linkouts.get("candidate_id") and st.button(
                        "Focus related candidate",
                        key=f"focus-related-candidate-{selected_case_id}-{selected_variant_id}",
                        width="stretch",
                    ):
                        st.session_state[f"candidate-filter-status-{selected_case_id}"] = "all"
                        st.session_state[f"candidate-filter-mhc-{selected_case_id}"] = "all"
                        st.session_state[f"candidate-ranking-min-{selected_case_id}"] = 0.0
                        st.session_state[f"candidate-binding-max-{selected_case_id}"] = 1.0
                        st.session_state[f"candidate-review-{selected_case_id}"] = variant_linkouts["candidate_id"]
                        st.rerun()
                with link_col2:
                    if variant_linkouts.get("structure_job_id") and st.button(
                        "Focus related structure job",
                        key=f"focus-related-structure-{selected_case_id}-{selected_variant_id}",
                        width="stretch",
                    ):
                        st.session_state[f"structure-job-{selected_case_id}"] = variant_linkouts["structure_job_id"]
                        st.rerun()
                with link_col3:
                    if variant_linkouts.get("report_id") and st.button(
                        "Focus related report",
                        key=f"focus-related-report-{selected_case_id}-{selected_variant_id}",
                        width="stretch",
                    ):
                        st.session_state[_CTX_PREFOCUS_REPORT_KEY] = variant_linkouts["report_id"]
                        st.rerun()
            with st.form(f"variant-review-form-{selected_case_id}"):
                current_variant_status = str(selected_variant.get("review_status") or "unreviewed")
                variant_status = st.selectbox(
                    "Variant review status",
                    review_status_options,
                    index=(
                        review_status_options.index(current_variant_status)
                        if current_variant_status in review_status_options
                        else 0
                    ),
                )
                variant_note = st.text_input(
                    "Variant note",
                    value=str(selected_variant.get("expert_review_notes") or ""),
                )
                variant_submit = st.form_submit_button("Update variant review", width="stretch")
            if variant_submit:
                variant_result, variant_error = safe_call(
                    client.review_variant,
                    selected_variant_id,
                    variant_status,
                    variant_note,
                )
                if variant_error:
                    st.error(variant_error)
                else:
                    st.success(f"Updated variant {variant_result['id']}")
                    st.rerun()
        else:
            st.info("No variants match the current filters.")

    if candidates_error:
        st.error(candidates_error)
    elif candidates:
        candidate_summary = build_candidate_review_summary(candidates)
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        metric_col1.metric("Candidates", candidate_summary["total"])
        metric_col2.metric("Unreviewed", candidate_summary["by_status"].get("unreviewed", 0))
        metric_col3.metric("Needs data", candidate_summary["by_status"].get("needs_data", 0))
        metric_col4.metric("Best ranking", candidate_summary["best_ranking_score"])
        candidate_presets = build_candidate_column_presets()
        candidate_filter_col1, candidate_filter_col2, candidate_filter_col3 = st.columns(3)
        candidate_filter_col4, candidate_filter_col5, candidate_filter_col6 = st.columns(3)
        candidate_mhc_options = [
            "all",
            *sorted(
                {
                    str(candidate.get("mhc_context"))
                    for candidate in candidates
                    if candidate.get("mhc_context")
                }
            ),
        ]
        with candidate_filter_col1:
            candidate_filter_status = st.selectbox(
                "Candidate filter status",
                options=["all", *review_status_options],
                key=f"candidate-filter-status-{selected_case_id}",
            )
        with candidate_filter_col2:
            candidate_filter_mhc = st.selectbox(
                "Candidate MHC filter",
                options=candidate_mhc_options,
                key=f"candidate-filter-mhc-{selected_case_id}",
            )
        with candidate_filter_col3:
            candidate_sort_key = st.selectbox(
                "Candidate sort",
                options=["ranking_score", "binding_rank", "review_status"],
                key=f"candidate-sort-{selected_case_id}",
            )
        with candidate_filter_col4:
            candidate_ranking_min = st.number_input(
                "Candidate ranking min",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.01,
                key=f"candidate-ranking-min-{selected_case_id}",
            )
        with candidate_filter_col5:
            candidate_binding_max = st.number_input(
                "Candidate binding max",
                min_value=0.0,
                max_value=1.0,
                value=1.0,
                step=0.01,
                key=f"candidate-binding-max-{selected_case_id}",
            )
        with candidate_filter_col6:
            candidate_column_preset = st.selectbox(
                "Candidate columns",
                options=list(candidate_presets.keys()),
                key=f"candidate-columns-{selected_case_id}",
            )
        filtered_candidates = sort_candidates(
            filter_candidates(
                candidates,
                review_status=candidate_filter_status,
                mhc_context=candidate_filter_mhc,
                ranking_score_min=candidate_ranking_min if candidate_ranking_min > 0 else None,
                binding_rank_max=candidate_binding_max if candidate_binding_max < 1 else None,
            ),
            sort_key=candidate_sort_key,
            reverse=candidate_sort_key == "ranking_score",
        )
        candidate_rows = apply_candidate_column_preset(
            flatten_candidate_rows(filtered_candidates),
            candidate_column_preset,
        )
        if candidate_rows:
            st.dataframe(normalize_table_rows(candidate_rows), width="stretch")
            candidate_lookup = {str(candidate["id"]): candidate for candidate in filtered_candidates}
            selected_candidate_id = st.selectbox(
                "Candidate review target",
                options=list(candidate_lookup.keys()),
                format_func=lambda candidate_id: format_candidate_option(candidate_lookup[candidate_id]),
                key=f"candidate-review-{selected_case_id}",
            )
            selected_candidate = candidate_lookup[selected_candidate_id]
            candidate_linkouts = build_candidate_linkout_targets(
                selected_candidate,
                reports=reports_for_linkouts or [],
                artifacts=artifacts_for_linkouts or [],
                structure_jobs=structure_jobs_for_linkouts or [],
            )
            with st.expander("Candidate detail preview", expanded=False):
                st.json(build_candidate_detail(selected_candidate))
                link_col1, link_col2, link_col3 = st.columns(3)
                with link_col1:
                    if candidate_linkouts.get("report_id") and st.button(
                        "Focus candidate review report",
                        key=f"focus-candidate-report-{selected_case_id}-{selected_candidate_id}",
                        width="stretch",
                    ):
                        st.session_state[_CTX_PREFOCUS_REPORT_KEY] = candidate_linkouts["report_id"]
                        st.rerun()
                with link_col2:
                    if candidate_linkouts.get("artifact_path") and st.button(
                        "Focus candidate artifact",
                        key=f"focus-candidate-artifact-{selected_case_id}-{selected_candidate_id}",
                        width="stretch",
                    ):
                        st.session_state[_CTX_PREFOCUS_ARTIFACT_KEY] = candidate_linkouts["artifact_path"]
                        st.session_state[_CTX_PREFOCUS_AUTO_OPEN_KEY] = {
                            "auto_open": True,
                            "case_id": selected_case_id,
                            "artifact_path": candidate_linkouts["artifact_path"],
                        }
                        st.rerun()
                with link_col3:
                    if candidate_linkouts.get("structure_job_id") and st.button(
                        "Focus structure job",
                        key=f"focus-structure-job-{selected_case_id}-{selected_candidate_id}",
                        width="stretch",
                    ):
                        st.session_state[f"structure-job-{selected_case_id}"] = candidate_linkouts["structure_job_id"]
                        st.rerun()
            with st.form(f"candidate-review-form-{selected_case_id}"):
                current_candidate_status = str(selected_candidate.get("review_status") or "unreviewed")
                candidate_status = st.selectbox(
                    "Candidate review status",
                    review_status_options,
                    index=(
                        review_status_options.index(current_candidate_status)
                        if current_candidate_status in review_status_options
                        else 0
                    ),
                )
                candidate_note = st.text_input(
                    "Candidate note",
                    value=str(selected_candidate.get("expert_review_notes") or ""),
                )
                candidate_submit = st.form_submit_button("Update candidate review", width="stretch")
            if candidate_submit:
                candidate_result, candidate_error = safe_call(
                    client.review_candidate,
                    selected_candidate_id,
                    candidate_status,
                    candidate_note,
                )
                if candidate_error:
                    st.error(candidate_error)
                else:
                    st.success(f"Updated candidate {candidate_result['id']}")
                    st.rerun()
        else:
            st.info("No candidates match the current filters.")


# ---------------------------------------------------------------------------
# Structure job explorer
# ---------------------------------------------------------------------------

def _render_structure_job_explorer(
    *,
    client: FoldAgentClient,
    api_url: str,
    selected_case_id: str,
    safe_call,
    execution_history: list[dict] | None,
) -> None:
    st.markdown("### Structure job explorer")
    structure_jobs, structure_jobs_error = safe_call(client.list_structure_jobs, selected_case_id)
    if structure_jobs_error:
        st.error(structure_jobs_error)
    elif not structure_jobs:
        st.info("No structure jobs for this case yet.")
    else:
        st.dataframe(normalize_table_rows(structure_jobs), width="stretch")
        selected_structure_job_id = st.selectbox(
            "Structure job detail",
            options=[job["id"] for job in structure_jobs],
            format_func=lambda job_id: next(
                (
                    f"{job.get('backend_used')} · {job.get('status')} · {job_id[:8]}"
                    for job in structure_jobs
                    if job["id"] == job_id
                ),
                job_id,
            ),
            key=f"structure-job-{selected_case_id}",
        )
        structure_job_detail, structure_job_detail_error = safe_call(client.get_structure_job, selected_structure_job_id)
        if structure_job_detail_error:
            st.error(structure_job_detail_error)
        else:
            related_execution = next(
                (
                    item
                    for item in (execution_history or [])
                    if item.get("runner_name") == structure_job_detail.get("backend_used")
                    and item.get("status") == structure_job_detail.get("status")
                ),
                None,
            )
            st.caption("Readable structure job preview")
            st.code(format_structure_job_preview(structure_job_detail))
            with st.expander("Raw structure job payload"):
                st.json(structure_job_detail)
            structure_artifacts = list_structure_artifacts((related_execution or {}).get("artifacts"))
            structure_artifact = select_structure_artifact(structure_artifacts)
            if structure_artifact:
                st.caption("Interactive 3D structure viewer")
                selected_structure_artifact = st.selectbox(
                    "Structure artifact",
                    options=structure_artifacts,
                    index=next(
                        (
                            idx
                            for idx, artifact in enumerate(structure_artifacts)
                            if artifact.get("path") == st.session_state.get(f"structure-viewer-path-{selected_structure_job_id}")
                        ),
                        next(
                            idx
                            for idx, artifact in enumerate(structure_artifacts)
                            if artifact.get("path") == structure_artifact.get("path")
                        ),
                    ),
                    format_func=lambda artifact: format_structure_artifact_option(artifact, structure_job_detail),
                    key=f"structure-artifact-picker-{selected_structure_job_id}",
                )
                st.session_state[f"structure-viewer-path-{selected_structure_job_id}"] = selected_structure_artifact.get("path")
                structure_format = viewer_format_for_artifact(selected_structure_artifact, structure_job_detail)
                overlay = format_structure_confidence_summary(structure_job_detail)
                viewer_col1, viewer_col2, viewer_col3, viewer_col4 = st.columns(4)
                viewer_col1.metric("Viewer artifact", selected_structure_artifact.get("filename") or "n/a")
                viewer_col2.metric("Viewer format", structure_format)
                viewer_col3.metric("Ranking score", overlay["ranking_score"])
                viewer_col4.metric("Output format", overlay["output_format"])
                confidence_col1, confidence_col2, confidence_col3 = st.columns(3)
                confidence_col1.metric("pTM", overlay["ptm"])
                confidence_col2.metric("ipTM", overlay["iptm"])
                confidence_col3.metric("Model path", overlay["model_path"])
                st.caption(f"Source URL: {overlay['source_url']}")
                compare_artifact = choose_compare_artifact(structure_artifacts, selected_structure_artifact)
                compare_enabled = st.toggle(
                    "Compare mode",
                    value=bool(compare_artifact and st.session_state.get(f"structure-compare-enabled-{selected_structure_job_id}")),
                    key=f"structure-compare-enabled-{selected_structure_job_id}",
                )
                selected_compare_artifact = None
                compare_candidates = [artifact for artifact in structure_artifacts if artifact.get("path") != selected_structure_artifact.get("path")]
                if compare_candidates:
                    selected_compare_artifact = st.selectbox(
                        "Compare against",
                        options=compare_candidates,
                        index=next(
                            (
                                idx
                                for idx, artifact in enumerate(compare_candidates)
                                if artifact.get("path") == st.session_state.get(f"structure-compare-path-{selected_structure_job_id}")
                            ),
                            0,
                        ),
                        format_func=lambda artifact: format_structure_artifact_option(artifact, structure_job_detail),
                        key=f"structure-compare-picker-{selected_structure_job_id}",
                        disabled=not compare_enabled,
                    )
                if st.button("Load 3D structure", key=f"load-structure-viewer-{selected_structure_job_id}", width="stretch"):
                    artifact_file, artifact_file_error = safe_call(client.download_artifact, selected_structure_artifact["path"])
                    if artifact_file_error:
                        st.error(artifact_file_error)
                    else:
                        try:
                            st.session_state[f"structure-viewer-text-{selected_structure_job_id}"] = artifact_file.decode("utf-8")
                            st.session_state[f"structure-viewer-format-{selected_structure_job_id}"] = structure_format
                            st.session_state[f"structure-viewer-path-{selected_structure_job_id}"] = selected_structure_artifact.get("path")
                            if compare_enabled and selected_compare_artifact:
                                compare_file, compare_file_error = safe_call(client.download_artifact, selected_compare_artifact["path"])
                                if compare_file_error:
                                    st.error(compare_file_error)
                                else:
                                    try:
                                        st.session_state[f"structure-compare-text-{selected_structure_job_id}"] = compare_file.decode("utf-8")
                                        st.session_state[f"structure-compare-format-{selected_structure_job_id}"] = viewer_format_for_artifact(selected_compare_artifact, structure_job_detail)
                                        st.session_state[f"structure-compare-path-{selected_structure_job_id}"] = selected_compare_artifact.get("path")
                                    except UnicodeDecodeError:
                                        st.error("Compare artifact is not UTF-8 text; viewer expects PDB/mmCIF text.")
                        except UnicodeDecodeError:
                            st.error("Structure artifact is not UTF-8 text; viewer expects PDB/mmCIF text.")
                cached_structure_text = st.session_state.get(f"structure-viewer-text-{selected_structure_job_id}")
                cached_structure_format = st.session_state.get(f"structure-viewer-format-{selected_structure_job_id}")
                cached_compare_text = st.session_state.get(f"structure-compare-text-{selected_structure_job_id}")
                cached_compare_format = st.session_state.get(f"structure-compare-format-{selected_structure_job_id}")
                if compare_enabled and cached_structure_text and cached_structure_format and cached_compare_text and cached_compare_format and selected_compare_artifact:
                    st.iframe(
                        build_compare_structure_viewer_html(
                            left_structure_text=cached_structure_text,
                            left_format=cached_structure_format,
                            left_label=selected_structure_artifact.get("filename") or "left",
                            right_structure_text=cached_compare_text,
                            right_format=cached_compare_format,
                            right_label=selected_compare_artifact.get("filename") or "right",
                        ),
                        height=560,
                    )
                elif cached_structure_text and cached_structure_format:
                    st.iframe(
                        build_structure_viewer_html(cached_structure_text, cached_structure_format),
                        height=560,
                    )
            else:
                st.info("No downloadable PDB/mmCIF artifact linked to this structure job yet.")
            if related_execution and related_execution.get("artifacts"):
                st.caption("Linked execution artifacts")
                st.dataframe(normalize_table_rows(related_execution["artifacts"]), width="stretch")


# ---------------------------------------------------------------------------
# Report detail / export / bundle / artifacts
# ---------------------------------------------------------------------------

def _render_report_detail(
    *,
    client: FoldAgentClient,
    api_url: str,
    selected_case_id: str,
    case_detail: dict,
    safe_call,
    render_api_error,
    execution_history: list[dict] | None,
    pipeline_case_id: str | None,
) -> None:
    reports, reports_error = safe_call(client.list_reports, selected_case_id)
    variants, _ = safe_call(client.list_variants, selected_case_id)
    candidates, _ = safe_call(client.list_candidates, selected_case_id)

    if reports_error:
        st.error(reports_error)
    elif not reports:
        st.info("No reports generated for this case yet.")
    else:
        st.dataframe(normalize_table_rows(reports), width="stretch")
        report_ids = [report["id"] for report in reports]
        # Prefocus: if a chip set a target report, select it by index
        prefocus_report_id = st.session_state.pop(_CTX_PREFOCUS_REPORT_KEY, None)
        default_report_index = (
            next((i for i, rid in enumerate(report_ids) if rid == prefocus_report_id), 0)
            if prefocus_report_id and prefocus_report_id in report_ids
            else 0
        )
        selected_report_id = st.selectbox(
            "Report detail/export",
            options=report_ids,
            index=default_report_index,
            format_func=lambda report_id: next(
                (
                    f"{report['report_type']} · {report_id[:8]}"
                    for report in reports
                    if report["id"] == report_id
                ),
                report_id,
            ),
            key=f"report-detail-{selected_case_id}",
        )
        report_payload, report_payload_error = safe_call(client.get_report, selected_report_id)
        if report_payload_error:
            st.error(report_payload_error)
        else:
            render_provenance_summary(
                client=client,
                api_url=api_url,
                variants=variants or [],
                candidates=candidates or [],
                safe_call=safe_call,
                report_payload=report_payload,
                execution_select_key=f"execution-viewer-{pipeline_case_id}" if pipeline_case_id else None,
                execution_history=execution_history or [],
            )
            if report_payload.get("report_type") == "ethics_package":
                ethics_summary = summarize_ethics_package_operator_state(report_payload, case_detail=case_detail)
                ethics_metric1, ethics_metric2, ethics_metric3, ethics_metric4 = st.columns(4)
                ethics_metric1.metric("Consent status", ethics_summary["consent_status"])
                ethics_metric2.metric("Case review", ethics_summary["review_status"])
                ethics_metric3.metric("Consent templates", ethics_summary["consent_template_count"])
                ethics_metric4.metric("Oversight items", ethics_summary["oversight_item_count"])
                if ethics_summary["needs_consent_attention"]:
                    st.warning("Ethics package needs consent follow-through before operator signoff.")
                if ethics_summary["needs_review_attention"]:
                    st.warning("Case review status is not yet in review/approved for this ethics package.")
                if not ethics_summary["species_matches_case"]:
                    st.error(
                        f"Ethics package species ({ethics_summary['report_species']}) does not match case species ({ethics_summary['case_species']})."
                    )
                st.caption("Ethics governance summary")
                st.dataframe(
                    normalize_table_rows(
                        [
                            {
                                "consent_status": ethics_summary["consent_status"],
                                "review_status": ethics_summary["review_status"],
                                "consent_templates": ethics_summary["consent_template_count"],
                                "privacy_notices": ethics_summary["privacy_notice_count"],
                                "risks": ethics_summary["risk_count"],
                                "benefits": ethics_summary["benefit_count"],
                                "oversight_items": ethics_summary["oversight_item_count"],
                                "jurisdiction_warning": ethics_summary["jurisdiction_warning"],
                            }
                        ]
                    ),
                    width="stretch",
                )
            if report_payload.get("report_type") == "candidate_review":
                cr_summary = summarize_candidate_review_operator_state(report_payload, case_detail=case_detail)
                cr_metric1, cr_metric2, cr_metric3, cr_metric4 = st.columns(4)
                cr_metric1.metric("Review status", cr_summary["review_status"])
                cr_metric2.metric("Candidates", cr_summary["candidate_count"])
                cr_metric3.metric("Top gene", cr_summary["top_candidate_gene"])
                cr_metric4.metric("Structure", cr_summary["structure_status"])
                if cr_summary["needs_review_attention"]:
                    st.warning("Candidate review status needs attention before operator signoff.")
                if cr_summary["needs_structure_attention"]:
                    st.warning("Structure evidence is incomplete or not yet completed for this candidate review.")
                if not cr_summary["species_matches_case"]:
                    st.error(
                        f"Report species ({cr_summary['report_species']}) does not match case species ({cr_summary['case_species']})."
                    )
                st.caption("Candidate review governance summary")
                st.dataframe(
                    normalize_table_rows(
                        [
                            {
                                "review_status": cr_summary["review_status"],
                                "candidate_count": cr_summary["candidate_count"],
                                "top_gene": cr_summary["top_candidate_gene"],
                                "structure_backend": cr_summary["structure_backend"],
                                "safety_labels": cr_summary["safety_label_count"],
                                "missing_data_items": cr_summary["missing_data_count"],
                                "ranking_score": cr_summary["ranking_score"],
                                "ptm": cr_summary["ptm"],
                                "iptm": cr_summary["iptm"],
                            }
                        ]
                    ),
                    width="stretch",
                )
                st.code(format_candidate_review_operator_summary(cr_summary))
            st.caption("Readable report preview")
            st.code(format_report_preview(report_payload))
            with st.expander("Raw report payload"):
                st.json(report_payload)
            export_format = st.radio(
                "Export format",
                options=["markdown", "json"],
                horizontal=True,
                key=f"export-format-{selected_case_id}",
            )
            export_col1, export_col2 = st.columns(2)
            with export_col1:
                if st.button("Load export", key=f"load-export-{selected_case_id}", width="stretch"):
                    export_payload, export_error = safe_call(client.export_report, selected_report_id, export_format)
                    if export_error:
                        render_api_error(export_error, fallback_title="Report export blocked by safety enforcement.")
                    else:
                        st.session_state[f"export-payload-{selected_case_id}"] = export_payload
            with export_col2:
                if st.button("Save export", key=f"save-export-{selected_case_id}", width="stretch"):
                    saved_export, saved_export_error = safe_call(client.save_report, selected_report_id, export_format)
                    if saved_export_error:
                        render_api_error(saved_export_error, fallback_title="Saving report export was blocked by safety enforcement.")
                    else:
                        st.session_state[f"saved-export-{selected_case_id}"] = saved_export
            cached_export_payload = st.session_state.get(f"export-payload-{selected_case_id}")
            if cached_export_payload is not None:
                st.caption("Export payload")
                if cached_export_payload.get("format") == "markdown":
                    st.code(cached_export_payload.get("content_text") or "")
                elif cached_export_payload.get("format") == "json":
                    if selected_report_id and report_payload_error is None and report_payload:
                        st.code(format_report_preview(report_payload))
                    with st.expander("Raw export payload"):
                        st.json(cached_export_payload)
            saved_export_payload = st.session_state.get(f"saved-export-{selected_case_id}")
            if saved_export_payload is not None:
                st.caption("Saved export artifact")
                st.json(saved_export_payload)

            if st.button("Load case bundle", key=f"load-bundle-{selected_case_id}", width="stretch"):
                bundle_payload, bundle_error = safe_call(client.get_case_bundle, selected_case_id)
                if bundle_error:
                    st.error(bundle_error)
                else:
                    st.session_state[f"bundle-payload-{selected_case_id}"] = bundle_payload
            cached_bundle_payload = st.session_state.get(f"bundle-payload-{selected_case_id}")
            if cached_bundle_payload is not None:
                st.caption("Case bundle")
                bundle_metric1, bundle_metric2, bundle_metric3, bundle_metric4 = st.columns(4)
                bundle_metric1.metric("Samples", len(cached_bundle_payload.get("samples", [])))
                bundle_metric2.metric("Variants", len(cached_bundle_payload.get("variants", [])))
                bundle_metric3.metric("Candidates", len(cached_bundle_payload.get("candidates", [])))
                bundle_metric4.metric("Reports", len(cached_bundle_payload.get("reports", [])))
                st.caption("Readable bundle preview")
                st.code(format_bundle_preview(cached_bundle_payload))
                with st.expander("Raw case bundle"):
                    st.json(cached_bundle_payload)
                bundle_export_format = st.radio(
                    "Bundle export format",
                    options=["markdown", "json"],
                    horizontal=True,
                    key=f"bundle-export-format-{selected_case_id}",
                )
                bundle_export_col1, bundle_export_col2 = st.columns(2)
                with bundle_export_col1:
                    if st.button("Load bundle export", key=f"load-bundle-export-{selected_case_id}", width="stretch"):
                        bundle_export_payload, bundle_export_error = safe_call(
                            client.export_case_bundle,
                            selected_case_id,
                            bundle_export_format,
                        )
                        if bundle_export_error:
                            render_api_error(bundle_export_error, fallback_title="Bundle export blocked by safety enforcement.")
                        else:
                            st.session_state[f"bundle-export-payload-{selected_case_id}"] = bundle_export_payload
                with bundle_export_col2:
                    if st.button("Save bundle export", key=f"save-bundle-export-{selected_case_id}", width="stretch"):
                        saved_bundle_export, saved_bundle_export_error = safe_call(
                            client.save_case_bundle,
                            selected_case_id,
                            bundle_export_format,
                        )
                        if saved_bundle_export_error:
                            render_api_error(saved_bundle_export_error, fallback_title="Saving bundle export was blocked by safety enforcement.")
                        else:
                            st.session_state[f"saved-bundle-export-{selected_case_id}"] = saved_bundle_export
                cached_bundle_export_payload = st.session_state.get(f"bundle-export-payload-{selected_case_id}")
                if cached_bundle_export_payload is not None:
                    st.caption("Bundle export payload")
                    if cached_bundle_export_payload.get("format") == "markdown":
                        st.code(cached_bundle_export_payload.get("content_text") or "")
                    elif cached_bundle_export_payload.get("format") == "json":
                        if cached_bundle_payload is not None:
                            st.code(format_bundle_preview(cached_bundle_payload))
                        with st.expander("Raw bundle export payload"):
                            st.json(cached_bundle_export_payload)
                saved_bundle_export_payload = st.session_state.get(f"saved-bundle-export-{selected_case_id}")
                if saved_bundle_export_payload is not None:
                    st.caption("Saved bundle artifact")
                    st.json(saved_bundle_export_payload)

                artifacts, artifacts_error = safe_call(client.list_case_artifacts, selected_case_id)
                if artifacts_error:
                    st.error(artifacts_error)
                elif artifacts:
                    st.caption("Saved artifacts")
                    st.dataframe(normalize_table_rows(artifacts), width="stretch")
                    # Prefocus: if a chip set a target artifact path, select it by index
                    prefocus_artifact_path = st.session_state.pop(_CTX_PREFOCUS_ARTIFACT_KEY, None)
                    # Auto-open: if macro focus signalled an exact single artifact, mark it
                    prefocus_auto_open = st.session_state.pop(_CTX_PREFOCUS_AUTO_OPEN_KEY, None)
                    default_artifact_index = (
                        next((i for i, a in enumerate(artifacts) if a.get("path") == prefocus_artifact_path), 0)
                        if prefocus_artifact_path
                        else 0
                    )
                    selected_artifact = st.selectbox(
                        "Artifact download target",
                        options=artifacts,
                        index=default_artifact_index,
                        format_func=lambda artifact: f"{artifact['artifact_type']} · {artifact['format']} · {artifact['filename']}",
                        key=f"artifact-download-{selected_case_id}",
                    )
                    meta_col1, meta_col2, meta_col3 = st.columns(3)
                    meta_col1.metric("File size", selected_artifact["file_size"])
                    meta_col2.metric("MIME type", selected_artifact["mime_type"])
                    meta_col3.metric("Saved at", selected_artifact["saved_at"])
                    # Auto-open: if a single unambiguous artifact was derivable from
                    # macro focus and its path matches the selected artifact, load
                    # content directly without requiring a second click.
                    should_auto_open = (
                        prefocus_auto_open is not None
                        and prefocus_auto_open.get("auto_open")
                        and prefocus_auto_open.get("case_id") == selected_case_id
                        and prefocus_auto_open.get("artifact_path") == selected_artifact.get("path")
                        and f"artifact-file-{selected_case_id}" not in st.session_state
                    )
                    if should_auto_open:
                        artifact_file, artifact_file_error = safe_call(client.download_artifact, selected_artifact["path"])
                        if artifact_file_error:
                            st.error(artifact_file_error)
                        else:
                            try:
                                st.session_state[f"artifact-file-{selected_case_id}"] = artifact_file.decode("utf-8")
                            except UnicodeDecodeError:
                                st.session_state[f"artifact-file-{selected_case_id}"] = f"Binary artifact: {len(artifact_file)} bytes"
                    artifact_download_col1, artifact_download_col2 = st.columns(2)
                    with artifact_download_col1:
                        st.link_button("Open artifact URL", api_url.rstrip("/") + selected_artifact["download_url"], width="stretch")
                    with artifact_download_col2:
                        if st.button("Load artifact file", key=f"load-artifact-file-{selected_case_id}", width="stretch"):
                            artifact_file, artifact_file_error = safe_call(client.download_artifact, selected_artifact["path"])
                            if artifact_file_error:
                                st.error(artifact_file_error)
                            else:
                                try:
                                    st.session_state[f"artifact-file-{selected_case_id}"] = artifact_file.decode("utf-8")
                                except UnicodeDecodeError:
                                    st.session_state[f"artifact-file-{selected_case_id}"] = f"Binary artifact: {len(artifact_file)} bytes"
                    cached_artifact_file = st.session_state.get(f"artifact-file-{selected_case_id}")
                    if cached_artifact_file is not None:
                        st.caption("Artifact file content")
                        st.code(cached_artifact_file)