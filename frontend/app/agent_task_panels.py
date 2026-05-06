"""Agent task operator helpers and dashboard workspace renderer."""

from __future__ import annotations

import json

import streamlit as st

from frontend.app.dashboard_helpers import normalize_table_rows


def _section(title: str, lines: list[str]) -> str:
    return "\n".join([title, *lines])


def build_agent_task_operator_summary(tasks: list[dict] | None) -> dict:
    payload = tasks or []
    status_counts: dict[str, int] = {}
    framework_counts: dict[str, int] = {}
    case_scoped_tasks = 0
    system_tasks = 0
    for item in payload:
        status = str(item.get("status") or "unknown")
        framework = str(item.get("framework") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        framework_counts[framework] = framework_counts.get(framework, 0) + 1
        if item.get("case_id"):
            case_scoped_tasks += 1
        else:
            system_tasks += 1
    return {
        "total_tasks": len(payload),
        "case_scoped_tasks": case_scoped_tasks,
        "system_tasks": system_tasks,
        "status_counts": status_counts,
        "framework_counts": framework_counts,
    }


def format_agent_task_operator_summary(summary: dict) -> str:
    return "\n\n".join(
        [
            "Agent task workspace",
            _section(
                "Summary",
                [
                    f"total_tasks={summary.get('total_tasks', 0)}",
                    f"case_scoped_tasks={summary.get('case_scoped_tasks', 0)}",
                    f"system_tasks={summary.get('system_tasks', 0)}",
                    "status_counts="
                    + (
                        ", ".join(
                            f"{k}:{v}"
                            for k, v in sorted((summary.get("status_counts") or {}).items())
                        )
                        or "none"
                    ),
                    "framework_counts="
                    + (
                        ", ".join(
                            f"{k}:{v}"
                            for k, v in sorted((summary.get("framework_counts") or {}).items())
                        )
                        or "none"
                    ),
                ],
            ),
        ]
    )


def build_agent_task_table_rows(tasks: list[dict] | None) -> list[dict]:
    rows: list[dict] = []
    for item in tasks or []:
        task_id = str(item.get("id") or "")
        case_id = str(item.get("case_id") or "system")
        rows.append(
            {
                "ID": task_id[:8],
                "Case": case_id[:8] if case_id != "system" else "system",
                "Framework": str(item.get("framework") or "unknown"),
                "Skill": str(item.get("skill_name") or "unknown"),
                "Status": str(item.get("status") or "unknown"),
                "Has logs": "yes" if item.get("logs") else "—",
                "Has artifacts": "yes" if item.get("artifacts") else "—",
                "Created": str(item.get("created_at") or "—"),
            }
        )
    return rows


def derive_agent_task_form_options(skills_payload: list[dict] | None) -> dict:
    frameworks: set[str] = set()
    skills_by_framework: dict[str, set[str]] = {}
    for item in skills_payload or []:
        framework = str(item.get("framework") or "other")
        skill_name = str(item.get("skill_name") or "")
        frameworks.add(framework)
        skills_by_framework.setdefault(framework, set())
        if skill_name:
            skills_by_framework[framework].add(skill_name)
    frameworks.add("other")
    ordered_frameworks = sorted(frameworks)
    return {
        "frameworks": ordered_frameworks,
        "skills_by_framework": {
            framework: sorted(skills_by_framework.get(framework, set()))
            for framework in ordered_frameworks
        },
    }


def format_agent_task_dry_run_preview(dry_run_payload: dict | None) -> str:
    payload = dry_run_payload or {}
    would_create = payload.get("would_create") or {}
    return "\n\n".join(
        [
            "Agent task dry run",
            _section(
                "Summary",
                [
                    f"dry_run={payload.get('dry_run')}",
                    f"case_exists={payload.get('case_exists')}",
                    f"framework={payload.get('framework')}",
                    f"skill_name={payload.get('skill_name')}",
                    f"status={payload.get('status')}",
                    f"skill_available={payload.get('skill_available')}",
                    f"skill_path={payload.get('skill_path') or 'n/a'}",
                ],
            ),
            _section(
                "Would create",
                [
                    f"case_id={would_create.get('case_id') or 'system'}",
                    f"framework={would_create.get('framework') or 'n/a'}",
                    f"skill_name={would_create.get('skill_name') or 'n/a'}",
                    f"status={would_create.get('status') or 'n/a'}",
                ],
            ),
        ]
    )


def format_agent_task_detail_preview(task_payload: dict | None) -> str:
    payload = task_payload or {}
    logs = payload.get("logs") or {}
    artifacts = payload.get("artifacts") or {}
    logs_keys = ", ".join(sorted(logs.keys())) if isinstance(logs, dict) and logs else "none"
    artifact_keys = (
        ", ".join(sorted(artifacts.keys())) if isinstance(artifacts, dict) and artifacts else "none"
    )
    return "\n\n".join(
        [
            "Agent task detail",
            _section(
                "Summary",
                [
                    f"id={payload.get('id') or 'n/a'}",
                    f"case_id={payload.get('case_id') or 'system'}",
                    f"framework={payload.get('framework') or 'n/a'}",
                    f"skill_name={payload.get('skill_name') or 'n/a'}",
                    f"status={payload.get('status') or 'n/a'}",
                    f"created_at={payload.get('created_at') or 'n/a'}",
                    f"logs_keys={logs_keys}",
                    f"artifact_keys={artifact_keys}",
                ],
            ),
        ]
    )


def _parse_optional_json_text(text: str) -> dict | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    parsed = json.loads(cleaned)
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise ValueError("JSON field must deserialize to an object")
    return parsed


def build_agent_task_update_payload(*, status: str, logs_text: str, artifacts_text: str) -> dict:
    return {
        "status": status,
        "logs": _parse_optional_json_text(logs_text),
        "artifacts": _parse_optional_json_text(artifacts_text),
    }


def render_agent_task_section(
    *,
    client,
    safe_call,
    render_api_error,
    cases: list[dict] | None,
    agent_skills: list[dict] | None,
) -> None:
    st.markdown("#### Agent task workspace")

    tasks, tasks_error = safe_call(client.list_agent_tasks)
    if tasks_error:
        render_api_error(tasks_error, fallback_title="Unable to load agent tasks.")
        tasks = []
    tasks = tasks or []

    summary = build_agent_task_operator_summary(tasks)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Tasks", summary["total_tasks"])
    metric_cols[1].metric("Case scoped", summary["case_scoped_tasks"])
    metric_cols[2].metric("System", summary["system_tasks"])
    metric_cols[3].metric("Pending", summary["status_counts"].get("pending", 0))
    st.code(format_agent_task_operator_summary(summary))

    form_options = derive_agent_task_form_options(agent_skills)
    case_options = {"system": None}
    for case in cases or []:
        case_options[str(case.get("id"))] = case.get("id")

    build_tab, tasks_tab = st.tabs(["Build task", "Task list"])

    with build_tab:
        with st.form("agent-task-workspace-form"):
            case_choice = st.selectbox(
                "Task scope",
                options=list(case_options.keys()),
                format_func=lambda x: "system" if x == "system" else f"{x[:8]} — case",
            )
            framework = st.selectbox("Framework", options=form_options["frameworks"])
            known_skills = form_options["skills_by_framework"].get(framework) or []
            if known_skills:
                skill_name = st.selectbox("Skill", options=known_skills)
            else:
                skill_name = st.text_input("Skill", value="")
            status = st.selectbox(
                "Initial status",
                options=["pending", "running", "completed", "failed", "cancelled"],
                index=0,
            )
            dry_run_submit = st.form_submit_button("Dry run", width="stretch")
            create_submit = st.form_submit_button("Create task", width="stretch")

        payload = {
            "case_id": case_options.get(case_choice),
            "framework": framework,
            "skill_name": skill_name,
            "status": status,
        }

        if dry_run_submit:
            dry_run_result, dry_run_error = safe_call(
                client.agent_task_dry_run,
                case_id=payload["case_id"],
                framework=framework,
                skill_name=skill_name,
                status=status,
            )
            if dry_run_error:
                render_api_error(dry_run_error, fallback_title="Agent task dry run failed.")
            else:
                st.session_state["agent-task-dry-run-result"] = dry_run_result
        if create_submit:
            create_result, create_error = safe_call(
                client.create_agent_task,
                payload["case_id"],
                framework=framework,
                skill_name=skill_name,
                status=status,
            )
            if create_error:
                render_api_error(create_error, fallback_title="Agent task creation failed.")
            else:
                st.success(f"Created agent task {str(create_result.get('id') or '')[:8]}")
                st.session_state["agent-task-last-created"] = create_result
                st.rerun()

        if st.session_state.get("agent-task-dry-run-result"):
            st.code(
                format_agent_task_dry_run_preview(st.session_state["agent-task-dry-run-result"])
            )
            with st.expander("Raw dry run payload"):
                st.json(st.session_state["agent-task-dry-run-result"])

    with tasks_tab:
        filter_cols = st.columns(3)
        selected_case_filter = filter_cols[0].selectbox(
            "Case filter",
            options=["all", *list(case_options.keys())],
            format_func=lambda x: "all" if x == "all" else ("system" if x == "system" else x[:8]),
        )
        selected_framework_filter = filter_cols[1].selectbox(
            "Framework filter",
            options=["all", *form_options["frameworks"]],
        )
        known_statuses = sorted({str(task.get("status") or "unknown") for task in tasks})
        selected_status_filter = filter_cols[2].selectbox(
            "Status filter",
            options=["all", *known_statuses],
        )

        filtered_tasks = []
        for task in tasks:
            if selected_case_filter != "all":
                task_case = task.get("case_id") or "system"
                if task_case != case_options.get(selected_case_filter) and not (
                    selected_case_filter == "system" and task_case in {None, "system"}
                ):
                    continue
            if (
                selected_framework_filter != "all"
                and str(task.get("framework") or "other") != selected_framework_filter
            ):
                continue
            if (
                selected_status_filter != "all"
                and str(task.get("status") or "unknown") != selected_status_filter
            ):
                continue
            filtered_tasks.append(task)

        if filtered_tasks:
            st.dataframe(
                normalize_table_rows(build_agent_task_table_rows(filtered_tasks)),
                width="stretch",
                hide_index=True,
            )
            task_labels = {
                f"{str(task.get('id') or '')[:8]} — {task.get('framework')} — {task.get('skill_name')} — {task.get('status')}": task
                for task in filtered_tasks
            }
            selected_task_label = st.selectbox("Task detail", options=list(task_labels.keys()))
            selected_task = task_labels[selected_task_label]
            st.code(format_agent_task_detail_preview(selected_task))
            with st.expander("Raw task payload"):
                st.json(selected_task)
            if selected_task.get("logs"):
                with st.expander("Task logs"):
                    st.json(selected_task.get("logs"))
            if selected_task.get("artifacts"):
                with st.expander("Task artifacts"):
                    st.json(selected_task.get("artifacts"))

            default_logs_text = (
                json.dumps(selected_task.get("logs"), indent=2, sort_keys=True)
                if selected_task.get("logs") is not None
                else ""
            )
            default_artifacts_text = (
                json.dumps(selected_task.get("artifacts"), indent=2, sort_keys=True)
                if selected_task.get("artifacts") is not None
                else ""
            )
            with st.form(f"agent-task-status-update-{selected_task.get('id')}"):
                updated_status = st.selectbox(
                    "Update status",
                    options=["pending", "running", "completed", "failed", "cancelled"],
                    index=["pending", "running", "completed", "failed", "cancelled"].index(
                        str(selected_task.get("status") or "pending")
                    )
                    if str(selected_task.get("status") or "pending")
                    in ["pending", "running", "completed", "failed", "cancelled"]
                    else 0,
                )
                updated_logs_text = st.text_area(
                    "Update logs (JSON object)", value=default_logs_text, height=140
                )
                updated_artifacts_text = st.text_area(
                    "Update artifacts (JSON object)",
                    value=default_artifacts_text,
                    height=140,
                )
                update_submit = st.form_submit_button("Update task", width="stretch")
            if update_submit:
                try:
                    update_payload = build_agent_task_update_payload(
                        status=updated_status,
                        logs_text=updated_logs_text,
                        artifacts_text=updated_artifacts_text,
                    )
                except ValueError as exc:
                    st.error(f"Invalid task JSON payload: {exc}")
                else:
                    updated_task, update_error = safe_call(
                        client.update_agent_task, str(selected_task.get("id")), **update_payload
                    )
                    if update_error:
                        render_api_error(update_error, fallback_title="Agent task update failed.")
                    else:
                        st.success(
                            f"Updated task {str(updated_task.get('id') or '')[:8]} to {updated_status}"
                        )
                        st.rerun()
        else:
            st.info("No agent tasks match the current filters.")
