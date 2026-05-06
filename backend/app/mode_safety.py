"""FoldAgent Research Mode Safety Configuration.

Defines research modes, safety levels, and access control checks.
"""

from __future__ import annotations

from enum import Enum


class ResearchMode(str, Enum):
    neoantigen = "neoantigen"
    variant_pathogenicity = "variant_pathogenicity"
    drug_discovery = "drug_discovery"
    vaccine_design = "vaccine_design"
    antibody_design = "antibody_design"
    gene_therapy = "gene_therapy"
    ppi_mapping = "ppi_mapping"
    enzyme_engineering = "enzyme_engineering"
    protein_misfolding = "protein_misfolding"


# ---------------------------------------------------------------------------
# Safety configuration per mode
# ---------------------------------------------------------------------------

MODE_SAFETY_CONFIG: dict[str, dict] = {
    ResearchMode.neoantigen: {
        "safety_level": "standard",
        "requires_attestation": False,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "chai1",
        ],
        "prohibited_actions": [],
        "disclaimers": [
            "Neoantigen predictions are computational estimates and require experimental validation.",
            "Not for clinical use without qualified medical oversight.",
        ],
    },
    ResearchMode.variant_pathogenicity: {
        "safety_level": "standard",
        "requires_attestation": False,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "alphafold_server",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
        ],
        "prohibited_actions": [],
        "disclaimers": [
            "Variant pathogenicity scores are research-grade; not a substitute for clinical genetics review.",
            "Results must be interpreted in clinical context by qualified personnel.",
        ],
    },
    ResearchMode.drug_discovery: {
        "safety_level": "elevated",
        "requires_attestation": True,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "chai1",
        ],
        "prohibited_actions": [
            "share_raw_binding_data_externally",
            "publish_without_ip_review",
        ],
        "disclaimers": [
            "Drug discovery outputs are for internal research only; IP review required before publication.",
            "Binding affinity predictions are indicative only and require wet-lab validation.",
        ],
    },
    ResearchMode.vaccine_design: {
        "safety_level": "elevated",
        "requires_attestation": True,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "rfdiffusion",
        ],
        "prohibited_actions": [
            "administer_to_humans_without_trial",
            "bypass_regulatory_review",
        ],
        "disclaimers": [
            "Vaccine design outputs require IND/regulatory review before human use.",
            "Computational immunogenicity predictions do not replace clinical trials.",
        ],
    },
    ResearchMode.antibody_design: {
        "safety_level": "elevated",
        "requires_attestation": True,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "rfdiffusion",
            "proteinmpnn",
            "chai1",
        ],
        "prohibited_actions": [
            "administer_to_humans_without_trial",
        ],
        "disclaimers": [
            "Antibody designs are computational predictions; experimental validation required.",
            "Humanization and safety assessment must precede clinical development.",
        ],
    },
    ResearchMode.gene_therapy: {
        "safety_level": "expert_only",
        "requires_attestation": True,
        "requires_ethics_review": True,
        "allowed_backends": [
            "mock",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "esmfold",
        ],
        "prohibited_actions": [
            "human_germline_editing",
            "distribute_vectors_without_biosafety_review",
            "use_without_iacuc_irb_approval",
        ],
        "disclaimers": [
            "Gene therapy research requires IRB/IACUC approval and institutional biosafety committee review.",
            "Germline editing is prohibited under this platform.",
            "All outputs are for pre-clinical research only.",
        ],
    },
    ResearchMode.ppi_mapping: {
        "safety_level": "standard",
        "requires_attestation": False,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "alphafold_server",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "chai1",
        ],
        "prohibited_actions": [],
        "disclaimers": [
            "PPI predictions are computational; experimental co-IP or structural validation recommended.",
        ],
    },
    ResearchMode.enzyme_engineering: {
        "safety_level": "elevated",
        "requires_attestation": True,
        "requires_ethics_review": False,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "boltz2",
            "esmfold",
            "openfold",
            "rfdiffusion",
            "rfdiffusion2",
            "proteinmpnn",
        ],
        "prohibited_actions": [
            "design_select_agents_without_biosafety_review",
        ],
        "disclaimers": [
            "Designed enzymes must be assessed for biosafety prior to synthesis and characterization.",
            "Select-agent regulations apply to certain enzymatic activities.",
        ],
    },
    ResearchMode.protein_misfolding: {
        "safety_level": "elevated",
        "requires_attestation": True,
        "requires_ethics_review": True,
        "allowed_backends": [
            "mock",
            "colabfold",
            "local_colabfold",
            "alphafold2_local",
            "alphafold3_local",
            "alphafold_db",
            "boltz1",
            "esmfold",
            "openfold",
        ],
        "prohibited_actions": [
            "synthesize_amyloidogenic_sequences_without_bsl2_approval",
            "distribute_misfolded_protein_models",
        ],
        "disclaimers": [
            "Protein misfolding research may involve prion-like sequences; BSL-2 handling recommended.",
            "Ethics review required for human neurodegenerative disease research involving patient data.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_mode_config(mode: str) -> dict:
    """Return the safety configuration for a research mode.

    Args:
        mode: ResearchMode name string

    Returns:
        Safety config dict.

    Raises:
        KeyError: if mode is unknown.
    """
    try:
        key = ResearchMode(mode)
    except ValueError:
        raise KeyError(
            f"Unknown research mode: {mode!r}. Available: {[m.value for m in ResearchMode]}"
        )
    return dict(MODE_SAFETY_CONFIG[key])


def check_mode_safety(mode: str, action: str) -> dict:
    """Check whether an action is permitted in the given research mode.

    Args:
        mode: ResearchMode name string
        action: action identifier string (e.g. "human_germline_editing")

    Returns:
        dict with keys:
            allowed: bool
            reason: str
            disclaimers: list[str]
            safety_level: str
            requires_attestation: bool
            requires_ethics_review: bool
    """
    config = get_mode_config(mode)  # raises KeyError if unknown
    prohibited = config.get("prohibited_actions", [])

    if action in prohibited:
        return {
            "allowed": False,
            "reason": f"Action '{action}' is prohibited in {mode} mode.",
            "disclaimers": config.get("disclaimers", []),
            "safety_level": config["safety_level"],
            "requires_attestation": config["requires_attestation"],
            "requires_ethics_review": config["requires_ethics_review"],
        }

    return {
        "allowed": True,
        "reason": f"Action '{action}' is permitted in {mode} mode.",
        "disclaimers": config.get("disclaimers", []),
        "safety_level": config["safety_level"],
        "requires_attestation": config["requires_attestation"],
        "requires_ethics_review": config["requires_ethics_review"],
    }
