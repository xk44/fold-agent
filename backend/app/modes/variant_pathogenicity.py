"""Variant Pathogenicity Mode — AlphaMissense Integration.

Provides:
  - AlphaMissense score lookup (mock/stub with 30 well-known pathogenic variants)
  - Variant-to-structure mapping
  - Germline vs somatic classification
  - Protein stability impact prediction
  - Pathogenicity report builder (aggregates per case)
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# AlphaMissense score lookup
# ---------------------------------------------------------------------------

# Pre-computed scores for well-known cancer-relevant mutations.
# Format: (GENE, MUTATION) -> score (0-1, where >0.564 = likely_pathogenic)
ALPHAMISSENSE_SCORES: dict[tuple[str, str], float] = {
    # TP53 hotspots
    ("TP53", "R175H"): 0.981,
    ("TP53", "G245S"): 0.974,
    ("TP53", "R248W"): 0.969,
    ("TP53", "R248Q"): 0.961,
    ("TP53", "R273H"): 0.956,
    ("TP53", "R273C"): 0.948,
    ("TP53", "R282W"): 0.942,
    ("TP53", "Y220C"): 0.937,
    # KRAS
    ("KRAS", "G12V"): 0.932,
    ("KRAS", "G12D"): 0.928,
    ("KRAS", "G12C"): 0.921,
    ("KRAS", "G13D"): 0.915,
    ("KRAS", "Q61H"): 0.887,
    # BRCA1
    ("BRCA1", "C61G"): 0.978,
    ("BRCA1", "R1699W"): 0.882,
    ("BRCA1", "M1775R"): 0.861,
    # BRCA2
    ("BRCA2", "K3326X"): 0.201,  # truncation — actually benign in isolation
    ("BRCA2", "D2723H"): 0.741,
    # EGFR
    ("EGFR", "L858R"): 0.893,
    ("EGFR", "T790M"): 0.847,
    ("EGFR", "E746A"): 0.831,
    # BRAF
    ("BRAF", "V600E"): 0.971,
    ("BRAF", "V600K"): 0.934,
    # PIK3CA
    ("PIK3CA", "H1047R"): 0.876,
    ("PIK3CA", "E545K"): 0.812,
    # PTEN
    ("PTEN", "R130Q"): 0.734,
    # IDH1
    ("IDH1", "R132H"): 0.891,
    # CDKN2A
    ("CDKN2A", "P114L"): 0.568,
    # MET
    ("MET", "Y1253D"): 0.798,
    # Benign reference
    ("LDLR", "V408M"): 0.182,
}


def classify_score(score: float) -> str:
    """Return AlphaMissense classification for a pathogenicity score.

    Thresholds from the AlphaMissense paper (Cheng et al. 2023):
      < 0.340  → likely_benign
      0.340 – 0.564 → uncertain
      > 0.564  → likely_pathogenic
    """
    if score < 0.34:
        return "likely_benign"
    if score <= 0.564:
        return "uncertain"
    return "likely_pathogenic"


@dataclass
class PathogenicityScore:
    gene: str
    mutation: str
    score: float
    classification: str
    confidence: str
    source: str = "alphamissense_stub"


def lookup_alphamissense(gene: str, mutation: str) -> PathogenicityScore | None:
    """Look up a pre-computed AlphaMissense score.

    Returns None if the variant is not in the stub table.
    """
    key = (gene.upper(), mutation)
    score = ALPHAMISSENSE_SCORES.get(key)
    if score is None:
        return None
    classification = classify_score(score)
    confidence = "high" if key[0] in {"TP53", "KRAS", "BRAF", "BRCA1"} else "moderate"
    return PathogenicityScore(
        gene=gene,
        mutation=mutation,
        score=score,
        classification=classification,
        confidence=confidence,
    )


def batch_lookup(variants: list[dict]) -> list[PathogenicityScore]:
    """Batch AlphaMissense lookup.

    Each element must have 'gene' and 'mutation' keys.
    Variants not found in the stub table are skipped.
    """
    results: list[PathogenicityScore] = []
    for v in variants:
        ps = lookup_alphamissense(v.get("gene", ""), v.get("mutation", ""))
        if ps is not None:
            results.append(ps)
    return results


# ---------------------------------------------------------------------------
# Variant-to-structure mapping
# ---------------------------------------------------------------------------

# Critical residues known to be functionally important (active sites, interfaces).
KNOWN_CRITICAL_RESIDUES: dict[str, list[int]] = {
    "TP53": [175, 245, 248, 249, 273, 282],
    "KRAS": [12, 13, 61, 146],
    "BRAF": [600],
    "EGFR": [790, 858, 719, 746, 747, 750],
    "BRCA1": [61, 1699, 1775],
    "BRCA2": [2723],
    "PIK3CA": [1047, 545, 542],
    "PTEN": [130, 173],
    "IDH1": [132],
    "MET": [1253],
}

# Residues known to be surface-exposed (approximate; for demo purposes)
_SURFACE_EXPOSED_RESIDUES: dict[str, list[int]] = {
    "TP53": [220, 249, 273],
    "EGFR": [858, 790],
    "KRAS": [12, 13],
    "BRAF": [600],
}


@dataclass
class VariantStructureMapping:
    variant_id: str
    gene: str
    mutation: str
    residue_position: int | None
    domain: str | None
    surface_exposed: bool | None
    structural_impact: str  # high / moderate / low / unknown


def _parse_residue_position(mutation: str) -> int | None:
    """Extract numeric position from a mutation string like R175H or G12V."""
    if not mutation:
        return None
    m = re.search(r"\d+", mutation)
    return int(m.group()) if m else None


def _infer_domain(gene: str, position: int | None) -> str | None:
    """Very coarse domain assignment for common genes."""
    if position is None:
        return None
    domains: dict[str, list[tuple[int, int, str]]] = {
        "TP53": [(102, 292, "DNA-binding domain"), (293, 363, "tetramerization domain")],
        "KRAS": [(1, 86, "G-domain"), (87, 166, "switch-II region")],
        "EGFR": [(712, 979, "kinase domain")],
        "BRCA1": [(1, 100, "RING domain"), (1642, 1736, "BRCT domain")],
        "PIK3CA": [(954, 1068, "kinase domain")],
    }
    for start, end, name in domains.get(gene.upper(), []):
        if start <= position <= end:
            return name
    return None


def map_variant_to_structure(variant: dict) -> VariantStructureMapping:
    """Map a variant dict to structural context.

    Expected keys: 'id', 'gene', 'mutation' (or 'protein_change').
    """
    variant_id = str(variant.get("id", ""))
    gene = str(variant.get("gene") or "").upper()
    mutation = str(variant.get("mutation") or variant.get("protein_change") or "")

    position = _parse_residue_position(mutation)
    domain = _infer_domain(gene, position)

    critical = position in KNOWN_CRITICAL_RESIDUES.get(gene, []) if position else False
    surface = position in _SURFACE_EXPOSED_RESIDUES.get(gene, []) if position else None

    if critical:
        structural_impact = "high"
    elif surface:
        structural_impact = "moderate"
    elif position is not None:
        structural_impact = "low"
    else:
        structural_impact = "unknown"

    return VariantStructureMapping(
        variant_id=variant_id,
        gene=gene,
        mutation=mutation,
        residue_position=position,
        domain=domain,
        surface_exposed=surface if not critical else True,
        structural_impact=structural_impact,
    )


# ---------------------------------------------------------------------------
# Germline vs somatic classification
# ---------------------------------------------------------------------------


class VariantOrigin(str, enum.Enum):
    germline = "germline"
    somatic = "somatic"
    uncertain = "uncertain"


def classify_variant_origin(variant: dict) -> str:
    """Classify variant origin using VAF heuristics.

    VAF > 0.4  → germline
    VAF < 0.3  → somatic
    0.3 – 0.4 → uncertain

    VAF may be supplied directly ('vaf') or nested inside 'quality_metrics'.
    """
    vaf = variant.get("vaf")
    if vaf is None:
        qm = variant.get("quality_metrics") or {}
        vaf = qm.get("vaf")

    if vaf is None:
        return VariantOrigin.uncertain.value

    try:
        vaf = float(vaf)
    except (TypeError, ValueError):
        return VariantOrigin.uncertain.value

    if vaf > 0.4:
        return VariantOrigin.germline.value
    if vaf < 0.3:
        return VariantOrigin.somatic.value
    return VariantOrigin.uncertain.value


# ---------------------------------------------------------------------------
# Protein stability impact prediction
# ---------------------------------------------------------------------------

AMINO_ACID_PROPERTIES: dict[str, dict] = {
    "A": {"charge": 0, "size": "small", "hydrophobic": True},
    "R": {"charge": 1, "size": "large", "hydrophobic": False},
    "N": {"charge": 0, "size": "medium", "hydrophobic": False},
    "D": {"charge": -1, "size": "medium", "hydrophobic": False},
    "C": {"charge": 0, "size": "small", "hydrophobic": True},
    "Q": {"charge": 0, "size": "medium", "hydrophobic": False},
    "E": {"charge": -1, "size": "medium", "hydrophobic": False},
    "G": {"charge": 0, "size": "tiny", "hydrophobic": False},
    "H": {"charge": 1, "size": "medium", "hydrophobic": False},
    "I": {"charge": 0, "size": "medium", "hydrophobic": True},
    "L": {"charge": 0, "size": "medium", "hydrophobic": True},
    "K": {"charge": 1, "size": "large", "hydrophobic": False},
    "M": {"charge": 0, "size": "medium", "hydrophobic": True},
    "F": {"charge": 0, "size": "large", "hydrophobic": True},
    "P": {"charge": 0, "size": "small", "hydrophobic": False},
    "S": {"charge": 0, "size": "small", "hydrophobic": False},
    "T": {"charge": 0, "size": "small", "hydrophobic": False},
    "W": {"charge": 0, "size": "large", "hydrophobic": True},
    "Y": {"charge": 0, "size": "large", "hydrophobic": False},
    "V": {"charge": 0, "size": "small", "hydrophobic": True},
    "X": {"charge": 0, "size": "unknown", "hydrophobic": False},  # stop / unknown
}

_SIZE_ORDER = {"tiny": 0, "small": 1, "medium": 2, "large": 3, "unknown": -1}


@dataclass
class StabilityImpact:
    ddg_estimate: float  # positive = destabilizing (kcal/mol estimate)
    destabilizing: bool
    confidence: str  # high / moderate / low


def _parse_mutation_aas(mutation: str) -> tuple[str, str] | None:
    """Extract ref/alt amino acids from a mutation string like R175H.

    Returns (ref_aa, alt_aa) single-letter codes, or None if unparseable.
    """
    m = re.match(r"^([A-Z*])(\d+)([A-Z*])$", mutation.strip())
    if not m:
        return None
    return m.group(1), m.group(3)


def estimate_stability_impact(gene: str, mutation: str) -> StabilityImpact:
    """Estimate protein stability impact from amino acid substitution properties.

    Rules:
      - Charge change        → moderate destabilizing (+2.0 kcal/mol estimate)
      - Large size change    → high destabilizing (+3.5)
      - Hydrophobic↔polar   → high destabilizing (+3.0)
      - Conservative (same class) → low impact (+0.5)
      - Mixed moderate changes → moderate (+1.5)
      - Unknown AA           → low confidence, neutral estimate
    """
    aas = _parse_mutation_aas(mutation)
    if aas is None:
        return StabilityImpact(ddg_estimate=0.0, destabilizing=False, confidence="low")

    ref_aa, alt_aa = aas
    ref_props = AMINO_ACID_PROPERTIES.get(ref_aa, AMINO_ACID_PROPERTIES["X"])
    alt_props = AMINO_ACID_PROPERTIES.get(alt_aa, AMINO_ACID_PROPERTIES["X"])

    if ref_props["size"] == "unknown" or alt_props["size"] == "unknown":
        return StabilityImpact(ddg_estimate=0.0, destabilizing=False, confidence="low")

    charge_change = ref_props["charge"] != alt_props["charge"]
    ref_size_val = _SIZE_ORDER[ref_props["size"]]
    alt_size_val = _SIZE_ORDER[alt_props["size"]]
    size_delta = abs(ref_size_val - alt_size_val)
    hydro_swap = ref_props["hydrophobic"] != alt_props["hydrophobic"]

    if size_delta >= 2 or (size_delta >= 1 and hydro_swap):
        # Large size change or size+hydrophobicity swap
        ddg = 3.5
        confidence = "high"
    elif hydro_swap and charge_change:
        ddg = 3.0
        confidence = "high"
    elif hydro_swap or charge_change:
        ddg = 2.0
        confidence = "moderate"
    elif size_delta == 1:
        ddg = 1.5
        confidence = "moderate"
    else:
        ddg = 0.5
        confidence = "high"

    destabilizing = ddg >= 1.5
    return StabilityImpact(ddg_estimate=ddg, destabilizing=destabilizing, confidence=confidence)


# ---------------------------------------------------------------------------
# Pathogenicity report builder
# ---------------------------------------------------------------------------


def build_pathogenicity_report(case_id: str, db) -> dict:
    """Aggregate pathogenicity data for all variants in a case.

    Returns a summary dict with per-variant details and aggregate counts.
    """
    from backend.app.models import Case, Variant  # late import to avoid circular

    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        return {"error": "case_not_found", "case_id": case_id}

    variants = db.query(Variant).filter(Variant.case_id == case_id).all()

    variant_details: list[dict] = []
    pathogenic_count = 0
    benign_count = 0
    uncertain_count = 0
    high_impact_count = 0

    for v in variants:
        gene = v.gene or ""
        mutation = v.protein_change or ""

        am_score = lookup_alphamissense(gene, mutation)
        struct_map = map_variant_to_structure(
            {"id": v.id, "gene": gene, "protein_change": mutation}
        )
        stability = estimate_stability_impact(gene, mutation)
        origin = classify_variant_origin({"vaf": (v.quality_metrics or {}).get("vaf")})

        if am_score:
            cls = am_score.classification
        else:
            cls = "unknown"

        if cls == "likely_pathogenic":
            pathogenic_count += 1
        elif cls == "likely_benign":
            benign_count += 1
        elif cls == "uncertain":
            uncertain_count += 1

        if struct_map.structural_impact == "high":
            high_impact_count += 1

        variant_details.append(
            {
                "variant_id": v.id,
                "gene": gene,
                "mutation": mutation,
                "alphamissense": {
                    "score": am_score.score if am_score else None,
                    "classification": cls,
                    "confidence": am_score.confidence if am_score else None,
                    "source": am_score.source if am_score else None,
                },
                "structure": {
                    "residue_position": struct_map.residue_position,
                    "domain": struct_map.domain,
                    "surface_exposed": struct_map.surface_exposed,
                    "structural_impact": struct_map.structural_impact,
                },
                "stability": {
                    "ddg_estimate": stability.ddg_estimate,
                    "destabilizing": stability.destabilizing,
                    "confidence": stability.confidence,
                },
                "origin": origin,
            }
        )

    return {
        "case_id": case_id,
        "total_variants": len(variants),
        "pathogenic_count": pathogenic_count,
        "benign_count": benign_count,
        "uncertain_count": uncertain_count,
        "unknown_count": len(variants) - pathogenic_count - benign_count - uncertain_count,
        "high_impact_count": high_impact_count,
        "variants": variant_details,
    }
