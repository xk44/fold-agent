import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.audit_viewer import (
    build_audit_action_options,
    filter_audit_entries,
    format_audit_entry_preview,
)


def test_build_audit_action_options_sorts_unique_actions_with_all_first() -> None:
    actions = build_audit_action_options(
        [
            {"action": "sample.uploaded"},
            {"action": "case.created"},
            {"action": "sample.uploaded"},
            {"action": "report.generated"},
        ]
    )

    assert actions == ["all", "case.created", "report.generated", "sample.uploaded"]


def test_filter_audit_entries_filters_by_action_and_text_query() -> None:
    entries = [
        {
            "id": "1",
            "action": "case.created",
            "actor": "api",
            "safety_gate_result": "pass",
            "details": {"diagnosis_summary": "melanoma"},
            "timestamp": "2026-04-19T10:00:00Z",
        },
        {
            "id": "2",
            "action": "sample.uploaded",
            "actor": "api",
            "safety_gate_result": "pass",
            "details": {"source_lab": "Lab A"},
            "timestamp": "2026-04-19T11:00:00Z",
        },
        {
            "id": "3",
            "action": "report.generated",
            "actor": "api",
            "safety_gate_result": "requires_approval",
            "details": {"report_type": "candidate_review"},
            "timestamp": "2026-04-19T12:00:00Z",
        },
    ]

    filtered = filter_audit_entries(entries, selected_action="sample.uploaded", query="lab a")

    assert [entry["id"] for entry in filtered] == ["2"]


def test_format_audit_entry_preview_surfaces_action_actor_and_detail_summary() -> None:
    preview = format_audit_entry_preview(
        {
            "id": "3",
            "action": "report.generated",
            "actor": "api",
            "safety_gate_result": "requires_approval",
            "details": {"report_type": "candidate_review", "blocked_patterns": ["dose"]},
            "timestamp": "2026-04-19T12:00:00Z",
        }
    )

    assert "report.generated" in preview
    assert "actor=api" in preview
    assert "gate=requires_approval" in preview
    assert "candidate_review" in preview
    assert "dose" in preview
