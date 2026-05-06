"""FoldAgent Safety Preflight System

Every write action, export, and agent task must pass through the safety
preflight system before execution. This module implements the core safety
checks that prevent prohibited outputs and enforce mode restrictions.
"""

import re

import structlog

from backend.app.safety.mrna_gate import evaluate_mrna_gate

logger = structlog.get_logger()

# Patterns that indicate prohibited outputs
UNSAFE_OUTPUT_PATTERNS = [
    # Manufacturing / formulation
    re.compile(r"(inject|injection|injectable)", re.IGNORECASE),
    re.compile(r"(dose|dosing|dosage)\s+(schedule|regimen|instruction)", re.IGNORECASE),
    re.compile(r"(LNP|lipid nanoparticle)\s+(formul|prepar|mix)", re.IGNORECASE),
    re.compile(r"(adjuvant|adjuvant)\s+(mix|prepar|formul)", re.IGNORECASE),
    re.compile(r"(steril|sterility|QC release).*(administ|inject|use)", re.IGNORECASE),
    re.compile(r"(ready\s+to\s+(inject|administ|use))", re.IGNORECASE),
    re.compile(r"(manufactur|prepar).*(vaccine|mRNA|RNA)", re.IGNORECASE),
    # Treatment instructions
    re.compile(r"(treatment|therapy)\s+(protocol|regimen|plan)\s+(for|to)", re.IGNORECASE),
    re.compile(r"(self.?administ|self.?inject|self.?treat)", re.IGNORECASE),
    # Clinical validity claims
    re.compile(r"(clinically\s+valid(ated)?|proven\s+effective|cures?\s+cancer)", re.IGNORECASE),
    re.compile(r"(AI|artificial intelligence)\s+(cures?|treats?|heals?)", re.IGNORECASE),
]


class PreflightResult:
    """Result of a safety preflight check."""

    PASS = "pass"
    BLOCK = "block"
    REQUIRES_APPROVAL = "requires_approval"

    def __init__(
        self, status: str, reason: str | None = None, blocked_patterns: list | None = None
    ):
        self.status = status
        self.reason = reason
        self.blocked_patterns = blocked_patterns or []

    @property
    def allowed(self) -> bool:
        return self.status == self.PASS

    @property
    def blocked(self) -> bool:
        return self.status == self.BLOCK

    @property
    def needs_approval(self) -> bool:
        return self.status == self.REQUIRES_APPROVAL


def check_text_for_unsafe_patterns(text: str) -> tuple[bool, list[str]]:
    """Check text against unsafe output patterns.

    Returns:
        Tuple of (is_safe, list_of_matched_pattern_descriptions)
    """
    matched = []
    for pattern in UNSAFE_OUTPUT_PATTERNS:
        if pattern.search(text):
            matched.append(f"Matched pattern: {pattern.pattern}")

    return len(matched) == 0, matched


def preflight_action(
    action: str,
    species_mode: str,
    content: str | None = None,
    is_expert_mode: bool = False,
    is_export: bool = False,
    involves_external_upload: bool = False,
    involves_sequence_data: bool = False,
) -> PreflightResult:
    """Run safety preflight checks before an action.

    This is the core safety gate. Every API write, export, and agent action
    should call this before proceeding.

    Args:
        action: The action being attempted (e.g., 'export_report', 'run_pipeline')
        species_mode: Current operating mode (demo, dog, human)
        content: Text content to check for unsafe patterns (optional)
        is_expert_mode: Whether expert mode is active
        is_export: Whether this is an export action
        involves_external_upload: Whether data will be uploaded externally
        involves_sequence_data: Whether this involves mRNA/sequence-level data

    Returns:
        PreflightResult indicating pass, block, or requires_approval
    """
    # Check 1: Unsafe text patterns
    if content:
        is_safe, unsafe_matches = check_text_for_unsafe_patterns(content)
        if not is_safe:
            logger.warning("safety_preflight_blocked", action=action, patterns=unsafe_matches)
            return PreflightResult(
                status=PreflightResult.BLOCK,
                reason=f"Content matches prohibited output patterns: {unsafe_matches}",
                blocked_patterns=unsafe_matches,
            )

    # Check 2: Dedicated mRNA / sequence-data gate
    mrna_gate_result = evaluate_mrna_gate(
        action=action,
        species_mode=species_mode,
        content=content,
        is_expert_mode=is_expert_mode,
        is_export=is_export,
        involves_sequence_data=involves_sequence_data,
    )
    if mrna_gate_result.status != PreflightResult.PASS:
        logger.warning(
            "safety_preflight_sequence_gate",
            action=action,
            status=mrna_gate_result.status,
            reason=mrna_gate_result.reason,
        )
        return mrna_gate_result

    # Check 3: External upload requires confirmation
    if involves_external_upload:
        logger.warning(
            "safety_preflight_requires_approval", action=action, reason="external_upload"
        )
        return PreflightResult(
            status=PreflightResult.REQUIRES_APPROVAL,
            reason="External data upload requires explicit user confirmation and privacy acknowledgment.",
        )

    # Check 4: Demo mode restrictions on real data claims
    if species_mode == "demo" and content:
        demo_warning_patterns = ["clinically validated", "treatment plan", "administer"]
        for pattern in demo_warning_patterns:
            if pattern.lower() in content.lower():
                return PreflightResult(
                    status=PreflightResult.BLOCK,
                    reason=f"Demo mode cannot make claims about: {pattern}",
                )

    # Check 5: Export actions require safety label (non-demo species only)
    REQUIRED_EXPORT_LABEL = "Research candidate only — not administerable"
    if is_export and species_mode != "demo":
        label_present = content and REQUIRED_EXPORT_LABEL.lower() in content.lower()
        if not label_present:
            logger.warning(
                "safety_preflight_export_label_missing",
                action=action,
                species_mode=species_mode,
            )
            return PreflightResult(
                status=PreflightResult.BLOCK,
                reason=(
                    f"Export blocked: content must include the required safety label: "
                    f'"{REQUIRED_EXPORT_LABEL}"'
                ),
            )
        logger.info("safety_preflight_export_check", action=action, species_mode=species_mode)

    # All checks passed
    logger.info("safety_preflight_pass", action=action, species_mode=species_mode)
    return PreflightResult(status=PreflightResult.PASS)
