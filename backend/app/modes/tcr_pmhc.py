"""TCR-pMHC Ternary Complex Modeling Mode — T-Cell Receptor / Peptide-MHC Analysis.

RESEARCH USE ONLY — Not for clinical or diagnostic use.

Provides:
  - TCR–peptide–MHC ternary complex modeling (AF3 stub)
  - T-cell response likelihood scoring based on TCR binding geometry
  - CDR loop analysis for TCR binding interface characterization
  - Multi-seed sampling for TCR–pMHC reliability (100+ seeds)
  - Immunogenicity prediction combining binding + TCR modeling
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------

TCR_PMHC_DISCLAIMER = (
    "RESEARCH USE ONLY — TCR-pMHC ternary complex predictions are computational "
    "stubs for research purposes. Results do not constitute clinical, diagnostic, "
    "or therapeutic advice. Structural coordinates are mock PDB data."
)

# ---------------------------------------------------------------------------
# Known TCR-pMHC complexes knowledge base
# ---------------------------------------------------------------------------

KNOWN_TCR_PMHC: dict[str, dict] = {
    "SLLMWITQC": {
        "peptide": "SLLMWITQC",
        "antigen": "NY-ESO-1",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV5",
        "tcr_vb": "TRBV6-5",
        "binding_affinity_nm": 2.4,
        "crystal_pdb_id": "2BNR",
        "t_cell_type": "CD8+",
        "cancer_association": "melanoma, lung, breast",
    },
    "ELAGIGILTV": {
        "peptide": "ELAGIGILTV",
        "antigen": "MART-1/Melan-A",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV12-2",
        "tcr_vb": "TRBV6-1",
        "binding_affinity_nm": 1.8,
        "crystal_pdb_id": "2P5E",
        "t_cell_type": "CD8+",
        "cancer_association": "melanoma",
    },
    "NLVPMVATV": {
        "peptide": "NLVPMVATV",
        "antigen": "CMV pp65",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV27",
        "tcr_vb": "TRBV20-1",
        "binding_affinity_nm": 3.1,
        "crystal_pdb_id": "3GSN",
        "t_cell_type": "CD8+",
        "cancer_association": "viral_infection",
    },
    "RMFPNAPYL": {
        "peptide": "RMFPNAPYL",
        "antigen": "WT1",
        "mhc_allele": "HLA-A*24:02",
        "tcr_va": "TRAV38-2",
        "tcr_vb": "TRBV7-2",
        "binding_affinity_nm": 5.6,
        "crystal_pdb_id": "3HPJ",
        "t_cell_type": "CD8+",
        "cancer_association": "AML, CML",
    },
    "GILGFVFTL": {
        "peptide": "GILGFVFTL",
        "antigen": "Influenza M1",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV27",
        "tcr_vb": "TRBV19",
        "binding_affinity_nm": 2.9,
        "crystal_pdb_id": "1OGA",
        "t_cell_type": "CD8+",
        "cancer_association": "none",
    },
    "KLVALGINAV": {
        "peptide": "KLVALGINAV",
        "antigen": "HIV Gag",
        "mhc_allele": "HLA-B*57:01",
        "tcr_va": "TRAV12-1",
        "tcr_vb": "TRBV29-1",
        "binding_affinity_nm": 4.2,
        "crystal_pdb_id": "5C0A",
        "t_cell_type": "CD8+",
        "cancer_association": "none",
    },
    "RAKFKQLL": {
        "peptide": "RAKFKQLL",
        "antigen": "EBV BZLF1",
        "mhc_allele": "HLA-B*08:01",
        "tcr_va": "TRAV5",
        "tcr_vb": "TRBV5-1",
        "binding_affinity_nm": 6.8,
        "crystal_pdb_id": "2AK4",
        "t_cell_type": "CD8+",
        "cancer_association": "lymphoma",
    },
    "LLFGYPVYV": {
        "peptide": "LLFGYPVYV",
        "antigen": "HTLV-1 Tax",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV12-2",
        "tcr_vb": "TRBV12-3",
        "binding_affinity_nm": 1.3,
        "crystal_pdb_id": "1AO7",
        "t_cell_type": "CD8+",
        "cancer_association": "T-cell lymphoma",
    },
    "GLCTLVAML": {
        "peptide": "GLCTLVAML",
        "antigen": "EBV BMLF1",
        "mhc_allele": "HLA-A*02:01",
        "tcr_va": "TRAV5",
        "tcr_vb": "TRBV20-1",
        "binding_affinity_nm": 3.7,
        "crystal_pdb_id": "3MRE",
        "t_cell_type": "CD8+",
        "cancer_association": "none",
    },
    "SIINFEKL": {
        "peptide": "SIINFEKL",
        "antigen": "OVA (model antigen)",
        "mhc_allele": "H-2Kb",
        "tcr_va": "TRAV14",
        "tcr_vb": "TRBV19",
        "binding_affinity_nm": 0.9,
        "crystal_pdb_id": "1G6R",
        "t_cell_type": "CD8+",
        "cancer_association": "model_system",
    },
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TernaryComplexResult:
    peptide: str
    mhc_allele: str
    tcr_sequence: str
    mock_pdb_id: str
    confidence_score: float
    interface_contacts: list[dict]
    binding_mode: str
    predicted_kd_nm: float
    mhc_peptide_groove_score: float
    tcr_docking_angle_deg: float
    disclaimer: str = field(default=TCR_PMHC_DISCLAIMER)


@dataclass
class TCellResponseScore:
    peptide: str
    mhc_allele: str
    binding_geometry_score: float
    predicted_activation: str
    cytokine_profile: dict[str, float]
    effector_function: str
    activation_threshold_nm: float
    stimulation_index: float


@dataclass
class CDRLoopAnalysis:
    tcr_sequence: str
    cdr1_alpha_positions: list[int]
    cdr2_alpha_positions: list[int]
    cdr3_alpha_positions: list[int]
    cdr1_beta_positions: list[int]
    cdr2_beta_positions: list[int]
    cdr3_beta_positions: list[int]
    cdr1_alpha_length: int
    cdr2_alpha_length: int
    cdr3_alpha_length: int
    cdr1_beta_length: int
    cdr2_beta_length: int
    cdr3_beta_length: int
    germline_deviation_cdr3_alpha: float
    germline_deviation_cdr3_beta: float
    dominant_contact_loop: str


@dataclass
class MultiSeedResult:
    peptide: str
    mhc_allele: str
    tcr_sequence: str
    n_seeds: int
    per_seed_scores: list[float]
    mean_score: float
    std_score: float
    confidence_interval_95: tuple[float, float]
    convergence_metric: float
    top_seed_index: int
    reproducibility_score: float


@dataclass
class ImmunogenicityPrediction:
    peptide: str
    mhc_allele: str
    tcr_sequence: str
    immunogenicity_score: float
    mhc_binding_component: float
    tcr_recognition_component: float
    t_cell_response_component: float
    predicted_response_class: str
    confidence: float
    contributing_factors: list[str]


# ---------------------------------------------------------------------------
# Helper: deterministic scoring from sequence content
# ---------------------------------------------------------------------------


def _seq_hash_score(s: str, lo: float = 0.0, hi: float = 1.0) -> float:
    """Map a string to a deterministic float in [lo, hi] using hash."""
    h = abs(hash(s))
    return lo + (h % 10000) / 10000.0 * (hi - lo)


def _seq_hash_int(s: str, lo: int, hi: int) -> int:
    h = abs(hash(s))
    return lo + h % (hi - lo + 1)


# ---------------------------------------------------------------------------
# predict_ternary_complex
# ---------------------------------------------------------------------------


def predict_ternary_complex(
    peptide: str,
    mhc_allele: str,
    tcr_sequence: str,
    options: dict | None = None,
) -> TernaryComplexResult:
    """Model TCR–peptide–MHC ternary complex (AF3 stub).

    Returns deterministic mock structural data based on sequence content.
    """
    opts = options or {}
    key = f"{peptide}:{mhc_allele}:{tcr_sequence}"

    # Check for known complex
    known = KNOWN_TCR_PMHC.get(peptide)
    if known and known["mhc_allele"] == mhc_allele:
        kd = known["binding_affinity_nm"]
        pdb_id = known["crystal_pdb_id"]
        confidence = _seq_hash_score(key + "conf", 0.72, 0.95)
    else:
        kd = _seq_hash_score(key + "kd", 0.5, 50.0)
        pdb_id = f"MODEL_{abs(hash(key)) % 90000 + 10000}"
        confidence = _seq_hash_score(key + "conf", 0.35, 0.88)

    # Build interface contacts deterministically
    pep_len = len(peptide)
    contacts = []
    n_contacts = _seq_hash_int(key, 4, 14)
    for i in range(n_contacts):
        pep_pos = (abs(hash(key + str(i))) % pep_len) + 1
        tcr_pos = (abs(hash(key + str(i) + "tcr")) % 30) + 90
        contacts.append(
            {
                "peptide_residue": pep_pos,
                "peptide_aa": peptide[pep_pos - 1],
                "tcr_residue": tcr_pos,
                "contact_type": ["hydrogen_bond", "van_der_waals", "hydrophobic", "salt_bridge"][
                    abs(hash(key + str(i))) % 4
                ],
                "distance_angstrom": round(2.8 + _seq_hash_score(key + str(i), 0.0, 2.2), 2),
            }
        )

    groove_score = _seq_hash_score(key + "groove", 0.4, 1.0)
    docking_angle = round(_seq_hash_score(key + "angle", 10.0, 50.0), 1)
    binding_modes = ["canonical_diagonal", "tilted", "reverse_tilted", "orthogonal"]
    bmode = binding_modes[abs(hash(key)) % 4]

    return TernaryComplexResult(
        peptide=peptide,
        mhc_allele=mhc_allele,
        tcr_sequence=tcr_sequence,
        mock_pdb_id=pdb_id,
        confidence_score=round(confidence, 4),
        interface_contacts=contacts,
        binding_mode=bmode,
        predicted_kd_nm=round(kd, 3),
        mhc_peptide_groove_score=round(groove_score, 4),
        tcr_docking_angle_deg=docking_angle,
    )


# ---------------------------------------------------------------------------
# score_tcell_response
# ---------------------------------------------------------------------------


def score_tcell_response(complex_result: TernaryComplexResult) -> TCellResponseScore:
    """Score T-cell response likelihood from ternary complex geometry."""
    key = f"{complex_result.peptide}:{complex_result.mhc_allele}:{complex_result.tcr_sequence}"

    geom = _seq_hash_score(key + "geom", 0.1, 1.0)
    # Weight by confidence and groove score
    geom = round(
        geom * 0.5
        + complex_result.confidence_score * 0.3
        + complex_result.mhc_peptide_groove_score * 0.2,
        4,
    )

    if geom >= 0.75:
        activation = "strong"
    elif geom >= 0.5:
        activation = "moderate"
    elif geom >= 0.3:
        activation = "weak"
    else:
        activation = "no_response"

    cytokines = {
        "IFN-gamma": round(_seq_hash_score(key + "ifng", 0.0, 1.0) * geom, 4),
        "IL-2": round(_seq_hash_score(key + "il2", 0.0, 0.8) * geom, 4),
        "TNF-alpha": round(_seq_hash_score(key + "tnfa", 0.0, 0.9) * geom, 4),
        "IL-4": round(_seq_hash_score(key + "il4", 0.0, 0.4) * (1 - geom), 4),
        "granzyme_B": round(_seq_hash_score(key + "gzmb", 0.0, 0.9) * geom, 4),
    }

    effectors = ["cytotoxic_killing", "cytokine_secretion", "proliferation", "anergy"]
    effector = effectors[abs(hash(key + "eff")) % 4] if geom > 0.3 else "anergy"

    threshold = round(_seq_hash_score(key + "thresh", 0.5, 20.0), 2)
    stim_index = round(geom * _seq_hash_score(key + "si", 1.0, 10.0), 3)

    return TCellResponseScore(
        peptide=complex_result.peptide,
        mhc_allele=complex_result.mhc_allele,
        binding_geometry_score=geom,
        predicted_activation=activation,
        cytokine_profile=cytokines,
        effector_function=effector,
        activation_threshold_nm=threshold,
        stimulation_index=stim_index,
    )


# ---------------------------------------------------------------------------
# analyze_cdr_loops
# ---------------------------------------------------------------------------


def analyze_cdr_loops(tcr_sequence: str) -> CDRLoopAnalysis:
    """Analyze CDR loop positions and characteristics for a TCR sequence."""
    s = tcr_sequence.upper()
    n = len(s)

    # Deterministic CDR positions based on sequence hash
    # Alpha chain CDRs (typical positions in full TCR alpha)
    base_a = abs(hash(s + "alpha")) % max(n - 40, 1)
    cdr1a_start = (base_a % max(n - 10, 1)) + 1
    cdr1a_len = _seq_hash_int(s + "c1alen", 5, 9)
    cdr1a = list(range(cdr1a_start, cdr1a_start + cdr1a_len))

    cdr2a_start = cdr1a_start + cdr1a_len + _seq_hash_int(s + "gap1a", 8, 14)
    cdr2a_len = _seq_hash_int(s + "c2alen", 4, 8)
    cdr2a = list(range(cdr2a_start, cdr2a_start + cdr2a_len))

    cdr3a_start = cdr2a_start + cdr2a_len + _seq_hash_int(s + "gap2a", 18, 30)
    cdr3a_len = _seq_hash_int(s + "c3alen", 10, 18)
    cdr3a = list(range(cdr3a_start, cdr3a_start + cdr3a_len))

    # Beta chain CDRs
    base_b = abs(hash(s + "beta")) % max(n - 40, 1)
    cdr1b_start = (base_b % max(n - 10, 1)) + 1
    cdr1b_len = _seq_hash_int(s + "c1blen", 5, 9)
    cdr1b = list(range(cdr1b_start, cdr1b_start + cdr1b_len))

    cdr2b_start = cdr1b_start + cdr1b_len + _seq_hash_int(s + "gap1b", 8, 14)
    cdr2b_len = _seq_hash_int(s + "c2blen", 4, 7)
    cdr2b = list(range(cdr2b_start, cdr2b_start + cdr2b_len))

    cdr3b_start = cdr2b_start + cdr2b_len + _seq_hash_int(s + "gap2b", 18, 30)
    cdr3b_len = _seq_hash_int(s + "c3blen", 10, 20)
    cdr3b = list(range(cdr3b_start, cdr3b_start + cdr3b_len))

    dev_a = round(_seq_hash_score(s + "deva", 0.0, 0.45), 4)
    dev_b = round(_seq_hash_score(s + "devb", 0.0, 0.45), 4)

    # Longest CDR3 typically dominates
    dominant = "CDR3_beta" if cdr3b_len >= cdr3a_len else "CDR3_alpha"

    return CDRLoopAnalysis(
        tcr_sequence=tcr_sequence,
        cdr1_alpha_positions=cdr1a,
        cdr2_alpha_positions=cdr2a,
        cdr3_alpha_positions=cdr3a,
        cdr1_beta_positions=cdr1b,
        cdr2_beta_positions=cdr2b,
        cdr3_beta_positions=cdr3b,
        cdr1_alpha_length=cdr1a_len,
        cdr2_alpha_length=cdr2a_len,
        cdr3_alpha_length=cdr3a_len,
        cdr1_beta_length=cdr1b_len,
        cdr2_beta_length=cdr2b_len,
        cdr3_beta_length=cdr3b_len,
        germline_deviation_cdr3_alpha=dev_a,
        germline_deviation_cdr3_beta=dev_b,
        dominant_contact_loop=dominant,
    )


# ---------------------------------------------------------------------------
# run_multiseed_sampling
# ---------------------------------------------------------------------------


def run_multiseed_sampling(
    peptide: str,
    mhc_allele: str,
    tcr_sequence: str,
    n_seeds: int = 100,
) -> MultiSeedResult:
    """Run multi-seed TCR-pMHC sampling for reliability assessment.

    Uses deterministic pseudo-random scores derived from seed + sequence hash.
    """
    base_key = f"{peptide}:{mhc_allele}:{tcr_sequence}"
    base_score = _seq_hash_score(base_key, 0.3, 0.9)

    # Generate per-seed scores deterministically
    scores: list[float] = []
    for i in range(n_seeds):
        seed_key = base_key + f":seed{i}"
        noise = _seq_hash_score(seed_key, -0.12, 0.12)
        s = max(0.0, min(1.0, base_score + noise))
        scores.append(round(s, 5))

    mean_s = round(sum(scores) / len(scores), 6)
    variance = sum((x - mean_s) ** 2 for x in scores) / len(scores)
    std_s = round(variance**0.5, 6)

    # 95% CI approximation
    margin = round(1.96 * std_s / (n_seeds**0.5), 6)
    ci = (round(max(0.0, mean_s - margin), 6), round(min(1.0, mean_s + margin), 6))

    # Convergence: coefficient of variation (lower = better converged)
    cv = round(std_s / mean_s if mean_s > 0 else 1.0, 6)
    convergence = round(max(0.0, 1.0 - cv), 6)

    top_idx = scores.index(max(scores))
    repro = round(_seq_hash_score(base_key + "repro", 0.6, 1.0) * convergence, 4)

    return MultiSeedResult(
        peptide=peptide,
        mhc_allele=mhc_allele,
        tcr_sequence=tcr_sequence,
        n_seeds=n_seeds,
        per_seed_scores=scores,
        mean_score=mean_s,
        std_score=std_s,
        confidence_interval_95=ci,
        convergence_metric=convergence,
        top_seed_index=top_idx,
        reproducibility_score=repro,
    )


# ---------------------------------------------------------------------------
# predict_immunogenicity
# ---------------------------------------------------------------------------


def predict_immunogenicity(
    peptide: str,
    mhc_allele: str,
    tcr_sequence: str,
) -> ImmunogenicityPrediction:
    """Combined immunogenicity prediction from binding + TCR + response modeling."""
    complex_result = predict_ternary_complex(peptide, mhc_allele, tcr_sequence)
    tcell_score = score_tcell_response(complex_result)
    multiseed = run_multiseed_sampling(peptide, mhc_allele, tcr_sequence, n_seeds=100)

    # Normalize kd component (lower kd = higher binding component)
    max_kd = 50.0
    mhc_component = round(max(0.0, min(1.0, 1.0 - complex_result.predicted_kd_nm / max_kd)), 4)
    tcr_component = round(complex_result.confidence_score, 4)
    response_component = round(tcell_score.binding_geometry_score, 4)

    # Weighted combination
    immuno_score = round(
        mhc_component * 0.35
        + tcr_component * 0.30
        + response_component * 0.25
        + multiseed.convergence_metric * 0.10,
        4,
    )
    immuno_score = max(0.0, min(1.0, immuno_score))

    if immuno_score >= 0.7:
        resp_class = "high_immunogenicity"
    elif immuno_score >= 0.45:
        resp_class = "moderate_immunogenicity"
    elif immuno_score >= 0.2:
        resp_class = "low_immunogenicity"
    else:
        resp_class = "non_immunogenic"

    confidence = round((complex_result.confidence_score + multiseed.reproducibility_score) / 2, 4)

    factors: list[str] = []
    if mhc_component > 0.7:
        factors.append("strong_MHC_groove_binding")
    if tcr_component > 0.7:
        factors.append("high_TCR_docking_confidence")
    if response_component > 0.6:
        factors.append("favorable_binding_geometry")
    if multiseed.convergence_metric > 0.8:
        factors.append("high_sampling_convergence")
    if tcell_score.predicted_activation in ("strong", "moderate"):
        factors.append(f"predicted_{tcell_score.predicted_activation}_T_cell_activation")
    if not factors:
        factors.append("insufficient_binding_signal")

    return ImmunogenicityPrediction(
        peptide=peptide,
        mhc_allele=mhc_allele,
        tcr_sequence=tcr_sequence,
        immunogenicity_score=immuno_score,
        mhc_binding_component=mhc_component,
        tcr_recognition_component=tcr_component,
        t_cell_response_component=response_component,
        predicted_response_class=resp_class,
        confidence=confidence,
        contributing_factors=factors,
    )


# ---------------------------------------------------------------------------
# Knowledge base accessors
# ---------------------------------------------------------------------------


def get_known_tcr_pmhc_complexes() -> dict[str, dict]:
    """Return the full KNOWN_TCR_PMHC knowledge base."""
    return KNOWN_TCR_PMHC


def lookup_tcr_pmhc(peptide: str) -> dict | None:
    """Look up a known TCR-pMHC complex by peptide sequence."""
    return KNOWN_TCR_PMHC.get(peptide.upper()) or KNOWN_TCR_PMHC.get(peptide)


# ---------------------------------------------------------------------------
# build_immunogenicity_report
# ---------------------------------------------------------------------------


def build_immunogenicity_report(
    peptide: str,
    mhc_allele: str,
    tcr_sequence: str,
) -> dict:
    """Build comprehensive immunogenicity report combining all sub-analyses."""
    complex_result = predict_ternary_complex(peptide, mhc_allele, tcr_sequence)
    tcell_score = score_tcell_response(complex_result)
    cdr_analysis = analyze_cdr_loops(tcr_sequence)
    multiseed = run_multiseed_sampling(peptide, mhc_allele, tcr_sequence, n_seeds=100)
    immunogenicity = predict_immunogenicity(peptide, mhc_allele, tcr_sequence)
    known = lookup_tcr_pmhc(peptide)

    return {
        "disclaimer": TCR_PMHC_DISCLAIMER,
        "input": {
            "peptide": peptide,
            "mhc_allele": mhc_allele,
            "tcr_sequence": tcr_sequence,
        },
        "known_complex": known,
        "ternary_complex": {
            "mock_pdb_id": complex_result.mock_pdb_id,
            "confidence_score": complex_result.confidence_score,
            "binding_mode": complex_result.binding_mode,
            "predicted_kd_nm": complex_result.predicted_kd_nm,
            "mhc_peptide_groove_score": complex_result.mhc_peptide_groove_score,
            "tcr_docking_angle_deg": complex_result.tcr_docking_angle_deg,
            "interface_contact_count": len(complex_result.interface_contacts),
            "interface_contacts": complex_result.interface_contacts,
        },
        "tcell_response": {
            "binding_geometry_score": tcell_score.binding_geometry_score,
            "predicted_activation": tcell_score.predicted_activation,
            "cytokine_profile": tcell_score.cytokine_profile,
            "effector_function": tcell_score.effector_function,
            "activation_threshold_nm": tcell_score.activation_threshold_nm,
            "stimulation_index": tcell_score.stimulation_index,
        },
        "cdr_loops": {
            "cdr3_alpha_length": cdr_analysis.cdr3_alpha_length,
            "cdr3_beta_length": cdr_analysis.cdr3_beta_length,
            "germline_deviation_cdr3_alpha": cdr_analysis.germline_deviation_cdr3_alpha,
            "germline_deviation_cdr3_beta": cdr_analysis.germline_deviation_cdr3_beta,
            "dominant_contact_loop": cdr_analysis.dominant_contact_loop,
        },
        "multiseed_sampling": {
            "n_seeds": multiseed.n_seeds,
            "mean_score": multiseed.mean_score,
            "std_score": multiseed.std_score,
            "confidence_interval_95": list(multiseed.confidence_interval_95),
            "convergence_metric": multiseed.convergence_metric,
            "reproducibility_score": multiseed.reproducibility_score,
        },
        "immunogenicity": {
            "immunogenicity_score": immunogenicity.immunogenicity_score,
            "mhc_binding_component": immunogenicity.mhc_binding_component,
            "tcr_recognition_component": immunogenicity.tcr_recognition_component,
            "t_cell_response_component": immunogenicity.t_cell_response_component,
            "predicted_response_class": immunogenicity.predicted_response_class,
            "confidence": immunogenicity.confidence,
            "contributing_factors": immunogenicity.contributing_factors,
        },
    }
