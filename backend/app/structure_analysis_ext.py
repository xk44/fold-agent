"""Advanced Structure Analysis Extensions — Phase 24 Tier 2

MSA-driven conformational ensembles, dynamics annotation, confidence calibration.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from enum import Enum


# ===========================================================================
# Feature 1: MSA-driven conformational ensemble
# ===========================================================================


@dataclass
class MSASubsample:
    subsample_id: int
    msa_depth: int
    diversity_score: float


@dataclass
class MSAConformationalState:
    state_id: int
    subsample_ids: list[int]
    pdb_data: str
    plddt_mean: float
    rmsd_to_consensus: float
    population_weight: float
    structural_class: str  # "ground_state" | "alternative" | "rare"


@dataclass
class MSAEnsembleResult:
    sequence: str
    n_subsamples: int
    n_clusters: int
    states: list[MSAConformationalState]
    msa_depth_range: tuple[int, int]
    functional_diversity: float
    ground_state_confidence: float


def _seq_hash_float(sequence: str, salt: str = "", lo: float = 0.0, hi: float = 1.0) -> float:
    """Deterministic float in [lo, hi) derived from sequence + salt."""
    digest = hashlib.md5(f"{sequence}{salt}".encode()).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    return lo + raw * (hi - lo)


def _seq_hash_int(sequence: str, salt: str = "", lo: int = 0, hi: int = 100) -> int:
    digest = hashlib.md5(f"{sequence}{salt}".encode()).hexdigest()
    raw = int(digest[:8], 16)
    return lo + (raw % (hi - lo + 1))


def generate_msa_subsamples(
    sequence: str,
    n_subsamples: int = 20,
    depth_range: tuple[int, int] = (32, 512),
) -> list[MSASubsample]:
    """Generate mock MSA subsamples with varying depth and diversity scores."""
    lo_depth, hi_depth = depth_range
    subsamples: list[MSASubsample] = []
    for i in range(n_subsamples):
        salt = f"sub_{i}"
        depth = _seq_hash_int(sequence, salt=salt, lo=lo_depth, hi=hi_depth)
        # Diversity roughly correlated with depth (higher depth = more diversity)
        base_div = _seq_hash_float(sequence, salt=f"div_{i}", lo=0.1, hi=0.9)
        depth_factor = (depth - lo_depth) / max(hi_depth - lo_depth, 1)
        diversity = min(1.0, base_div * (0.5 + 0.5 * depth_factor))
        subsamples.append(MSASubsample(
            subsample_id=i,
            msa_depth=depth,
            diversity_score=round(diversity, 4),
        ))
    return subsamples


def cluster_msa_conformations(
    sequence: str,
    subsamples: list[MSASubsample],
    rmsd_threshold: float = 2.0,
) -> MSAEnsembleResult:
    """Cluster subsamples into conformational states by greedy RMSD grouping."""
    if not subsamples:
        return MSAEnsembleResult(
            sequence=sequence,
            n_subsamples=0,
            n_clusters=0,
            states=[],
            msa_depth_range=(0, 0),
            functional_diversity=0.0,
            ground_state_confidence=0.0,
        )

    # Deterministic cluster assignment: group by diversity quartile buckets
    diversities = [s.diversity_score for s in subsamples]
    sorted_div = sorted(diversities)
    n = len(sorted_div)
    q1 = sorted_div[n // 4]
    q2 = sorted_div[n // 2]
    q3 = sorted_div[3 * n // 4]

    def _bucket(d: float) -> int:
        if d <= q1:
            return 0
        if d <= q2:
            return 1
        if d <= q3:
            return 2
        return 3

    # Assign subsamples to buckets
    buckets: dict[int, list[MSASubsample]] = {}
    for s in subsamples:
        b = _bucket(s.diversity_score)
        buckets.setdefault(b, []).append(s)

    # Only keep non-empty buckets as clusters
    occupied = sorted(buckets.keys())
    n_clusters = len(occupied)

    # Compute population weights proportional to bucket size
    total = len(subsamples)
    raw_weights = [len(buckets[b]) / total for b in occupied]
    # Normalise (already sum to 1, but guard float drift)
    weight_sum = sum(raw_weights)
    weights = [w / weight_sum for w in raw_weights]

    # Sort clusters by weight descending (largest = ground state)
    cluster_order = sorted(range(n_clusters), key=lambda i: -weights[i])

    states: list[MSAConformationalState] = []
    for rank, ci in enumerate(cluster_order):
        b = occupied[ci]
        members = buckets[b]
        sub_ids = [s.subsample_id for s in members]
        mean_depth = sum(s.msa_depth for s in members) / len(members)
        plddt = 50.0 + _seq_hash_float(sequence, salt=f"plddt_{b}", lo=0.0, hi=40.0)
        rmsd = 0.0 if rank == 0 else _seq_hash_float(sequence, salt=f"rmsd_{b}", lo=0.5, hi=rmsd_threshold * 2.5)
        w = weights[ci]

        if rank == 0:
            s_class = "ground_state"
        elif w >= 0.15:
            s_class = "alternative"
        else:
            s_class = "rare"

        # Mock PDB snippet
        seq_len = len(sequence)
        pdb_lines = [f"REMARK MSA-state {rank} depth={mean_depth:.0f} pLDDT={plddt:.1f}"]
        for j, aa in enumerate(sequence[:min(seq_len, 5)]):
            pdb_lines.append(
                f"ATOM  {j+1:5d}  CA  {aa:3s} A{j+1:4d}    "
                f"  1.000   1.000   1.000  1.00{plddt/100:.2f}           C"
            )
        pdb_lines.append("END")

        states.append(MSAConformationalState(
            state_id=rank,
            subsample_ids=sub_ids,
            pdb_data="\n".join(pdb_lines),
            plddt_mean=round(plddt, 2),
            rmsd_to_consensus=round(rmsd, 3),
            population_weight=round(w, 4),
            structural_class=s_class,
        ))

    depths = [s.msa_depth for s in subsamples]
    depth_range = (min(depths), max(depths))
    # Functional diversity = mean pairwise RMSD approximation
    rmsds = [st.rmsd_to_consensus for st in states if st.rmsd_to_consensus > 0]
    functional_diversity = round(sum(rmsds) / len(rmsds), 3) if rmsds else 0.0
    ground_state_confidence = round(states[0].plddt_mean / 100.0, 4) if states else 0.0

    return MSAEnsembleResult(
        sequence=sequence,
        n_subsamples=len(subsamples),
        n_clusters=n_clusters,
        states=states,
        msa_depth_range=depth_range,
        functional_diversity=functional_diversity,
        ground_state_confidence=ground_state_confidence,
    )


def run_msa_ensemble(sequence: str, n_subsamples: int = 20) -> MSAEnsembleResult:
    """Full MSA-driven conformational ensemble pipeline."""
    subsamples = generate_msa_subsamples(sequence, n_subsamples=n_subsamples)
    return cluster_msa_conformations(sequence, subsamples)


# ===========================================================================
# Feature 2: Protein dynamics annotation
# ===========================================================================

#: Per-residue intrinsic backbone flexibility propensity (0 = rigid, 1 = flexible).
AMINO_ACID_FLEXIBILITY: dict[str, float] = {
    "G": 0.90,  # glycine — maximal flexibility
    "P": 0.70,  # proline — helix-breaker / loop former
    "S": 0.55,  # serine
    "T": 0.50,  # threonine
    "N": 0.48,  # asparagine
    "D": 0.47,  # aspartate
    "Q": 0.45,  # glutamine
    "E": 0.44,  # glutamate
    "K": 0.43,  # lysine
    "R": 0.40,  # arginine
    "H": 0.35,  # histidine
    "A": 0.30,  # alanine
    "M": 0.28,  # methionine
    "L": 0.25,  # leucine
    "I": 0.22,  # isoleucine
    "V": 0.20,  # valine
    "C": 0.18,  # cysteine — often in disulfide bridges
    "F": 0.18,  # phenylalanine
    "Y": 0.17,  # tyrosine
    "W": 0.15,  # tryptophan — bulky, rigid
}
_DEFAULT_FLEX = 0.35


@dataclass
class DynamicsResidue:
    index: int
    residue: str
    backbone_flexibility: float  # 0–1
    sidechain_flexibility: float  # 0–1
    predicted_bfactor: float
    dynamics_class: str  # "rigid" | "flexible" | "highly_flexible" | "hinge"


@dataclass
class DynamicsProfile:
    sequence: str
    residues: list[DynamicsResidue]
    mean_flexibility: float
    flexible_regions: list[tuple[int, int]]
    hinge_residues: list[int]
    overall_dynamics_class: str  # "rigid_globular" | "partially_flexible" | "highly_dynamic"


def predict_dynamics(sequence: str) -> DynamicsProfile:
    """Compute per-residue flexibility from amino acid propensity + position effects."""
    seq = sequence.upper()
    n = len(seq)
    if n == 0:
        return DynamicsProfile(
            sequence=sequence,
            residues=[],
            mean_flexibility=0.0,
            flexible_regions=[],
            hinge_residues=[],
            overall_dynamics_class="rigid_globular",
        )

    residues: list[DynamicsResidue] = []
    backbone_flexes: list[float] = []

    for i, aa in enumerate(seq):
        intrinsic = AMINO_ACID_FLEXIBILITY.get(aa, _DEFAULT_FLEX)
        # Terminal boost: first/last 10% of sequence are more flexible
        terminal_boost = 0.0
        if n > 1:
            frac = i / (n - 1)
            if frac < 0.1 or frac > 0.9:
                terminal_boost = 0.15

        backbone_flex = min(1.0, intrinsic + terminal_boost)
        # Sidechain flexibility moderately correlated but independent
        sidechain_flex = min(1.0, intrinsic * 1.1 + terminal_boost * 0.5)

        # Convert to B-factor scale (Å² — typical range 10–80)
        bfactor = 10.0 + backbone_flex * 70.0

        if backbone_flex < 0.25:
            dclass = "rigid"
        elif backbone_flex < 0.50:
            dclass = "flexible"
        else:
            dclass = "highly_flexible"

        backbone_flexes.append(backbone_flex)
        residues.append(DynamicsResidue(
            index=i,
            residue=aa,
            backbone_flexibility=round(backbone_flex, 4),
            sidechain_flexibility=round(sidechain_flex, 4),
            predicted_bfactor=round(bfactor, 2),
            dynamics_class=dclass,
        ))

    # Identify hinges: positions where flexibility changes abruptly (|Δflex| > 0.3)
    hinge_residues: list[int] = []
    for i in range(1, n):
        delta = abs(backbone_flexes[i] - backbone_flexes[i - 1])
        if delta >= 0.30:
            hinge_residues.append(i)
            residues[i] = DynamicsResidue(
                index=residues[i].index,
                residue=residues[i].residue,
                backbone_flexibility=residues[i].backbone_flexibility,
                sidechain_flexibility=residues[i].sidechain_flexibility,
                predicted_bfactor=residues[i].predicted_bfactor,
                dynamics_class="hinge",
            )

    # Identify flexible regions (runs of consecutive flexible/highly_flexible residues)
    flexible_regions: list[tuple[int, int]] = []
    start: int | None = None
    for i, r in enumerate(residues):
        if r.dynamics_class in ("flexible", "highly_flexible", "hinge"):
            if start is None:
                start = i
        else:
            if start is not None:
                if i - start >= 2:
                    flexible_regions.append((start, i - 1))
                start = None
    if start is not None and n - start >= 2:
        flexible_regions.append((start, n - 1))

    mean_flex = sum(backbone_flexes) / n
    if mean_flex < 0.30:
        overall = "rigid_globular"
    elif mean_flex < 0.55:
        overall = "partially_flexible"
    else:
        overall = "highly_dynamic"

    return DynamicsProfile(
        sequence=sequence,
        residues=residues,
        mean_flexibility=round(mean_flex, 4),
        flexible_regions=flexible_regions,
        hinge_residues=hinge_residues,
        overall_dynamics_class=overall,
    )


def annotate_structure_with_dynamics(pdb_data: str, profile: DynamicsProfile) -> str:
    """Inject predicted B-factor values into PDB ATOM lines from the dynamics profile."""
    bfactor_map: dict[int, float] = {}
    for r in profile.residues:
        bfactor_map[r.index] = r.predicted_bfactor

    output_lines: list[str] = []
    residue_counter: dict[str, int] = {}  # chain+resnum → 0-based index

    for line in pdb_data.splitlines():
        if line.startswith("ATOM") or line.startswith("HETATM"):
            # PDB columns: res_seq = cols 22-26, chain = col 21
            try:
                chain = line[21]
                res_seq_str = line[22:26].strip()
                key = f"{chain}{res_seq_str}"
                if key not in residue_counter:
                    idx = len(residue_counter)
                    residue_counter[key] = idx
                res_idx = residue_counter[key]
                bf = bfactor_map.get(res_idx, 0.0)
                # B-factor field: cols 60-66 (6 chars, right-justified, 2 decimals)
                bf_str = f"{bf:6.2f}"
                if len(line) >= 66:
                    line = line[:60] + bf_str + line[66:]
                else:
                    line = line.rstrip().ljust(60) + bf_str
            except (IndexError, ValueError):
                pass
        output_lines.append(line)

    return "\n".join(output_lines)


# ===========================================================================
# Feature 3: Confidence calibration
# ===========================================================================


class ProteinClass(str, Enum):
    globular = "globular"
    membrane = "membrane"
    idr_rich = "idr_rich"
    fibrous = "fibrous"
    metalloprotein = "metalloprotein"
    antibody = "antibody"
    enzyme = "enzyme"


@dataclass
class CalibrationCurve:
    protein_class: ProteinClass
    plddt_bins: list[float]      # left edge of each bin (0, 10, 20, …, 90)
    actual_accuracy: list[float]  # expected real-world accuracy at that pLDDT bin
    n_benchmarked: int
    calibration_error: float     # mean absolute calibration error
    overconfident_range: tuple[float, float] | None   # pLDDT range where model is overconfident
    underconfident_range: tuple[float, float] | None  # pLDDT range where model is underconfident


# Pre-computed mock calibration curves.
# Bins: [0, 10, 20, 30, 40, 50, 60, 70, 80, 90] → 10 entries.
# Values represent fraction of residues placed correctly at ≤1 Å in benchmark set.
_BINS = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]

CALIBRATION_DATA: dict[ProteinClass, CalibrationCurve] = {
    ProteinClass.globular: CalibrationCurve(
        protein_class=ProteinClass.globular,
        plddt_bins=_BINS,
        actual_accuracy=[0.05, 0.10, 0.18, 0.28, 0.40, 0.55, 0.68, 0.78, 0.88, 0.95],
        n_benchmarked=4821,
        calibration_error=0.032,
        overconfident_range=None,
        underconfident_range=None,
    ),
    ProteinClass.membrane: CalibrationCurve(
        protein_class=ProteinClass.membrane,
        plddt_bins=_BINS,
        actual_accuracy=[0.04, 0.08, 0.14, 0.22, 0.32, 0.44, 0.54, 0.60, 0.65, 0.68],
        # Above pLDDT 70 the model is overconfident for membrane proteins
        n_benchmarked=1203,
        calibration_error=0.118,
        overconfident_range=(70.0, 100.0),
        underconfident_range=None,
    ),
    ProteinClass.idr_rich: CalibrationCurve(
        protein_class=ProteinClass.idr_rich,
        plddt_bins=_BINS,
        actual_accuracy=[0.12, 0.20, 0.30, 0.38, 0.42, 0.50, 0.62, 0.74, 0.84, 0.91],
        # Below pLDDT 40 the model is underconfident for IDRs (ensemble-averaged real accuracy is higher)
        n_benchmarked=892,
        calibration_error=0.085,
        overconfident_range=None,
        underconfident_range=(0.0, 40.0),
    ),
    ProteinClass.fibrous: CalibrationCurve(
        protein_class=ProteinClass.fibrous,
        plddt_bins=_BINS,
        actual_accuracy=[0.03, 0.07, 0.13, 0.20, 0.30, 0.42, 0.55, 0.65, 0.72, 0.78],
        n_benchmarked=347,
        calibration_error=0.094,
        overconfident_range=(80.0, 100.0),
        underconfident_range=None,
    ),
    ProteinClass.metalloprotein: CalibrationCurve(
        protein_class=ProteinClass.metalloprotein,
        plddt_bins=_BINS,
        actual_accuracy=[0.05, 0.09, 0.16, 0.25, 0.37, 0.50, 0.63, 0.74, 0.82, 0.89],
        n_benchmarked=628,
        calibration_error=0.047,
        overconfident_range=None,
        underconfident_range=None,
    ),
    ProteinClass.antibody: CalibrationCurve(
        protein_class=ProteinClass.antibody,
        plddt_bins=_BINS,
        actual_accuracy=[0.04, 0.09, 0.17, 0.27, 0.39, 0.53, 0.66, 0.76, 0.85, 0.92],
        n_benchmarked=1547,
        calibration_error=0.038,
        overconfident_range=None,
        underconfident_range=None,
    ),
    ProteinClass.enzyme: CalibrationCurve(
        protein_class=ProteinClass.enzyme,
        plddt_bins=_BINS,
        actual_accuracy=[0.05, 0.11, 0.19, 0.29, 0.42, 0.57, 0.70, 0.80, 0.89, 0.95],
        n_benchmarked=3102,
        calibration_error=0.029,
        overconfident_range=None,
        underconfident_range=None,
    ),
}


def get_calibration_curve(protein_class: ProteinClass) -> CalibrationCurve:
    return CALIBRATION_DATA[protein_class]


def calibrate_confidence(plddt: float, protein_class: ProteinClass) -> dict:
    """Return adjusted confidence and calibration metadata for a given pLDDT score."""
    curve = CALIBRATION_DATA[protein_class]
    plddt_clamped = max(0.0, min(100.0, plddt))

    # Find the bin index
    bin_idx = min(int(plddt_clamped // 10), len(curve.plddt_bins) - 1)
    raw_accuracy = curve.actual_accuracy[bin_idx]

    # Calibration offset: actual - (pLDDT/100)
    calibration_offset = round(raw_accuracy - plddt_clamped / 100.0, 4)
    adjusted_confidence = round(max(0.0, min(1.0, raw_accuracy)), 4)

    warning: str | None = None
    if curve.overconfident_range and curve.overconfident_range[0] <= plddt_clamped <= curve.overconfident_range[1]:
        warning = (
            f"pLDDT {plddt_clamped:.1f} falls in the overconfident range "
            f"{curve.overconfident_range} for {protein_class.value} proteins. "
            "Actual accuracy is substantially lower than pLDDT suggests."
        )
    elif curve.underconfident_range and curve.underconfident_range[0] <= plddt_clamped <= curve.underconfident_range[1]:
        warning = (
            f"pLDDT {plddt_clamped:.1f} falls in the underconfident range "
            f"{curve.underconfident_range} for {protein_class.value} proteins. "
            "Actual accuracy may be higher than pLDDT suggests."
        )

    return {
        "raw_plddt": round(plddt_clamped, 2),
        "adjusted_confidence": adjusted_confidence,
        "calibration_offset": calibration_offset,
        "protein_class": protein_class.value,
        "warning": warning,
    }


def classify_protein(sequence: str) -> ProteinClass:
    """Heuristic classifier based on amino acid composition."""
    seq = sequence.upper()
    n = len(seq)
    if n == 0:
        return ProteinClass.globular

    def frac(aas: str) -> float:
        return sum(seq.count(a) for a in aas) / n

    hydrophobic_tm = frac("VILMFW")
    gps_content = frac("GPS")
    cys_content = frac("C")

    # Check for transmembrane-like long hydrophobic stretches (≥15 consecutive VILMFW)
    tm_pattern = re.compile(r"[VILMFW]{15,}")
    has_tm_segment = bool(tm_pattern.search(seq))

    # Fibrous: high G/A + tandem repeats heuristic
    ga_content = frac("GA")
    # Antibody: contains CDR-like motifs — heuristic: C-X{10,12}-C pattern
    disulfide_motif = bool(re.search(r"C.{10,12}C", seq))
    # Enzyme: active-site heuristic — catalytic triads SHD / CHD patterns present
    enzyme_motif = bool(re.search(r"[STC][HKR][DE]", seq))

    if has_tm_segment or (hydrophobic_tm > 0.55 and not disulfide_motif):
        return ProteinClass.membrane
    if gps_content > 0.35:
        return ProteinClass.idr_rich
    if cys_content > 0.08:
        return ProteinClass.metalloprotein
    if disulfide_motif and n < 600:
        return ProteinClass.antibody
    if ga_content > 0.45:
        return ProteinClass.fibrous
    if enzyme_motif:
        return ProteinClass.enzyme
    return ProteinClass.globular


def auto_calibrate(sequence: str, plddt: float) -> dict:
    """Classify the protein then return calibrated confidence."""
    protein_class = classify_protein(sequence)
    result = calibrate_confidence(plddt, protein_class)
    result["classified_as"] = protein_class.value
    return result
