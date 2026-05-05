from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.agent_task_panels import (
    build_agent_task_operator_summary,
    build_agent_task_table_rows,
    build_agent_task_update_payload,
    derive_agent_task_form_options,
    format_agent_task_detail_preview,
    format_agent_task_dry_run_preview,
    format_agent_task_operator_summary,
)


def test_build_agent_task_operator_summary_counts_statuses_and_frameworks() -> None:
    summary = build_agent_task_operator_summary(
        [
            {
                "id": "task-1",
                "case_id": "case-1",
                "framework": "hermes",
                "skill_name": "monitor_case_progress",
                "status": "pending",
                "logs": None,
                "artifacts": None,
                "created_at": "2026-04-22T18:00:00",
            },
            {
                "id": "task-2",
                "case_id": None,
                "framework": "openclaw",
                "skill_name": "run_bioinformatics_pipeline",
                "status": "completed",
                "logs": {"steps": 3},
                "artifacts": {"report": "x"},
                "created_at": "2026-04-22T18:05:00",
            },
        ]
    )

    assert summary["total_tasks"] == 2
    assert summary["case_scoped_tasks"] == 1
    assert summary["system_tasks"] == 1
    assert summary["status_counts"]["pending"] == 1
    assert summary["status_counts"]["completed"] == 1
    assert summary["framework_counts"]["hermes"] == 1
    assert summary["framework_counts"]["openclaw"] == 1


def test_build_agent_task_table_rows_flattens_fields() -> None:
    rows = build_agent_task_table_rows(
        [
            {
                "id": "task-12345678",
                "case_id": "case-12345678",
                "framework": "hermes",
                "skill_name": "monitor_case_progress",
                "status": "running",
                "logs": {"line": "ok"},
                "artifacts": None,
                "created_at": "2026-04-22T18:00:00",
            }
        ]
    )

    assert rows == [
        {
            "ID": "task-123",
            "Case": "case-123",
            "Framework": "hermes",
            "Skill": "monitor_case_progress",
            "Status": "running",
            "Has logs": "yes",
            "Has artifacts": "—",
            "Created": "2026-04-22T18:00:00",
        }
    ]


def test_derive_agent_task_form_options_groups_skills_by_framework() -> None:
    options = derive_agent_task_form_options(
        [
            {"framework": "hermes", "skill_name": "monitor_case_progress"},
            {"framework": "hermes", "skill_name": "create_ethics_review_package"},
            {"framework": "openclaw", "skill_name": "run_bioinformatics_pipeline"},
        ]
    )

    assert options["frameworks"] == ["hermes", "openclaw", "other"]
    assert options["skills_by_framework"]["hermes"] == [
        "create_ethics_review_package",
        "monitor_case_progress",
    ]
    assert options["skills_by_framework"]["other"] == []


def test_format_agent_task_dry_run_preview_renders_core_fields() -> None:
    preview = format_agent_task_dry_run_preview(
        {
            "dry_run": True,
            "case_exists": True,
            "framework": "hermes",
            "skill_name": "monitor_case_progress",
            "status": "pending",
            "skill_available": True,
            "skill_path": "skills/hermes/monitor_case_progress/SKILL.md",
            "would_create": {
                "case_id": "case-1",
                "framework": "hermes",
                "skill_name": "monitor_case_progress",
                "status": "pending",
            },
        }
    )

    assert "Agent task dry run" in preview
    assert "framework=hermes" in preview
    assert "skill_name=monitor_case_progress" in preview
    assert "case_id=case-1" in preview


def test_format_agent_task_operator_summary_renders_compact_preview() -> None:
    text = format_agent_task_operator_summary(
        {
            "total_tasks": 3,
            "case_scoped_tasks": 2,
            "system_tasks": 1,
            "status_counts": {"pending": 2, "completed": 1},
            "framework_counts": {"hermes": 2, "openclaw": 1},
        }
    )

    assert "Agent task workspace" in text
    assert "total_tasks=3" in text
    assert "status_counts=completed:1, pending:2" in text
    assert "framework_counts=hermes:2, openclaw:1" in text


def test_format_agent_task_detail_preview_renders_logs_and_artifacts_summary() -> None:
    text = format_agent_task_detail_preview(
        {
            "id": "task-1",
            "case_id": "case-1",
            "framework": "hermes",
            "skill_name": "monitor_case_progress",
            "status": "running",
            "logs": {"steps": ["one", "two"]},
            "artifacts": {"report_path": "/tmp/report.md"},
            "created_at": "2026-04-22T18:00:00",
        }
    )

    assert "Agent task detail" in text
    assert "framework=hermes" in text
    assert "logs_keys=steps" in text
    assert "artifact_keys=report_path" in text


def test_build_agent_task_update_payload_parses_json_fields() -> None:
    payload = build_agent_task_update_payload(
        status="completed",
        logs_text='{"steps": ["done"]}',
        artifacts_text='{"report_path": "/tmp/report.md"}',
    )

    assert payload == {
        "status": "completed",
        "logs": {"steps": ["done"]},
        "artifacts": {"report_path": "/tmp/report.md"},
    }


def test_build_agent_task_update_payload_treats_blank_json_as_none() -> None:
    payload = build_agent_task_update_payload(
        status="failed",
        logs_text="   ",
        artifacts_text="",
    )

    assert payload == {
        "status": "failed",
        "logs": None,
        "artifacts": None,
    }
