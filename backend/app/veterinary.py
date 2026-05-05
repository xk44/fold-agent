"""Veterinary / Multi-Species Support — Phase 24 Tier 3

Species-specific MHC alleles, cross-species ortholog comparison,
and veterinary compassionate use documentation.
RESEARCH USE ONLY — not for clinical veterinary use without DVM oversight.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Feature 1: Species-specific MHC allele database
# ---------------------------------------------------------------------------


class Species(str, Enum):
    human = "human"
    canine = "canine"
    feline = "feline"
    equine = "equine"
    murine = "murine"
    porcine = "porcine"


@dataclass
class MHCAllele:
    species: Species
    allele_name: str
    locus: str  # "MHC-I" | "MHC-II"
    source_db: str
    binding_data_available: bool
    cross_species_equivalent: Optional[str] = None


# fmt: off
MHC_ALLELE_DATABASE: list[MHCAllele] = [
    # ── Human (15) ────────────────────────────────────────────────────────
    MHCAllele(Species.human, "HLA-A*02:01",    "MHC-I",  "IMGT/HLA", True,  "DLA-88*001:01"),
    MHCAllele(Species.human, "HLA-A*24:02",    "MHC-I",  "IMGT/HLA", True,  "DLA-88*002:01"),
    MHCAllele(Species.human, "HLA-A*01:01",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-A*03:01",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-B*07:02",    "MHC-I",  "IMGT/HLA", True,  "DLA-88*003:01"),
    MHCAllele(Species.human, "HLA-B*08:01",    "MHC-I",  "IMGT/HLA", True,  "DLA-88*004:01"),
    MHCAllele(Species.human, "HLA-B*15:01",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-B*44:02",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-C*07:01",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-C*07:02",    "MHC-I",  "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-DRB1*01:01", "MHC-II", "IMGT/HLA", True,  "DLA-DRB1*001:01"),
    MHCAllele(Species.human, "HLA-DRB1*03:01", "MHC-II", "IMGT/HLA", True,  "DLA-DRB1*002:01"),
    MHCAllele(Species.human, "HLA-DRB1*04:01", "MHC-II", "IMGT/HLA", True,  None),
    MHCAllele(Species.human, "HLA-DQB1*02:01", "MHC-II", "IMGT/HLA", True,  "DLA-DQB1*001:01"),
    MHCAllele(Species.human, "HLA-DQB1*03:01", "MHC-II", "IMGT/HLA", True,  None),

    # ── Canine (12) ───────────────────────────────────────────────────────
    MHCAllele(Species.canine, "DLA-88*001:01",  "MHC-I",  "IPD-MHC", True,  "HLA-A*02:01"),
    MHCAllele(Species.canine, "DLA-88*002:01",  "MHC-I",  "IPD-MHC", True,  "HLA-A*24:02"),
    MHCAllele(Species.canine, "DLA-88*003:01",  "MHC-I",  "IPD-MHC", True,  "HLA-B*07:02"),
    MHCAllele(Species.canine, "DLA-88*004:01",  "MHC-I",  "IPD-MHC", True,  "HLA-B*08:01"),
    MHCAllele(Species.canine, "DLA-88*005:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.canine, "DLA-88*006:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.canine, "DLA-12*001:01",  "MHC-I",  "IPD-MHC", True,  None),
    MHCAllele(Species.canine, "DLA-12*002:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.canine, "DLA-DRB1*001:01","MHC-II", "IPD-MHC", True,  "HLA-DRB1*01:01"),
    MHCAllele(Species.canine, "DLA-DRB1*002:01","MHC-II", "IPD-MHC", True,  "HLA-DRB1*03:01"),
    MHCAllele(Species.canine, "DLA-DQA1*001:01","MHC-II", "IPD-MHC", True,  None),
    MHCAllele(Species.canine, "DLA-DQB1*001:01","MHC-II", "IPD-MHC", True,  "HLA-DQB1*02:01"),

    # ── Feline (9) ────────────────────────────────────────────────────────
    MHCAllele(Species.feline, "FLA-A*001:01",   "MHC-I",  "IPD-MHC", True,  "HLA-A*02:01"),
    MHCAllele(Species.feline, "FLA-A*002:01",   "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.feline, "FLA-B*001:01",   "MHC-I",  "IPD-MHC", True,  None),
    MHCAllele(Species.feline, "FLA-B*002:01",   "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.feline, "FLA-C*001:01",   "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.feline, "FLA-E*001:01",   "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.feline, "FLA-DRB*001:01", "MHC-II", "IPD-MHC", True,  "HLA-DRB1*01:01"),
    MHCAllele(Species.feline, "FLA-DRB*002:01", "MHC-II", "IPD-MHC", False, None),
    MHCAllele(Species.feline, "FLA-DQB*001:01", "MHC-II", "IPD-MHC", False, None),

    # ── Equine (6) ────────────────────────────────────────────────────────
    MHCAllele(Species.equine, "ELA-A1*001:01",  "MHC-I",  "IPD-MHC", True,  "HLA-A*02:01"),
    MHCAllele(Species.equine, "ELA-A2*001:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.equine, "ELA-A3*001:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.equine, "ELA-DRA*001:01", "MHC-II", "IPD-MHC", True,  None),
    MHCAllele(Species.equine, "ELA-DRB*001:01", "MHC-II", "IPD-MHC", True,  "HLA-DRB1*01:01"),
    MHCAllele(Species.equine, "ELA-DRB*002:01", "MHC-II", "IPD-MHC", False, None),

    # ── Murine (9) ────────────────────────────────────────────────────────
    MHCAllele(Species.murine, "H-2Kb",  "MHC-I",  "IEDB",    True,  "HLA-B*07:02"),
    MHCAllele(Species.murine, "H-2Db",  "MHC-I",  "IEDB",    True,  "HLA-A*02:01"),
    MHCAllele(Species.murine, "H-2Kd",  "MHC-I",  "IEDB",    True,  None),
    MHCAllele(Species.murine, "H-2Dd",  "MHC-I",  "IEDB",    True,  None),
    MHCAllele(Species.murine, "H-2Ld",  "MHC-I",  "IEDB",    False, None),
    MHCAllele(Species.murine, "H-2IAb", "MHC-II", "IEDB",    True,  "HLA-DRB1*01:01"),
    MHCAllele(Species.murine, "H-2IAd", "MHC-II", "IEDB",    True,  None),
    MHCAllele(Species.murine, "H-2IEd", "MHC-II", "IEDB",    False, None),
    MHCAllele(Species.murine, "H-2IEk", "MHC-II", "IEDB",    False, None),

    # ── Porcine (7) ───────────────────────────────────────────────────────
    MHCAllele(Species.porcine, "SLA-1*01:01",  "MHC-I",  "IPD-MHC", True,  "HLA-A*02:01"),
    MHCAllele(Species.porcine, "SLA-1*02:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.porcine, "SLA-2*01:01",  "MHC-I",  "IPD-MHC", True,  None),
    MHCAllele(Species.porcine, "SLA-3*01:01",  "MHC-I",  "IPD-MHC", False, None),
    MHCAllele(Species.porcine, "SLA-DRA*01:01","MHC-II", "IPD-MHC", False, None),
    MHCAllele(Species.porcine, "SLA-DRB1*01:01","MHC-II","IPD-MHC", True,  "HLA-DRB1*01:01"),
    MHCAllele(Species.porcine, "SLA-DQB1*01:01","MHC-II","IPD-MHC", False, None),
]
# fmt: on


def get_alleles_for_species(species: Species) -> list[MHCAllele]:
    """Return all MHC alleles registered for *species*."""
    return [a for a in MHC_ALLELE_DATABASE if a.species == species]


def find_cross_species_equivalent(allele_name: str) -> list[MHCAllele]:
    """Find orthologs across species for *allele_name*.

    Returns the source allele (if found) plus any alleles whose
    cross_species_equivalent matches the query, deduplicated.
    """
    results: list[MHCAllele] = []
    # Alleles that directly reference the query as their equivalent
    for allele in MHC_ALLELE_DATABASE:
        if allele.cross_species_equivalent == allele_name:
            results.append(allele)
    # The query allele itself (if it exists) points to another allele
    source = next((a for a in MHC_ALLELE_DATABASE if a.allele_name == allele_name), None)
    if source and source.cross_species_equivalent:
        target = next(
            (a for a in MHC_ALLELE_DATABASE if a.allele_name == source.cross_species_equivalent),
            None,
        )
        if target and target not in results:
            results.append(target)
    return results


@dataclass
class CalibrationWarning:
    source_allele: str
    target_species: Species
    warning_level: str  # "high" | "medium" | "low"
    message: str
    recommended_action: str


# Mapping (source_species → target_species) → warning level
_CROSS_SPECIES_WARNING_MATRIX: dict[tuple[str, str], str] = {
    ("human", "murine"):  "medium",
    ("murine", "human"):  "medium",
    ("human", "canine"):  "medium",
    ("canine", "human"):  "medium",
    ("human", "feline"):  "high",
    ("feline", "human"):  "high",
    ("human", "equine"):  "high",
    ("equine", "human"):  "high",
    ("human", "porcine"): "low",
    ("porcine", "human"): "low",
    ("canine", "feline"): "medium",
    ("feline", "canine"): "medium",
    ("canine", "murine"): "high",
    ("murine", "canine"): "high",
    ("canine", "equine"): "high",
    ("equine", "canine"): "high",
    ("canine", "porcine"):"high",
    ("porcine", "canine"):"high",
    ("feline", "murine"): "high",
    ("murine", "feline"): "high",
    ("feline", "equine"): "high",
    ("equine", "feline"): "high",
    ("murine", "porcine"):"high",
    ("porcine", "murine"):"high",
    ("equine", "porcine"):"high",
    ("porcine", "equine"):"high",
}

_RECOMMENDED_ACTIONS: dict[str, str] = {
    "low": (
        "Proceed with cross-species prediction; validate with species-specific "
        "experimental data when available."
    ),
    "medium": (
        "Use species-specific prediction tools where possible; cross-validate "
        "predictions with experimental binding assays."
    ),
    "high": (
        "Do not rely on cross-species MHC predictions without extensive experimental "
        "validation; consult species-specific binding databases."
    ),
}


def get_calibration_warning(allele_name: str, target_species: Species) -> CalibrationWarning:
    """Return a calibration warning for using *allele_name* predictions on *target_species*."""
    source = next((a for a in MHC_ALLELE_DATABASE if a.allele_name == allele_name), None)

    if source is None:
        return CalibrationWarning(
            source_allele=allele_name,
            target_species=target_species,
            warning_level="high",
            message=(
                f"Allele '{allele_name}' not found in database. "
                "Cross-species accuracy cannot be assessed."
            ),
            recommended_action=_RECOMMENDED_ACTIONS["high"],
        )

    if source.species == target_species:
        return CalibrationWarning(
            source_allele=allele_name,
            target_species=target_species,
            warning_level="low",
            message="Source allele and target species match; no cross-species calibration needed.",
            recommended_action="No additional action required.",
        )

    key = (source.species.value, target_species.value)
    level = _CROSS_SPECIES_WARNING_MATRIX.get(key, "high")

    messages: dict[str, str] = {
        "low": (
            f"Allele {allele_name} ({source.species.value}) shows reasonable conservation "
            f"with {target_species.value} MHC; predictions may have moderate accuracy."
        ),
        "medium": (
            f"Allele {allele_name} ({source.species.value}) has partial structural similarity "
            f"to {target_species.value} MHC; prediction accuracy is reduced."
        ),
        "high": (
            f"Allele {allele_name} ({source.species.value}) is poorly conserved relative to "
            f"{target_species.value} MHC; cross-species predictions are unreliable."
        ),
    }

    return CalibrationWarning(
        source_allele=allele_name,
        target_species=target_species,
        warning_level=level,
        message=messages[level],
        recommended_action=_RECOMMENDED_ACTIONS[level],
    )


# ---------------------------------------------------------------------------
# Feature 2: Cross-species ortholog structural comparison
# ---------------------------------------------------------------------------

# fmt: off
ORTHOLOG_DATABASE: dict[str, dict] = {
    "TP53": {
        "human": "TP53", "canine": "TP53", "feline": "TP53", "murine": "Trp53",
        "identity_pct": {"canine": 79.2, "feline": 82.1, "murine": 77.8, "equine": 78.5, "porcine": 80.1},
    },
    "KRAS": {
        "human": "KRAS", "canine": "KRAS", "feline": "KRAS", "murine": "Kras",
        "identity_pct": {"canine": 98.6, "feline": 98.4, "murine": 99.1, "equine": 97.9, "porcine": 98.0},
    },
    "BRAF": {
        "human": "BRAF", "canine": "BRAF", "feline": "BRAF", "murine": "Braf",
        "identity_pct": {"canine": 97.1, "feline": 96.5, "murine": 95.9, "equine": 96.0, "porcine": 96.3},
    },
    "EGFR": {
        "human": "EGFR", "canine": "EGFR", "feline": "EGFR", "murine": "Egfr",
        "identity_pct": {"canine": 87.3, "feline": 86.8, "murine": 83.2, "equine": 85.0, "porcine": 86.5},
    },
    "BRCA1": {
        "human": "BRCA1", "canine": "BRCA1", "feline": "BRCA1", "murine": "Brca1",
        "identity_pct": {"canine": 68.2, "feline": 65.4, "murine": 59.3, "equine": 64.1, "porcine": 66.8},
    },
    "BRCA2": {
        "human": "BRCA2", "canine": "BRCA2", "feline": "BRCA2", "murine": "Brca2",
        "identity_pct": {"canine": 71.4, "feline": 69.7, "murine": 59.1, "equine": 68.9, "porcine": 70.2},
    },
    "PIK3CA": {
        "human": "PIK3CA", "canine": "PIK3CA", "feline": "PIK3CA", "murine": "Pik3ca",
        "identity_pct": {"canine": 97.3, "feline": 97.0, "murine": 96.6, "equine": 96.8, "porcine": 97.1},
    },
    "PTEN": {
        "human": "PTEN", "canine": "PTEN", "feline": "PTEN", "murine": "Pten",
        "identity_pct": {"canine": 97.6, "feline": 97.2, "murine": 97.5, "equine": 97.0, "porcine": 97.4},
    },
    "MYC": {
        "human": "MYC", "canine": "MYC", "feline": "MYC", "murine": "Myc",
        "identity_pct": {"canine": 91.5, "feline": 90.8, "murine": 88.6, "equine": 90.2, "porcine": 91.0},
    },
    "RB1": {
        "human": "RB1", "canine": "RB1", "feline": "RB1", "murine": "Rb1",
        "identity_pct": {"canine": 89.4, "feline": 88.7, "murine": 87.2, "equine": 88.9, "porcine": 89.1},
    },
    "APC": {
        "human": "APC", "canine": "APC", "feline": "APC", "murine": "Apc",
        "identity_pct": {"canine": 77.8, "feline": 76.3, "murine": 73.1, "equine": 75.5, "porcine": 76.9},
    },
    "CDK4": {
        "human": "CDK4", "canine": "CDK4", "feline": "CDK4", "murine": "Cdk4",
        "identity_pct": {"canine": 99.0, "feline": 98.8, "murine": 98.5, "equine": 98.7, "porcine": 98.9},
    },
    "MDM2": {
        "human": "MDM2", "canine": "MDM2", "feline": "MDM2", "murine": "Mdm2",
        "identity_pct": {"canine": 76.5, "feline": 75.1, "murine": 72.3, "equine": 74.8, "porcine": 75.9},
    },
    "VHL": {
        "human": "VHL", "canine": "VHL", "feline": "VHL", "murine": "Vhl",
        "identity_pct": {"canine": 84.3, "feline": 83.6, "murine": 81.9, "equine": 83.0, "porcine": 83.8},
    },
    "NRAS": {
        "human": "NRAS", "canine": "NRAS", "feline": "NRAS", "murine": "Nras",
        "identity_pct": {"canine": 99.1, "feline": 99.0, "murine": 99.1, "equine": 98.9, "porcine": 99.0},
    },
    "HRAS": {
        "human": "HRAS", "canine": "HRAS", "feline": "HRAS", "murine": "Hras",
        "identity_pct": {"canine": 99.1, "feline": 98.8, "murine": 99.1, "equine": 98.6, "porcine": 98.9},
    },
    "FGFR1": {
        "human": "FGFR1", "canine": "FGFR1", "feline": "FGFR1", "murine": "Fgfr1",
        "identity_pct": {"canine": 96.2, "feline": 95.8, "murine": 94.7, "equine": 95.5, "porcine": 95.9},
    },
    "ALK": {
        "human": "ALK", "canine": "ALK", "feline": "ALK", "murine": "Alk",
        "identity_pct": {"canine": 93.8, "feline": 93.2, "murine": 91.4, "equine": 92.6, "porcine": 93.0},
    },
    "JAK2": {
        "human": "JAK2", "canine": "JAK2", "feline": "JAK2", "murine": "Jak2",
        "identity_pct": {"canine": 96.9, "feline": 96.4, "murine": 95.8, "equine": 96.1, "porcine": 96.6},
    },
    "MTOR": {
        "human": "MTOR", "canine": "MTOR", "feline": "MTOR", "murine": "Mtor",
        "identity_pct": {"canine": 98.3, "feline": 98.1, "murine": 97.9, "equine": 98.0, "porcine": 98.2},
    },
}
# fmt: on

_SPECIES_ALIASES: dict[str, str] = {
    "human": "human",
    "canine": "canine",
    "dog": "canine",
    "feline": "feline",
    "cat": "feline",
    "murine": "murine",
    "mouse": "murine",
    "equine": "equine",
    "horse": "equine",
    "porcine": "porcine",
    "pig": "porcine",
}


def _resolve_species(species: str) -> str:
    return _SPECIES_ALIASES.get(species.lower(), species.lower())


def _structural_conservation(identity_pct: float) -> float:
    """Heuristic: map sequence identity → structural conservation score [0,1]."""
    # Structural conservation tends to be higher than sequence identity
    clamped = max(0.0, min(100.0, identity_pct))
    return round(min(1.0, (clamped / 100.0) * 1.15), 4)


def _model_quality_score(identity_pct: float) -> float:
    """Score reflecting suitability as animal model [0,1]."""
    clamped = max(0.0, min(100.0, identity_pct))
    return round(clamped / 100.0, 4)


def _recommendation(identity_pct: float, gene: str, species: str) -> str:
    if identity_pct >= 97:
        return (
            f"{species.capitalize()} is an excellent model for {gene} "
            "(>97% sequence identity; high structural conservation expected)."
        )
    elif identity_pct >= 85:
        return (
            f"{species.capitalize()} is a good model for {gene} "
            f"({identity_pct:.1f}% identity); minor structural divergence possible."
        )
    elif identity_pct >= 70:
        return (
            f"{species.capitalize()} is an acceptable model for {gene} "
            f"({identity_pct:.1f}% identity); validate key functional residues."
        )
    else:
        return (
            f"{species.capitalize()} is a poor model for {gene} "
            f"({identity_pct:.1f}% identity); significant structural differences expected."
        )


@dataclass
class OrthologComparison:
    gene: str
    species_pair: tuple[str, str]
    ortholog_gene: str
    sequence_identity_pct: float
    structural_conservation: float
    variant_conserved: Optional[bool]
    model_quality_score: float
    recommendation: str


def compare_orthologs(gene: str, target_species: str) -> OrthologComparison:
    """Compare human *gene* orthologs with *target_species*."""
    resolved = _resolve_species(target_species)
    entry = ORTHOLOG_DATABASE.get(gene.upper()) or ORTHOLOG_DATABASE.get(gene)

    if entry is None:
        # Unknown gene — return minimal stub with low scores
        return OrthologComparison(
            gene=gene,
            species_pair=("human", resolved),
            ortholog_gene="unknown",
            sequence_identity_pct=0.0,
            structural_conservation=0.0,
            variant_conserved=None,
            model_quality_score=0.0,
            recommendation=(
                f"Gene '{gene}' not found in ortholog database. "
                "Manual literature review required."
            ),
        )

    identity = entry.get("identity_pct", {}).get(resolved, 0.0)
    ortholog_name = entry.get(resolved, "unknown")

    return OrthologComparison(
        gene=gene,
        species_pair=("human", resolved),
        ortholog_gene=ortholog_name,
        sequence_identity_pct=identity,
        structural_conservation=_structural_conservation(identity),
        variant_conserved=None,
        model_quality_score=_model_quality_score(identity),
        recommendation=_recommendation(identity, gene, resolved),
    )


def rank_animal_models(gene: str, variant: Optional[str] = None) -> list[OrthologComparison]:
    """Rank all available species by structural conservation for *gene*."""
    non_human = [s.value for s in Species if s.value != "human"]
    comparisons = [compare_orthologs(gene, sp) for sp in non_human]
    comparisons.sort(key=lambda c: c.structural_conservation, reverse=True)
    return comparisons


def check_variant_conservation(gene: str, variant_position: int, target_species: str) -> dict:
    """Assess whether *variant_position* in *gene* is conserved in *target_species*.

    Returns a dict with keys: gene, position, target_species, conserved (bool),
    confidence (float), notes (str).
    Uses a deterministic hash-based stub (no external deps).
    """
    resolved = _resolve_species(target_species)
    entry = ORTHOLOG_DATABASE.get(gene.upper()) or ORTHOLOG_DATABASE.get(gene)

    if entry is None:
        return {
            "gene": gene,
            "position": variant_position,
            "target_species": resolved,
            "conserved": None,
            "confidence": 0.0,
            "notes": f"Gene '{gene}' not found in ortholog database.",
        }

    identity = entry.get("identity_pct", {}).get(resolved, 0.0)
    # Deterministic pseudo-random conservation check based on gene+pos+species
    seed = hashlib.md5(f"{gene}:{variant_position}:{resolved}".encode()).hexdigest()
    seed_int = int(seed[:8], 16)
    # Weight conservation probability by sequence identity
    conserved_prob = identity / 100.0
    conserved = (seed_int % 100) < int(conserved_prob * 100)
    confidence = round(conserved_prob * (0.7 + 0.3 * ((seed_int >> 8) % 100) / 100), 4)

    return {
        "gene": gene,
        "position": variant_position,
        "target_species": resolved,
        "conserved": conserved,
        "confidence": confidence,
        "notes": (
            f"Based on {identity:.1f}% sequence identity between human and {resolved} "
            f"{entry.get(resolved, gene)}. Experimental validation recommended."
        ),
    }


# ---------------------------------------------------------------------------
# Feature 3: Veterinary compassionate use documentation
# ---------------------------------------------------------------------------

AVMA_GUIDELINES: dict[str, str] = {
    "compassionate_use": (
        "AVMA Guidelines for Compassionate Use of Investigational New Animal Drugs (INADs) — "
        "Extralabel Drug Use in Animals (ELDU) under 21 CFR Part 530."
    ),
    "informed_consent": (
        "AVMA Client Consent Guidelines: Informed consent must be obtained from the animal owner "
        "prior to initiating investigational treatment."
    ),
    "adverse_events": (
        "AVMA/USDA Adverse Event Reporting: All adverse events must be reported to the attending "
        "DVM and, where applicable, to USDA APHIS Center for Veterinary Biologics (CVB)."
    ),
    "experimental_biologics": (
        "AVMA Policy on Experimental Biologics: Use of unlicensed biologics requires USDA APHIS "
        "Veterinary Biologics permit under 9 CFR Part 102."
    ),
    "species_specific": (
        "AVMA Species-Specific Guidelines: Treatment protocols must account for "
        "species-specific pharmacokinetics, immunology, and welfare considerations."
    ),
    "record_keeping": (
        "AVMA Record-Keeping Requirements: Complete medical records including treatment rationale, "
        "dosing, response, and adverse events must be maintained for a minimum of 5 years."
    ),
}

USDA_REQUIREMENTS_BY_SPECIES: dict[str, list[str]] = {
    "canine": [
        "USDA APHIS notification required for investigational biologic use under 9 CFR 102.5.",
        "State veterinary board notification may be required depending on jurisdiction.",
        "Owner informed consent documentation must be retained by attending DVM.",
        "Adverse event reporting to USDA CVB within 15 days of observation.",
    ],
    "feline": [
        "USDA APHIS notification required for investigational biologic use under 9 CFR 102.5.",
        "Owner informed consent documentation must be retained by attending DVM.",
        "Adverse event reporting to USDA CVB within 15 days of observation.",
    ],
    "equine": [
        "USDA APHIS notification required for investigational biologic use under 9 CFR 102.5.",
        "Equine Infectious Anemia (EIA) status must be current (Coggins test).",
        "USDA APHIS VS Form 10-11 may be required for interstate transport.",
        "Adverse event reporting to USDA CVB within 15 days of observation.",
        "State animal health official notification recommended.",
    ],
    "bovine": [
        "USDA APHIS notification required under 9 CFR 102.5.",
        "USDA APHIS VS Form 1-27 for movement of animals under investigation.",
        "Adverse event reporting to USDA CVB within 15 days of observation.",
        "Slaughter withdrawal periods must be documented and enforced.",
    ],
    "porcine": [
        "USDA APHIS notification required under 9 CFR 102.5.",
        "Swine Health Protection Act compliance if interstate movement involved.",
        "Adverse event reporting to USDA CVB within 15 days of observation.",
        "Slaughter withdrawal periods must be documented and enforced.",
    ],
    "murine": [
        "IACUC approval required for investigational use in research mice.",
        "Institutional Animal Care and Use Committee oversight required.",
        "USDA APHIS oversight not required for laboratory rodents.",
        "Adverse event reporting to IACUC per institutional protocol.",
    ],
    "default": [
        "USDA APHIS notification may be required depending on species classification.",
        "Owner/responsible party informed consent documentation required.",
        "Adverse event reporting per applicable federal and state regulations.",
        "Consult attending DVM and institutional biosafety committee.",
    ],
}


@dataclass
class VetAttestationRequirements:
    dvm_license_required: bool
    institutional_approval: bool
    owner_consent_required: bool
    adverse_event_reporting: bool
    usda_notification: bool
    state_specific_requirements: list[str]


@dataclass
class CompassionateUseDocument:
    document_type: str
    species: str
    condition: str
    proposed_treatment_summary: str
    attending_vet_attestation: str
    owner_consent_text: str
    regulatory_notices: list[str]
    avma_guidelines_ref: str
    usda_requirements: list[str]
    document_text: str
    generated_at: str  # ISO 8601


_INSTITUTIONAL_APPROVAL_SPECIES = {"murine", "porcine", "bovine"}
_USDA_NOTIFICATION_SPECIES = {"canine", "feline", "equine", "bovine", "porcine"}

_STATE_REQUIREMENTS: dict[str, list[str]] = {
    "equine": [
        "California: notify CA Department of Food and Agriculture (CDFA) for equine biologics.",
        "Florida: notify FL Department of Agriculture and Consumer Services.",
        "Texas: TAHC notification required for equine biologics use.",
    ],
    "bovine": [
        "Notify state veterinarian for bovine investigational biologic use.",
        "Contact state brand inspection office if applicable.",
    ],
    "canine": [
        "Check state veterinary practice act for extralabel drug use provisions.",
    ],
    "feline": [
        "Check state veterinary practice act for extralabel drug use provisions.",
    ],
}


def get_attestation_requirements(species: str) -> VetAttestationRequirements:
    """Return attestation requirements for *species*."""
    sp = species.lower()
    return VetAttestationRequirements(
        dvm_license_required=True,
        institutional_approval=sp in _INSTITUTIONAL_APPROVAL_SPECIES,
        owner_consent_required=sp != "murine",
        adverse_event_reporting=True,
        usda_notification=sp in _USDA_NOTIFICATION_SPECIES,
        state_specific_requirements=_STATE_REQUIREMENTS.get(sp, []),
    )


def generate_owner_consent_form(species: str, condition: str, treatment_summary: str) -> str:
    """Generate plain-text owner consent form."""
    sp_display = species.capitalize()
    return f"""OWNER/GUARDIAN INFORMED CONSENT FOR INVESTIGATIONAL TREATMENT

Animal Species: {sp_display}
Diagnosis/Condition: {condition}

I, the owner/guardian of the above-described animal, hereby:

1. ACKNOWLEDGE that the proposed investigational treatment described below is experimental
   and has not received full regulatory approval for use in {sp_display.lower()}s.

2. UNDERSTAND that the proposed treatment is:
   {treatment_summary}

3. AUTHORIZE the attending veterinarian to administer the proposed investigational treatment.

4. ACCEPT that risks, benefits, and alternatives have been explained to my satisfaction.

5. UNDERSTAND that I may withdraw consent at any time without prejudice to my animal's care.

6. AGREE to notify the attending veterinarian of any adverse events or unexpected changes
   in my animal's condition.

7. CONFIRM that I have been informed of applicable regulatory requirements under AVMA and
   USDA guidelines, including adverse event reporting obligations.

This consent is provided voluntarily and without coercion.

Owner/Guardian Signature: ____________________________  Date: ____________

Attending Veterinarian: ____________________________  License No.: ____________

Witness: ____________________________  Date: ____________

AVMA Reference: {AVMA_GUIDELINES['informed_consent']}

--- RESEARCH USE ONLY — NOT FOR CLINICAL USE WITHOUT LICENSED DVM OVERSIGHT ---
"""


def generate_compassionate_use_doc(
    species: str,
    condition: str,
    treatment_summary: str,
    vet_name: str,
    vet_license: str,
    owner_name: str,
    animal_id: str,
) -> CompassionateUseDocument:
    """Generate a veterinary compassionate use document (USDA/AVMA-aligned)."""
    sp = species.lower()
    sp_display = species.capitalize()
    now = datetime.now(tz=timezone.utc).isoformat()

    attestation = (
        f"I, {vet_name} (License No.: {vet_license}), a licensed veterinarian, hereby attest that:\n"
        f"1. I have examined the animal identified as '{animal_id}' ({sp_display}).\n"
        f"2. The animal has been diagnosed with: {condition}.\n"
        f"3. Conventional treatment options have been considered and/or exhausted.\n"
        f"4. The proposed investigational treatment represents the best available option "
        f"for this animal's welfare under the circumstances.\n"
        f"5. I will monitor the animal throughout treatment and report adverse events "
        f"as required by applicable regulations.\n"
        f"6. This treatment will be administered in accordance with AVMA compassionate "
        f"use guidelines and applicable USDA requirements."
    )

    owner_consent = generate_owner_consent_form(species, condition, treatment_summary)

    usda_reqs = USDA_REQUIREMENTS_BY_SPECIES.get(sp, USDA_REQUIREMENTS_BY_SPECIES["default"])
    reqs = get_attestation_requirements(species)

    regulatory_notices = [
        "RESEARCH USE ONLY — not for clinical veterinary use without DVM oversight.",
        f"AVMA Guidelines: {AVMA_GUIDELINES['compassionate_use']}",
        f"Adverse Event Reporting: {AVMA_GUIDELINES['adverse_events']}",
    ]
    if reqs.usda_notification:
        regulatory_notices.append(
            f"USDA APHIS Notification Required: 9 CFR Part 102 applies to this species ({sp_display})."
        )
    if reqs.institutional_approval:
        regulatory_notices.append(
            "Institutional IACUC/biosafety committee approval required prior to treatment."
        )

    doc_text = f"""================================================================================
VETERINARY COMPASSIONATE USE DOCUMENT
USDA/AVMA-Aligned — RESEARCH USE ONLY
================================================================================

Document Type: Veterinary Compassionate Use Authorization
Generated At: {now}

ANIMAL INFORMATION
  Species:   {sp_display}
  Animal ID: {animal_id}
  Condition: {condition}

PROPOSED TREATMENT
  {treatment_summary}

ATTENDING VETERINARIAN ATTESTATION
  {attestation}

OWNER CONSENT
  Owner Name: {owner_name}
  (See attached Owner Consent Form)

REGULATORY NOTICES
  {''.join(f"  • {n}" + chr(10) for n in regulatory_notices)}
USDA REQUIREMENTS
  {''.join(f"  • {r}" + chr(10) for r in usda_reqs)}
AVMA GUIDELINES REFERENCE
  {AVMA_GUIDELINES['compassionate_use']}
  {AVMA_GUIDELINES['record_keeping']}

================================================================================
DISCLAIMER: This document is generated for research and administrative purposes
only. It does not constitute regulatory approval. All clinical decisions must be
made by a licensed veterinarian in accordance with applicable law.
================================================================================
"""

    return CompassionateUseDocument(
        document_type="Veterinary Compassionate Use Authorization",
        species=sp_display,
        condition=condition,
        proposed_treatment_summary=treatment_summary,
        attending_vet_attestation=attestation,
        owner_consent_text=owner_consent,
        regulatory_notices=regulatory_notices,
        avma_guidelines_ref=AVMA_GUIDELINES["compassionate_use"],
        usda_requirements=usda_reqs,
        document_text=doc_text,
        generated_at=now,
    )
