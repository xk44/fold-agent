"""Dry-run mode for NeoVax agent actions.

Simulates actions and returns what WOULD happen without executing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DryRunResult:
    """Result of a dry-run simulation."""

    action: str
    would_affect: list[str]
    parameters: dict
    safety_level: str  # safe | requires-review | dangerous
    requires_approval: bool
    notes: str = field(default="")


# ---------------------------------------------------------------------------
# Approval-required registry
# ---------------------------------------------------------------------------

APPROVAL_REQUIRED_ACTIONS: list[str] = [
    "delete_case",
    "export_data",
    "generate_report",
    "submit_alphafold",
    "run_pipeline",
]

_APPROVAL_REASONS: dict[str, tuple[str, str]] = {
    "delete_case": (
        "Deletes all case data permanently. This action cannot be undone.",
        "Explicitly confirm deletion by setting confirm=true in the request body.",
    ),
    "export_data": (
        "Exports potentially sensitive case data including sequence and subject information.",
        "Confirm data export is authorised and compliant with privacy policy.",
    ),
    "generate_report": (
        "Generates a research report that may reference sensitive patient or subject data.",
        "Ensure professional oversight is in place before generating reports.",
    ),
    "submit_alphafold": (
        "Submits sequence data to an external AlphaFold Server (external API call).",
        "Confirm external data transfer is permitted under the applicable data governance policy.",
    ),
    "run_pipeline": (
        "Executes the full analysis pipeline, which may run external bioinformatics tools.",
        "Verify pipeline configuration and resource availability before executing.",
    ),
}


def check_approval_required(action: str) -> dict:
    """Return approval requirement info for a given action name."""
    required = action in APPROVAL_REQUIRED_ACTIONS
    if required:
        reason, prompt = _APPROVAL_REASONS.get(action, ("Approval required.", "Confirm the action."))
    else:
        reason = "This action does not require explicit approval."
        prompt = ""
    return {
        "action": action,
        "required": required,
        "reason": reason,
        "approval_prompt": prompt,
    }


# ---------------------------------------------------------------------------
# Dry-run implementations per action
# ---------------------------------------------------------------------------

def _dry_run_create_case(params: dict) -> DryRunResult:
    species = params.get("species", "demo")
    return DryRunResult(
        action="create_case",
        would_affect=["cases table"],
        parameters=params,
        safety_level="requires-review",
        requires_approval=False,
        notes=(
            f"Would create a new case with species='{species}'. "
            "No data will be written in dry-run mode."
        ),
    )


def _dry_run_run_pipeline(params: dict) -> DryRunResult:
    case_id = params.get("case_id", "<unknown>")
    steps = params.get("steps", ["all"])
    return DryRunResult(
        action="run_pipeline",
        would_affect=["pipeline_runs table", "variants table", "candidates table", f"case {case_id}"],
        parameters=params,
        safety_level="dangerous",
        requires_approval=True,
        notes=(
            f"Would run pipeline steps {steps} for case '{case_id}'. "
            "Triggers bioinformatics tools (BWA, GATK, VEP, pVACtools). "
            "Requires approval before execution."
        ),
    )


def _dry_run_generate_report(params: dict) -> DryRunResult:
    case_id = params.get("case_id", "<unknown>")
    report_type = params.get("report_type", "candidate-review")
    return DryRunResult(
        action="generate_report",
        would_affect=["reports table", f"case {case_id}"],
        parameters=params,
        safety_level="requires-review",
        requires_approval=True,
        notes=(
            f"Would generate a '{report_type}' report for case '{case_id}'. "
            "Report is research-only and carries the RESEARCH_LABEL disclaimer. "
            "Requires professional oversight."
        ),
    )


def _dry_run_export_data(params: dict) -> DryRunResult:
    case_id = params.get("case_id", "<unknown>")
    fmt = params.get("format", "json")
    return DryRunResult(
        action="export_data",
        would_affect=[f"case {case_id} bundle", "artifacts directory"],
        parameters=params,
        safety_level="dangerous",
        requires_approval=True,
        notes=(
            f"Would export case '{case_id}' data in '{fmt}' format. "
            "Includes all samples, variants, candidates, and reports. "
            "Requires approval due to sensitive data export."
        ),
    )


def _dry_run_delete_case(params: dict) -> DryRunResult:
    case_id = params.get("case_id", "<unknown>")
    return DryRunResult(
        action="delete_case",
        would_affect=[
            f"case {case_id}",
            "samples",
            "variants",
            "candidates",
            "reports",
            "pipeline_runs",
            "structure_jobs",
            "audit_logs",
        ],
        parameters=params,
        safety_level="dangerous",
        requires_approval=True,
        notes=(
            f"Would permanently delete case '{case_id}' and ALL associated records. "
            "This action is irreversible. Requires explicit confirm=true."
        ),
    )


def _dry_run_submit_alphafold(params: dict) -> DryRunResult:
    backend = params.get("backend", "alphafold_server")
    sequence = params.get("sequence", "")
    return DryRunResult(
        action="submit_alphafold",
        would_affect=["structure_jobs table", "external AlphaFold API"],
        parameters={**params, "sequence": sequence[:20] + "..." if len(sequence) > 20 else sequence},
        safety_level="dangerous",
        requires_approval=True,
        notes=(
            f"Would submit sequence data to backend '{backend}'. "
            "If backend is 'alphafold_server', data will be sent to an external service. "
            "Requires approval for external data transfer."
        ),
    )


_ACTION_HANDLERS = {
    "create_case": _dry_run_create_case,
    "run_pipeline": _dry_run_run_pipeline,
    "generate_report": _dry_run_generate_report,
    "export_data": _dry_run_export_data,
    "delete_case": _dry_run_delete_case,
    "submit_alphafold": _dry_run_submit_alphafold,
}

SUPPORTED_DRY_RUN_ACTIONS: list[str] = list(_ACTION_HANDLERS.keys())


def dry_run_action(action_name: str, params: dict) -> DryRunResult:
    """Simulate an action and return what would happen without executing it.

    Parameters
    ----------
    action_name:
        Name of the action to simulate. See ``SUPPORTED_DRY_RUN_ACTIONS``.
    params:
        Parameters that would be passed to the action.

    Raises
    ------
    ValueError
        If ``action_name`` is not in ``SUPPORTED_DRY_RUN_ACTIONS``.
    """
    handler = _ACTION_HANDLERS.get(action_name)
    if handler is None:
        raise ValueError(
            f"Unknown action '{action_name}'. "
            f"Supported actions: {SUPPORTED_DRY_RUN_ACTIONS}"
        )
    return handler(params)
