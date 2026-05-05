"""Event-prefix presets for different dashboard/operator views.

These presets must align with the backend's real event families exposed by
`/agent/events`. Keep names explicit so narrowing is intentional and easy to
verify in tests.
"""
from __future__ import annotations

# Canonical backend event-family prefixes.
PREFIX_AGENT_TASK = "agent_task."
PREFIX_BACKGROUND_JOB = "background_job."
PREFIX_BUNDLE = "bundle."
PREFIX_CANDIDATE = "candidate."
PREFIX_CASE = "case."
PREFIX_DEMO = "demo."
PREFIX_EXPERT = "expert."
PREFIX_PIPELINE = "pipeline."
PREFIX_REPORT = "report."
PREFIX_SAFETY = "safety."
PREFIX_SAMPLE = "sample."
PREFIX_STRUCTURE_JOB = "structure_job."
PREFIX_SUBJECT = "subject."
PREFIX_VARIANT = "variant."
PREFIX_ALPHAFOLD = "alphafold."

# Backward-compatible aliases used by older callers/tests.
PREFIX_STRUCTURE = PREFIX_STRUCTURE_JOB
PREFIX_ALPHAFOLD_BACKEND = PREFIX_ALPHAFOLD
PREFIX_ALPHAFOLD_STRUCTURE = PREFIX_ALPHAFOLD

_ALL_KNOWN_PREFIXES: tuple[str, ...] = (
    PREFIX_AGENT_TASK,
    PREFIX_BACKGROUND_JOB,
    PREFIX_BUNDLE,
    PREFIX_CANDIDATE,
    PREFIX_CASE,
    PREFIX_DEMO,
    PREFIX_EXPERT,
    PREFIX_PIPELINE,
    PREFIX_REPORT,
    PREFIX_SAFETY,
    PREFIX_SAMPLE,
    PREFIX_STRUCTURE_JOB,
    PREFIX_SUBJECT,
    PREFIX_VARIANT,
    PREFIX_ALPHAFOLD,
)

# Main dashboard page still needs the full known family set because it renders
# live feed, operator/job surfaces, pipeline surfaces, case inspection, and
# report/export surfaces on one page.
DASHBOARD_PREFIXES: tuple[str, ...] = _ALL_KNOWN_PREFIXES

# Operator-facing job/event surfaces.
OPERATOR_PREFIXES: tuple[str, ...] = (
    PREFIX_AGENT_TASK,
    PREFIX_BACKGROUND_JOB,
    PREFIX_EXPERT,
    PREFIX_PIPELINE,
    PREFIX_SAFETY,
    PREFIX_STRUCTURE_JOB,
    PREFIX_ALPHAFOLD,
)

# Pipeline/structure execution surfaces.
PIPELINE_PREFIXES: tuple[str, ...] = (
    PREFIX_BACKGROUND_JOB,
    PREFIX_PIPELINE,
    PREFIX_SAFETY,
    PREFIX_STRUCTURE_JOB,
    PREFIX_ALPHAFOLD,
)

# Narrow safety-only surface.
SAFETY_PREFIXES: tuple[str, ...] = (
    PREFIX_SAFETY,
    PREFIX_EXPERT,
)

_PRESETS: dict[str, tuple[str, ...] | None] = {
    "dashboard": DASHBOARD_PREFIXES,
    "operator": OPERATOR_PREFIXES,
    "pipeline": PIPELINE_PREFIXES,
    "safety": SAFETY_PREFIXES,
    "all": None,
}


def resolve_prefixes(view: str) -> tuple[str, ...] | None:
    return _PRESETS.get(view)


def validate_prefixes(prefixes: tuple[str, ...] | None) -> list[str]:
    if prefixes is None:
        return []
    valid = set(_ALL_KNOWN_PREFIXES)
    return [p for p in prefixes if p not in valid]


def merge_prefixes(*presets: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if any(p is None for p in presets):
        return None
    merged: set[str] = set()
    for preset in presets:
        if preset:
            merged.update(preset)
    return tuple(sorted(merged)) if merged else None


def prefixes_for_families(*families: str) -> tuple[str, ...]:
    lookup = {
        "agent_task": PREFIX_AGENT_TASK,
        "background_job": PREFIX_BACKGROUND_JOB,
        "bundle": PREFIX_BUNDLE,
        "candidate": PREFIX_CANDIDATE,
        "case": PREFIX_CASE,
        "demo": PREFIX_DEMO,
        "expert": PREFIX_EXPERT,
        "pipeline": PREFIX_PIPELINE,
        "report": PREFIX_REPORT,
        "safety": PREFIX_SAFETY,
        "sample": PREFIX_SAMPLE,
        "structure": PREFIX_STRUCTURE_JOB,
        "structure_job": PREFIX_STRUCTURE_JOB,
        "subject": PREFIX_SUBJECT,
        "variant": PREFIX_VARIANT,
        "alphafold": PREFIX_ALPHAFOLD,
        "alphafold_backend": PREFIX_ALPHAFOLD,
        "alphafold_structure": PREFIX_ALPHAFOLD,
    }
    result: list[str] = []
    for family in families:
        prefix = lookup.get(family.lower())
        if prefix is not None:
            result.append(prefix)
    return tuple(result)
