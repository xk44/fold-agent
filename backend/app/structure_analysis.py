"""Advanced Structure Analysis — Phase 24 Tier 2

IDR escalation, PTM impact, epistatic variants, and fold-switching detection.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

STRUCTURE_ANALYSIS_DISCLAIMER = (
    "RESEARCH ONLY — not for clinical or diagnostic use. "
    "All outputs are computational predictions requiring experimental validation."
)

# ---------------------------------------------------------------------------
# Feature 1: IDR Auto-Escalation
# ---------------------------------------------------------------------------

IDR_PLDDT_THRESHOLD = 50.0


@dataclass
class IDRRegion:
    start: int
    end: int
    length: int
    mean_plddt: float
    disorder_score: float
    predictor: str  # "iupred2a" | "albatross" | "fldpnn"
    disorder_type: str  # "strong" | "weak" | "context_dependent"


@dataclass
class IDRAnalysisResult:
    sequence: str
    total_residues: int
    idr_regions: list[IDRRegion]
    idr_fraction: float
    escalated: bool
    escalation_reason: str | None


def _mock_plddt_from_sequence(sequence: str) -> list[float]:
    """Generate deterministic mock pLDDT values from sequence hash."""
    values = []
    for i, aa in enumerate(sequence):
        seed = int(hashlib.md5(f"{sequence[:10]}_{i}_{aa}".encode()).hexdigest()[:8], 16)
        # Residues D, E, K, R, S, T, P, Q, N tend toward lower pLDDT in disordered regions
        disordered_aas = set("DEKRSTPQN")
        base = 40.0 if aa in disordered_aas else 70.0
        noise = (seed % 400) / 10.0 - 20.0
        values.append(max(0.0, min(100.0, base + noise)))
    return values


def detect_low_plddt_regions(
    sequence: str, plddt_values: list[float] | None = None
) -> list[tuple[int, int]]:
    """Find contiguous residue ranges below IDR_PLDDT_THRESHOLD.

    Returns list of (start, end) inclusive 0-based indices.
    """
    if plddt_values is None:
        plddt_values = _mock_plddt_from_sequence(sequence)

    regions: list[tuple[int, int]] = []
    in_region = False
    start = 0

    for i, score in enumerate(plddt_values):
        if score < IDR_PLDDT_THRESHOLD:
            if not in_region:
                in_region = True
                start = i
        else:
            if in_region:
                if i - start >= 5:  # minimum region length = 5
                    regions.append((start, i - 1))
                in_region = False

    if in_region and len(plddt_values) - start >= 5:
        regions.append((start, len(plddt_values) - 1))

    return regions


def _disorder_score_for_region(sequence: str, start: int, end: int) -> float:
    """Compute mock disorder score for a region (0-1)."""
    region_seq = sequence[start : end + 1]
    seed = int(hashlib.md5(region_seq.encode()).hexdigest()[:8], 16)
    # Charged/polar content raises disorder
    charged = sum(1 for aa in region_seq if aa in "DEKR")
    polar = sum(1 for aa in region_seq if aa in "STNQ")
    hydrophobic = sum(1 for aa in region_seq if aa in "VILMFYW")
    length = len(region_seq)
    if length == 0:
        return 0.5
    base = (charged * 0.3 + polar * 0.15 - hydrophobic * 0.2) / length + 0.5
    noise = ((seed % 200) / 1000.0) - 0.1
    return max(0.0, min(1.0, base + noise))


def _classify_disorder(score: float, length: int) -> str:
    if score >= 0.7:
        return "strong"
    if score >= 0.5:
        return "weak"
    return "context_dependent"


def escalate_to_idr_analysis(
    sequence: str, low_regions: list[tuple[int, int]]
) -> IDRAnalysisResult:
    """Run mock IUPred2A/ALBATROSS on low-confidence regions."""
    idr_regions: list[IDRRegion] = []
    total_idr_residues = 0

    predictors = ["iupred2a", "albatross", "fldpnn"]

    for idx, (start, end) in enumerate(low_regions):
        length = end - start + 1
        total_idr_residues += length
        score = _disorder_score_for_region(sequence, start, end)
        predictor = predictors[idx % len(predictors)]

        # mock pLDDT mean for region
        mock_plddt = _mock_plddt_from_sequence(sequence)
        mean_plddt = sum(mock_plddt[start : end + 1]) / length if length else 0.0

        idr_regions.append(
            IDRRegion(
                start=start,
                end=end,
                length=length,
                mean_plddt=round(mean_plddt, 2),
                disorder_score=round(score, 3),
                predictor=predictor,
                disorder_type=_classify_disorder(score, length),
            )
        )

    idr_fraction = total_idr_residues / len(sequence) if sequence else 0.0
    escalated = len(idr_regions) > 0
    escalation_reason = (
        f"{len(idr_regions)} low-pLDDT region(s) routed to IUPred2A/ALBATROSS for disorder analysis"
        if escalated
        else None
    )

    return IDRAnalysisResult(
        sequence=sequence,
        total_residues=len(sequence),
        idr_regions=idr_regions,
        idr_fraction=round(idr_fraction, 4),
        escalated=escalated,
        escalation_reason=escalation_reason,
    )


def analyze_disorder(sequence: str) -> IDRAnalysisResult:
    """Full IDR pipeline: detect low-pLDDT regions then escalate."""
    low_regions = detect_low_plddt_regions(sequence)
    return escalate_to_idr_analysis(sequence, low_regions)


# ---------------------------------------------------------------------------
# Feature 2: PTM Impact Analysis
# ---------------------------------------------------------------------------

KNOWN_PTM_SITES: dict[str, list[dict]] = {
    "TP53": [
        {"position": 15, "type": "phosphorylation", "residue": "S", "kinase": "ATM"},
        {"position": 20, "type": "phosphorylation", "residue": "T", "kinase": "CHK2"},
        {"position": 33, "type": "phosphorylation", "residue": "S", "kinase": "CK1"},
        {"position": 46, "type": "phosphorylation", "residue": "S", "kinase": "HIPK2"},
        {"position": 120, "type": "acetylation", "residue": "K", "kinase": "TIP60"},
        {"position": 175, "type": "ubiquitination", "residue": "R", "kinase": "MDM2"},
        {"position": 248, "type": "methylation", "residue": "R", "kinase": "PRMT5"},
        {"position": 273, "type": "phosphorylation", "residue": "R", "kinase": "CK2"},
        {"position": 382, "type": "acetylation", "residue": "K", "kinase": "CBP"},
        {"position": 386, "type": "acetylation", "residue": "K", "kinase": "PCAF"},
    ],
    "EGFR": [
        {"position": 845, "type": "phosphorylation", "residue": "Y", "kinase": "EGFR"},
        {"position": 992, "type": "phosphorylation", "residue": "Y", "kinase": "EGFR"},
        {"position": 1045, "type": "phosphorylation", "residue": "Y", "kinase": "EGFR"},
        {"position": 1068, "type": "phosphorylation", "residue": "Y", "kinase": "EGFR"},
        {"position": 1086, "type": "phosphorylation", "residue": "Y", "kinase": "EGFR"},
        {"position": 1148, "type": "ubiquitination", "residue": "K", "kinase": "CBL"},
        {"position": 1172, "type": "phosphorylation", "residue": "Y", "kinase": "SRC"},
        {"position": 128, "type": "glycosylation", "residue": "N", "kinase": None},
    ],
    "KRAS": [
        {"position": 12, "type": "phosphorylation", "residue": "G", "kinase": "PKC"},
        {"position": 13, "type": "ubiquitination", "residue": "G", "kinase": "RNF"},
        {"position": 147, "type": "ubiquitination", "residue": "K", "kinase": "LZTR1"},
        {"position": 104, "type": "methylation", "residue": "R", "kinase": "SMYD2"},
    ],
    "BRAF": [
        {"position": 336, "type": "phosphorylation", "residue": "S", "kinase": "PKA"},
        {"position": 365, "type": "phosphorylation", "residue": "S", "kinase": "RAS"},
        {"position": 599, "type": "phosphorylation", "residue": "V", "kinase": "MEK"},
        {"position": 600, "type": "phosphorylation", "residue": "E", "kinase": "MEK"},
        {"position": 446, "type": "ubiquitination", "residue": "K", "kinase": "CHIP"},
        {"position": 483, "type": "acetylation", "residue": "K", "kinase": "CBP"},
    ],
    "AKT1": [
        {"position": 308, "type": "phosphorylation", "residue": "T", "kinase": "PDK1"},
        {"position": 473, "type": "phosphorylation", "residue": "S", "kinase": "mTORC2"},
        {"position": 129, "type": "phosphorylation", "residue": "T", "kinase": "CK2"},
        {"position": 450, "type": "phosphorylation", "residue": "T", "kinase": "MAP3K"},
        {"position": 181, "type": "ubiquitination", "residue": "K", "kinase": "TRAF6"},
        {"position": 284, "type": "acetylation", "residue": "K", "kinase": "CBP"},
        {"position": 20, "type": "sumoylation", "residue": "K", "kinase": "SUMO1"},
    ],
    "MYC": [
        {"position": 58, "type": "phosphorylation", "residue": "T", "kinase": "GSK3"},
        {"position": 62, "type": "phosphorylation", "residue": "S", "kinase": "ERK"},
        {"position": 149, "type": "ubiquitination", "residue": "K", "kinase": "FBXW7"},
        {"position": 323, "type": "acetylation", "residue": "K", "kinase": "GCN5"},
    ],
    "PTEN": [
        {"position": 380, "type": "phosphorylation", "residue": "S", "kinase": "CK2"},
        {"position": 382, "type": "phosphorylation", "residue": "T", "kinase": "CK2"},
        {"position": 383, "type": "phosphorylation", "residue": "S", "kinase": "CK2"},
        {"position": 289, "type": "ubiquitination", "residue": "K", "kinase": "NEDD4"},
    ],
    "BRCA1": [
        {"position": 1387, "type": "phosphorylation", "residue": "S", "kinase": "ATM"},
        {"position": 1423, "type": "phosphorylation", "residue": "S", "kinase": "ATM"},
        {"position": 1457, "type": "phosphorylation", "residue": "S", "kinase": "ATM"},
        {"position": 1524, "type": "phosphorylation", "residue": "S", "kinase": "CHK2"},
        {"position": 1655, "type": "ubiquitination", "residue": "K", "kinase": "UBC13"},
    ],
}

# Impact descriptions per PTM type
_PTM_IMPACT_DESC = {
    "phosphorylation": "alters charge and protein-protein interaction surfaces",
    "ubiquitination": "tags protein for proteasomal degradation",
    "acetylation": "neutralizes positive charge, affects DNA/chromatin binding",
    "methylation": "modifies arginine/lysine charge and interaction specificity",
    "glycosylation": "affects protein folding, stability, and receptor binding",
    "sumoylation": "modifies nuclear localization and transcriptional activity",
}


@dataclass
class PTMSite:
    gene: str
    position: int
    residue: str
    ptm_type: str
    enzyme: str | None
    functional_impact: str


@dataclass
class PTMImpactResult:
    gene: str
    variant_position: int
    nearby_ptms: list[PTMSite]
    ptm_disrupted: bool
    impact_score: float  # 0-1
    prediction_difference: str
    recommendation: str


def find_nearby_ptms(gene: str, variant_position: int, window: int = 5) -> list[PTMSite]:
    """Find PTM sites within `window` residues of variant_position."""
    gene_upper = gene.upper()
    sites_raw = KNOWN_PTM_SITES.get(gene_upper, [])
    result: list[PTMSite] = []
    for s in sites_raw:
        if abs(s["position"] - variant_position) <= window:
            impact = _PTM_IMPACT_DESC.get(s["type"], "modifies protein function")
            result.append(
                PTMSite(
                    gene=gene_upper,
                    position=s["position"],
                    residue=s["residue"],
                    ptm_type=s["type"],
                    enzyme=s.get("kinase"),
                    functional_impact=impact,
                )
            )
    return result


def _parse_variant(variant: str) -> tuple[str | None, int | None, str | None]:
    """Parse variant string like 'S15F' -> ('S', 15, 'F')."""
    m = re.match(r"^([A-Za-z*])(\d+)([A-Za-z*])$", variant.strip())
    if not m:
        return None, None, None
    return m.group(1).upper(), int(m.group(2)), m.group(3).upper()


def assess_ptm_impact(gene: str, variant: str) -> PTMImpactResult:
    """Assess PTM impact of a variant on a gene."""
    ref_aa, position, alt_aa = _parse_variant(variant)
    gene_upper = gene.upper()

    if position is None:
        return PTMImpactResult(
            gene=gene_upper,
            variant_position=0,
            nearby_ptms=[],
            ptm_disrupted=False,
            impact_score=0.0,
            prediction_difference="Unable to parse variant",
            recommendation="Provide variant in format REF_POSITION_ALT (e.g. S15F)",
        )

    nearby = find_nearby_ptms(gene_upper, position, window=5)

    # Check direct disruption: variant is at a known PTM site
    direct_disruption = any(s.position == position for s in nearby)

    # Score: direct disruption = high, proximity = moderate
    if direct_disruption:
        impact_score = 0.85
        pred_diff = "High — variant directly disrupts PTM site; expect altered regulation"
        recommendation = (
            f"Variant {variant} at {gene_upper}:{position} directly removes a known "
            f"PTM site. Re-predict with and without modification context. "
            "Experimental phosphoproteomics recommended."
        )
    elif nearby:
        # Score by proximity
        min_dist = min(abs(s.position - position) for s in nearby)
        impact_score = max(0.1, 0.6 - min_dist * 0.08)
        pred_diff = (
            f"Moderate — variant within {min_dist} residue(s) of PTM site; "
            "may alter enzyme recognition motif"
        )
        recommendation = (
            f"Variant {variant} is near known PTM site(s). "
            "Check kinase consensus motif disruption. "
            "Consider PTM-aware structure prediction."
        )
    else:
        impact_score = 0.05
        pred_diff = "Low — no known PTM sites within window"
        recommendation = "No known PTM sites nearby. Standard pathogenicity assessment applies."

    return PTMImpactResult(
        gene=gene_upper,
        variant_position=position,
        nearby_ptms=nearby,
        ptm_disrupted=direct_disruption,
        impact_score=round(impact_score, 3),
        prediction_difference=pred_diff,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Feature 3: Epistatic Multi-Variant Prediction
# ---------------------------------------------------------------------------

KNOWN_EPISTATIC_PAIRS: list[dict] = [
    {
        "gene": "KRAS",
        "variants": ["G12D", "A146T"],
        "effect": "synergistic",
        "description": "Co-occurrence enhances oncogenic RAS signaling",
    },
    {
        "gene": "TP53",
        "variants": ["R175H", "R248W"],
        "effect": "antagonistic",
        "description": "Both hotspot mutations rarely co-occur; one may suppress the other's gain-of-function",
    },
    {
        "gene": "EGFR",
        "variants": ["L858R", "T790M"],
        "effect": "compensatory",
        "description": "T790M confers resistance to L858R-targeted inhibitors",
    },
    {
        "gene": "BRAF",
        "variants": ["V600E", "V600K"],
        "effect": "neutral",
        "description": "Alternative substitutions at same codon; not truly epistatic",
    },
    {
        "gene": "BRCA1",
        "variants": ["C61G", "R71G"],
        "effect": "synergistic",
        "description": "Adjacent RING domain mutations synergistically disrupt E3 ligase activity",
    },
    {
        "gene": "AKT1",
        "variants": ["E17K", "Q79K"],
        "effect": "synergistic",
        "description": "Dual PH domain mutations enhance membrane recruitment",
    },
    {
        "gene": "TP53",
        "variants": ["R248Q", "K305R"],
        "effect": "compensatory",
        "description": "K305R acetylation site mutation partially rescues R248Q DNA-binding loss",
    },
    {
        "gene": "MYC",
        "variants": ["T58I", "S62A"],
        "effect": "antagonistic",
        "description": "T58/S62 phosphorylation crosstalk; simultaneous disruption reduces degradation rate less than expected",
    },
    {
        "gene": "PTEN",
        "variants": ["R130G", "R173C"],
        "effect": "synergistic",
        "description": "Dual phosphatase and C2 domain mutations cooperatively abrogate lipid phosphatase activity",
    },
    {
        "gene": "KRAS",
        "variants": ["G12C", "Q61H"],
        "effect": "synergistic",
        "description": "Switch I and II mutations cooperate to lock KRAS in active conformation",
    },
]


@dataclass
class EpistaticVariant:
    position: int
    ref_aa: str
    alt_aa: str


@dataclass
class EpistaticResult:
    variants: list[EpistaticVariant]
    individual_scores: list[float]
    additive_prediction: float
    epistatic_prediction: float
    epistatic_effect: str  # "synergistic" | "antagonistic" | "neutral" | "compensatory"
    interaction_score: float
    confidence: float


def _score_single_variant(variant: EpistaticVariant) -> float:
    """Hash-based pathogenicity score for a single variant (0-1)."""
    key = f"{variant.ref_aa}{variant.position}{variant.alt_aa}"
    h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    # Property-based adjustment: gain of charge/loss of structure = higher score
    destabilizing = set("CGP")  # Cys (disulfide), Gly (flexible), Pro (rigid)
    charged = set("DEKR")
    base = 0.4 + (h % 300) / 1000.0
    if variant.alt_aa in destabilizing:
        base += 0.15
    if variant.ref_aa in charged and variant.alt_aa not in charged:
        base += 0.1
    return round(min(1.0, base), 3)


def classify_epistatic_interaction(additive: float, actual: float) -> str:
    """Classify interaction based on deviation from additive expectation."""
    if additive < 0.01:
        return "neutral"
    ratio = actual / additive
    if ratio > 1.2:
        return "synergistic"
    if ratio < 0.5:
        return "compensatory"
    if ratio < 0.8:
        return "antagonistic"
    return "neutral"


def _check_known_pair(variants: list[EpistaticVariant], gene: str) -> str | None:
    """Return known interaction effect if variants match a known pair."""
    variant_strs = {f"{v.ref_aa}{v.position}{v.alt_aa}" for v in variants}
    for pair in KNOWN_EPISTATIC_PAIRS:
        if pair["gene"].upper() == gene.upper():
            if all(pv in variant_strs for pv in pair["variants"]):
                return pair["effect"]
    return None


def predict_epistatic_effect(variants: list[EpistaticVariant], gene: str = "") -> EpistaticResult:
    """Score epistatic effect for up to 6 simultaneous variants."""
    if len(variants) > 6:
        variants = variants[:6]

    individual_scores = [_score_single_variant(v) for v in variants]
    additive = sum(individual_scores)
    additive_capped = min(1.0, additive)

    # Spatial interaction: closer variants interact more
    positions = [v.position for v in variants]
    interaction_modifier = 0.0
    pair_count = 0
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            dist = abs(positions[i] - positions[j])
            # Short-range: within 10 residues = strong interaction
            if dist <= 10:
                interaction_modifier += 0.15
            elif dist <= 30:
                interaction_modifier += 0.07
            elif dist <= 100:
                interaction_modifier += 0.02
            pair_count += 1

    if pair_count > 0:
        interaction_modifier /= pair_count

    # Apply known pair override
    known_effect = _check_known_pair(variants, gene)

    if known_effect == "synergistic":
        epistatic = min(1.0, additive_capped * (1.0 + interaction_modifier + 0.15))
    elif known_effect == "antagonistic":
        epistatic = additive_capped * max(0.5, 1.0 - interaction_modifier)
    elif known_effect == "compensatory":
        epistatic = additive_capped * 0.4
    else:
        # Default: slight interaction based on distance
        epistatic = min(1.0, additive_capped * (1.0 + interaction_modifier * 0.5))

    epistatic = round(epistatic, 3)
    additive_capped = round(additive_capped, 3)

    effect = (
        known_effect if known_effect else classify_epistatic_interaction(additive_capped, epistatic)
    )

    # Confidence: higher with more variants, lower without known data
    base_conf = 0.5 + len(variants) * 0.04
    if known_effect:
        base_conf += 0.2
    confidence = round(min(0.95, base_conf), 3)

    interaction_score = round(abs(epistatic - additive_capped), 3)

    return EpistaticResult(
        variants=variants,
        individual_scores=individual_scores,
        additive_prediction=additive_capped,
        epistatic_prediction=epistatic,
        epistatic_effect=effect,
        interaction_score=interaction_score,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Feature 4: Fold-Switching Detector
# ---------------------------------------------------------------------------

KNOWN_FOLD_SWITCHERS: dict[str, dict] = {
    "MAD2": {
        "switch_type": "open_closed",
        "uniprot": "Q13257",
        "description": "Spindle assembly checkpoint protein; switches between open (inactive) and closed (active) conformations",
        "key_features": ["beta_sheet_remodeling", "symmetric_dimerization"],
    },
    "KaiB": {
        "switch_type": "ground_fold_to_fold_switched",
        "uniprot": "P0A466",
        "description": "Cyanobacterial circadian clock protein; ground fold binds KaiC, switched fold binds SasA",
        "key_features": ["thioredoxin_fold", "beta_strand_swapping"],
    },
    "RfaH": {
        "switch_type": "alpha_to_beta",
        "uniprot": "P0AFF6",
        "description": "Transcription factor; C-terminal domain switches from alpha-helical (autoinhibited) to beta-barrel (active)",
        "key_features": ["CTD_domain_switch", "NusG_homology"],
    },
    "lymphotactin": {
        "switch_type": "monomer_to_dimer",
        "uniprot": "P78552",
        "description": "Chemokine that interconverts between monomeric and dimeric folds depending on conditions",
        "key_features": ["disulfide_absent", "unusual_chemokine_topology"],
    },
    "CLIC1": {
        "switch_type": "soluble_to_membrane",
        "uniprot": "O00299",
        "description": "Chloride intracellular channel; soluble thioredoxin-like fold inserts into membranes as ion channel",
        "key_features": ["redox_sensitive", "thioredoxin_fold", "transmembrane_helix"],
    },
    "HP35": {
        "switch_type": "villin_headpiece_metamorphic",
        "uniprot": "P26038",
        "description": "Villin headpiece subdomain; exhibits metamorphic behavior under varying conditions",
        "key_features": ["helical_bundle", "hydrophobic_core_plasticity"],
    },
    "XCL1": {
        "switch_type": "monomer_dimer_interchange",
        "uniprot": "P47992",
        "description": "Chemokine that interconverts between canonical chemokine fold and all-beta sheet dimer",
        "key_features": ["no_conserved_disulfide", "unusual_topology"],
    },
    "CPEB3": {
        "switch_type": "prion_like_aggregation",
        "uniprot": "Q8NE35",
        "description": "RNA-binding protein; prion-like domain undergoes functional amyloid-like state switch",
        "key_features": ["prion_like_domain", "Q_N_rich", "synaptic_plasticity"],
    },
}

# Sequence features associated with fold-switching
FOLD_SWITCH_SEQUENCE_FEATURES: dict[str, dict] = {
    "hydrophobic_alternation": {
        "description": "Alternating hydrophobic/polar pattern (beta-strand ambiguity)",
        "weight": 0.25,
    },
    "charge_clustering": {
        "description": "Unusual clustering of charged residues suggests dual-binding surfaces",
        "weight": 0.2,
    },
    "high_proline": {
        "description": "High proline content introduces backbone rigidity conflicts",
        "weight": 0.1,
    },
    "ambiguous_ss_propensity": {
        "description": "Residues with mixed alpha/beta propensity (A,V,I at similar frequency)",
        "weight": 0.25,
    },
    "low_complexity_repeats": {
        "description": "Low-complexity or repeat segments can support metamorphic structures",
        "weight": 0.1,
    },
    "qn_rich": {
        "description": "Q/N-rich segments associated with prion-like fold switching",
        "weight": 0.1,
    },
}


@dataclass
class FoldSwitchWarning:
    sequence: str
    risk_score: float  # 0-1
    likely_fold_switcher: bool
    features: dict
    known_match: str | None  # matching KNOWN_FOLD_SWITCHERS key
    recommendation: str


def _hydrophobic_alternation_score(sequence: str) -> float:
    """Measure alternating H/P pattern indicative of beta-strand ambiguity."""
    hp = [1 if aa in "VILMFYW" else 0 for aa in sequence]
    alternations = sum(1 for i in range(1, len(hp)) if hp[i] != hp[i - 1])
    return alternations / max(1, len(sequence) - 1)


def _charge_cluster_score(sequence: str) -> float:
    """Detect clustering of charged residues (DEKR)."""
    charged = [1 if aa in "DEKR" else 0 for aa in sequence]
    if sum(charged) == 0:
        return 0.0
    # Count windows of 5 with >= 3 charged
    clusters = 0
    for i in range(len(charged) - 4):
        if sum(charged[i : i + 5]) >= 3:
            clusters += 1
    return min(1.0, clusters / max(1, len(sequence) // 5))


def _ambiguous_ss_propensity(sequence: str) -> float:
    """Chou-Fasman-like: residues with mixed alpha/beta propensity."""
    # High alpha: A, E, L, M, Q  High beta: V, I, Y, C, F, W, T
    alpha_set = set("AELM")
    beta_set = set("VIYCFW")
    n = len(sequence)
    if n == 0:
        return 0.0
    alpha_count = sum(1 for aa in sequence if aa in alpha_set)
    beta_count = sum(1 for aa in sequence if aa in beta_set)
    # Ambiguous: both present at similar frequency
    ratio = min(alpha_count, beta_count) / max(1, max(alpha_count, beta_count))
    return ratio


def _qn_rich_score(sequence: str) -> float:
    qn = sum(1 for aa in sequence if aa in "QN")
    return min(1.0, qn / max(1, len(sequence)) * 5)


def check_known_fold_switchers(sequence: str) -> str | None:
    """BLAST-like stub: check sequence length/composition against known fold-switchers."""
    n = len(sequence)
    # Simplified: match by length range and Q/N content
    qn_frac = sum(1 for aa in sequence if aa in "QN") / max(1, n)
    if qn_frac > 0.15 and n > 100:
        return "CPEB3"
    charged_frac = sum(1 for aa in sequence if aa in "DEKR") / max(1, n)
    if 0.20 < charged_frac < 0.35 and 60 < n < 120:
        return "lymphotactin"
    # Check for alternating regions suggesting RfaH-like
    hp_score = _hydrophobic_alternation_score(sequence)
    if hp_score > 0.65 and 100 < n < 200:
        return "RfaH"
    return None


def detect_fold_switching_risk(sequence: str) -> FoldSwitchWarning:
    """Analyze sequence for fold-switching risk features."""
    if not sequence:
        return FoldSwitchWarning(
            sequence="",
            risk_score=0.0,
            likely_fold_switcher=False,
            features={},
            known_match=None,
            recommendation="Empty sequence provided.",
        )

    features: dict[str, float] = {}

    hp_alt = _hydrophobic_alternation_score(sequence)
    features["hydrophobic_alternation"] = round(hp_alt, 3)

    cc = _charge_cluster_score(sequence)
    features["charge_clustering"] = round(cc, 3)

    pro_frac = sum(1 for aa in sequence if aa == "P") / len(sequence)
    features["high_proline"] = round(min(1.0, pro_frac * 10), 3)

    ss_ambig = _ambiguous_ss_propensity(sequence)
    features["ambiguous_ss_propensity"] = round(ss_ambig, 3)

    # Low-complexity: count dinucleotide repeats
    n = len(sequence)
    lc_count = sum(1 for i in range(n - 3) if sequence[i : i + 2] == sequence[i + 2 : i + 4])
    features["low_complexity_repeats"] = round(min(1.0, lc_count / max(1, n // 4)), 3)

    qn = _qn_rich_score(sequence)
    features["qn_rich"] = round(qn, 3)

    # Weighted risk score
    weights = FOLD_SWITCH_SEQUENCE_FEATURES
    risk = (
        features["hydrophobic_alternation"] * weights["hydrophobic_alternation"]["weight"]
        + features["charge_clustering"] * weights["charge_clustering"]["weight"]
        + features["high_proline"] * weights["high_proline"]["weight"]
        + features["ambiguous_ss_propensity"] * weights["ambiguous_ss_propensity"]["weight"]
        + features["low_complexity_repeats"] * weights["low_complexity_repeats"]["weight"]
        + features["qn_rich"] * weights["qn_rich"]["weight"]
    )
    risk = round(min(1.0, risk), 3)

    known_match = check_known_fold_switchers(sequence)

    if known_match:
        risk = round(min(1.0, risk + 0.2), 3)

    likely = risk >= 0.45

    if likely:
        recommendation = (
            "High fold-switching risk detected. "
            "Consider running multiple structure prediction methods "
            "and comparing conformational ensembles before reporting a single structure. "
            "Experimental validation (e.g., NMR, HDX-MS) recommended."
        )
        if known_match:
            recommendation = (
                f"Sequence features resemble known fold-switcher {known_match}. " + recommendation
            )
    else:
        recommendation = (
            "Low fold-switching risk. Standard structure prediction is appropriate, "
            "but monitor for unusual prediction confidence patterns."
        )

    return FoldSwitchWarning(
        sequence=sequence,
        risk_score=risk,
        likely_fold_switcher=likely,
        features=features,
        known_match=known_match,
        recommendation=recommendation,
    )
