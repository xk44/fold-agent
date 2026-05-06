"""Clinical Variant Integration — Phase 24 Tier 1

ACMG criterion auto-scoring, VUS reclassification queue, and ClinVar evidence mapping.

RESEARCH USE ONLY. Not for clinical diagnostic use without expert validation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# ACMG Criterion Auto-Scoring (Feature 1)
# ---------------------------------------------------------------------------


class ACMGCriterion(str, Enum):
    PP3 = "PP3"  # Computational evidence supports pathogenicity
    BP4 = "BP4"  # Computational evidence suggests benign
    PS3 = "PS3"  # Functional studies damaging
    BS3 = "BS3"  # Functional studies no damaging effect
    PM1 = "PM1"  # Located in mutational hot spot / critical domain
    PM5 = "PM5"  # Novel missense at position with known pathogenic missense
    PP2 = "PP2"  # Missense in gene with low benign variation
    BP1 = "BP1"  # Missense in gene where only truncating variants cause disease


# ACMG combining rules: (pathogenic_count, benign_count) -> classification
# Simplified rules from Richards et al. 2015 (PMID 25741868)
ACMG_COMBINING_RULES: dict[str, dict] = {
    "pathogenic": {
        "description": "≥2 strong OR 1 very_strong+1 moderate OR ...",
        "min_path_score": 6.0,
        "max_benign_score": 0.0,
    },
    "likely_pathogenic": {
        "description": "1 strong+1-2 moderate OR 1 strong+2 supporting OR ...",
        "min_path_score": 3.5,
        "max_benign_score": 0.5,
    },
    "VUS": {
        "description": "Does not meet criteria for other classes",
        "min_path_score": 0.0,
        "max_benign_score": 2.0,
    },
    "likely_benign": {
        "description": "1 strong benign OR ≥2 moderate benign",
        "min_path_score": 0.0,
        "max_benign_score": 3.5,
    },
    "benign": {
        "description": "1 standalone benign OR 2 strong benign",
        "min_path_score": 0.0,
        "max_benign_score": 6.0,
    },
}

_STRENGTH_WEIGHTS: dict[str, float] = {
    "supporting": 1.0,
    "moderate": 2.0,
    "strong": 4.0,
    "very_strong": 8.0,
}

# Critical domains per gene (residue ranges) — mirrors variant_pathogenicity.py
_CRITICAL_DOMAINS: dict[str, list[tuple[int, int, str]]] = {
    "TP53": [
        (94, 102, "proline-rich"),
        (102, 292, "DNA-binding domain"),
        (293, 363, "tetramerization domain"),
    ],
    "KRAS": [(1, 86, "G-domain"), (87, 166, "switch-II region")],
    "EGFR": [(712, 979, "kinase domain")],
    "BRCA1": [(1, 100, "RING domain"), (1642, 1736, "BRCT domain")],
    "BRCA2": [(10, 40, "NLS"), (2402, 3190, "DNA-binding domain")],
    "PIK3CA": [(954, 1068, "kinase domain"), (430, 517, "helical domain")],
    "PTEN": [(1, 185, "phosphatase domain")],
    "IDH1": [(96, 279, "catalytic domain")],
    "BRAF": [(457, 717, "kinase domain")],
    "MET": [(1075, 1390, "kinase domain")],
}

# Genes where primarily truncating variants cause disease (BP1 relevant)
_TRUNCATING_DISEASE_GENES: set[str] = {"BRCA2", "APC", "MLH1", "MSH2", "VHL", "NF1", "NF2"}

# Genes with low benign missense variation (PP2 relevant)
_LOW_BENIGN_MISSENSE_GENES: set[str] = {"TP53", "BRCA1", "BRCA2", "MEN1", "CDH1"}


def _extract_position(variant: str) -> int | None:
    """Extract numeric residue position from variant notation like R175H."""
    import re

    m = re.search(r"\d+", variant)
    return int(m.group()) if m else None


def _in_critical_domain(gene: str, position: int | None) -> tuple[bool, str | None]:
    """Return (in_domain, domain_name) for a gene + residue position."""
    if position is None:
        return False, None
    for start, end, name in _CRITICAL_DOMAINS.get(gene.upper(), []):
        if start <= position <= end:
            return True, name
    return False, None


def _deterministic_score(gene: str, variant: str, salt: str) -> float:
    """Hash-based pseudo-score in [0, 1] for reproducibility when real score absent."""
    digest = hashlib.sha256(f"{gene}:{variant}:{salt}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


@dataclass
class ACMGEvidence:
    criterion: ACMGCriterion
    met: bool
    strength: str  # supporting / moderate / strong / very_strong
    evidence_source: str
    detail: str


@dataclass
class ACMGClassification:
    variant: str
    gene: str
    evidences: list[ACMGEvidence]
    pathogenicity_class: str  # pathogenic / likely_pathogenic / VUS / likely_benign / benign
    overall_score: float  # 0-1


def score_acmg_criteria(
    gene: str,
    variant: str,
    alphamissense_score: float | None = None,
    conservation_score: float | None = None,
    structural_context: dict | None = None,
) -> ACMGClassification:
    """Compute ACMG criterion scores for a variant.

    RESEARCH USE ONLY — not for clinical diagnostic use.

    Args:
        gene: HGNC gene symbol (e.g. "TP53").
        variant: Protein-level variant (e.g. "R175H").
        alphamissense_score: AlphaMissense pathogenicity score [0, 1].
        conservation_score: PhyloP/GERP-style conservation score [0, 1].
        structural_context: Dict with optional keys:
            - in_critical_domain (bool)
            - domain_name (str)
            - has_known_pathogenic_at_position (bool)
    Returns:
        ACMGClassification with all assessed criteria.
    """
    gene = gene.upper()
    evidences: list[ACMGEvidence] = []
    position = _extract_position(variant)

    # --- Resolve or impute scores ---
    am_score = alphamissense_score
    if am_score is None:
        # Try known table first
        try:
            from backend.app.modes.variant_pathogenicity import ALPHAMISSENSE_SCORES

            am_score = ALPHAMISSENSE_SCORES.get((gene, variant))
        except ImportError:
            pass
    if am_score is None:
        am_score = _deterministic_score(gene, variant, "alphamissense")

    cons_score = conservation_score
    if cons_score is None:
        cons_score = _deterministic_score(gene, variant, "conservation")

    # Resolve structural context
    sc = structural_context or {}
    in_domain, domain_name = _in_critical_domain(gene, position)
    is_critical = sc.get("in_critical_domain", in_domain)
    dom_name = sc.get("domain_name", domain_name)
    known_path_at_pos = sc.get("has_known_pathogenic_at_position", False)

    # If position is in known critical residue list, mark known_path_at_pos
    if not known_path_at_pos and position is not None:
        try:
            from backend.app.modes.variant_pathogenicity import KNOWN_CRITICAL_RESIDUES

            known_path_at_pos = position in KNOWN_CRITICAL_RESIDUES.get(gene, [])
        except ImportError:
            known_path_at_pos = _deterministic_score(gene, variant, "known_path") > 0.6

    # --- PP3: Computational evidence — pathogenic ---
    pp3_met = am_score > 0.7 or cons_score > 0.8
    pp3_detail = (
        f"AlphaMissense={am_score:.3f} (>0.7)"
        if am_score > 0.7
        else f"Conservation={cons_score:.3f} (>0.8)"
    )
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.PP3,
            met=pp3_met,
            strength="supporting",
            evidence_source="AlphaMissense+Conservation",
            detail=pp3_detail
            if pp3_met
            else f"AlphaMissense={am_score:.3f}, Conservation={cons_score:.3f} — thresholds not met",
        )
    )

    # --- BP4: Computational evidence — benign ---
    bp4_met = am_score < 0.3 and cons_score < 0.4
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.BP4,
            met=bp4_met,
            strength="supporting",
            evidence_source="AlphaMissense+Conservation",
            detail=(
                f"AlphaMissense={am_score:.3f} (<0.3) and Conservation={cons_score:.3f} (<0.4)"
                if bp4_met
                else f"AlphaMissense={am_score:.3f}, Conservation={cons_score:.3f} — benign thresholds not met"
            ),
        )
    )

    # --- PS3: Functional studies — damaging (strong) ---
    ps3_met = am_score > 0.85 and is_critical
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.PS3,
            met=ps3_met,
            strength="strong",
            evidence_source="Structural+AlphaMissense",
            detail=(
                f"High AlphaMissense ({am_score:.3f}) in critical domain ({dom_name})"
                if ps3_met
                else "Insufficient computational functional evidence"
            ),
        )
    )

    # --- BS3: Functional studies — no damaging effect ---
    bs3_met = am_score < 0.2 and cons_score < 0.3
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.BS3,
            met=bs3_met,
            strength="strong",
            evidence_source="AlphaMissense+Conservation",
            detail=(
                f"AlphaMissense={am_score:.3f}, Conservation={cons_score:.3f} — computationally tolerated"
                if bs3_met
                else "Evidence does not support benign functional impact"
            ),
        )
    )

    # --- PM1: Located in hot spot / critical domain ---
    pm1_met = bool(is_critical)
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.PM1,
            met=pm1_met,
            strength="moderate",
            evidence_source="Structural annotation",
            detail=(
                f"Residue {position} is within {dom_name}"
                if pm1_met
                else f"Residue {position} not in annotated critical domain"
            ),
        )
    )

    # --- PM5: Novel missense at position with known pathogenic missense ---
    pm5_met = known_path_at_pos and not _is_known_variant(gene, variant)
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.PM5,
            met=pm5_met,
            strength="moderate",
            evidence_source="ClinVar/structural cross-reference",
            detail=(
                f"Different pathogenic missense known at residue {position}"
                if pm5_met
                else f"No known pathogenic missense at residue {position} or variant is itself known"
            ),
        )
    )

    # --- PP2: Missense in gene with low benign variation ---
    pp2_met = gene in _LOW_BENIGN_MISSENSE_GENES
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.PP2,
            met=pp2_met,
            strength="supporting",
            evidence_source="Gene-level constraint",
            detail=(
                f"{gene} has low missense benign variation (constrained gene)"
                if pp2_met
                else f"{gene} not in low-benign-missense gene list"
            ),
        )
    )

    # --- BP1: Missense in gene where truncating variants cause disease ---
    bp1_met = gene in _TRUNCATING_DISEASE_GENES
    evidences.append(
        ACMGEvidence(
            criterion=ACMGCriterion.BP1,
            met=bp1_met,
            strength="supporting",
            evidence_source="Gene-level disease mechanism",
            detail=(
                f"{gene} primarily causes disease via truncating variants"
                if bp1_met
                else f"{gene} not in truncating-disease-mechanism gene list"
            ),
        )
    )

    # --- Combine criteria into classification ---
    path_score = sum(
        _STRENGTH_WEIGHTS[e.strength]
        for e in evidences
        if e.met
        and e.criterion
        in (
            ACMGCriterion.PP3,
            ACMGCriterion.PS3,
            ACMGCriterion.PM1,
            ACMGCriterion.PM5,
            ACMGCriterion.PP2,
        )
    )
    benign_score = sum(
        _STRENGTH_WEIGHTS[e.strength]
        for e in evidences
        if e.met and e.criterion in (ACMGCriterion.BP4, ACMGCriterion.BS3, ACMGCriterion.BP1)
    )

    if path_score >= 6.0 and benign_score == 0.0:
        path_class = "pathogenic"
    elif path_score >= 3.5 and benign_score <= 0.5:
        path_class = "likely_pathogenic"
    elif benign_score >= 6.0 and path_score == 0.0:
        path_class = "benign"
    elif benign_score >= 3.5 and path_score <= 0.5:
        path_class = "likely_benign"
    else:
        path_class = "VUS"

    # Overall score: normalized pathogenic dominance
    total = path_score + benign_score
    overall = path_score / total if total > 0 else 0.5

    return ACMGClassification(
        variant=variant,
        gene=gene,
        evidences=evidences,
        pathogenicity_class=path_class,
        overall_score=round(overall, 4),
    )


def _is_known_variant(gene: str, variant: str) -> bool:
    """Return True if variant is in the AlphaMissense stub table."""
    try:
        from backend.app.modes.variant_pathogenicity import ALPHAMISSENSE_SCORES

        return (gene.upper(), variant) in ALPHAMISSENSE_SCORES
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# VUS Reclassification Queue (Feature 2)
# ---------------------------------------------------------------------------


@dataclass
class VUSEntry:
    variant_id: str
    gene: str
    variant: str
    current_class: str  # always "VUS" on creation
    last_scored: str  # ISO date
    alphamissense_score: float | None
    structural_score: float | None
    pending_reclassification: bool


@dataclass
class ReclassificationResult:
    variant_id: str
    old_class: str
    new_class: str
    evidence_delta: list[str]
    confidence: float
    auto_reclassified: bool


def _make_vus_entry(
    variant_id: str,
    gene: str,
    variant: str,
    last_scored: str,
    am_score: float | None = None,
    struct_score: float | None = None,
    pending: bool = True,
) -> VUSEntry:
    return VUSEntry(
        variant_id=variant_id,
        gene=gene,
        variant=variant,
        current_class="VUS",
        last_scored=last_scored,
        alphamissense_score=am_score,
        structural_score=struct_score,
        pending_reclassification=pending,
    )


MOCK_VUS_DATABASE: list[VUSEntry] = [
    _make_vus_entry("VUS-001", "TP53", "V143A", "2024-01-15", 0.512, 0.48),
    _make_vus_entry("VUS-002", "TP53", "L194R", "2024-02-20", 0.631, 0.55),
    _make_vus_entry("VUS-003", "BRCA1", "P1749R", "2024-03-10", 0.498, None),
    _make_vus_entry("VUS-004", "BRCA2", "S1982R", "2024-01-05", 0.441, 0.39),
    _make_vus_entry("VUS-005", "EGFR", "G719S", "2024-04-01", 0.723, 0.61),
    _make_vus_entry("VUS-006", "KRAS", "A59T", "2024-03-22", 0.389, 0.42),
    _make_vus_entry("VUS-007", "PIK3CA", "R88Q", "2023-12-01", 0.501, 0.50),
    _make_vus_entry("VUS-008", "PTEN", "G129E", "2024-02-14", 0.652, None, pending=True),
    _make_vus_entry("VUS-009", "IDH1", "V71I", "2024-01-30", 0.318, 0.29),
    _make_vus_entry("VUS-010", "BRAF", "G466V", "2024-04-15", 0.728, 0.68),
    _make_vus_entry("VUS-011", "MET", "T1010I", "2024-03-05", 0.544, 0.51),
    _make_vus_entry("VUS-012", "CDKN2A", "A57V", "2023-11-20", 0.485, 0.44),
    _make_vus_entry("VUS-013", "TP53", "C238Y", "2024-05-01", None, 0.72),
    _make_vus_entry("VUS-014", "BRCA1", "L1657P", "2024-04-20", 0.811, 0.79),
    _make_vus_entry("VUS-015", "EGFR", "S768I", "2024-05-10", 0.763, 0.71),
    _make_vus_entry("VUS-016", "KRAS", "T58I", "2024-02-28", 0.419, 0.37),
    _make_vus_entry("VUS-017", "PIK3CA", "N345K", "2023-10-15", 0.593, 0.55),
    _make_vus_entry("VUS-018", "PTEN", "Y155C", "2024-03-18", 0.677, None),
    _make_vus_entry("VUS-019", "BRCA2", "N991D", "2024-01-22", 0.339, 0.31),
    _make_vus_entry("VUS-020", "MET", "D1010H", "2024-06-01", 0.821, 0.80),
]


def get_vus_queue() -> list[VUSEntry]:
    """Return all VUS entries pending re-scoring."""
    return [v for v in MOCK_VUS_DATABASE if v.pending_reclassification]


def rescore_vus(variant_id: str) -> ReclassificationResult:
    """Run ACMG scoring on a single VUS and return reclassification result.

    RESEARCH USE ONLY.
    """
    entry = next((v for v in MOCK_VUS_DATABASE if v.variant_id == variant_id), None)
    if entry is None:
        raise KeyError(f"VUS entry not found: {variant_id}")

    classification = score_acmg_criteria(
        gene=entry.gene,
        variant=entry.variant,
        alphamissense_score=entry.alphamissense_score,
        structural_context={
            "structural_score": entry.structural_score,
        },
    )

    new_class = classification.pathogenicity_class
    old_class = entry.current_class
    auto_reclassified = new_class != old_class

    evidence_delta: list[str] = []
    for e in classification.evidences:
        if e.met:
            evidence_delta.append(f"{e.criterion.value} ({e.strength}): {e.detail}")

    confidence = (
        classification.overall_score
        if new_class in ("pathogenic", "likely_pathogenic")
        else (
            1.0 - classification.overall_score if new_class in ("benign", "likely_benign") else 0.5
        )
    )

    return ReclassificationResult(
        variant_id=variant_id,
        old_class=old_class,
        new_class=new_class,
        evidence_delta=evidence_delta,
        confidence=round(confidence, 4),
        auto_reclassified=auto_reclassified,
    )


def rescore_all_vus() -> list[ReclassificationResult]:
    """Batch rescore all VUS entries in the queue.

    RESEARCH USE ONLY.
    """
    results: list[ReclassificationResult] = []
    for entry in MOCK_VUS_DATABASE:
        try:
            result = rescore_vus(entry.variant_id)
            results.append(result)
        except KeyError:
            pass
    return results


# ---------------------------------------------------------------------------
# ClinVar Evidence Mapping (Feature 3)
# ---------------------------------------------------------------------------


@dataclass
class ClinVarEvidence:
    clinvar_id: str
    variant: str
    gene: str
    significance: str
    review_stars: int  # 0-4
    conditions: list[str]
    last_updated: str
    structural_residue: int | None
    structural_domain: str | None


@dataclass
class StructuralClinVarMapping:
    gene: str
    total_variants: int
    mapped_variants: list[ClinVarEvidence]
    unmapped_count: int
    pathogenic_hotspots: list[dict]
    domain_summary: dict


def _clinvar(
    clinvar_id: str,
    variant: str,
    gene: str,
    significance: str,
    review_stars: int,
    conditions: list[str],
    last_updated: str,
    residue: int | None = None,
    domain: str | None = None,
) -> ClinVarEvidence:
    return ClinVarEvidence(
        clinvar_id=clinvar_id,
        variant=variant,
        gene=gene,
        significance=significance,
        review_stars=review_stars,
        conditions=conditions,
        last_updated=last_updated,
        structural_residue=residue,
        structural_domain=domain,
    )


MOCK_CLINVAR_DB: list[ClinVarEvidence] = [
    # TP53 entries
    _clinvar(
        "CV-100001",
        "R175H",
        "TP53",
        "Pathogenic",
        4,
        ["Li-Fraumeni syndrome", "Breast cancer"],
        "2024-01-10",
        175,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-100002",
        "G245S",
        "TP53",
        "Pathogenic",
        4,
        ["Li-Fraumeni syndrome"],
        "2024-01-10",
        245,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-100003",
        "R248W",
        "TP53",
        "Pathogenic",
        4,
        ["Li-Fraumeni syndrome", "Colorectal cancer"],
        "2024-01-10",
        248,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-100004",
        "R248Q",
        "TP53",
        "Pathogenic",
        4,
        ["Li-Fraumeni syndrome"],
        "2024-03-15",
        248,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-100005",
        "R273H",
        "TP53",
        "Pathogenic",
        4,
        ["Multiple cancers"],
        "2024-02-20",
        273,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-100006",
        "V143A",
        "TP53",
        "Uncertain significance",
        1,
        ["Li-Fraumeni syndrome"],
        "2023-06-01",
        143,
        "DNA-binding domain",
    ),
    # KRAS entries
    _clinvar(
        "CV-200001",
        "G12V",
        "KRAS",
        "Pathogenic",
        3,
        ["Non-small cell lung cancer", "Colorectal cancer"],
        "2024-01-15",
        12,
        "G-domain",
    ),
    _clinvar(
        "CV-200002",
        "G12D",
        "KRAS",
        "Pathogenic",
        3,
        ["Pancreatic cancer", "Colorectal cancer"],
        "2024-01-15",
        12,
        "G-domain",
    ),
    _clinvar(
        "CV-200003",
        "G12C",
        "KRAS",
        "Pathogenic",
        4,
        ["Non-small cell lung cancer"],
        "2024-02-01",
        12,
        "G-domain",
    ),
    _clinvar(
        "CV-200004",
        "Q61H",
        "KRAS",
        "Likely pathogenic",
        2,
        ["Colorectal cancer"],
        "2023-11-20",
        61,
        "G-domain",
    ),
    # BRCA1 entries
    _clinvar(
        "CV-300001",
        "C61G",
        "BRCA1",
        "Pathogenic",
        4,
        ["Hereditary breast and ovarian cancer"],
        "2024-01-05",
        61,
        "RING domain",
    ),
    _clinvar(
        "CV-300002",
        "R1699W",
        "BRCA1",
        "Pathogenic",
        3,
        ["Hereditary breast cancer"],
        "2024-03-10",
        1699,
        "BRCT domain",
    ),
    _clinvar(
        "CV-300003",
        "M1775R",
        "BRCA1",
        "Pathogenic",
        4,
        ["Hereditary breast and ovarian cancer"],
        "2024-01-05",
        1775,
        "BRCT domain",
    ),
    _clinvar(
        "CV-300004",
        "P1749R",
        "BRCA1",
        "Uncertain significance",
        1,
        ["Hereditary breast cancer"],
        "2023-09-15",
        1749,
        "BRCT domain",
    ),
    # BRCA2 entries
    _clinvar(
        "CV-400001",
        "D2723H",
        "BRCA2",
        "Likely pathogenic",
        2,
        ["Hereditary breast cancer"],
        "2024-02-15",
        2723,
        "DNA-binding domain",
    ),
    _clinvar(
        "CV-400002",
        "K3326X",
        "BRCA2",
        "Benign",
        3,
        ["Hereditary cancer — general"],
        "2024-01-20",
        3326,
        None,
    ),
    # EGFR entries
    _clinvar(
        "CV-500001",
        "L858R",
        "EGFR",
        "Pathogenic",
        4,
        ["Non-small cell lung cancer"],
        "2024-04-01",
        858,
        "kinase domain",
    ),
    _clinvar(
        "CV-500002",
        "T790M",
        "EGFR",
        "Pathogenic",
        4,
        ["Non-small cell lung cancer — drug resistance"],
        "2024-04-01",
        790,
        "kinase domain",
    ),
    _clinvar(
        "CV-500003",
        "E746A",
        "EGFR",
        "Pathogenic",
        3,
        ["Non-small cell lung cancer"],
        "2024-03-15",
        746,
        "kinase domain",
    ),
    _clinvar(
        "CV-500004",
        "G719S",
        "EGFR",
        "Uncertain significance",
        2,
        ["Non-small cell lung cancer"],
        "2023-12-10",
        719,
        "kinase domain",
    ),
    # BRAF entries
    _clinvar(
        "CV-600001",
        "V600E",
        "BRAF",
        "Pathogenic",
        4,
        ["Melanoma", "Colorectal cancer", "Thyroid cancer"],
        "2024-04-15",
        600,
        "kinase domain",
    ),
    _clinvar(
        "CV-600002",
        "V600K",
        "BRAF",
        "Pathogenic",
        3,
        ["Melanoma"],
        "2024-02-28",
        600,
        "kinase domain",
    ),
    # PIK3CA entries
    _clinvar(
        "CV-700001",
        "H1047R",
        "PIK3CA",
        "Pathogenic",
        4,
        ["Breast cancer", "Colorectal cancer"],
        "2024-01-30",
        1047,
        "kinase domain",
    ),
    _clinvar(
        "CV-700002",
        "E545K",
        "PIK3CA",
        "Pathogenic",
        3,
        ["Breast cancer"],
        "2024-02-10",
        545,
        "helical domain",
    ),
    # PTEN entries
    _clinvar(
        "CV-800001",
        "R130Q",
        "PTEN",
        "Pathogenic",
        3,
        ["Cowden syndrome"],
        "2024-03-20",
        130,
        "phosphatase domain",
    ),
    # IDH1 entries
    _clinvar(
        "CV-900001",
        "R132H",
        "IDH1",
        "Pathogenic",
        4,
        ["Glioma", "AML"],
        "2024-04-10",
        132,
        "catalytic domain",
    ),
    # MET entries
    _clinvar(
        "CV-1000001",
        "Y1253D",
        "MET",
        "Pathogenic",
        3,
        ["Hereditary papillary renal carcinoma"],
        "2024-03-01",
        1253,
        "kinase domain",
    ),
    # CDKN2A entries
    _clinvar(
        "CV-1100001",
        "P114L",
        "CDKN2A",
        "Likely pathogenic",
        2,
        ["Melanoma — germline"],
        "2023-10-15",
        114,
        None,
    ),
    # Additional VUS / benign entries
    _clinvar(
        "CV-1200001",
        "V408M",
        "LDLR",
        "Benign",
        3,
        ["Familial hypercholesterolemia"],
        "2024-01-15",
        408,
        None,
    ),
    _clinvar(
        "CV-1200002",
        "A57V",
        "CDKN2A",
        "Uncertain significance",
        1,
        ["Melanoma"],
        "2023-08-20",
        57,
        None,
    ),
]


def lookup_clinvar(gene: str, variant: str | None = None) -> list[ClinVarEvidence]:
    """Look up ClinVar entries for a gene, optionally filtered by variant.

    RESEARCH USE ONLY.
    """
    gene_upper = gene.upper()
    results = [e for e in MOCK_CLINVAR_DB if e.gene.upper() == gene_upper]
    if variant is not None:
        results = [e for e in results if e.variant.upper() == variant.upper()]
    return results


def map_clinvar_to_structure(gene: str) -> StructuralClinVarMapping:
    """Map all ClinVar entries for a gene onto structural context.

    Identifies pathogenic hotspot residues and domain-level summaries.

    RESEARCH USE ONLY.
    """
    entries = lookup_clinvar(gene)
    mapped = [e for e in entries if e.structural_residue is not None]
    unmapped_count = len(entries) - len(mapped)

    # Identify pathogenic hotspot residues
    pathogenic_residues: dict[int, list[ClinVarEvidence]] = {}
    for e in mapped:
        if (
            e.significance in ("Pathogenic", "Likely pathogenic")
            and e.structural_residue is not None
        ):
            pathogenic_residues.setdefault(e.structural_residue, []).append(e)

    hotspots = []
    for residue, evs in sorted(pathogenic_residues.items()):
        hotspots.append(
            {
                "residue": residue,
                "domain": evs[0].structural_domain,
                "variant_count": len(evs),
                "variants": [e.variant for e in evs],
                "max_review_stars": max(e.review_stars for e in evs),
            }
        )

    # Domain-level summary
    domain_counts: dict[str, dict[str, int]] = {}
    for e in mapped:
        dom = e.structural_domain or "Unknown"
        if dom not in domain_counts:
            domain_counts[dom] = {
                "pathogenic": 0,
                "likely_pathogenic": 0,
                "VUS": 0,
                "benign": 0,
                "other": 0,
            }
        sig = e.significance
        if sig == "Pathogenic":
            domain_counts[dom]["pathogenic"] += 1
        elif sig == "Likely pathogenic":
            domain_counts[dom]["likely_pathogenic"] += 1
        elif sig == "Uncertain significance":
            domain_counts[dom]["VUS"] += 1
        elif sig == "Benign":
            domain_counts[dom]["benign"] += 1
        else:
            domain_counts[dom]["other"] += 1

    return StructuralClinVarMapping(
        gene=gene.upper(),
        total_variants=len(entries),
        mapped_variants=mapped,
        unmapped_count=unmapped_count,
        pathogenic_hotspots=hotspots,
        domain_summary=domain_counts,
    )


def get_clinvar_stats() -> dict:
    """Return summary statistics for the mock ClinVar database.

    RESEARCH USE ONLY.
    """
    sig_counts: dict[str, int] = {}
    gene_counts: dict[str, int] = {}
    star_distribution: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

    for e in MOCK_CLINVAR_DB:
        sig_counts[e.significance] = sig_counts.get(e.significance, 0) + 1
        gene_counts[e.gene] = gene_counts.get(e.gene, 0) + 1
        star_distribution[e.review_stars] = star_distribution.get(e.review_stars, 0) + 1

    mapped_count = sum(1 for e in MOCK_CLINVAR_DB if e.structural_residue is not None)

    return {
        "total_entries": len(MOCK_CLINVAR_DB),
        "significance_distribution": sig_counts,
        "gene_distribution": gene_counts,
        "review_star_distribution": star_distribution,
        "structurally_mapped": mapped_count,
        "unmapped": len(MOCK_CLINVAR_DB) - mapped_count,
        "safety_label": "RESEARCH USE ONLY — mock data, not real ClinVar",
    }
