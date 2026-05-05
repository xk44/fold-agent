"""Pipeline status and step management page for NeoVax-Agent dashboard.

Renders pipeline run history, available steps, and dry-run controls.
"""

from __future__ import annotations

from typing import Any

STATUS_ICONS: dict[str, str] = {
    "success": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "running": "🔄",
    "queued": "⏳",
}


def render_pipeline_status(
    api_base: str,
    case_id: str | None,
    http_get: Any,
    http_post: Any,
    st: Any,
) -> None:
    st.header("Pipeline Status")

    if case_id is None:
        st.info("Select a case to view pipeline status.")
        return

    tab_history, tab_steps, tab_run = st.tabs(
        ["Run History", "Available Steps", "Run Pipeline"]
    )

    with tab_history:
        _render_run_history(api_base, case_id, http_get, st)

    with tab_steps:
        _render_available_steps(api_base, http_get, st)

    with tab_run:
        _render_run_pipeline(api_base, case_id, http_get, http_post, st)


def _render_run_history(api_base: str, case_id: str, http_get: Any, st: Any) -> None:
    st.subheader("Run History")

    try:
        data = http_get(f"{api_base}/cases/{case_id}/pipeline/status").json()
    except Exception as exc:
        st.error(f"Failed to fetch pipeline status: {exc}")
        return

    runs = data if isinstance(data, list) else data.get("runs", [])

    if not runs:
        st.info("No pipeline runs recorded yet.")
        return

    for run in runs:
        run_id = run.get("run_id", run.get("id", "unknown"))
        run_status = run.get("status", "unknown")
        icon = STATUS_ICONS.get(run_status, "❓")
        started = run.get("started_at", run.get("created_at", ""))
        label = f"{icon} Run {str(run_id)[:8]} — {run_status}"
        if started:
            label += f" ({started})"

        with st.expander(label):
            steps = run.get("steps", run.get("step_results", []))
            if steps:
                for step in steps:
                    step_name = step.get("name", step.get("step", "unknown"))
                    step_status = step.get("status", "unknown")
                    step_icon = STATUS_ICONS.get(step_status, "❓")
                    duration = step.get("duration_seconds", step.get("duration"))
                    error = step.get("error")

                    cols = st.columns([1, 4, 2])
                    cols[0].write(step_icon)
                    cols[1].write(f"**{step_name}**")
                    if duration is not None:
                        cols[2].write(f"{duration}s")
                    if error:
                        st.error(f"Error: {error}")
            else:
                st.caption("No step details available.")


def _render_available_steps(api_base: str, http_get: Any, st: Any) -> None:
    st.subheader("Available Steps")

    try:
        data = http_get(f"{api_base}/pipeline/steps").json()
    except Exception as exc:
        st.error(f"Failed to fetch pipeline steps: {exc}")
        return

    steps = data if isinstance(data, list) else data.get("steps", [])

    if not steps:
        st.info("No pipeline steps registered.")
        return

    rows = [
        {
            "Name": s.get("name", s.get("step", "unknown")),
            "Description": s.get("description", "—"),
        }
        for s in steps
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_run_pipeline(
    api_base: str, case_id: str, http_get: Any, http_post: Any, st: Any
) -> None:
    st.subheader("Run Pipeline")

    try:
        data = http_get(f"{api_base}/pipeline/steps").json()
        steps = data if isinstance(data, list) else data.get("steps", [])
    except Exception:
        steps = []

    selected_steps: list[str] = []
    if steps:
        st.write("Select steps to include:")
        for step in steps:
            name = step.get("name", step.get("step", ""))
            if name and st.checkbox(name, value=True, key=f"pipeline_step_{name}"):
                selected_steps.append(name)
    else:
        st.info("No steps available — all steps will be included if run.")

    col_dry, col_run = st.columns(2)

    with col_dry:
        if st.button("Dry Run", use_container_width=True):
            payload: dict[str, Any] = {"case_id": case_id}
            if selected_steps:
                payload["steps"] = selected_steps
            try:
                result = http_post(f"{api_base}/pipeline/dry-run", json=payload).json()
                st.success("Dry run complete.")
                st.json(result)
            except Exception as exc:
                st.error(f"Dry run failed: {exc}")

    with col_run:
        st.button("Run", disabled=True, use_container_width=True, help="Full pipeline execution coming soon.")
