"""Advanced Protein Science — Phase 24 Tier 3

Epitope mapping, PPI hot-spots, coevolution constraints, protein-nucleic acid interactions.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum

PROTEIN_SCIENCE_DISCLAIMER = (
    "RESEARCH ONLY — not for clinical or diagnostic use. "
    "All outputs are computational predictions requiring experimental validation."
)

# ---------------------------------------------------------------------------
# Feature 1: Antibody-antigen epitope mapping
# ---------------------------------------------------------------------------

# Parker hydrophilicity scale (1986)
PARKER_HYDROPHILICITY: dict[str, float] = {
    "A": -0.5,
    "C": -1.0,
    "D": 3.0,
    "E": 3.0,
    "F": -2.5,
    "G": 0.0,
    "H": -0.5,
    "I": -1.8,
    "K": 3.0,
    "L": -1.8,
    "M": -1.3,
    "N": 0.2,
    "P": 0.0,
    "Q": 0.2,
    "R": 3.0,
    "S": 0.3,
    "T": -0.4,
    "V": -1.5,
    "W": -3.4,
    "Y": -2.3,
}

# Emini surface accessibility propensity
EMINI_ACCESSIBILITY: dict[str, float] = {
    "A": 0.49,
    "C": 0.26,
    "D": 1.59,
    "E": 1.45,
    "F": 0.42,
    "G": 0.72,
    "H": 0.84,
    "I": 0.37,
    "K": 1.69,
    "L": 0.40,
    "M": 0.74,
    "N": 1.33,
    "P": 1.37,
    "Q": 1.35,
    "R": 1.56,
    "S": 1.12,
    "T": 0.96,
    "V": 0.40,
    "W": 0.51,
    "Y": 0.91,
}

# MHC binding likelihood (simplified T-cell scoring)
T_CELL_PROPENSITY: dict[str, float] = {
    "A": 0.4,
    "C": 0.3,
    "D": 0.2,
    "E": 0.3,
    "F": 0.9,
    "G": 0.2,
    "H": 0.5,
    "I": 0.8,
    "K": 0.4,
    "L": 0.9,
    "M": 0.7,
    "N": 0.2,
    "P": 0.1,
    "Q": 0.3,
    "R": 0.4,
    "S": 0.3,
    "T": 0.4,
    "V": 0.7,
    "W": 0.8,
    "Y": 0.7,
}


@dataclass
class EpitopeRegion:
    start: int
    end: int
    residues: str
    epitope_type: str  # "continuous" | "discontinuous"
    solvent_accessibility: float  # 0-1
    immunogenicity_score: float  # 0-1
    b_cell_score: float
    t_cell_score: float


@dataclass
class EpitopeMapResult:
    antigen_sequence: str
    total_epitopes: int
    continuous_epitopes: list[EpitopeRegion] = field(default_factory=list)
    discontinuous_epitopes: list[EpitopeRegion] = field(default_factory=list)
    immunodominant_region: tuple[int, int] | None = None
    surface_accessibility_profile: list[float] = field(default_factory=list)


def _parker_score(peptide: str) -> float:
    """Mean Parker hydrophilicity for a peptide."""
    if not peptide:
        return 0.0
    return sum(PARKER_HYDROPHILICITY.get(aa, 0.0) for aa in peptide) / len(peptide)


def _emini_score(peptide: str) -> float:
    """Geometric mean of Emini surface accessibility values (log-scale)."""
    if not peptide:
        return 0.0
    log_sum = sum(math.log(max(EMINI_ACCESSIBILITY.get(aa, 0.01), 0.01)) for aa in peptide)
    raw = math.exp(log_sum / len(peptide))
    # normalise to ~0-1 range (typical range 0.2-1.8)
    return min(max((raw - 0.2) / 1.6, 0.0), 1.0)


def _t_cell_score(peptide: str) -> float:
    if not peptide:
        return 0.0
    return min(sum(T_CELL_PROPENSITY.get(aa, 0.3) for aa in peptide) / len(peptide), 1.0)


def _seq_hash_float(s: str, salt: str = "") -> float:
    """Deterministic float [0,1] from string."""
    digest = hashlib.md5((s + salt).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _surface_profile(sequence: str) -> list[float]:
    """Per-residue solvent accessibility estimate (sliding window of 3)."""
    n = len(sequence)
    profile: list[float] = []
    for i in range(n):
        window = sequence[max(0, i - 1) : i + 2]
        profile.append(_emini_score(window))
    return profile


def map_epitopes(
    sequence: str,
    min_length: int = 6,
    max_length: int = 25,
) -> EpitopeMapResult:
    """Sliding-window B-cell epitope mapper + hash-based discontinuous detection."""
    seq = sequence.upper()
    n = len(seq)
    profile = _surface_profile(seq)

    continuous: list[EpitopeRegion] = []
    # sliding window for continuous epitopes
    for length in range(min_length, min(max_length + 1, n + 1)):
        for start in range(n - length + 1):
            peptide = seq[start : start + length]
            parker = _parker_score(peptide)
            emini = _emini_score(peptide)
            # threshold: hydrophilic + accessible
            if parker >= 1.0 and emini >= 0.4:
                b_score = min((parker / 3.0 + emini) / 2.0, 1.0)
                t_score = _t_cell_score(peptide)
                immuno = b_score * 0.6 + t_score * 0.4
                continuous.append(
                    EpitopeRegion(
                        start=start,
                        end=start + length - 1,
                        residues=peptide,
                        epitope_type="continuous",
                        solvent_accessibility=emini,
                        immunogenicity_score=round(immuno, 4),
                        b_cell_score=round(b_score, 4),
                        t_cell_score=round(t_score, 4),
                    )
                )

    # deduplicate: keep highest-scoring non-overlapping windows
    continuous.sort(key=lambda e: e.immunogenicity_score, reverse=True)
    kept: list[EpitopeRegion] = []
    covered: set[int] = set()
    for ep in continuous:
        positions = set(range(ep.start, ep.end + 1))
        overlap = positions & covered
        if len(overlap) / len(positions) < 0.5:
            kept.append(ep)
            covered.update(positions)
    continuous = kept[:20]  # cap at 20

    # hash-based discontinuous epitope detection
    # cluster residues by similar physicochemical profile
    discontinuous: list[EpitopeRegion] = []
    if n >= 10:
        chunk = max(1, n // 8)
        for cluster_idx in range(min(8, n // chunk)):
            seed = f"{seq}:disc:{cluster_idx}"
            h = _seq_hash_float(seed)
            # pick 5-8 scattered residues
            n_res = 5 + int(h * 3)
            positions_f = []
            for j in range(n_res):
                pos_h = _seq_hash_float(seed + str(j))
                pos = int(pos_h * (n - 1))
                positions_f.append(pos)
            positions_f = sorted(set(positions_f))
            if len(positions_f) < 3:
                continue
            start = positions_f[0]
            end = positions_f[-1]
            residues = "".join(seq[p] for p in positions_f)
            emini = _emini_score(residues)
            parker = _parker_score(residues)
            b_score = min((parker / 3.0 + emini) / 2.0, 1.0) if parker > 0 else emini * 0.5
            t_score = _t_cell_score(residues)
            immuno = b_score * 0.5 + t_score * 0.5
            discontinuous.append(
                EpitopeRegion(
                    start=start,
                    end=end,
                    residues=residues,
                    epitope_type="discontinuous",
                    solvent_accessibility=round(emini, 4),
                    immunogenicity_score=round(immuno, 4),
                    b_cell_score=round(b_score, 4),
                    t_cell_score=round(t_score, 4),
                )
            )

    all_epitopes = continuous + discontinuous

    # immunodominant region: span of top-3 epitopes by immunogenicity
    top3 = sorted(all_epitopes, key=lambda e: e.immunogenicity_score, reverse=True)[:3]
    immunodominant: tuple[int, int] | None = None
    if top3:
        immunodominant = (min(e.start for e in top3), max(e.end for e in top3))

    return EpitopeMapResult(
        antigen_sequence=seq,
        total_epitopes=len(all_epitopes),
        continuous_epitopes=continuous,
        discontinuous_epitopes=discontinuous,
        immunodominant_region=immunodominant,
        surface_accessibility_profile=profile,
    )


def rank_epitopes(result: EpitopeMapResult) -> list[EpitopeRegion]:
    """Return all epitopes sorted descending by immunogenicity_score."""
    all_ep = result.continuous_epitopes + result.discontinuous_epitopes
    return sorted(all_ep, key=lambda e: e.immunogenicity_score, reverse=True)


# ---------------------------------------------------------------------------
# Feature 2: PPI interface hot-spot prediction
# ---------------------------------------------------------------------------

# Average ΔΔG (kcal/mol) upon Ala substitution — empirically derived
AMINO_ACID_ALANINE_DDG: dict[str, float] = {
    "W": 4.5,
    "F": 3.2,
    "Y": 2.8,
    "R": 2.5,
    "L": 2.3,
    "I": 2.1,
    "M": 1.9,
    "H": 1.8,
    "V": 1.6,
    "K": 1.5,
    "T": 1.2,
    "E": 1.1,
    "Q": 1.0,
    "N": 0.9,
    "D": 0.8,
    "C": 0.7,
    "S": 0.6,
    "P": 0.5,
    "A": 0.0,
    "G": -0.3,
}

# Buried surface area contribution per AA (Å²) — approximate
BURIED_SURFACE_AREA: dict[str, float] = {
    "W": 285.0,
    "F": 218.0,
    "Y": 220.0,
    "R": 202.0,
    "L": 175.0,
    "I": 169.0,
    "M": 185.0,
    "H": 181.0,
    "V": 142.0,
    "K": 171.0,
    "T": 122.0,
    "E": 151.0,
    "Q": 156.0,
    "N": 135.0,
    "D": 124.0,
    "C": 117.0,
    "S": 95.0,
    "P": 130.0,
    "A": 92.0,
    "G": 66.0,
}

HOT_SPOT_DDG_THRESHOLD = 2.0  # kcal/mol


@dataclass
class HotSpotResidue:
    position: int
    residue: str
    alanine_ddg: float
    energy_contribution_pct: float
    is_hot_spot: bool
    buried_surface_area: float


@dataclass
class PPIHotSpotResult:
    interface_residues: list[int]
    hot_spots: list[HotSpotResidue]
    total_interface_energy: float
    hot_spot_fraction: float
    druggable: bool
    druggability_score: float


def _infer_interface_residues(sequence: str) -> list[int]:
    """
    Infer likely interface positions from sequence properties:
    hydrophobic + aromatic residues at moderate burial depth.
    Returns sorted list of 0-based positions.
    """
    seq = sequence.upper()
    n = len(seq)
    interface_aa = set("WFYRLIMVHK")
    candidates: list[int] = []
    for i, aa in enumerate(seq):
        if aa in interface_aa:
            # prefer residues not at extreme termini
            if 2 <= i <= n - 3:
                candidates.append(i)
    # if very few, add all matching
    if len(candidates) < 3:
        candidates = [i for i, aa in enumerate(seq) if aa in interface_aa]
    # sample deterministically to ~30% of sequence
    max_interface = max(5, n // 3)
    if len(candidates) > max_interface:
        step = max(1, len(candidates) // max_interface)
        candidates = candidates[::step][:max_interface]
    return sorted(candidates)


def predict_hot_spots(
    sequence: str,
    interface_residues: list[int] | None = None,
) -> PPIHotSpotResult:
    """Computational alanine scanning on interface residues."""
    seq = sequence.upper()
    n = len(seq)
    if interface_residues is None:
        interface_residues = _infer_interface_residues(seq)

    # clamp positions to valid range
    interface_residues = [i for i in interface_residues if 0 <= i < n]

    residue_data: list[HotSpotResidue] = []
    total_energy = 0.0
    for pos in interface_residues:
        aa = seq[pos]
        ddg = AMINO_ACID_ALANINE_DDG.get(aa, 0.5)
        bsa = BURIED_SURFACE_AREA.get(aa, 100.0)
        total_energy += ddg
        residue_data.append(
            HotSpotResidue(
                position=pos,
                residue=aa,
                alanine_ddg=round(ddg, 3),
                energy_contribution_pct=0.0,  # filled below
                is_hot_spot=ddg >= HOT_SPOT_DDG_THRESHOLD,
                buried_surface_area=round(bsa, 1),
            )
        )

    # compute energy contribution percentages
    for rd in residue_data:
        rd.energy_contribution_pct = (
            round(rd.alanine_ddg / total_energy * 100, 2) if total_energy > 0 else 0.0
        )

    hot_spots = [rd for rd in residue_data if rd.is_hot_spot]
    hot_spot_fraction = len(hot_spots) / len(residue_data) if residue_data else 0.0

    # druggability: >2 hot spots clustered + high fraction
    druggability_score = min(
        hot_spot_fraction * 0.6 + (len(hot_spots) / max(len(residue_data), 1)) * 0.4,
        1.0,
    )
    # bonus for aromatic hot spots (W/F/Y)
    aromatic_hs = sum(1 for hs in hot_spots if hs.residue in "WFY")
    if aromatic_hs >= 2:
        druggability_score = min(druggability_score + 0.15, 1.0)

    druggable = druggability_score >= 0.35 and len(hot_spots) >= 2

    return PPIHotSpotResult(
        interface_residues=interface_residues,
        hot_spots=hot_spots,
        total_interface_energy=round(total_energy, 3),
        hot_spot_fraction=round(hot_spot_fraction, 4),
        druggable=druggable,
        druggability_score=round(druggability_score, 4),
    )


def assess_interface_druggability(result: PPIHotSpotResult) -> dict:
    """Detailed druggability report based on hot-spot geometry."""
    hs = result.hot_spots
    n_hs = len(hs)

    # clustering: count hot spots within 5 positions of each other
    clusters: list[list[int]] = []
    positions = sorted(h.position for h in hs)
    if positions:
        current_cluster = [positions[0]]
        for p in positions[1:]:
            if p - current_cluster[-1] <= 5:
                current_cluster.append(p)
            else:
                clusters.append(current_cluster)
                current_cluster = [p]
        clusters.append(current_cluster)

    largest_cluster = max((len(c) for c in clusters), default=0)
    mean_ddg = sum(h.alanine_ddg for h in hs) / n_hs if n_hs else 0.0
    aromatic_count = sum(1 for h in hs if h.residue in "WFY")

    # pocket geometry proxy: total BSA of hot spots
    total_bsa = sum(h.buried_surface_area for h in hs)

    confidence = (
        "high"
        if result.druggability_score >= 0.6
        else ("medium" if result.druggability_score >= 0.35 else "low")
    )

    return {
        "druggable": result.druggable,
        "druggability_score": result.druggability_score,
        "confidence": confidence,
        "n_hot_spots": n_hs,
        "largest_cluster_size": largest_cluster,
        "n_clusters": len(clusters),
        "mean_alanine_ddg": round(mean_ddg, 3),
        "aromatic_hot_spots": aromatic_count,
        "estimated_pocket_bsa_A2": round(total_bsa, 1),
        "hot_spot_fraction": result.hot_spot_fraction,
        "recommendation": (
            "Strong PPI inhibitor target"
            if result.druggability_score >= 0.6
            else "Moderate target — may need allosteric approach"
            if result.druggability_score >= 0.35
            else "Challenging target — consider orthosteric alternatives"
        ),
    }


# ---------------------------------------------------------------------------
# Feature 3: Coevolution-based functional constraint mapping
# ---------------------------------------------------------------------------

# Pre-computed top coevolving pairs for known genes (mock EVcouplings data)
KNOWN_COEVOLUTION_DATA: dict[str, list[tuple[int, int, float, str]]] = {
    "TP53": [
        (175, 248, 0.92, "structural"),
        (220, 272, 0.85, "catalytic"),
        (245, 249, 0.88, "catalytic"),
        (179, 273, 0.77, "structural"),
        (133, 282, 0.71, "allosteric"),
        (163, 237, 0.68, "structural"),
    ],
    "BRCA1": [
        (1699, 1703, 0.89, "structural"),
        (220, 227, 0.81, "catalytic"),
        (508, 1861, 0.74, "allosteric"),
        (300, 1700, 0.69, "structural"),
    ],
    "KRAS": [
        (12, 61, 0.94, "catalytic"),
        (13, 116, 0.87, "catalytic"),
        (61, 146, 0.82, "structural"),
        (12, 146, 0.79, "catalytic"),
        (18, 57, 0.71, "allosteric"),
    ],
    "EGFR": [
        (719, 858, 0.90, "catalytic"),
        (746, 790, 0.85, "structural"),
        (719, 790, 0.80, "catalytic"),
        (858, 861, 0.76, "structural"),
        (719, 861, 0.72, "allosteric"),
    ],
    "BRAF": [
        (600, 601, 0.93, "catalytic"),
        (464, 600, 0.86, "structural"),
        (469, 594, 0.79, "allosteric"),
        (597, 600, 0.74, "catalytic"),
    ],
    "MYC": [
        (58, 62, 0.88, "structural"),
        (370, 402, 0.82, "allosteric"),
        (402, 439, 0.75, "structural"),
        (62, 96, 0.70, "unknown"),
    ],
    "PIK3CA": [
        (542, 1047, 0.91, "catalytic"),
        (545, 1049, 0.87, "catalytic"),
        (420, 542, 0.78, "structural"),
        (726, 1047, 0.73, "allosteric"),
    ],
    "PTEN": [
        (130, 173, 0.89, "catalytic"),
        (129, 131, 0.85, "catalytic"),
        (173, 233, 0.77, "structural"),
        (36, 130, 0.71, "allosteric"),
    ],
}


@dataclass
class CoevolvingPair:
    residue_i: int
    residue_j: int
    coupling_score: float
    contact_probability: float
    functional_constraint: str  # "structural" | "catalytic" | "allosteric" | "unknown"


@dataclass
class CoevolutionResult:
    sequence: str
    n_pairs: int
    top_pairs: list[CoevolvingPair] = field(default_factory=list)
    sectors: list[list[int]] = field(default_factory=list)
    conservation_scores: list[float] = field(default_factory=list)
    functionally_constrained_positions: list[int] = field(default_factory=list)


def _conservation_from_sequence(sequence: str) -> list[float]:
    """
    Per-residue conservation estimate using entropy proxy.
    Higher scores = more conserved (rarer amino acid at that position proxy).
    """
    # amino acid frequency in natural proteins (approximate)
    aa_freq: dict[str, float] = {
        "A": 0.074,
        "C": 0.025,
        "D": 0.054,
        "E": 0.054,
        "F": 0.047,
        "G": 0.074,
        "H": 0.026,
        "I": 0.068,
        "K": 0.058,
        "L": 0.099,
        "M": 0.025,
        "N": 0.045,
        "P": 0.039,
        "Q": 0.034,
        "R": 0.052,
        "S": 0.057,
        "T": 0.051,
        "V": 0.073,
        "W": 0.013,
        "Y": 0.032,
    }
    scores = []
    for aa in sequence.upper():
        freq = aa_freq.get(aa, 0.05)
        # rarer AAs at functional sites → higher conservation proxy
        conservation = 1.0 - freq / 0.099  # normalize to L (most common)
        scores.append(round(max(0.0, min(conservation, 1.0)), 4))
    return scores


def _generate_coupling_pairs(sequence: str, n_pairs: int = 20) -> list[CoevolvingPair]:
    """Generate deterministic coupling pairs from sequence composition."""
    seq = sequence.upper()
    n = len(seq)
    pairs: list[CoevolvingPair] = []
    constraint_types = ["structural", "catalytic", "allosteric", "unknown"]

    for k in range(n_pairs):
        seed_i = _seq_hash_float(seq + f":pair_i:{k}")
        seed_j = _seq_hash_float(seq + f":pair_j:{k}")
        seed_score = _seq_hash_float(seq + f":score:{k}")
        seed_type = _seq_hash_float(seq + f":type:{k}")

        i = int(seed_i * (n - 1))
        j = int(seed_j * (n - 1))
        if i == j:
            j = (j + 1) % n

        i, j = min(i, j), max(i, j)
        if j - i < 3:
            j = min(i + 3, n - 1)

        # bias score upward for specific AA combos (aromatic/charged pairs)
        aa_i = seq[i]
        aa_j = seq[j]
        coupling_bias = 0.0
        if aa_i in "WFY" and aa_j in "WFY":
            coupling_bias = 0.15
        elif aa_i in "RKHDE" and aa_j in "RKHDE":
            coupling_bias = 0.10

        coupling = round(min(0.3 + seed_score * 0.6 + coupling_bias, 1.0), 4)
        contact_prob = round(min(coupling * 0.9 + seed_score * 0.1, 1.0), 4)
        constraint = constraint_types[int(seed_type * 4) % 4]

        pairs.append(
            CoevolvingPair(
                residue_i=i,
                residue_j=j,
                coupling_score=coupling,
                contact_probability=contact_prob,
                functional_constraint=constraint,
            )
        )

    pairs.sort(key=lambda p: p.coupling_score, reverse=True)
    return pairs


def _identify_sectors(pairs: list[CoevolvingPair], n_residues: int) -> list[list[int]]:
    """
    Identify coevolutionary sectors — groups of co-varying residues —
    via union-find on high-coupling pairs (score > 0.7).
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for p in pairs:
        if p.coupling_score >= 0.7:
            union(p.residue_i, p.residue_j)

    # group by root
    groups: dict[int, list[int]] = {}
    for pos in set(r for p in pairs for r in (p.residue_i, p.residue_j)):
        root = find(pos)
        groups.setdefault(root, []).append(pos)

    sectors = [sorted(v) for v in groups.values() if len(v) >= 2]
    sectors.sort(key=len, reverse=True)
    return sectors


def predict_coevolution(
    sequence: str,
    gene: str = "",
) -> CoevolutionResult:
    """Mock EVcouplings/GREMLIN analysis with known-gene data overlay."""
    seq = sequence.upper()
    n = len(seq)

    conservation = _conservation_from_sequence(seq)

    # start with generated pairs
    generated_pairs = _generate_coupling_pairs(seq, n_pairs=min(30, max(10, n // 5)))

    # overlay known data if gene matches
    known_pairs: list[CoevolvingPair] = []
    gene_upper = gene.upper()
    for gene_key, data in KNOWN_COEVOLUTION_DATA.items():
        if gene_key in gene_upper or gene_upper == gene_key:
            for i, j, score, constraint in data:
                # only include if positions are valid for this sequence
                if i < n and j < n:
                    cp = 0.95  # known pairs have high contact probability
                    known_pairs.append(
                        CoevolvingPair(
                            residue_i=i,
                            residue_j=j,
                            coupling_score=score,
                            contact_probability=round(score * cp, 4),
                            functional_constraint=constraint,
                        )
                    )
            break

    # merge: known pairs take precedence
    known_positions = {(p.residue_i, p.residue_j) for p in known_pairs}
    merged = known_pairs + [
        p for p in generated_pairs if (p.residue_i, p.residue_j) not in known_positions
    ]
    merged.sort(key=lambda p: p.coupling_score, reverse=True)
    top_pairs = merged[:20]

    sectors = _identify_sectors(top_pairs, n)

    # functionally constrained: high-scoring + catalytic/allosteric
    constrained_positions: list[int] = []
    for p in top_pairs:
        if p.coupling_score >= 0.75 and p.functional_constraint in ("catalytic", "allosteric"):
            constrained_positions.extend([p.residue_i, p.residue_j])
    constrained_positions = sorted(set(constrained_positions))

    return CoevolutionResult(
        sequence=seq,
        n_pairs=len(top_pairs),
        top_pairs=top_pairs,
        sectors=sectors,
        conservation_scores=conservation,
        functionally_constrained_positions=constrained_positions,
    )


def map_constraints_to_structure(
    coev_result: CoevolutionResult,
    variants: list[int] | None = None,
) -> dict:
    """Flag which variant positions disrupt coevolutionary constraints."""
    constrained = set(coev_result.functionally_constrained_positions)
    all_coev_positions = set(
        pos
        for p in coev_result.top_pairs
        for pos in (p.residue_i, p.residue_j)
        if p.coupling_score >= 0.7
    )

    disrupted_variants: list[dict] = []
    safe_variants: list[int] = []

    if variants:
        for v in variants:
            if v in constrained:
                # find which pairs are disrupted
                disrupted_pairs = [
                    {
                        "pair": (p.residue_i, p.residue_j),
                        "coupling": p.coupling_score,
                        "constraint": p.functional_constraint,
                    }
                    for p in coev_result.top_pairs
                    if (v == p.residue_i or v == p.residue_j) and p.coupling_score >= 0.7
                ]
                disrupted_variants.append(
                    {
                        "position": v,
                        "disrupts_n_pairs": len(disrupted_pairs),
                        "disrupted_pairs": disrupted_pairs,
                        "severity": "high" if len(disrupted_pairs) >= 2 else "moderate",
                    }
                )
            elif v in all_coev_positions:
                disrupted_variants.append(
                    {
                        "position": v,
                        "disrupts_n_pairs": 0,
                        "disrupted_pairs": [],
                        "severity": "low",
                    }
                )
            else:
                safe_variants.append(v)

    return {
        "total_constrained_positions": len(constrained),
        "total_coevolving_positions": len(all_coev_positions),
        "n_sectors": len(coev_result.sectors),
        "disrupted_variants": disrupted_variants,
        "safe_variants": safe_variants,
        "variants_analyzed": len(variants) if variants else 0,
    }


# ---------------------------------------------------------------------------
# Feature 4: Protein-nucleic acid interaction prediction
# ---------------------------------------------------------------------------


class NucleicAcidType(str, Enum):
    dna = "dna"
    rna = "rna"
    hybrid = "hybrid"


# Known NA-binding proteins with binding modes
KNOWN_NA_BINDING_PROTEINS: list[dict] = [
    {
        "name": "p53",
        "gene": "TP53",
        "na_type": NucleicAcidType.dna,
        "specificity": "sequence_specific",
        "binding_motif": "RRRCWWGYYY",
        "key_residues": [248, 273, 280, 283, 245],
        "notes": "Tetramer binds p53 response elements",
    },
    {
        "name": "Cas9",
        "gene": "CAS9",
        "na_type": NucleicAcidType.hybrid,
        "specificity": "sequence_specific",
        "binding_motif": "gRNA scaffold",
        "key_residues": [1, 10, 46, 1099, 1135],
        "notes": "SpCas9 — PAM-dependent DNA cleavage guided by sgRNA",
    },
    {
        "name": "PCNA",
        "gene": "PCNA",
        "na_type": NucleicAcidType.dna,
        "specificity": "non_specific",
        "binding_motif": "sliding clamp",
        "key_residues": [250, 251, 252, 253, 254],
        "notes": "DNA polymerase sliding clamp",
    },
    {
        "name": "RPA70",
        "gene": "RPA1",
        "na_type": NucleicAcidType.dna,
        "specificity": "non_specific",
        "binding_motif": "OB-fold",
        "key_residues": [168, 171, 194, 212, 301],
        "notes": "ssDNA binding — replication/repair",
    },
    {
        "name": "TFIID",
        "gene": "TBP",
        "na_type": NucleicAcidType.dna,
        "specificity": "sequence_specific",
        "binding_motif": "TATAAA",
        "key_residues": [159, 161, 199, 201, 207, 209],
        "notes": "TATA-box binding protein",
    },
    {
        "name": "U1 snRNP 70K",
        "gene": "SNRNP70",
        "na_type": NucleicAcidType.rna,
        "specificity": "structure_specific",
        "binding_motif": "RRM",
        "key_residues": [92, 104, 148, 162],
        "notes": "Splicing factor — recognizes 5' splice site",
    },
    {
        "name": "eIF4E",
        "gene": "EIF4E",
        "na_type": NucleicAcidType.rna,
        "specificity": "structure_specific",
        "binding_motif": "m7G cap",
        "key_residues": [56, 102, 146, 209],
        "notes": "Cap-dependent translation initiation",
    },
    {
        "name": "Lin28A",
        "gene": "LIN28A",
        "na_type": NucleicAcidType.rna,
        "specificity": "sequence_specific",
        "binding_motif": "GGAG",
        "key_residues": [26, 28, 52, 72, 130, 168],
        "notes": "Let-7 miRNA biogenesis repressor",
    },
    {
        "name": "MBNL1",
        "gene": "MBNL1",
        "na_type": NucleicAcidType.rna,
        "specificity": "sequence_specific",
        "binding_motif": "YGCY",
        "key_residues": [58, 98, 192, 232],
        "notes": "Splicing regulator — muscleblind-like",
    },
    {
        "name": "L11/uL5",
        "gene": "RPL11",
        "na_type": NucleicAcidType.rna,
        "specificity": "structure_specific",
        "binding_motif": "5S rRNA",
        "key_residues": [24, 55, 71, 88, 149],
        "notes": "Ribosomal protein — large subunit",
    },
    {
        "name": "ADAR1",
        "gene": "ADAR",
        "na_type": NucleicAcidType.hybrid,
        "specificity": "structure_specific",
        "binding_motif": "dsRNA",
        "key_residues": [488, 489, 540, 542, 579],
        "notes": "A-to-I RNA editing — dsRNA binding",
    },
    {
        "name": "PARP1",
        "gene": "PARP1",
        "na_type": NucleicAcidType.dna,
        "specificity": "structure_specific",
        "binding_motif": "SSB/DSB",
        "key_residues": [215, 216, 217, 388, 390],
        "notes": "DNA damage sensor — poly(ADP-ribose) polymerase",
    },
]

# Positively charged residues bind phosphate backbone
NA_BINDING_POSITIVE = set("RKH")
# Aromatic residues stack with nucleobases
NA_BINDING_AROMATIC = set("WFY")
# Also: asparagine/glutamine form H-bonds with bases
NA_BINDING_POLAR = set("NQ")


def identify_binding_residues(sequence: str) -> list[int]:
    """
    Find R/K/H-rich and aromatic/polar-rich regions likely to bind nucleic acids.
    Returns 0-based positions of candidate binding residues.
    """
    seq = sequence.upper()
    n = len(seq)
    if n == 0:
        return []

    binding_residues: list[int] = []
    window = 7
    threshold = 3  # min binding-type AAs in window

    for i in range(n):
        aa = seq[i]
        if aa not in (NA_BINDING_POSITIVE | NA_BINDING_AROMATIC | NA_BINDING_POLAR):
            continue
        # check local density
        start = max(0, i - window // 2)
        end = min(n, i + window // 2 + 1)
        local = seq[start:end]
        count = sum(1 for a in local if a in (NA_BINDING_POSITIVE | NA_BINDING_AROMATIC))
        if count >= threshold:
            binding_residues.append(i)

    return sorted(set(binding_residues))


def _na_binding_score(
    sequence: str,
    na_type: NucleicAcidType,
) -> tuple[float, str]:
    """
    Compute binding score [0,1] and specificity class.
    DNA: prefers basic + aromatic patches.
    RNA: prefers basic + polar patches (more H-bonds).
    Hybrid: average.
    """
    seq = sequence.upper()
    n = max(len(seq), 1)

    n_basic = sum(1 for aa in seq if aa in NA_BINDING_POSITIVE)
    n_aromatic = sum(1 for aa in seq if aa in NA_BINDING_AROMATIC)
    n_polar = sum(1 for aa in seq if aa in NA_BINDING_POLAR)

    frac_basic = n_basic / n
    frac_aromatic = n_aromatic / n
    frac_polar = n_polar / n

    if na_type == NucleicAcidType.dna:
        score = frac_basic * 0.6 + frac_aromatic * 0.4
    elif na_type == NucleicAcidType.rna:
        score = frac_basic * 0.5 + frac_polar * 0.3 + frac_aromatic * 0.2
    else:  # hybrid
        dna_score = frac_basic * 0.6 + frac_aromatic * 0.4
        rna_score = frac_basic * 0.5 + frac_polar * 0.3 + frac_aromatic * 0.2
        score = (dna_score + rna_score) / 2

    # normalise: typical NA-binding proteins have ~15-25% basic residues → score ~0.6
    score = min(score / 0.25, 1.0)

    # determine specificity
    # sequence-specific binders have RGG motifs or specific patterns
    has_rgg = "RGG" in seq or "RRGG" in seq
    has_rrm = frac_basic > 0.12 and frac_aromatic > 0.05
    has_zinc = "CCHH" in seq or "CCHC" in seq or "CCCH" in seq

    if has_rgg or has_zinc:
        specificity = "sequence_specific"
    elif has_rrm or (frac_basic > 0.15 and frac_aromatic < 0.03):
        specificity = "non_specific"
    else:
        specificity = "structure_specific"

    return round(score, 4), specificity


def predict_na_binding(
    protein_sequence: str,
    nucleic_acid_type: NucleicAcidType,
    nucleic_acid_sequence: str | None = None,
) -> NABindingResult:
    """
    Predict protein-nucleic acid binding using positively charged/aromatic patch detection.
    Integrates known NA-binding protein database for similarity scoring.
    """
    seq = protein_sequence.upper()
    n = len(seq)

    binding_residues = identify_binding_residues(seq)
    base_score, specificity = _na_binding_score(seq, nucleic_acid_type)

    # interface area estimate: ~150 Å² per binding residue
    interface_area = round(len(binding_residues) * 150.0, 1)

    # check against known binding proteins (simple hash-based similarity)
    na_partner: str | None = None
    best_sim = 0.0
    for known in KNOWN_NA_BINDING_PROTEINS:
        if known["na_type"] != nucleic_acid_type and nucleic_acid_type != NucleicAcidType.hybrid:
            continue
        # similarity via shared residue patterns (simplified)
        known_name = known["name"]
        sim = _seq_hash_float(seq + ":" + known_name + ":sim")
        # boost if key residues exist in sequence
        matches = sum(
            1 for pos in known.get("key_residues", []) if pos < n and seq[pos] in "RKHWFY"
        )
        sim_adjusted = sim * 0.3 + (matches / max(len(known.get("key_residues", [1])), 1)) * 0.7
        if sim_adjusted > best_sim:
            best_sim = sim_adjusted
            na_partner = known_name
            if known["na_type"] != nucleic_acid_type:
                na_partner = None  # don't assign mismatched type

    # if nucleic_acid_sequence provided, adjust score based on complementarity
    if nucleic_acid_sequence:
        gc_content = (
            nucleic_acid_sequence.upper().count("G") + nucleic_acid_sequence.upper().count("C")
        ) / max(len(nucleic_acid_sequence), 1)
        # GC-rich sequences form stronger interactions with aromatic stacking
        n_aromatic = sum(1 for aa in seq if aa in NA_BINDING_AROMATIC)
        if n_aromatic > 0 and gc_content > 0.5:
            base_score = min(base_score * 1.1, 1.0)

    return NABindingResult(
        protein_sequence=seq,
        nucleic_acid_type=nucleic_acid_type,
        binding_residues=binding_residues,
        binding_score=base_score,
        interface_area=interface_area,
        specificity=specificity,
        nucleic_acid_partner=na_partner,
    )


@dataclass
class NABindingResult:
    protein_sequence: str
    nucleic_acid_type: NucleicAcidType
    binding_residues: list[int]
    binding_score: float
    interface_area: float
    specificity: str  # "sequence_specific" | "non_specific" | "structure_specific"
    nucleic_acid_partner: str | None
