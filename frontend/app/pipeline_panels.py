"""Focused render helpers for the FoldAgent pipeline & AlphaFold panels.

This module extracts the large pipeline / AlphaFold UI surfaces from
dashboard.py into reusable render functions:

- ``render_alphafold_diagnostics`` — backend diagnostics overview
- ``render_pipeline_section``      — pipeline case selector, status, shell
                                    panels, execution history, unified runs,
                                    and pipeline history

All functions accept their data as explicit arguments (no hidden
``st.session_state`` reads except where the original dashboard code
already did).  The goal is to keep behaviour identical while making
dashboard.py shorter and each surface independently testable.

Only Streamlit render helpers — pure logic stays in report_preview.py
and event_stream.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from frontend.app.report_preview import (
    build_alphafold_backend_capability_chips,
    build_alphafold_backend_form_state,
    build_alphafold_inline_troubleshooting_chips,
    build_alphafold_invalid_backend_rows,
    build_alphafold_recommended_switch_state,
    build_alphafold_run_form_transition,
    build_alphafold_run_payload_preview,
    build_alphafold_submission_gate,
    choose_default_alphafold_backend,
    extract_backend_capability_table,
    format_alphafold_backend_form_guidance,
    format_alphafold_backend_option_label,
    format_alphafold_diagnostics_metrics,
    format_alphafold_diagnostics_preview,
    format_alphafold_dry_run_preview,
    format_alphafold_operator_summary,
    format_alphafold_troubleshooting_summary,
    format_alphafold_validation_error,
    format_safety_enforcement_error,
    summarize_alphafold_operator_status,
    summarize_alphafold_recommended_backend,
)
from frontend.app.dashboard_helpers import normalize_table_rows

from skills.shared.foldagent_client import AlphaFoldValidationError, SafetyEnforcementError

if TYPE_CHECKING:
    from skills.shared.foldagent_client import FoldAgentClient


# ---------------------------------------------------------------------------
# AlphaFold backend diagnostics
# ---------------------------------------------------------------------------

def render_alphafold_diagnostics(
    alphafold_backends: dict | None,
    alphafold_backends_error: str | None,
) -> None:
    """Render the AlphaFold backend diagnostics panel.

    Args:
        alphafold_backends: Dict of backend name → payload (or None).
        alphafold_backends_error: Error string if the API call failed.
    """
    st.subheader("AlphaFold backend diagnostics")
    if alphafold_backends_error:
        st.error(alphafold_backends_error)
    elif alphafold_backends:
        operator_status = summarize_alphafold_operator_status(alphafold_backends)
        metrics = format_alphafold_diagnostics_metrics(alphafold_backends)
        metric_columns = st.columns(len(metrics))
        for column, metric in zip(metric_columns, metrics):
            column.metric(metric["label"], metric["value"])

        # Operator-oriented compact summary
        st.caption("Operator summary")
        st.code(format_alphafold_operator_summary(alphafold_backends))

        # Invalid backend table — surfaced at top level, not buried in expander
        invalid_rows = build_alphafold_invalid_backend_rows(alphafold_backends)
        if invalid_rows:
            st.markdown("#### Invalid backends")
            st.dataframe(normalize_table_rows(invalid_rows), width="stretch", hide_index=True)

        recommended_backend = summarize_alphafold_recommended_backend(alphafold_backends)
        if recommended_backend.get("backend_name"):
            st.success(
                recommended_backend["label"]
                + " — "
                + " ".join(recommended_backend.get("reason_lines") or [])
            )
        capability_rows = extract_backend_capability_table(alphafold_backends)
        st.caption("Readable backend diagnostics preview")
        st.code(format_alphafold_diagnostics_preview(alphafold_backends))
        troubleshooting_summary = format_alphafold_troubleshooting_summary(alphafold_backends)
        if troubleshooting_summary.strip() != "AlphaFold validation troubleshooting":
            with st.expander("Validation troubleshooting"):
                st.code(troubleshooting_summary)
        with st.expander("Backend capability table"):
            st.dataframe(normalize_table_rows(capability_rows), width="stretch")
        with st.expander("Raw AlphaFold backend payload"):
            st.dataframe(normalize_table_rows(list(alphafold_backends.values())), width="stretch")
    else:
        st.info("No AlphaFold backend diagnostics available.")


# ---------------------------------------------------------------------------
# Pipeline status + shell run panels + execution history
# ---------------------------------------------------------------------------

def render_pipeline_section(
    *,
    client: FoldAgentClient,
    cases: list[dict],
    api_url: str,
    safe_call,
    render_api_error,
    alphafold_backends: dict | None,
    alphafold_backends_error: str | None,
    pipeline_adapters: dict | None,
    pipeline_adapters_error: str | None,
) -> list[dict] | None:
    """Render the pipeline status, shell panels, execution history, unified runs,
    and pipeline history.

    Returns:
        ``execution_history`` list (or None) so that downstream panels can
        reuse it for provenance / structure linkback.
    """
    st.subheader("Pipeline status")
    pipeline_case_options = [case["id"] for case in cases] if cases else []
    if not pipeline_case_options:
        st.info("Create a case to run the mock pipeline.")
        return None

    pipeline_case_id = st.selectbox(
        "Pipeline case",
        options=pipeline_case_options,
        format_func=lambda case_id: next(
            (
                f"{case['species']} · {case['id'][:8]} · {case.get('diagnosis_summary') or 'no summary'}"
                for case in cases
                if case["id"] == case_id
            ),
            case_id,
        ),
        key="pipeline-case-selector",
    )
    pipe_left, pipe_right = st.columns([1, 2])
    with pipe_left:
        if st.button("Run mock pipeline", width="stretch"):
            pipeline_run, pipeline_error = safe_call(client.run_pipeline, pipeline_case_id)
            if pipeline_error:
                render_api_error(pipeline_error, fallback_title="Pipeline run blocked by safety enforcement.")
            else:
                st.success(f"Pipeline run {pipeline_run['id']} completed")
                st.rerun()
    with pipe_right:
        pipeline_status, pipeline_status_error = safe_call(client.pipeline_status, pipeline_case_id)
        if pipeline_status_error:
            st.info("No pipeline run yet for this case.")
        else:
            metric1, metric2, metric3 = st.columns(3)
            metric1.metric("Status", pipeline_status["status"])
            metric2.metric("Completed steps", pipeline_status["completed_steps"])
            metric3.metric("Total steps", pipeline_status["total_steps"])
            st.dataframe(normalize_table_rows(pipeline_status.get("steps", [])), width="stretch")

    shell_left, shell_right = st.columns(2)
    with shell_left:
        _render_bioinformatics_shell(
            client=client,
            pipeline_case_id=pipeline_case_id,
            pipeline_adapters=pipeline_adapters,
            pipeline_adapters_error=pipeline_adapters_error,
            safe_call=safe_call,
            render_api_error=render_api_error,
        )
    with shell_right:
        _render_alphafold_shell(
            client=client,
            pipeline_case_id=pipeline_case_id,
            alphafold_backends=alphafold_backends,
            alphafold_backends_error=alphafold_backends_error,
            safe_call=safe_call,
            render_api_error=render_api_error,
        )

    execution_history, execution_history_error = safe_call(client.list_execution_history, pipeline_case_id)
    if execution_history_error:
        st.info("No shell execution history available yet.")
    elif execution_history:
        st.markdown("#### Shell execution history")
        st.dataframe(normalize_table_rows(execution_history), width="stretch")
        selected_execution = st.selectbox(
            "Execution log viewer",
            options=execution_history,
            index=next((i for i, item in enumerate(execution_history) if item["id"] == st.session_state.get(f"execution-viewer-{pipeline_case_id}")), 0),
            format_func=lambda item: f"{item['runner_kind']} · {item['runner_name']} · {item['status']}",
            key=f"execution-viewer-{pipeline_case_id}",
        )
        if selected_execution.get("artifacts"):
            st.caption("Execution artifacts")
            st.dataframe(normalize_table_rows(selected_execution["artifacts"]), width="stretch")
            selected_exec_artifact = st.selectbox(
                "Execution artifact",
                options=selected_execution["artifacts"],
                format_func=lambda artifact: f"{artifact['artifact_type']} · {artifact['filename']}",
                key=f"execution-artifact-{pipeline_case_id}",
            )
            exec_col1, exec_col2 = st.columns(2)
            with exec_col1:
                st.link_button("Open execution artifact", api_url.rstrip("/") + selected_exec_artifact["download_url"], width="stretch")
            with exec_col2:
                if st.button("Load execution artifact", key=f"load-execution-artifact-{pipeline_case_id}", width="stretch"):
                    artifact_file, artifact_file_error = safe_call(client.download_artifact, selected_exec_artifact["path"])
                    if artifact_file_error:
                        st.error(artifact_file_error)
                    else:
                        try:
                            st.session_state[f"execution-artifact-file-{pipeline_case_id}"] = artifact_file.decode("utf-8")
                        except UnicodeDecodeError:
                            st.session_state[f"execution-artifact-file-{pipeline_case_id}"] = f"Binary artifact: {len(artifact_file)} bytes"
            cached_execution_artifact = st.session_state.get(f"execution-artifact-file-{pipeline_case_id}")
            if cached_execution_artifact is not None:
                st.caption("Execution artifact content")
                st.code(cached_execution_artifact)

    unified_runs, unified_runs_error = safe_call(client._get, f"/cases/{pipeline_case_id}/runs")
    if unified_runs_error:
        st.info("No unified runs available yet.")
    else:
        unified_runs_payload = unified_runs.json()
        st.markdown("#### Unified runs view")
        st.dataframe(normalize_table_rows(unified_runs_payload), width="stretch")
        if unified_runs_payload:
            selected_run = st.selectbox(
                "Unified run detail",
                options=unified_runs_payload,
                format_func=lambda item: f"{item['run_kind']} · {item['name']} · {item['status']}",
                key=f"unified-run-{pipeline_case_id}",
            )
            if selected_run and selected_run.get("artifacts"):
                st.caption("Run-linked artifacts")
                st.dataframe(normalize_table_rows(selected_run["artifacts"]), width="stretch")
        else:
            st.info("No unified runs available yet.")

    pipeline_history, pipeline_history_error = safe_call(client.pipeline_history, pipeline_case_id)
    if pipeline_history_error:
        st.info("No pipeline history available yet.")
    elif pipeline_history:
        st.markdown("#### Pipeline history")
        st.dataframe(normalize_table_rows(pipeline_history), width="stretch")

    return execution_history


# ---------------------------------------------------------------------------
# Private: bioinformatics adapter shells
# ---------------------------------------------------------------------------

def _render_bioinformatics_shell(
    *,
    client: FoldAgentClient,
    pipeline_case_id: str,
    pipeline_adapters: dict | None,
    pipeline_adapters_error: str | None,
    safe_call,
    render_api_error,
) -> None:
    """Render the bioinformatics adapter shells panel."""
    st.markdown("#### Bioinformatics adapter shells")
    if pipeline_adapters_error:
        st.error(pipeline_adapters_error)
    elif pipeline_adapters:
        st.dataframe(normalize_table_rows(list(pipeline_adapters.values())), width="stretch")
        shell_adapter_name = st.selectbox(
            "Pipeline shell adapter",
            options=["vep", "pvactools"],
            key="pipeline-shell-adapter",
        )
        with st.form("pipeline-shell-run-form"):
            shell_input_vcf = st.text_input("Shell input VCF", value="/tmp/mock.vcf")
            shell_output_path = st.text_input("Shell output path", value="/tmp/mock.out")
            shell_sample_name = st.text_input("Shell sample name", value="demo-sample")
            shell_submit = st.form_submit_button("Run shell wrapper", width="stretch")
        if shell_submit:
            payload = {
                "case_id": pipeline_case_id,
                "input_vcf": shell_input_vcf,
                "output_path": shell_output_path,
            }
            if shell_adapter_name == "pvactools":
                payload["sample_name"] = shell_sample_name
            shell_result, shell_error = safe_call(client.pipeline_adapter_run, shell_adapter_name, payload)
            if shell_error:
                render_api_error(shell_error, fallback_title="Pipeline shell wrapper blocked by safety enforcement.")
            else:
                st.session_state["pipeline-shell-run-result"] = shell_result
        if st.session_state.get("pipeline-shell-run-result") is not None:
            st.json(st.session_state["pipeline-shell-run-result"])


# ---------------------------------------------------------------------------
# Private: AlphaFold backend shells
# ---------------------------------------------------------------------------

def _render_alphafold_shell(
    *,
    client: FoldAgentClient,
    pipeline_case_id: str,
    alphafold_backends: dict | None,
    alphafold_backends_error: str | None,
    safe_call,
    render_api_error,
) -> None:
    """Render the AlphaFold backend shell panel."""
    st.markdown("#### AlphaFold backend shells")
    if alphafold_backends_error:
        st.error(alphafold_backends_error)
    elif alphafold_backends:
        st.caption("Diagnostics preview shown above; use this panel to run a backend.")
        backend_options = sorted(alphafold_backends.keys())
        default_backend = choose_default_alphafold_backend(alphafold_backends)
        default_backend_index = backend_options.index(default_backend) if default_backend in backend_options else 0
        alphafold_backend_name = st.selectbox(
            "AlphaFold shell backend",
            options=backend_options,
            index=default_backend_index,
            format_func=lambda name: format_alphafold_backend_option_label(name, alphafold_backends.get(name) or {}),
            key="alphafold-shell-backend",
        )
        selected_backend_payload = alphafold_backends.get(alphafold_backend_name) or {}
        backend_form_state = build_alphafold_backend_form_state(
            alphafold_backend_name,
            selected_backend_payload,
            alphafold_backends,
        )
        if backend_form_state["severity"] == "error":
            st.error("Selected backend is not currently runnable. Review warnings below before submitting.")
        elif backend_form_state["severity"] == "warning":
            st.warning("Selected backend has extra requirements. Review warnings below before submitting.")
        else:
            st.info("Selected backend is ready for the required input type shown below.")
        if backend_form_state.get("recommended_backend_name"):
            st.caption(
                "Suggested safer default: "
                + (backend_form_state.get("recommended_backend_label") or backend_form_state["recommended_backend_name"])
            )
        switch_state = build_alphafold_recommended_switch_state(backend_form_state)
        if switch_state["show_switch"]:
            if st.button(
                switch_state["button_label"],
                key=f"alphafold-switch-{pipeline_case_id}",
                width="stretch",
            ):
                target_backend_name = switch_state["target_backend_name"]
                target_backend_payload = alphafold_backends.get(target_backend_name) or {}
                target_form_state = build_alphafold_backend_form_state(
                    target_backend_name,
                    target_backend_payload,
                    alphafold_backends,
                )
                transition = build_alphafold_run_form_transition(
                    current_values={
                        "sequence": st.session_state.get("alphafold-sequence", ""),
                        "json_path": st.session_state.get("alphafold-json-path", ""),
                        "accession": st.session_state.get("alphafold-accession", ""),
                        "job_name": st.session_state.get("alphafold-job-name", "demo-af-job"),
                        "acknowledged": st.session_state.get("alphafold-ack", False),
                    },
                    old_form_state=backend_form_state,
                    new_form_state=target_form_state,
                )
                new_values = transition["new_values"]
                st.session_state["alphafold-shell-backend"] = target_backend_name
                st.session_state["alphafold-sequence"] = new_values["sequence"]
                st.session_state["alphafold-json-path"] = new_values["json_path"]
                st.session_state["alphafold-accession"] = new_values["accession"]
                st.session_state["alphafold-job-name"] = new_values["job_name"]
                st.session_state["alphafold-ack"] = new_values["acknowledged"]
                st.session_state[f"alphafold-transition-{pipeline_case_id}"] = transition
                st.rerun()
        capability_chips = build_alphafold_backend_capability_chips(
            alphafold_backend_name, selected_backend_payload
        )
        st.caption(" · ".join(capability_chips))
        troubleshooting_chips = build_alphafold_inline_troubleshooting_chips(
            alphafold_backend_name,
            selected_backend_payload,
        )
        if troubleshooting_chips != ["status: ready"]:
            st.caption("Troubleshooting: " + " · ".join(troubleshooting_chips))
        st.code(format_alphafold_backend_form_guidance(backend_form_state))
        transition_notice = st.session_state.pop(f"alphafold-transition-{pipeline_case_id}", None)
        if transition_notice:
            preserved = ", ".join(transition_notice.get("preserved_fields") or []) or "none"
            stale = ", ".join(transition_notice.get("stale_fields") or []) or "none"
            st.info(f"Switched backend. Preserved: {preserved}. Reset stale incompatible fields: {stale}.")
        with st.form("alphafold-shell-run-form"):
            af_sequence = st.text_area(
                "AlphaFold sequence",
                value=st.session_state.get("alphafold-sequence", "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"),
                key="alphafold-sequence",
                disabled=not backend_form_state["field_enabled"]["sequence"],
                help="Used for ColabFold/local ColabFold/AlphaFold2-style sequence submission.",
            )
            if backend_form_state["disabled_field_reasons"]["sequence"]:
                st.caption(" ".join(backend_form_state["disabled_field_reasons"]["sequence"]))
            af_job_name = st.text_input(
                "AlphaFold job name",
                value=st.session_state.get("alphafold-job-name", "demo-af-job"),
                key="alphafold-job-name",
            )
            af_json_path = st.text_input(
                "AlphaFold JSON path",
                value=st.session_state.get("alphafold-json-path", "/tmp/af-input.json"),
                key="alphafold-json-path",
                disabled=not backend_form_state["field_enabled"]["json_path"],
                help="Used for AlphaFold 3 local/server JSON submission.",
            )
            if backend_form_state["disabled_field_reasons"]["json_path"]:
                st.caption(" ".join(backend_form_state["disabled_field_reasons"]["json_path"]))
            af_accession = st.text_input(
                "AlphaFold DB accession",
                value=st.session_state.get("alphafold-accession", "P04637"),
                key="alphafold-accession",
                disabled=not backend_form_state["field_enabled"]["accession"],
                help="Used for AlphaFold DB reference lookups.",
            )
            if backend_form_state["disabled_field_reasons"]["accession"]:
                st.caption(" ".join(backend_form_state["disabled_field_reasons"]["accession"]))
            af_ack = False
            if backend_form_state["requires_acknowledgement"]:
                af_ack = st.checkbox(backend_form_state["acknowledgement_label"], value=st.session_state.get("alphafold-ack", False), key="alphafold-ack")
            submission_gate = build_alphafold_submission_gate(
                backend_form_state,
                acknowledged=af_ack,
                sequence=af_sequence,
                json_path=af_json_path,
                accession=af_accession,
            )
            payload_preview = build_alphafold_run_payload_preview(
                case_id=pipeline_case_id,
                backend_name=alphafold_backend_name,
                form_state=backend_form_state,
                job_name=af_job_name,
                sequence=af_sequence,
                json_path=af_json_path,
                accession=af_accession,
            )
            st.caption("Payload preview")
            st.json(payload_preview)
            dry_run_preview, dry_run_preview_error = safe_call(
                client.alphafold_backend_dry_run,
                alphafold_backend_name,
                payload_preview,
            )
            if dry_run_preview_error:
                st.error(dry_run_preview_error)
            elif dry_run_preview:
                st.caption("Dry-run validation preview")
                st.code(format_alphafold_dry_run_preview(dry_run_preview))
            if submission_gate["submit_block_reason"]:
                st.warning(submission_gate["submit_block_reason"])
            af_submit = st.form_submit_button(
                "Run AlphaFold shell",
                width="stretch",
                disabled=not submission_gate["submit_enabled"],
            )
        if af_submit:
            payload = build_alphafold_run_payload_preview(
                case_id=pipeline_case_id,
                backend_name=alphafold_backend_name,
                form_state=backend_form_state,
                job_name=af_job_name,
                sequence=af_sequence,
                json_path=af_json_path,
                accession=af_accession,
            )
            try:
                af_result = client.alphafold_backend_run(alphafold_backend_name, payload)
                st.session_state["alphafold-shell-run-result"] = af_result
                st.session_state["alphafold-shell-run-error"] = None
                st.session_state["alphafold-shell-run-safety-error"] = None
            except AlphaFoldValidationError as exc:
                st.session_state["alphafold-shell-run-error"] = exc.payload
                st.session_state["alphafold-shell-run-safety-error"] = None
                st.session_state["alphafold-shell-run-result"] = None
            except SafetyEnforcementError as exc:
                st.session_state["alphafold-shell-run-safety-error"] = exc.payload
                st.session_state["alphafold-shell-run-error"] = None
                st.session_state["alphafold-shell-run-result"] = None
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get("alphafold-shell-run-safety-error") is not None:
            st.error("AlphaFold run blocked by safety enforcement.")
            st.code(format_safety_enforcement_error(st.session_state["alphafold-shell-run-safety-error"]))
        if st.session_state.get("alphafold-shell-run-error") is not None:
            st.error("AlphaFold backend validation blocked the run.")
            st.code(format_alphafold_validation_error(st.session_state["alphafold-shell-run-error"]))
        if st.session_state.get("alphafold-shell-run-result") is not None:
            st.json(st.session_state["alphafold-shell-run-result"])
