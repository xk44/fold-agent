import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.safety_policy_view import (
    build_mode_restriction_rows,
    build_safety_policy_metrics,
    derive_safety_policy_references,
    format_safety_policy_summary,
    parse_safety_policy_markdown,
)

SAMPLE_POLICY = """# FoldAgent Safety Policy

## Scope

This policy governs all outputs.

## Hard Boundaries

### MUST NOT Generate

1. DIY vaccine manufacturing protocols
2. Injection instructions of any kind

### MUST Include On Every Export

- Research candidate only -- not administerable
- Professional review required

## Safety Preflight System

The preflight system checks:
- Whether the action is in the prohibited outputs list
- Whether the action requires expert mode
- Whether the action requires professional attestation
- Whether the output matches unsafe text patterns

If the preflight system blocks an action:
- The action is NOT executed
- The attempt is logged in the audit trail

## Mode Restrictions

### Demo Mode
- Synthetic data only
- No real patient data

### Human / Clinical Mode
- Requires assigned physician/oncologist
- Not for treatment use on every output

## Audit Requirements

- case_id
- actor

## mRNA / Construct Handling

- Explicit expert mode activation
- Manual approval checkpoint

## AlphaFold Output Policy

- Structure prediction only -- not clinical validation
- Confidence metrics (pLDDT, pAE)

## Agent Skill Safety

- Include a safety boundaries section in SKILL.md
- Support dry-run mode

## Unsafe Text Scanner

- Dosing language patterns
- Injection/administration instructions
"""


def test_parse_safety_policy_markdown_extracts_lists_and_modes() -> None:
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)

    assert policy["scope"] == "This policy governs all outputs."
    assert policy["must_not_generate"] == [
        "DIY vaccine manufacturing protocols",
        "Injection instructions of any kind",
    ]
    assert policy["must_include_on_every_export"] == [
        "Research candidate only -- not administerable",
        "Professional review required",
    ]
    assert policy["preflight_checks"] == [
        "Whether the action is in the prohibited outputs list",
        "Whether the action requires expert mode",
        "Whether the action requires professional attestation",
        "Whether the output matches unsafe text patterns",
    ]
    assert policy["preflight_block_behavior"] == [
        "The action is NOT executed",
        "The attempt is logged in the audit trail",
    ]
    assert policy["mode_restrictions"]["demo mode"] == [
        "Synthetic data only",
        "No real patient data",
    ]
    assert policy["mode_restrictions"]["human / clinical mode"] == [
        "Requires assigned physician/oncologist",
        "Not for treatment use on every output",
    ]


def test_build_safety_policy_metrics_counts_sections() -> None:
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)

    assert build_safety_policy_metrics(policy) == [
        {"label": "Blocked outputs", "value": "2"},
        {"label": "Export requirements", "value": "2"},
        {"label": "Preflight checks", "value": "4"},
        {"label": "Mode profiles", "value": "2"},
    ]


def test_format_safety_policy_summary_surfaces_scope_and_counts() -> None:
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)
    summary = format_safety_policy_summary(policy)

    assert "This policy governs all outputs." in summary
    assert "blocked_outputs=2" in summary
    assert "export_requirements=2" in summary
    assert "preflight_checks=4" in summary
    assert "demo mode" in summary
    assert "human / clinical mode" in summary


def test_build_mode_restriction_rows_renders_table_friendly_strings() -> None:
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)
    rows = build_mode_restriction_rows(policy)

    assert rows == [
        {
            "mode": "demo mode",
            "restriction_count": "2",
            "restrictions": "Synthetic data only | No real patient data",
        },
        {
            "mode": "human / clinical mode",
            "restriction_count": "2",
            "restrictions": "Requires assigned physician/oncologist | Not for treatment use on every output",
        },
    ]


def test_derive_safety_policy_references_maps_requires_approval_to_policy_rules() -> None:
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)
    refs = derive_safety_policy_references(
        {
            "detail": "Sequence-level data access requires expert mode and professional attestation.",
            "safety_status": "requires_approval",
            "safety_reason": "Sequence-level data access requires expert mode and professional attestation.",
            "blocked_patterns": [],
        },
        policy,
    )

    assert "Safety Preflight System -> Whether the action requires expert mode" in refs
    assert "Safety Preflight System -> Whether the action requires professional attestation" in refs
    assert "mRNA / Construct Handling -> Explicit expert mode activation" in refs
    assert "mRNA / Construct Handling -> Manual approval checkpoint" in refs


def test_derive_safety_policy_references_maps_blocked_patterns_to_scanner_and_boundary_rules() -> (
    None
):
    policy = parse_safety_policy_markdown(SAMPLE_POLICY)
    refs = derive_safety_policy_references(
        {
            "detail": "Blocked unsafe export content.",
            "safety_status": "block",
            "safety_reason": "Blocked unsafe export content.",
            "blocked_patterns": ["dose", "injection"],
        },
        policy,
    )

    assert "Hard Boundaries / MUST NOT Generate -> Dosing schedules for any substance" in refs
    assert "Hard Boundaries / MUST NOT Generate -> Injection instructions of any kind" in refs
    assert "Unsafe Text Scanner -> Dosing language patterns" in refs
    assert "Unsafe Text Scanner -> Injection/administration instructions" in refs
