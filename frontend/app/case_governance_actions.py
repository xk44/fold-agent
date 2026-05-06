"""Pure helpers for case and subject redaction/deletion operator controls."""

from __future__ import annotations


def build_case_redaction_preview(
    case_detail: dict | None,
    *,
    redaction_level: str,
    confirm: bool,
    reason: str | None = None,
) -> dict:
    case_detail = case_detail or {}
    current_level = str(case_detail.get("redaction_level") or "full")
    target_level = str(redaction_level or current_level)
    return {
        "case_id": str(case_detail.get("id") or "unknown"),
        "current_level": current_level,
        "target_level": target_level,
        "confirm": bool(confirm),
        "reason": (reason or "").strip(),
        "will_change": current_level != target_level,
        "severity": "high" if target_level in {"anonymous", "deleted"} else "medium",
    }


def format_case_redaction_preview(preview: dict) -> str:
    return "\n".join(
        [
            "Case redaction preview",
            f"case_id={preview.get('case_id')}",
            f"current_level={preview.get('current_level')}",
            f"target_level={preview.get('target_level')}",
            f"will_change={preview.get('will_change')}",
            f"confirm={preview.get('confirm')}",
            f"severity={preview.get('severity')}",
            f"reason={preview.get('reason') or 'n/a'}",
        ]
    )


def build_subject_redaction_preview(
    subject_detail: dict | None,
    *,
    redaction_level: str,
    confirm: bool,
    reason: str | None = None,
) -> dict:
    subject_detail = subject_detail or {}
    current_level = str(subject_detail.get("redaction_level") or "full")
    target_level = str(redaction_level or current_level)
    return {
        "subject_id": str(subject_detail.get("id") or "unknown"),
        "display_name": str(
            subject_detail.get("anonymized_display_name") or subject_detail.get("id") or "unknown"
        ),
        "current_level": current_level,
        "target_level": target_level,
        "confirm": bool(confirm),
        "reason": (reason or "").strip(),
        "will_change": current_level != target_level,
        "severity": "high" if target_level in {"anonymous", "deleted"} else "medium",
    }


def format_subject_redaction_preview(preview: dict) -> str:
    return "\n".join(
        [
            "Subject redaction preview",
            f"subject_id={preview.get('subject_id')}",
            f"display_name={preview.get('display_name')}",
            f"current_level={preview.get('current_level')}",
            f"target_level={preview.get('target_level')}",
            f"will_change={preview.get('will_change')}",
            f"confirm={preview.get('confirm')}",
            f"severity={preview.get('severity')}",
            f"reason={preview.get('reason') or 'n/a'}",
        ]
    )


def build_case_delete_preview(
    case_detail: dict | None,
    *,
    hard_delete: bool,
    confirm: bool,
    reason: str | None = None,
) -> dict:
    case_detail = case_detail or {}
    delete_mode = "hard_delete" if hard_delete else "soft_delete"
    return {
        "case_id": str(case_detail.get("id") or "unknown"),
        "current_level": str(case_detail.get("redaction_level") or "full"),
        "delete_mode": delete_mode,
        "confirm": bool(confirm),
        "reason": (reason or "").strip(),
        "resulting_level": "deleted",
        "severity": "critical" if hard_delete else "high",
    }


def format_case_delete_preview(preview: dict) -> str:
    return "\n".join(
        [
            "Case deletion preview",
            f"case_id={preview.get('case_id')}",
            f"current_level={preview.get('current_level')}",
            f"delete_mode={preview.get('delete_mode')}",
            f"resulting_level={preview.get('resulting_level')}",
            f"confirm={preview.get('confirm')}",
            f"severity={preview.get('severity')}",
            f"reason={preview.get('reason') or 'n/a'}",
        ]
    )
