from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.report_preview import (
    format_agent_event_stream_preview,
    format_agent_skill_inventory_preview,
    summarize_agent_event_stream,
    summarize_agent_skill_inventory,
)


def test_summarize_agent_skill_inventory_counts_frameworks_and_boundaries() -> None:
    payload = [
        {
            "framework": "claude_code",
            "skill_name": "run_full_neovax_case_review",
            "description": "research coordination under professional oversight",
            "safety_boundaries": ["Research candidate only — not administerable"],
            "required_api_endpoints": ["POST /safety/preflight"],
        },
        {
            "framework": "hermes",
            "skill_name": "monitor_case_progress",
            "description": "monitor a case",
            "safety_boundaries": ["Professional oversight required"],
            "required_api_endpoints": ["GET /cases/{case_id}"],
        },
    ]

    summary = summarize_agent_skill_inventory(payload)

    assert summary["total_skills"] == 2
    assert summary["framework_counts"]["claude_code"] == 1
    assert summary["framework_counts"]["hermes"] == 1
    assert summary["skills_with_safety_boundaries"] == 2


def test_format_agent_skill_inventory_preview_renders_sections() -> None:
    preview = format_agent_skill_inventory_preview(
        [
            {
                "framework": "claude_code",
                "skill_name": "run_full_neovax_case_review",
                "skill_path": "skills/claude-code/run_full_neovax_case_review/SKILL.md",
                "description": "research coordination under professional oversight",
                "safety_boundaries": ["Research candidate only — not administerable"],
                "required_api_endpoints": ["POST /safety/preflight"],
            }
        ]
    )

    assert "Agent skill inventory" in preview
    assert "total_skills=1" in preview
    assert "run_full_neovax_case_review" in preview
    assert "POST /safety/preflight" in preview


def test_summarize_agent_event_stream_counts_event_families() -> None:
    payload = {
        "events": [
            {"event": "case.created", "data": {"case_id": "case-1"}},
            {"event": "agent_task.created", "data": {"case_id": "case-1"}},
            {"event": "report.generated", "data": {"case_id": "case-1"}},
        ]
    }

    summary = summarize_agent_event_stream(payload)

    assert summary["total_events"] == 3
    assert summary["event_family_counts"]["case"] == 1
    assert summary["event_family_counts"]["agent_task"] == 1
    assert summary["event_family_counts"]["report"] == 1


def test_format_agent_event_stream_preview_renders_recent_events() -> None:
    preview = format_agent_event_stream_preview(
        {
            "events": [
                {"event": "case.created", "data": {"case_id": "case-1", "action": "case.created"}},
                {"event": "agent_task.created", "data": {"case_id": "case-1", "action": "agent_task.created"}},
            ]
        }
    )

    assert "Agent event stream" in preview
    assert "total_events=2" in preview
    assert "case.created" in preview
    assert "agent_task.created" in preview
