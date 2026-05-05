"""Dedicated mRNA/sequence safety gate helpers."""

from __future__ import annotations

import re

_SEQUENCE_PATTERN = re.compile(r"\b[ACGUTNacgutn]{12,}\b")
_SEQUENCE_ACTION_HINTS = ("sequence", "mrna", "rna", "construct")


def looks_like_sequence_content(content: str | None) -> bool:
    if not content:
        return False
    return _SEQUENCE_PATTERN.search(content.replace("\n", " ")) is not None


def evaluate_mrna_gate(
    *,
    action: str,
    species_mode: str,
    content: str | None = None,
    is_expert_mode: bool = False,
    is_export: bool = False,
    involves_sequence_data: bool = False,
):
    from backend.app.safety.preflight import PreflightResult

    action_lower = action.lower()
    sequence_context = (
        involves_sequence_data
        or looks_like_sequence_content(content)
        or any(hint in action_lower for hint in _SEQUENCE_ACTION_HINTS)
    )
    if not sequence_context:
        return PreflightResult(status=PreflightResult.PASS)

    if species_mode == "human" and is_export and not is_expert_mode:
        return PreflightResult(
            status=PreflightResult.BLOCK,
            reason="Human mode sequence export is blocked without physician/oncologist oversight and IRB approval.",
        )

    if not is_expert_mode:
        return PreflightResult(
            status=PreflightResult.REQUIRES_APPROVAL,
            reason="Sequence-level data access requires expert mode and professional attestation.",
        )

    return PreflightResult(status=PreflightResult.PASS)
