"""FoldAgent MVP dashboard.

Live Streamlit UI for the current FastAPI case/safety/sample endpoints.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from frontend.app.report_preview import (
    build_alphafold_backend_capability_chips,
    build_alphafold_backend_form_state,
    build_alphafold_run_payload_preview,
    choose_default_alphafold_backend,
    extract_backend_capability_table,
    format_alphafold_backend_form_guidance,
    format_alphafold_backend_option_label,
    format_alphafold_diagnostics_metrics,
    format_alphafold_diagnostics_preview,
    format_alphafold_troubleshooting_summary,
    format_alphafold_validation_error,
    format_bundle_preview,
    format_report_preview,
    format_structure_job_preview,
    summarize_alphafold_recommended_backend,
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
from skills.shared.foldagent_client import AlphaFoldValidationError, FoldAgentClient

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_URL = os.environ.get("FOLDAGENT_API_URL", "http://localhost:8000")

st.set_page_config(page_title="FoldAgent", layout="wide")

st.title("FoldAgent")
st.caption("Local-first, safety-gated research coordination platform")
st.warning(
    "Research coordination only. Not medical advice, not veterinary advice, "
    "not treatment instructions, and not a vaccine manufacturing tool."
)

with st.sidebar:
    st.subheader("Connection")
    api_url = st.text_input("API URL", value=DEFAULT_API_URL)
    client = FoldAgentClient(base_url=api_url)

    if st.button("Refresh API status", use_container_width=True):
        st.session_state["refresh_requested"] = True


def safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # pragma: no cover - streamlit path
        return None, str(exc)


def parse_due_date(value: str | None):
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def task_sort_key(task: dict):
    due = parse_due_date(task.get("due_date"))
    return (due is None, due or datetime.max.replace(tzinfo=timezone.utc), task.get("title") or "")


def flatten_candidate_rows(candidates: list[dict] | None) -> list[dict]:
    rows = []
    for candidate in candidates or []:
        structure = candidate.get("structure_evidence") or {}
        prediction_scores = candidate.get("prediction_scores") or {}
        peptide_metadata = candidate.get("peptide_metadata") or {}
        rows.append(
            {
                "id": candidate.get("id"),
                "variant_id": candidate.get("variant_id"),
                "mhc_context": candidate.get("mhc_context"),
                "peptide_sequence": peptide_metadata.get("sequence"),
                "binding_rank": prediction_scores.get("binding_rank"),
                "immunogenicity": prediction_scores.get("immunogenicity"),
                "structure_backend": structure.get("backend"),
                "structure_status": structure.get("alphafold_status"),
                "ranking_score": structure.get("ranking_score"),
                "ptm": structure.get("ptm"),
                "iptm": structure.get("iptm"),
                "model_cif": structure.get("model_cif") or structure.get("pdb_file"),
                "source_url": structure.get("source_url"),
                "review_status": candidate.get("review_status"),
                "last_parsed_execution_id": candidate.get("last_parsed_execution_id"),
            }
        )
    return rows


def render_task_card(task: dict) -> None:
    due = parse_due_date(task.get("due_date"))
    now = datetime.now(timezone.utc)
    overdue = bool(due and due < now and task.get("status") not in {"done"})
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


def render_provenance_summary(
    variants: list[dict] | None,
    candidates: list[dict] | None,
    report_payload: dict | None = None,
    execution_select_key: str | None = None,
    execution_history: list[dict] | None = None,
) -> None:
    variant_sources = sorted(
        {
            (variant.get("quality_metrics") or {}).get("parsed_from")
            for variant in (variants or [])
            if (variant.get("quality_metrics") or {}).get("parsed_from")
        }
    )
    candidate_sources = sorted(
        {
            (candidate.get("prediction_scores") or {}).get("parsed_from")
            for candidate in (candidates or [])
            if (candidate.get("prediction_scores") or {}).get("parsed_from")
        }
    )
    structure_backends = sorted(
        {
            (candidate.get("structure_evidence") or {}).get("backend")
            for candidate in (candidates or [])
            if (candidate.get("structure_evidence") or {}).get("backend")
        }
    )
    structure_statuses = sorted(
        {
            (candidate.get("structure_evidence") or {}).get("alphafold_status")
            for candidate in (candidates or [])
            if (candidate.get("structure_evidence") or {}).get("alphafold_status")
        }
    )
    variant_execution_ids = [variant.get("last_parsed_execution_id") for variant in (variants or []) if variant.get("last_parsed_execution_id")]
    candidate_execution_ids = [candidate.get("last_parsed_execution_id") for candidate in (candidates or []) if candidate.get("last_parsed_execution_id")]

    st.markdown("### Parsed provenance")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Variant parsed_from", ", ".join(variant_sources) if variant_sources else "mock_only")
    col2.metric("Candidate parsed_from", ", ".join(candidate_sources) if candidate_sources else "mock_only")
    col3.metric("Structure backend", ", ".join(structure_backends) if structure_backends else "mock_only")
    col4.metric("Structure status", ", ".join(structure_statuses) if structure_statuses else "mock_only")

    structure_scores = [
        candidate.get("structure_evidence") or {}
        for candidate in (candidates or [])
        if candidate.get("structure_evidence")
    ]
    score_col1, score_col2, score_col3 = st.columns(3)
    score_col1.metric(
        "Best ranking_score",
        max((item.get("ranking_score") for item in structure_scores if item.get("ranking_score") is not None), default="n/a"),
    )
    score_col2.metric(
        "Best pTM",
        max((item.get("ptm") for item in structure_scores if item.get("ptm") is not None), default="n/a"),
    )
    score_col3.metric(
        "Best ipTM",
        max((item.get("iptm") for item in structure_scores if item.get("iptm") is not None), default="n/a"),
    )

    trace_col1, trace_col2 = st.columns(2)
    trace_col1.caption("Variant parsed execution IDs")
    trace_col1.code("\n".join(variant_execution_ids) if variant_execution_ids else "none")
    trace_col2.caption("Candidate parsed execution IDs")
    trace_col2.code("\n".join(candidate_execution_ids) if candidate_execution_ids else "none")

    combined_execution_ids = []
    for execution_id in variant_execution_ids + candidate_execution_ids:
        if execution_id not in combined_execution_ids:
            combined_execution_ids.append(execution_id)
    if execution_select_key and combined_execution_ids:
        st.caption("Traceability shortcuts")
        shortcut_cols = st.columns(min(len(combined_execution_ids), 4))
        for idx, execution_id in enumerate(combined_execution_ids[:4]):
            with shortcut_cols[idx]:
                if st.button(f"Focus {execution_id[:8]}", key=f"focus-{execution_select_key}-{execution_id}", use_container_width=True):
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
                        use_container_width=True,
                    )
                with shortcut_action_col2:
                    if st.button(
                        f"Load artifact {primary_artifact['filename']}",
                        key=f"load-focused-{execution_select_key}-{selected_execution_id}",
                        use_container_width=True,
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


def fetch_health(c: FoldAgentClient):
    """Fetch health, accepting 503 degraded responses without raising."""
    try:
        response = c.client.get("/health", headers=c._headers(), timeout=10.0)
        return response.json(), None
    except Exception as exc:
        return None, str(exc)


health, health_error = fetch_health(client)
version, version_error = safe_call(client.version)
cases, cases_error = safe_call(client.list_cases)
if cases_error:
    st.error(f"Unable to load cases: {cases_error}")
    cases = []

pipeline_adapters, pipeline_adapters_error = safe_call(client.client.get, "/pipeline/adapters")
alphafold_backends, alphafold_backends_error = safe_call(client.client.get, "/alphafold/backends")
if pipeline_adapters:
    pipeline_adapters = pipeline_adapters.json()
if alphafold_backends:
    alphafold_backends = alphafold_backends.json()

status_left, status_right = st.columns(2)
with status_left:
    st.subheader("API health")
    if health_error:
        st.error(health_error)
    else:
        if isinstance(health, dict) and health.get("status") == "degraded":
            missing = health.get("missing_tables") or []
            st.warning(f"API degraded — missing: {', '.join(missing) if missing else 'tables'}")
        st.json(health)
with status_right:
    st.subheader("API version")
    if version_error:
        st.error(version_error)
    else:
        st.json(version)

st.subheader("AlphaFold backend diagnostics")
if alphafold_backends_error:
    st.error(alphafold_backends_error)
elif alphafold_backends:
    metrics = format_alphafold_diagnostics_metrics(alphafold_backends)
    metric_columns = st.columns(len(metrics))
    for column, metric in zip(metric_columns, metrics):
        column.metric(metric["label"], metric["value"])
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
        st.dataframe(capability_rows, use_container_width=True)
    with st.expander("Raw AlphaFold backend payload"):
        st.dataframe(list(alphafold_backends.values()), use_container_width=True)
else:
    st.info("No AlphaFold backend diagnostics available.")

st.subheader("Pipeline status")
pipeline_case_options = [case["id"] for case in cases] if cases else []
if not pipeline_case_options:
    st.info("Create a case to run the mock pipeline.")
else:
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
        if st.button("Run mock pipeline", use_container_width=True):
            pipeline_run, pipeline_error = safe_call(client.run_pipeline, pipeline_case_id)
            if pipeline_error:
                st.error(pipeline_error)
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
            st.dataframe(pipeline_status.get("steps", []), use_container_width=True)

    shell_left, shell_right = st.columns(2)
    with shell_left:
        st.markdown("#### Bioinformatics adapter shells")
        if pipeline_adapters_error:
            st.error(pipeline_adapters_error)
        elif pipeline_adapters:
            st.dataframe(list(pipeline_adapters.values()), use_container_width=True)
            shell_adapter_name = st.selectbox(
                "Pipeline shell adapter",
                options=["vep", "pvactools"],
                key="pipeline-shell-adapter",
            )
            with st.form("pipeline-shell-run-form"):
                shell_input_vcf = st.text_input("Shell input VCF", value="/tmp/mock.vcf")
                shell_output_path = st.text_input("Shell output path", value="/tmp/mock.out")
                shell_sample_name = st.text_input("Shell sample name", value="demo-sample")
                shell_submit = st.form_submit_button("Run shell wrapper", use_container_width=True)
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
                    st.error(shell_error)
                else:
                    st.session_state["pipeline-shell-run-result"] = shell_result
            if st.session_state.get("pipeline-shell-run-result") is not None:
                st.json(st.session_state["pipeline-shell-run-result"])
    with shell_right:
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
                alphafold_backend_name, selected_backend_payload
            )
            if backend_form_state["severity"] == "error":
                st.error("Selected backend is not currently runnable. Review warnings below before submitting.")
            elif backend_form_state["severity"] == "warning":
                st.warning("Selected backend has extra requirements. Review warnings below before submitting.")
            else:
                st.info("Selected backend is ready for the required input type shown below.")
            capability_chips = build_alphafold_backend_capability_chips(
                alphafold_backend_name, selected_backend_payload
            )
            st.caption(" · ".join(capability_chips))
            st.code(format_alphafold_backend_form_guidance(backend_form_state))
            with st.form("alphafold-shell-run-form"):
                af_sequence = st.text_area(
                    "AlphaFold sequence",
                    value="MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
                    disabled=not backend_form_state["field_enabled"]["sequence"],
                    help="Used for ColabFold/local ColabFold/AlphaFold2-style sequence submission.",
                )
                if backend_form_state["disabled_field_reasons"]["sequence"]:
                    st.caption(" ".join(backend_form_state["disabled_field_reasons"]["sequence"]))
                af_job_name = st.text_input("AlphaFold job name", value="demo-af-job")
                af_json_path = st.text_input(
                    "AlphaFold JSON path",
                    value="/tmp/af-input.json",
                    disabled=not backend_form_state["field_enabled"]["json_path"],
                    help="Used for AlphaFold 3 local/server JSON submission.",
                )
                if backend_form_state["disabled_field_reasons"]["json_path"]:
                    st.caption(" ".join(backend_form_state["disabled_field_reasons"]["json_path"]))
                af_accession = st.text_input(
                    "AlphaFold DB accession",
                    value="P04637",
                    disabled=not backend_form_state["field_enabled"]["accession"],
                    help="Used for AlphaFold DB reference lookups.",
                )
                if backend_form_state["disabled_field_reasons"]["accession"]:
                    st.caption(" ".join(backend_form_state["disabled_field_reasons"]["accession"]))
                af_ack = False
                if backend_form_state["requires_acknowledgement"]:
                    af_ack = st.checkbox(backend_form_state["acknowledgement_label"], value=False)
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
                submit_block_reason = backend_form_state["submit_block_reason"]
                if backend_form_state["requires_acknowledgement"] and af_ack:
                    submit_block_reason = ""
                if submit_block_reason:
                    st.warning(submit_block_reason)
                af_submit = st.form_submit_button(
                    "Run AlphaFold shell",
                    use_container_width=True,
                    disabled=bool(submit_block_reason),
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
                except AlphaFoldValidationError as exc:
                    st.session_state["alphafold-shell-run-error"] = exc.payload
                    st.session_state["alphafold-shell-run-result"] = None
                except Exception as exc:
                    st.error(str(exc))
            if st.session_state.get("alphafold-shell-run-error") is not None:
                st.error("AlphaFold backend validation blocked the run.")
                st.code(format_alphafold_validation_error(st.session_state["alphafold-shell-run-error"]))
            if st.session_state.get("alphafold-shell-run-result") is not None:
                st.json(st.session_state["alphafold-shell-run-result"])

    execution_history, execution_history_error = safe_call(client.list_execution_history, pipeline_case_id)
    if execution_history_error:
        st.info("No shell execution history available yet.")
    elif execution_history:
        st.markdown("#### Shell execution history")
        st.dataframe(execution_history, use_container_width=True)
        selected_execution = st.selectbox(
            "Execution log viewer",
            options=execution_history,
            index=next((i for i, item in enumerate(execution_history) if item["id"] == st.session_state.get(f"execution-viewer-{pipeline_case_id}")), 0),
            format_func=lambda item: f"{item['runner_kind']} · {item['runner_name']} · {item['status']}",
            key=f"execution-viewer-{pipeline_case_id}",
        )
        if selected_execution.get("artifacts"):
            st.caption("Execution artifacts")
            st.dataframe(selected_execution["artifacts"], use_container_width=True)
            selected_exec_artifact = st.selectbox(
                "Execution artifact",
                options=selected_execution["artifacts"],
                format_func=lambda artifact: f"{artifact['artifact_type']} · {artifact['filename']}",
                key=f"execution-artifact-{pipeline_case_id}",
            )
            exec_col1, exec_col2 = st.columns(2)
            with exec_col1:
                st.link_button("Open execution artifact", api_url.rstrip("/") + selected_exec_artifact["download_url"], use_container_width=True)
            with exec_col2:
                if st.button("Load execution artifact", key=f"load-execution-artifact-{pipeline_case_id}", use_container_width=True):
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
        st.dataframe(unified_runs_payload, use_container_width=True)
        selected_run = st.selectbox(
            "Unified run detail",
            options=unified_runs_payload,
            format_func=lambda item: f"{item['run_kind']} · {item['name']} · {item['status']}",
            key=f"unified-run-{pipeline_case_id}",
        )
        if selected_run and selected_run.get("artifacts"):
            st.caption("Run-linked artifacts")
            st.dataframe(selected_run["artifacts"], use_container_width=True)

    pipeline_history, pipeline_history_error = safe_call(client.pipeline_history, pipeline_case_id)
    if pipeline_history_error:
        st.info("No pipeline history available yet.")
    elif pipeline_history:
        st.markdown("#### Pipeline history")
        st.dataframe(pipeline_history, use_container_width=True)

create_col, inspect_col = st.columns([1, 2])

with create_col:
    st.subheader("Create case")
    with st.form("create-case"):
        species = st.selectbox("Species mode", ["demo", "dog", "human"], index=0)
        diagnosis_summary = st.text_area("Diagnosis summary", value="Synthetic demo research case")
        supervising_professional = st.text_input("Supervising professional", value="")
        create_submitted = st.form_submit_button("Create case", use_container_width=True)
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

with inspect_col:
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
        )
        case_detail, case_error = safe_call(client.get_case, selected_case_id)
        if case_error:
            st.error(case_error)
        else:
            st.json(case_detail)

        st.markdown("### Case tasks")
        task_left, task_right = st.columns(2)
        with task_left:
            with st.form(f"create-task-{selected_case_id}"):
                task_title = st.text_input("Task title", value="")
                task_status = st.selectbox("Task status", ["todo", "in_progress", "done", "blocked"], index=0)
                task_owner = st.text_input("Task owner", value="")
                task_due_date = st.text_input("Task due date (ISO)", value="")
                task_notes = st.text_area("Task notes", value="")
                task_submit = st.form_submit_button("Create task", use_container_width=True)
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
                st.dataframe(sorted_tasks, use_container_width=True)
                selected_task_id = st.selectbox(
                    "Task update target",
                    options=[task["id"] for task in sorted_tasks],
                    format_func=lambda task_id: next((f"{task['status']} · {task['title']}" for task in sorted_tasks if task["id"] == task_id), task_id),
                    key=f"task-target-{selected_case_id}",
                )
                with st.form(f"update-task-{selected_case_id}"):
                    update_task_status = st.selectbox("Update task status", ["todo", "in_progress", "done", "blocked"], index=0)
                    update_task_notes = st.text_area("Update task notes", value="")
                    update_task_submit = st.form_submit_button("Update task", use_container_width=True)
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

        sample_left, sample_right = st.columns(2)
        with sample_left:
            st.markdown("### Register sample")
            with st.form("register-sample"):
                sample_type = st.selectbox("Sample type", ["tumor", "normal", "rna", "other"], index=0)
                file_path = st.text_input("Primary file path", value="/tmp/demo.vcf")
                checksum = st.text_input("Checksum", value="")
                source_lab = st.text_input("Source lab", value="")
                sample_submit = st.form_submit_button("Register sample", use_container_width=True)
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
                st.dataframe(samples, use_container_width=True)
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

        st.markdown("### Audit log")
        audit_entries, audit_error = safe_call(client.get_audit_log, selected_case_id)
        if audit_error:
            st.error(audit_error)
        elif not audit_entries:
            st.info("No audit entries for this case yet.")
        else:
            st.dataframe(audit_entries, use_container_width=True)

        st.markdown("### Reports")
        report_col1, report_col2 = st.columns(2)
        with report_col1:
            if st.button("Generate candidate review", use_container_width=True):
                report_result, report_error = safe_call(client.generate_candidate_review_report, selected_case_id)
                if report_error:
                    st.error(report_error)
                else:
                    st.success(f"Generated report {report_result['id']}")
                    st.session_state["last_report_id"] = report_result["id"]
                    st.rerun()
        with report_col2:
            if st.button("Generate ethics package", use_container_width=True):
                report_result, report_error = safe_call(client.generate_ethics_package, selected_case_id)
                if report_error:
                    st.error(report_error)
                else:
                    st.success(f"Generated report {report_result['id']}")
                    st.session_state["last_report_id"] = report_result["id"]
                    st.rerun()

        st.markdown("### Candidate review table")
        variants, variants_error = safe_call(client.list_variants, selected_case_id)
        candidates, candidates_error = safe_call(client.list_candidates, selected_case_id)
        # Pre-fetch structure jobs and reports so focus buttons can reference them
        structure_jobs, structure_jobs_error = safe_call(client.list_structure_jobs, selected_case_id)
        reports, reports_error = safe_call(client.list_reports, selected_case_id)
        if not variants_error and not candidates_error:
            render_provenance_summary(
                variants or [],
                candidates or [],
                execution_select_key=f"execution-viewer-{pipeline_case_id}",
                execution_history=execution_history or [],
            )

        # --- Variant filter/sort controls ---
        if not variants_error and variants:
            variant_filter_col1, variant_filter_col2, variant_filter_col3 = st.columns(3)
            with variant_filter_col1:
                variant_filter_status = st.selectbox(
                    "Variant filter status",
                    options=["all", "unreviewed", "needs_data", "expert_rejected", "expert_accepted_for_further_research"],
                    key=f"variant-filter-status-{selected_case_id}",
                )
            with variant_filter_col2:
                variant_sort = st.selectbox(
                    "Variant sort",
                    options=["gene", "protein_change", "vaf_desc", "vaf_asc"],
                    key=f"variant-sort-{selected_case_id}",
                )
            with variant_filter_col3:
                variant_columns = st.selectbox(
                    "Variant columns",
                    options=["default", "minimal", "full"],
                    key=f"variant-columns-{selected_case_id}",
                )
            vaf_col1, vaf_col2 = st.columns(2)
            with vaf_col1:
                variant_vaf_min = st.number_input(
                    "Variant VAF min",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.01,
                    key=f"variant-vaf-min-{selected_case_id}",
                )
            with vaf_col2:
                variant_vaf_max = st.number_input(
                    "Variant VAF max",
                    min_value=0.0,
                    max_value=1.0,
                    value=1.0,
                    step=0.01,
                    key=f"variant-vaf-max-{selected_case_id}",
                )

        if variants_error:
            st.error(variants_error)
        elif variants:
            st.dataframe(variants, use_container_width=True)
            selected_variant_id = st.selectbox(
                "Variant review target",
                options=[variant["id"] for variant in variants],
                format_func=lambda variant_id: next(
                    (
                        f"{variant.get('gene') or 'unknown'} · {variant.get('protein_change') or variant_id[:8]}"
                        for variant in variants
                        if variant["id"] == variant_id
                    ),
                    variant_id,
                ),
                key=f"variant-review-{selected_case_id}",
            )

            # Focus buttons for variant → related objects
            variant_focus_col1, variant_focus_col2, variant_focus_col3 = st.columns(3)
            with variant_focus_col1:
                if st.button("Focus related candidate", key=f"focus-related-candidate-{selected_case_id}", use_container_width=True):
                    # Find the first candidate linked to the selected variant
                    related = next(
                        (c for c in (candidates or []) if c.get("variant_id") == selected_variant_id),
                        None,
                    )
                    if related:
                        st.session_state[f"candidate-review-{selected_case_id}"] = related["id"]
                        st.session_state[f"candidate-mhc-filter-{selected_case_id}"] = "all"
                        st.rerun()
            with variant_focus_col2:
                if st.button("Focus related structure job", key=f"focus-related-structure-{selected_case_id}", use_container_width=True):
                    # Find structure job for the first candidate linked to the selected variant
                    related_candidate = next(
                        (c for c in (candidates or []) if c.get("variant_id") == selected_variant_id),
                        None,
                    )
                    if related_candidate:
                        related_job = next(
                            (j for j in (structure_jobs or []) if j.get("candidate_id") == related_candidate["id"]),
                            None,
                        )
                        if related_job:
                            st.session_state[f"structure-job-{selected_case_id}"] = related_job["id"]
                            st.rerun()
            with variant_focus_col3:
                if st.button("Focus related report", key=f"focus-related-report-{selected_case_id}", use_container_width=True):
                    # Focus the candidate_review report (first one found)
                    related_report = next(
                        (r for r in (reports or []) if r.get("report_type") == "candidate_review"),
                        None,
                    )
                    if related_report:
                        st.session_state[f"report-detail-{selected_case_id}"] = related_report["id"]
                        st.rerun()

            with st.form(f"variant-review-form-{selected_case_id}"):
                variant_status = st.selectbox(
                    "Variant review status",
                    [
                        "unreviewed",
                        "needs_data",
                        "expert_rejected",
                        "expert_accepted_for_further_research",
                    ],
                    index=0,
                )
                variant_note = st.text_input("Variant note", value="")
                variant_submit = st.form_submit_button("Update variant review", use_container_width=True)
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

        # --- Candidate filter/sort controls ---
        if not candidates_error and candidates:
            mhc_options = ["all"] + sorted({c.get("mhc_context") for c in candidates if c.get("mhc_context")})
            candidate_filter_col1, candidate_filter_col2, candidate_filter_col3, candidate_filter_col4 = st.columns(4)
            with candidate_filter_col1:
                candidate_filter_status = st.selectbox(
                    "Candidate filter status",
                    options=["all", "unreviewed", "needs_data", "expert_rejected", "expert_accepted_for_further_research"],
                    key=f"candidate-filter-status-{selected_case_id}",
                )
            with candidate_filter_col2:
                candidate_mhc_filter = st.selectbox(
                    "Candidate MHC filter",
                    options=mhc_options,
                    key=f"candidate-mhc-filter-{selected_case_id}",
                )
            with candidate_filter_col3:
                candidate_sort = st.selectbox(
                    "Candidate sort",
                    options=["binding_rank_asc", "binding_rank_desc", "immunogenicity_desc", "ranking_score_desc"],
                    key=f"candidate-sort-{selected_case_id}",
                )
            with candidate_filter_col4:
                candidate_columns = st.selectbox(
                    "Candidate columns",
                    options=["default", "minimal", "full"],
                    key=f"candidate-columns-{selected_case_id}",
                )
            cand_num_col1, cand_num_col2 = st.columns(2)
            with cand_num_col1:
                candidate_ranking_min = st.number_input(
                    "Candidate ranking min",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.0,
                    step=0.01,
                    key=f"candidate-ranking-min-{selected_case_id}",
                )
            with cand_num_col2:
                candidate_binding_max = st.number_input(
                    "Candidate binding max",
                    min_value=0.0,
                    max_value=1.0,
                    value=1.0,
                    step=0.01,
                    key=f"candidate-binding-max-{selected_case_id}",
                )

        if candidates_error:
            st.error(candidates_error)
        elif candidates:
            candidate_rows = flatten_candidate_rows(candidates)
            st.dataframe(candidate_rows, use_container_width=True)
            selected_candidate_id = st.selectbox(
                "Candidate review target",
                options=[candidate["id"] for candidate in candidates],
                format_func=lambda candidate_id: next(
                    (
                        f"{candidate.get('mhc_context') or 'candidate'} · {candidate_id[:8]}"
                        for candidate in candidates
                        if candidate["id"] == candidate_id
                    ),
                    candidate_id,
                ),
                key=f"candidate-review-{selected_case_id}",
            )

            # Focus buttons for candidate → related objects
            cand_focus_col1, cand_focus_col2, cand_focus_col3 = st.columns(3)
            with cand_focus_col1:
                if st.button("Focus structure job", key=f"focus-structure-job-{selected_case_id}", use_container_width=True):
                    related_job = next(
                        (j for j in (structure_jobs or []) if j.get("candidate_id") == selected_candidate_id),
                        None,
                    )
                    if related_job:
                        st.session_state[f"structure-job-{selected_case_id}"] = related_job["id"]
                        st.rerun()
            with cand_focus_col2:
                if st.button("Focus candidate review report", key=f"focus-candidate-report-{selected_case_id}", use_container_width=True):
                    related_report = next(
                        (r for r in (reports or []) if r.get("report_type") == "candidate_review"),
                        None,
                    )
                    if related_report:
                        st.session_state[f"report-detail-{selected_case_id}"] = related_report["id"]
                        st.rerun()
            with cand_focus_col3:
                if st.button("Focus candidate artifact", key=f"focus-candidate-artifact-{selected_case_id}", use_container_width=True):
                    # Find artifact linked to this candidate's structure job
                    related_job = next(
                        (j for j in (structure_jobs or []) if j.get("candidate_id") == selected_candidate_id),
                        None,
                    )
                    artifacts_for_focus, _aff_err = safe_call(client.list_case_artifacts, selected_case_id)
                    if artifacts_for_focus:
                        # Find first report artifact (candidate_review type)
                        related_artifact = next(
                            (a for a in artifacts_for_focus if a.get("artifact_type") == "report"),
                            artifacts_for_focus[0] if artifacts_for_focus else None,
                        )
                        if related_artifact:
                            st.session_state[f"artifact-download-{selected_case_id}"] = related_artifact
                            st.rerun()

            with st.form(f"candidate-review-form-{selected_case_id}"):
                candidate_status = st.selectbox(
                    "Candidate review status",
                    [
                        "unreviewed",
                        "needs_data",
                        "expert_rejected",
                        "expert_accepted_for_further_research",
                    ],
                    index=0,
                )
                candidate_note = st.text_input("Candidate note", value="")
                candidate_submit = st.form_submit_button("Update candidate review", use_container_width=True)
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

        st.markdown("### Structure job explorer")
        if structure_jobs_error:
            st.error(structure_jobs_error)
        elif not structure_jobs:
            st.info("No structure jobs for this case yet.")
        else:
            st.dataframe(structure_jobs, use_container_width=True)
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
                    if st.button("Load 3D structure", key=f"load-structure-viewer-{selected_structure_job_id}", use_container_width=True):
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
                        components.html(
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
                        components.html(
                            build_structure_viewer_html(cached_structure_text, cached_structure_format),
                            height=560,
                        )
                else:
                    st.info("No downloadable PDB/mmCIF artifact linked to this structure job yet.")
                if related_execution and related_execution.get("artifacts"):
                    st.caption("Linked execution artifacts")
                    st.dataframe(related_execution["artifacts"], use_container_width=True)

        if reports_error:
            st.error(reports_error)
        elif not reports:
            st.info("No reports generated for this case yet.")
        else:
            st.dataframe(reports, use_container_width=True)
            report_ids = [report["id"] for report in reports]
            selected_report_id = st.selectbox(
                "Report detail/export",
                options=report_ids,
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
                    variants or [],
                    candidates or [],
                    report_payload,
                    execution_select_key=f"execution-viewer-{pipeline_case_id}",
                    execution_history=execution_history or [],
                )
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
                    if st.button("Load export", key=f"load-export-{selected_case_id}", use_container_width=True):
                        export_payload, export_error = safe_call(client.export_report, selected_report_id, export_format)
                        if export_error:
                            st.error(export_error)
                        else:
                            st.session_state[f"export-payload-{selected_case_id}"] = export_payload
                with export_col2:
                    if st.button("Save export", key=f"save-export-{selected_case_id}", use_container_width=True):
                        saved_export, saved_export_error = safe_call(client.save_report, selected_report_id, export_format)
                        if saved_export_error:
                            st.error(saved_export_error)
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

                if st.button("Load case bundle", key=f"load-bundle-{selected_case_id}", use_container_width=True):
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
                        if st.button("Load bundle export", key=f"load-bundle-export-{selected_case_id}", use_container_width=True):
                            bundle_export_payload, bundle_export_error = safe_call(
                                client.export_case_bundle,
                                selected_case_id,
                                bundle_export_format,
                            )
                            if bundle_export_error:
                                st.error(bundle_export_error)
                            else:
                                st.session_state[f"bundle-export-payload-{selected_case_id}"] = bundle_export_payload
                    with bundle_export_col2:
                        if st.button("Save bundle export", key=f"save-bundle-export-{selected_case_id}", use_container_width=True):
                            saved_bundle_export, saved_bundle_export_error = safe_call(
                                client.save_case_bundle,
                                selected_case_id,
                                bundle_export_format,
                            )
                            if saved_bundle_export_error:
                                st.error(saved_bundle_export_error)
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
                        st.dataframe(artifacts, use_container_width=True)
                        selected_artifact = st.selectbox(
                            "Artifact download target",
                            options=artifacts,
                            format_func=lambda artifact: f"{artifact['artifact_type']} · {artifact['format']} · {artifact['filename']}",
                            key=f"artifact-download-{selected_case_id}",
                        )
                        meta_col1, meta_col2, meta_col3 = st.columns(3)
                        meta_col1.metric("File size", selected_artifact["file_size"])
                        meta_col2.metric("MIME type", selected_artifact["mime_type"])
                        meta_col3.metric("Saved at", selected_artifact["saved_at"])
                        artifact_download_col1, artifact_download_col2 = st.columns(2)
                        with artifact_download_col1:
                            st.link_button("Open artifact URL", api_url.rstrip("/") + selected_artifact["download_url"], use_container_width=True)
                        with artifact_download_col2:
                            if st.button("Load artifact file", key=f"load-artifact-file-{selected_case_id}", use_container_width=True):
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

st.subheader("Safety preflight")
with st.form("safety-preflight"):
    action = st.text_input("Action", value="generate_report")
    safety_species_mode = st.selectbox("Mode", ["demo", "dog", "human"], index=0)
    content = st.text_area("Content to scan", value="Candidate review summary for expert discussion.")
    is_export = st.checkbox("Export action", value=True)
    external_upload = st.checkbox("External upload", value=False)
    sequence_data = st.checkbox("Sequence-level data", value=False)
    preflight_submit = st.form_submit_button("Run preflight", use_container_width=True)

if preflight_submit:
    result, error = safe_call(
        client.safety_preflight,
        action=action,
        species_mode=safety_species_mode,
        content=content,
        is_export=is_export,
        involves_external_upload=external_upload,
        involves_sequence_data=sequence_data,
    )
    if error:
        st.error(error)
    else:
        st.json(result)

st.subheader("Safety banner")
st.code("Research candidate only — not administerable")

if (ROOT / "examples" / "synthetic_demo_case.json").exists():
    with st.expander("Bundled example case payload"):
        st.json((ROOT / "examples" / "synthetic_demo_case.json").read_text())
