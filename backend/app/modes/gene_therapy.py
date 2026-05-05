"""Gene Therapy Mode — CRISPR, AAV delivery, and transgene safety pipeline.

Provides:
  - CRISPR-Cas structure prediction (12 Cas variants)
  - Guide RNA design and scoring
  - PAM specificity analysis
  - AAV capsid tropism modeling
  - Transgene safety scoring
  - Base/prime editor modeling
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# CRISPR-Cas variants
# ---------------------------------------------------------------------------

@dataclass
class CasVariant:
    name: str
    cas_type: str  # Cas9 | Cas12 | Cas13
    source_organism: str
    sequence_length: int  # amino acids
    pam_sequence: str
    editing_type: str  # DSB | nickase | base_edit | prime_edit
    af_confidence: float  # 0-1 pLDDT-like


KNOWN_CAS_VARIANTS: dict[str, CasVariant] = {
    "SpCas9": CasVariant(
        name="SpCas9",
        cas_type="Cas9",
        source_organism="Streptococcus pyogenes",
        sequence_length=1368,
        pam_sequence="NGG",
        editing_type="DSB",
        af_confidence=0.94,
    ),
    "SaCas9": CasVariant(
        name="SaCas9",
        cas_type="Cas9",
        source_organism="Staphylococcus aureus",
        sequence_length=1053,
        pam_sequence="NNGRRT",
        editing_type="DSB",
        af_confidence=0.91,
    ),
    "CjCas9": CasVariant(
        name="CjCas9",
        cas_type="Cas9",
        source_organism="Campylobacter jejuni",
        sequence_length=984,
        pam_sequence="NNNNRYAC",
        editing_type="DSB",
        af_confidence=0.87,
    ),
    "NmCas9": CasVariant(
        name="NmCas9",
        cas_type="Cas9",
        source_organism="Neisseria meningitidis",
        sequence_length=1082,
        pam_sequence="NNNNGATT",
        editing_type="DSB",
        af_confidence=0.85,
    ),
    "AsCas12a": CasVariant(
        name="AsCas12a",
        cas_type="Cas12",
        source_organism="Acidaminococcus sp.",
        sequence_length=1307,
        pam_sequence="TTTV",
        editing_type="DSB",
        af_confidence=0.92,
    ),
    "LbCas12a": CasVariant(
        name="LbCas12a",
        cas_type="Cas12",
        source_organism="Lachnospiraceae bacterium",
        sequence_length=1228,
        pam_sequence="TTTV",
        editing_type="DSB",
        af_confidence=0.89,
    ),
    "CasX": CasVariant(
        name="CasX",
        cas_type="Cas12",
        source_organism="Planctomycetes bacterium",
        sequence_length=986,
        pam_sequence="TTCN",
        editing_type="DSB",
        af_confidence=0.83,
    ),
    "Cas13a": CasVariant(
        name="Cas13a",
        cas_type="Cas13",
        source_organism="Leptotrichia shahii",
        sequence_length=1078,
        pam_sequence="none (RNA-targeting)",
        editing_type="DSB",
        af_confidence=0.88,
    ),
    "ABE8e": CasVariant(
        name="ABE8e",
        cas_type="Cas9",
        source_organism="Engineered (SpCas9 nickase + TadA-8e)",
        sequence_length=1458,
        pam_sequence="NGG",
        editing_type="base_edit",
        af_confidence=0.86,
    ),
    "BE4max": CasVariant(
        name="BE4max",
        cas_type="Cas9",
        source_organism="Engineered (SpCas9 nickase + APOBEC1)",
        sequence_length=1480,
        pam_sequence="NGG",
        editing_type="base_edit",
        af_confidence=0.85,
    ),
    "PE2": CasVariant(
        name="PE2",
        cas_type="Cas9",
        source_organism="Engineered (SpCas9 nickase + MMLV RT)",
        sequence_length=1791,
        pam_sequence="NGG",
        editing_type="prime_edit",
        af_confidence=0.82,
    ),
    "OpenCRISPR-1": CasVariant(
        name="OpenCRISPR-1",
        cas_type="Cas9",
        source_organism="Engineered (AI-designed)",
        sequence_length=1368,
        pam_sequence="NGG",
        editing_type="DSB",
        af_confidence=0.90,
    ),
}


def predict_cas_structure(cas_name: str) -> dict:
    """Stub: Return mock AlphaFold confidence and domain info for a Cas variant.

    Returns structural predictions for known variants; returns a low-confidence
    stub for unknown variants.
    """
    variant = KNOWN_CAS_VARIANTS.get(cas_name)
    if variant is None:
        return {
            "cas_name": cas_name,
            "found": False,
            "af_confidence": 0.0,
            "domains": [],
            "note": "Variant not in knowledge base — no structural model available",
        }

    domains: list[dict] = []
    if variant.cas_type == "Cas9":
        domains = [
            {"name": "REC lobe", "residues": [1, 500], "function": "guide RNA binding"},
            {"name": "NUC lobe", "residues": [501, variant.sequence_length], "function": "DNA cleavage"},
            {"name": "RuvC domain", "residues": [1, 60], "function": "non-target strand cleavage"},
            {"name": "HNH domain", "residues": [775, 908], "function": "target strand cleavage"},
        ]
    elif variant.cas_type == "Cas12":
        domains = [
            {"name": "RuvC domain", "residues": [1, 200], "function": "DNA cleavage (both strands)"},
            {"name": "WED domain", "residues": [201, 500], "function": "PAM recognition"},
            {"name": "PI domain", "residues": [501, variant.sequence_length], "function": "PAM interaction"},
        ]
    elif variant.cas_type == "Cas13":
        domains = [
            {"name": "HEPN domain 1", "residues": [1, 350], "function": "RNA cleavage"},
            {"name": "HEPN domain 2", "residues": [700, variant.sequence_length], "function": "RNA cleavage"},
        ]

    return {
        "cas_name": cas_name,
        "found": True,
        "cas_type": variant.cas_type,
        "source_organism": variant.source_organism,
        "sequence_length": variant.sequence_length,
        "af_confidence": variant.af_confidence,
        "plddt_mean": round(variant.af_confidence * 100, 1),
        "domains": domains,
        "editing_type": variant.editing_type,
        "pam_sequence": variant.pam_sequence,
    }


# ---------------------------------------------------------------------------
# Guide RNA design
# ---------------------------------------------------------------------------

@dataclass
class GuideRNA:
    target_sequence: str  # 20 nt
    pam: str
    strand: str  # + | -
    gc_content: float
    off_target_score: float  # 0-1, lower = fewer off-targets
    efficiency_score: float  # 0-1, higher = more efficient
    self_complementarity: float  # 0-1, lower = less hairpin risk


# PAM sequences per cas type for guide design
_CAS_PAM_MAP: dict[str, str] = {
    "SpCas9": "NGG",
    "SaCas9": "NNGRRT",
    "CjCas9": "NNNNRYAC",
    "NmCas9": "NNNNGATT",
    "AsCas12a": "TTTV",
    "LbCas12a": "TTTV",
    "CasX": "TTCN",
    "ABE8e": "NGG",
    "BE4max": "NGG",
    "PE2": "NGG",
    "OpenCRISPR-1": "NGG",
}

_BASES = "ACGT"
_RNG_SEED = 42


def _mock_sequence(length: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choices(_BASES, k=length))


def design_guides(
    target_gene: str,
    cas_type: str = "SpCas9",
    n_guides: int = 5,
) -> list[GuideRNA]:
    """Stub: Generate mock guide RNAs for a target gene and Cas type.

    GC content is constrained to 40-60% optimal range.
    Scores are deterministically seeded per (gene, cas_type, guide_index).
    """
    pam = _CAS_PAM_MAP.get(cas_type, "NGG")
    guides: list[GuideRNA] = []

    for i in range(n_guides):
        seed = hash((target_gene.upper(), cas_type, i)) % (2**31)
        rng = random.Random(seed)

        # Build a 20-nt sequence biased toward 40-60% GC
        bases_gc = "GC"
        bases_at = "AT"
        seq_chars = []
        for pos in range(20):
            if rng.random() < 0.50:
                seq_chars.append(rng.choice(bases_gc))
            else:
                seq_chars.append(rng.choice(bases_at))
        target_seq = "".join(seq_chars)

        gc = (target_seq.count("G") + target_seq.count("C")) / 20.0
        # If GC outside 40-60, nudge toward center (still mock)
        if gc < 0.40 or gc > 0.60:
            # Replace up to 3 bases to adjust
            idx_list = list(range(20))
            rng.shuffle(idx_list)
            arr = list(target_seq)
            for idx in idx_list[:3]:
                if gc < 0.40:
                    arr[idx] = rng.choice(bases_gc)
                else:
                    arr[idx] = rng.choice(bases_at)
            target_seq = "".join(arr)
            gc = (target_seq.count("G") + target_seq.count("C")) / 20.0

        guides.append(
            GuideRNA(
                target_sequence=target_seq,
                pam=pam,
                strand=rng.choice(["+", "-"]),
                gc_content=round(gc, 3),
                off_target_score=round(rng.uniform(0.05, 0.35), 3),
                efficiency_score=round(rng.uniform(0.55, 0.95), 3),
                self_complementarity=round(rng.uniform(0.01, 0.20), 3),
            )
        )

    return guides


def score_guide(guide_sequence: str) -> dict:
    """Score a guide RNA sequence for editing suitability.

    Returns gc_content, homopolymer_penalty, self_comp_score.
    """
    seq = guide_sequence.upper().strip()
    length = len(seq)
    if length == 0:
        return {
            "guide_sequence": guide_sequence,
            "length": 0,
            "gc_content": 0.0,
            "homopolymer_penalty": 0.0,
            "self_comp_score": 0.0,
            "note": "Empty sequence",
        }

    gc = (seq.count("G") + seq.count("C")) / length

    # Homopolymer penalty: penalize runs of >=4 identical bases
    homopolymer_penalty = 0.0
    run = 1
    for j in range(1, len(seq)):
        if seq[j] == seq[j - 1]:
            run += 1
            if run >= 4:
                homopolymer_penalty = min(homopolymer_penalty + 0.15, 1.0)
        else:
            run = 1

    # Self-complementarity: count Watson-Crick complement pairs in first/last 8 nt
    complement = {"A": "T", "T": "A", "G": "C", "C": "G"}
    half = min(8, length // 2)
    matches = sum(
        1
        for k in range(half)
        if k < length and (length - 1 - k) < length and seq[k] == complement.get(seq[length - 1 - k], "")
    )
    self_comp_score = round(matches / half, 3) if half > 0 else 0.0

    return {
        "guide_sequence": guide_sequence,
        "length": length,
        "gc_content": round(gc, 3),
        "homopolymer_penalty": round(homopolymer_penalty, 3),
        "self_comp_score": self_comp_score,
        "gc_optimal": 0.40 <= gc <= 0.60,
    }


# ---------------------------------------------------------------------------
# PAM specificity analysis
# ---------------------------------------------------------------------------

@dataclass
class PAMAnalysis:
    cas_type: str
    canonical_pam: str
    alternative_pams: list[str]
    specificity_score: float  # 0-1, higher = more stringent PAM requirement
    mismatch_tolerance: int  # mismatches tolerated in PAM


PAM_DATABASE: dict[str, dict] = {
    "SpCas9": {
        "canonical_pam": "NGG",
        "alternative_pams": ["NAG", "NGA"],
        "specificity_score": 0.72,
        "mismatch_tolerance": 1,
    },
    "SaCas9": {
        "canonical_pam": "NNGRRT",
        "alternative_pams": ["NNGRRN", "NNGRRC"],
        "specificity_score": 0.85,
        "mismatch_tolerance": 1,
    },
    "CjCas9": {
        "canonical_pam": "NNNNRYAC",
        "alternative_pams": ["NNNNRYAT"],
        "specificity_score": 0.91,
        "mismatch_tolerance": 1,
    },
    "NmCas9": {
        "canonical_pam": "NNNNGATT",
        "alternative_pams": ["NNNNGTTT"],
        "specificity_score": 0.88,
        "mismatch_tolerance": 1,
    },
    "AsCas12a": {
        "canonical_pam": "TTTV",
        "alternative_pams": ["TTTN", "CTTV"],
        "specificity_score": 0.80,
        "mismatch_tolerance": 1,
    },
    "LbCas12a": {
        "canonical_pam": "TTTV",
        "alternative_pams": ["TTTN"],
        "specificity_score": 0.83,
        "mismatch_tolerance": 0,
    },
    "CasX": {
        "canonical_pam": "TTCN",
        "alternative_pams": ["TTCC", "TTCA"],
        "specificity_score": 0.86,
        "mismatch_tolerance": 1,
    },
    "ABE8e": {
        "canonical_pam": "NGG",
        "alternative_pams": ["NAG"],
        "specificity_score": 0.72,
        "mismatch_tolerance": 1,
    },
    "BE4max": {
        "canonical_pam": "NGG",
        "alternative_pams": ["NAG", "NGA"],
        "specificity_score": 0.72,
        "mismatch_tolerance": 1,
    },
    "PE2": {
        "canonical_pam": "NGG",
        "alternative_pams": ["NAG"],
        "specificity_score": 0.72,
        "mismatch_tolerance": 1,
    },
    "OpenCRISPR-1": {
        "canonical_pam": "NGG",
        "alternative_pams": ["NAG"],
        "specificity_score": 0.74,
        "mismatch_tolerance": 1,
    },
}


def analyze_pam_specificity(cas_type: str) -> PAMAnalysis:
    """Return PAM specificity analysis for a given Cas type.

    Falls back to SpCas9 defaults for unknown Cas types.
    """
    data = PAM_DATABASE.get(cas_type, PAM_DATABASE["SpCas9"])
    return PAMAnalysis(
        cas_type=cas_type,
        canonical_pam=data["canonical_pam"],
        alternative_pams=list(data["alternative_pams"]),
        specificity_score=data["specificity_score"],
        mismatch_tolerance=data["mismatch_tolerance"],
    )


# ---------------------------------------------------------------------------
# AAV capsid tropism modeling
# ---------------------------------------------------------------------------

@dataclass
class AAVSerotype:
    name: str
    tropism: list[str]
    receptor: str
    transduction_efficiency: dict[str, float]  # tissue -> 0-1 score


AAV_SEROTYPES: dict[str, AAVSerotype] = {
    "AAV1": AAVSerotype(
        name="AAV1",
        tropism=["muscle", "CNS", "heart", "lung"],
        receptor="AAVR, sialic acid",
        transduction_efficiency={
            "muscle": 0.90,
            "CNS": 0.65,
            "heart": 0.75,
            "lung": 0.50,
            "liver": 0.20,
            "retina": 0.30,
        },
    ),
    "AAV2": AAVSerotype(
        name="AAV2",
        tropism=["liver", "muscle", "CNS", "retina"],
        receptor="HSPG, AAVR",
        transduction_efficiency={
            "liver": 0.65,
            "muscle": 0.55,
            "CNS": 0.60,
            "retina": 0.85,
            "heart": 0.40,
            "lung": 0.30,
        },
    ),
    "AAV3": AAVSerotype(
        name="AAV3",
        tropism=["liver", "muscle"],
        receptor="HSPG, FGFR1",
        transduction_efficiency={
            "liver": 0.75,
            "muscle": 0.55,
            "CNS": 0.30,
            "retina": 0.25,
            "heart": 0.35,
            "lung": 0.20,
        },
    ),
    "AAV4": AAVSerotype(
        name="AAV4",
        tropism=["CNS", "lung", "retina"],
        receptor="Sialic acid (O-linked)",
        transduction_efficiency={
            "CNS": 0.60,
            "lung": 0.55,
            "retina": 0.60,
            "liver": 0.20,
            "muscle": 0.15,
            "heart": 0.20,
        },
    ),
    "AAV5": AAVSerotype(
        name="AAV5",
        tropism=["CNS", "lung", "retina", "liver"],
        receptor="PDGFR, sialic acid (N-linked)",
        transduction_efficiency={
            "CNS": 0.80,
            "lung": 0.85,
            "retina": 0.80,
            "liver": 0.60,
            "muscle": 0.45,
            "heart": 0.40,
        },
    ),
    "AAV6": AAVSerotype(
        name="AAV6",
        tropism=["muscle", "heart", "lung"],
        receptor="AAVR, EGFR, sialic acid",
        transduction_efficiency={
            "muscle": 0.88,
            "heart": 0.85,
            "lung": 0.80,
            "liver": 0.35,
            "CNS": 0.40,
            "retina": 0.25,
        },
    ),
    "AAV7": AAVSerotype(
        name="AAV7",
        tropism=["muscle", "CNS"],
        receptor="AAVR",
        transduction_efficiency={
            "muscle": 0.85,
            "CNS": 0.65,
            "liver": 0.25,
            "heart": 0.50,
            "lung": 0.30,
            "retina": 0.20,
        },
    ),
    "AAV8": AAVSerotype(
        name="AAV8",
        tropism=["liver", "muscle", "CNS", "heart"],
        receptor="LamR, AAVR",
        transduction_efficiency={
            "liver": 0.95,
            "muscle": 0.80,
            "CNS": 0.70,
            "heart": 0.75,
            "lung": 0.40,
            "retina": 0.50,
        },
    ),
    "AAV9": AAVSerotype(
        name="AAV9",
        tropism=["CNS", "heart", "muscle", "liver", "lung"],
        receptor="LamR, galactose",
        transduction_efficiency={
            "CNS": 0.90,
            "heart": 0.88,
            "muscle": 0.85,
            "liver": 0.80,
            "lung": 0.65,
            "retina": 0.55,
        },
    ),
    "AAVrh10": AAVSerotype(
        name="AAVrh10",
        tropism=["CNS", "liver", "lung"],
        receptor="AAVR",
        transduction_efficiency={
            "CNS": 0.92,
            "liver": 0.78,
            "lung": 0.60,
            "muscle": 0.55,
            "heart": 0.60,
            "retina": 0.45,
        },
    ),
    "AAV-PHP.eB": AAVSerotype(
        name="AAV-PHP.eB",
        tropism=["CNS"],
        receptor="LY6A (mouse), AAVR",
        transduction_efficiency={
            "CNS": 0.98,
            "liver": 0.30,
            "muscle": 0.20,
            "lung": 0.15,
            "heart": 0.25,
            "retina": 0.35,
        },
    ),
    "AAV-DJ": AAVSerotype(
        name="AAV-DJ",
        tropism=["liver", "muscle", "heart"],
        receptor="HSPG, sialic acid, LamR",
        transduction_efficiency={
            "liver": 0.97,
            "muscle": 0.75,
            "heart": 0.70,
            "CNS": 0.50,
            "lung": 0.45,
            "retina": 0.40,
        },
    ),
}


def recommend_serotype(target_tissue: str) -> list[AAVSerotype]:
    """Return AAV serotypes ranked by transduction efficiency for the given tissue.

    Matching is case-insensitive. Returns serotypes where the tissue appears
    in the tropism list or transduction_efficiency dict, sorted descending by score.
    """
    tissue = target_tissue.lower()
    ranked: list[tuple[float, AAVSerotype]] = []

    for serotype in AAV_SEROTYPES.values():
        # Look up efficiency for closest tissue key match
        score = 0.0
        for key, val in serotype.transduction_efficiency.items():
            if tissue in key.lower() or key.lower() in tissue:
                score = max(score, val)
        if score > 0:
            ranked.append((score, serotype))

    ranked.sort(key=lambda t: -t[0])
    return [s for _, s in ranked]


def model_capsid_receptor(serotype: str) -> dict:
    """Stub: Return mock AF3 capsid-receptor docking model for an AAV serotype."""
    aav = AAV_SEROTYPES.get(serotype)
    if aav is None:
        return {
            "serotype": serotype,
            "found": False,
            "note": "Serotype not in knowledge base",
        }
    return {
        "serotype": serotype,
        "found": True,
        "receptor": aav.receptor,
        "model_type": "AF3_capsid_receptor_stub",
        "docking_score": round(random.Random(serotype).uniform(-12.5, -7.0), 2),
        "contact_residues": [62, 272, 381, 447, 533, 585, 661],
        "predicted_kd_nm": round(random.Random(serotype + "_kd").uniform(5.0, 500.0), 1),
        "confidence": "low (stub model — AF3 not executed)",
    }


# ---------------------------------------------------------------------------
# Transgene safety scoring
# ---------------------------------------------------------------------------

@dataclass
class TransgeneSafety:
    gene: str
    variant_count: int
    pathogenic_variants: list[str]
    integration_risk: str  # low | moderate | high
    immunogenicity_risk: str  # low | moderate | high
    expression_level_estimate: str  # low | moderate | high


# Known pathogenic variant patterns (simplified)
_PATHOGENIC_VARIANT_PATTERNS: dict[str, list[str]] = {
    "TP53": ["R175H", "R248W", "R248Q", "R273H", "R273C", "G245S"],
    "KRAS": ["G12D", "G12V", "G12C", "Q61H"],
    "BRAF": ["V600E", "V600K"],
    "BRCA1": ["5382insC", "C61G", "M1775R"],
    "BRCA2": ["N991D", "K3326X", "T3033Nfs"],
    "APC": ["E1309D", "R1450X"],
    "PTEN": ["R130Q", "R130G", "C124S"],
    "RB1": ["R661W", "R579X"],
    "MLH1": ["A681T", "K618A"],
    "CFTR": ["F508del", "G542X", "G551D", "W1282X"],
    "SMN1": ["exon7del"],
    "DMD": ["exon51del", "exon45del"],
    "MECP2": ["R168X", "T158M", "R255X"],
    "RPGR": ["ORF15_frameshift"],
}

# Integration risk by delivery modality implied by gene name keywords
_INTEGRATION_RISK_RULES: dict[str, str] = {
    "LTR": "high",
    "transposon": "high",
    "piggyBac": "high",
    "lentiviral": "moderate",
    "AAV": "low",
    "episomal": "low",
}

# Immunogenic gene keywords (simplified heuristic)
_IMMUNOGENIC_KEYWORDS = {"cas9", "cas12", "gfp", "luciferase", "lacz", "bacterial", "viral"}


def score_transgene_safety(gene: str, sequence: str) -> TransgeneSafety:
    """Score a transgene for safety based on known pathogenic variants and risk heuristics.

    - Checks sequence for known pathogenic variant motifs (amino acid signatures).
    - Estimates integration risk from gene name keywords.
    - Estimates immunogenicity from gene name (bacterial/viral proteins are more immunogenic).
    - Expression estimate based on sequence length (proxy for coding capacity).
    """
    gene_upper = gene.upper()
    seq_upper = sequence.upper()

    # Count variants found in sequence
    known_variants = _PATHOGENIC_VARIANT_PATTERNS.get(gene_upper, [])
    # Simplified: check if variant amino acid codes appear in sequence as substrings
    found_pathogenic: list[str] = []
    for variant in known_variants:
        # Extract the amino acid change part (letters only)
        aa_part = "".join(c for c in variant if c.isalpha())
        if aa_part and len(aa_part) >= 2 and aa_part[1:] in seq_upper:
            found_pathogenic.append(variant)

    variant_count = len(known_variants)

    # Integration risk
    integration_risk = "low"
    for keyword, risk in _INTEGRATION_RISK_RULES.items():
        if keyword.lower() in gene.lower() or keyword.lower() in sequence.lower():
            if risk == "high":
                integration_risk = "high"
                break
            elif risk == "moderate" and integration_risk == "low":
                integration_risk = "moderate"

    # Immunogenicity risk
    gene_lower = gene.lower()
    immunogenicity_risk = "low"
    for keyword in _IMMUNOGENIC_KEYWORDS:
        if keyword in gene_lower:
            immunogenicity_risk = "high"
            break
    if immunogenicity_risk == "low" and len(sequence) > 3000:
        immunogenicity_risk = "moderate"

    # Expression estimate: proxy by sequence length
    if len(sequence) < 500:
        expression_level_estimate = "low"
    elif len(sequence) < 2000:
        expression_level_estimate = "moderate"
    else:
        expression_level_estimate = "high"

    return TransgeneSafety(
        gene=gene,
        variant_count=variant_count,
        pathogenic_variants=found_pathogenic,
        integration_risk=integration_risk,
        immunogenicity_risk=immunogenicity_risk,
        expression_level_estimate=expression_level_estimate,
    )


# ---------------------------------------------------------------------------
# Base/prime editor modeling
# ---------------------------------------------------------------------------

@dataclass
class EditorResult:
    editor_type: str  # ABE | CBE | PE
    target_base: str
    result_base: str
    edit_window: tuple[int, int]
    bystander_edits: list[dict]
    efficiency_estimate: float


EDITOR_SPECS: dict[str, dict] = {
    "ABE8e": {
        "editor_type": "ABE",
        "target_base": "A",
        "result_base": "G",
        "edit_window": (4, 8),  # positions 4-8 from PAM-distal end (1-indexed)
        "efficiency_range": (0.50, 0.92),
        "bystander_window": (3, 10),
    },
    "BE4max": {
        "editor_type": "CBE",
        "target_base": "C",
        "result_base": "T",
        "edit_window": (4, 8),
        "efficiency_range": (0.40, 0.85),
        "bystander_window": (3, 9),
    },
    "PE2": {
        "editor_type": "PE",
        "target_base": "any",
        "result_base": "user-defined",
        "edit_window": (3, 12),
        "efficiency_range": (0.10, 0.45),
        "bystander_window": (1, 20),
    },
    "PE3": {
        "editor_type": "PE",
        "target_base": "any",
        "result_base": "user-defined",
        "edit_window": (3, 12),
        "efficiency_range": (0.15, 0.55),
        "bystander_window": (1, 20),
    },
}


def model_base_edit(
    target_sequence: str,
    position: int,
    editor: str = "ABE8e",
) -> EditorResult:
    """Model a base edit at a given position in the target sequence.

    position: 1-indexed position within the protospacer.
    Returns the predicted edit outcome and bystander edits within the window.
    """
    specs = EDITOR_SPECS.get(editor, EDITOR_SPECS["ABE8e"])
    seq = target_sequence.upper()
    win_start, win_end = specs["edit_window"]
    bystander_start, bystander_end = specs["bystander_window"]
    target_base = specs["target_base"]
    result_base = specs["result_base"]

    # Efficiency: interpolate based on position within edit window
    eff_min, eff_max = specs["efficiency_range"]
    if win_start <= position <= win_end:
        center = (win_start + win_end) / 2
        closeness = 1.0 - abs(position - center) / max(win_end - win_start, 1)
        efficiency = round(eff_min + closeness * (eff_max - eff_min), 3)
    else:
        efficiency = round(eff_min * 0.3, 3)  # out-of-window: low efficiency

    # Identify bystander edit candidates
    bystander_edits: list[dict] = []
    for i, base in enumerate(seq):
        pos_1idx = i + 1
        if pos_1idx == position:
            continue
        if bystander_start <= pos_1idx <= bystander_end:
            if target_base == "any" or base == target_base:
                bystander_edits.append({
                    "position": pos_1idx,
                    "original_base": base,
                    "edited_base": result_base if target_base != "any" else base,
                    "estimated_frequency": round(efficiency * 0.3, 3),
                })

    # Actual base at position
    actual_base = seq[position - 1] if 0 < position <= len(seq) else "N"

    return EditorResult(
        editor_type=specs["editor_type"],
        target_base=actual_base,
        result_base=result_base if target_base == "any" else (result_base if actual_base == target_base else actual_base),
        edit_window=(win_start, win_end),
        bystander_edits=bystander_edits,
        efficiency_estimate=efficiency,
    )


def model_prime_edit(
    target_sequence: str,
    desired_edit: str,
    pegRNA_length: int = 20,
) -> dict:
    """Stub: Model a prime edit for the given target sequence and desired edit.

    Returns mock pegRNA design and efficiency estimate.
    """
    seq = target_sequence.upper()
    pe_specs = EDITOR_SPECS["PE2"]
    eff_min, eff_max = pe_specs["efficiency_range"]

    # Stub efficiency: penalize long desired edits
    edit_len = len(desired_edit)
    efficiency = round(max(eff_min, eff_max - edit_len * 0.02), 3)

    rng = random.Random(hash(target_sequence + desired_edit) % (2**31))

    return {
        "target_sequence": target_sequence,
        "desired_edit": desired_edit,
        "pegRNA_length": pegRNA_length,
        "spacer": seq[:20] if len(seq) >= 20 else seq,
        "rt_template": desired_edit[:10] if len(desired_edit) >= 10 else desired_edit,
        "pbs_length": rng.randint(10, 17),
        "efficiency_estimate": efficiency,
        "edit_type": (
            "substitution" if len(desired_edit) == 1
            else "insertion" if len(desired_edit) > 1
            else "deletion"
        ),
        "note": "Stub model — pegRNA optimization not performed",
    }
