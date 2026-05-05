from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.case_governance_actions import (
    build_case_delete_preview,
    build_case_redaction_preview,
    build_subject_redaction_preview,
    format_case_delete_preview,
    format_case_redaction_preview,
    format_subject_redaction_preview,
)


def test_build_case_redaction_preview_marks_change_and_severity() -> None:
    preview = build_case_redaction_preview(
        {"id": "case-1", "redaction_level": "full"},
        redaction_level="anonymous",
        confirm=True,
        reason="privacy request",
    )

    assert preview == {
        "case_id": "case-1",
        "current_level": "full",
        "target_level": "anonymous",
        "confirm": True,
        "reason": "privacy request",
        "will_change": True,
        "severity": "high",
    }


def test_format_case_redaction_preview_renders_core_fields() -> None:
    text = format_case_redaction_preview(
        {
            "case_id": "case-1",
            "current_level": "full",
            "target_level": "deidentify",
            "confirm": False,
            "reason": "",
            "will_change": True,
            "severity": "medium",
        }
    )

    assert "Case redaction preview" in text
    assert "target_level=deidentify" in text
    assert "confirm=False" in text


def test_build_case_delete_preview_distinguishes_soft_and_hard_delete() -> None:
    soft = build_case_delete_preview(
        {"id": "case-1", "redaction_level": "full"},
        hard_delete=False,
        confirm=True,
        reason="retention expired",
    )
    hard = build_case_delete_preview(
        {"id": "case-1", "redaction_level": "full"},
        hard_delete=True,
        confirm=True,
        reason="retention expired",
    )

    assert soft["delete_mode"] == "soft_delete"
    assert soft["severity"] == "high"
    assert hard["delete_mode"] == "hard_delete"
    assert hard["severity"] == "critical"


def test_format_case_delete_preview_renders_core_fields() -> None:
    text = format_case_delete_preview(
        {
            "case_id": "case-1",
            "current_level": "full",
            "delete_mode": "hard_delete",
            "confirm": True,
            "reason": "cleanup",
            "resulting_level": "deleted",
            "severity": "critical",
        }
    )

    assert "Case deletion preview" in text
    assert "delete_mode=hard_delete" in text
    assert "severity=critical" in text


def test_build_subject_redaction_preview_tracks_subject_and_level() -> None:
    preview = build_subject_redaction_preview(
        {"id": "sub-1", "redaction_level": "full", "anonymized_display_name": "Rosie-demo"},
        redaction_level="deidentify",
        confirm=True,
        reason="owner request",
    )

    assert preview == {
        "subject_id": "sub-1",
        "display_name": "Rosie-demo",
        "current_level": "full",
        "target_level": "deidentify",
        "confirm": True,
        "reason": "owner request",
        "will_change": True,
        "severity": "medium",
    }


def test_format_subject_redaction_preview_renders_core_fields() -> None:
    text = format_subject_redaction_preview(
        {
            "subject_id": "sub-1",
            "display_name": "Rosie-demo",
            "current_level": "deidentify",
            "target_level": "anonymous",
            "confirm": False,
            "reason": "",
            "will_change": True,
            "severity": "high",
        }
    )

    assert "Subject redaction preview" in text
    assert "subject_id=sub-1" in text
    assert "target_level=anonymous" in text
    assert "severity=high" in text
