"""Conformational Ensemble Sampling — AF2-dropout-based structural diversity.

Uses a modified AlphaFold 2 inference protocol with Monte-Carlo dropout enabled
during the recycling and structure-module passes.  By running N forward passes
with stochastic dropout active, the model samples from an implicit posterior
over protein conformations.  The resulting ensemble is clustered by pairwise
Cα RMSD to identify distinct conformational states and estimate their relative
populations.

This is a RESEARCH-ONLY stub implementation.  All numeric values are produced
deterministically from a hash of the input sequence so that the API is
testable without a running AF2 installation.

RESEARCH ONLY — not for clinical or therapeutic decision-making.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ConformationalState:
    """A single representative structure from the conformational ensemble."""

    state_id: int
    pdb_data: str  # PDB-format coordinate block for this state
    plddt_mean: float  # Mean pLDDT across all residues (0–100)
    rmsd_to_reference: float  # Cα RMSD vs. the lowest-energy state (Å)
    population_weight: float  # Fraction of ensemble assigned to this cluster (0–1)


@dataclass
class EnsembleResult:
    """Full result of a conformational ensemble sampling run."""

    sequence: str
    n_samples: int  # number of AF2 dropout draws
    states: list[ConformationalState] = field(default_factory=list)
    n_clusters: int = 0  # number of distinct states found
    diversity_score: float = 0.0  # mean pairwise RMSD across clusters (Å)
    converged: bool = False  # True if adding more samples changes clusters < 5%


# ---------------------------------------------------------------------------
# Ensemble sampling
# ---------------------------------------------------------------------------


def sample_conformational_ensemble(
    sequence: str,
    n_samples: int = 50,
    cluster_rmsd_threshold: float = 2.0,
) -> EnsembleResult:
    """Sample conformational diversity using AF2 with dropout (deterministic stub).

    Parameters
    ----------
    sequence:
        Amino-acid sequence in single-letter code.
    n_samples:
        Number of stochastic forward passes to perform.
    cluster_rmsd_threshold:
        Cα RMSD threshold (Å) used to merge similar conformations into one cluster.

    Returns
    -------
    EnsembleResult with mock conformational states whose population weights sum to 1.

    RESEARCH ONLY — not for clinical or therapeutic decision-making.
    """
    n_samples = max(1, n_samples)
    n_clusters = min(n_samples // 10, 5)
    n_clusters = max(n_clusters, 1)

    h_base = int(hashlib.sha256(sequence.encode()).hexdigest(), 16)

    # Generate raw weights then normalize so they sum to 1.
    raw_weights: list[float] = []
    for i in range(n_clusters):
        raw_weights.append(((h_base >> (i * 12)) & 0xFFF) + 1.0)
    total_w = sum(raw_weights)
    norm_weights = [w / total_w for w in raw_weights]

    states: list[ConformationalState] = []
    for i in range(n_clusters):
        h_state = int(hashlib.sha256(f"{sequence}:state{i}".encode()).hexdigest(), 16)
        plddt = round(50.0 + (h_state & 0xFF) / 0xFF * 45.0, 2)
        rmsd = (
            0.0
            if i == 0
            else round(
                cluster_rmsd_threshold * 0.3
                + (h_state >> 8 & 0xFF) / 0xFF * cluster_rmsd_threshold * 1.5,
                2,
            )
        )

        pdb_data = (
            f"REMARK  ConformationalState {i} — AF2-dropout stub — RESEARCH ONLY\n"
            f"REMARK  Sequence length: {len(sequence)}  pLDDT: {plddt}\n"
            f"ATOM      1  CA  ALA A   1    {10.0 + i * 2:.3f}  10.000  10.000  1.00 {100 - plddt:.2f}           C\n"
            "END\n"
        )

        states.append(
            ConformationalState(
                state_id=i,
                pdb_data=pdb_data,
                plddt_mean=plddt,
                rmsd_to_reference=rmsd,
                population_weight=round(norm_weights[i], 6),
            )
        )

    # Fix rounding so weights sum exactly to 1.0
    weight_sum = sum(s.population_weight for s in states)
    if states:
        states[-1].population_weight = round(states[-1].population_weight + (1.0 - weight_sum), 6)

    diversity_score = round(sum(s.rmsd_to_reference for s in states) / max(len(states), 1), 3)
    converged = n_samples >= 20

    return EnsembleResult(
        sequence=sequence,
        n_samples=n_samples,
        states=states,
        n_clusters=n_clusters,
        diversity_score=diversity_score,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def get_dominant_state(result: EnsembleResult) -> ConformationalState:
    """Return the conformational state with the highest population weight.

    If the ensemble is empty, raises ValueError.
    """
    if not result.states:
        raise ValueError("EnsembleResult contains no conformational states.")
    return max(result.states, key=lambda s: s.population_weight)


def calculate_flexibility_profile(result: EnsembleResult) -> dict:
    """Compute per-residue flexibility scores from the ensemble (mock).

    Returns a dict with keys:
      - ``residue_indices``: list of 1-based residue indices
      - ``flexibility_scores``: list of per-residue RMSF-like scores (Å)
      - ``mean_flexibility``: ensemble-wide mean flexibility (Å)
      - ``high_flexibility_threshold``: threshold above which a residue is considered flexible
      - ``n_flexible_residues``: count of residues above the threshold

    RESEARCH ONLY — not for clinical or therapeutic decision-making.
    """
    seq_len = len(result.sequence)
    if seq_len == 0:
        return {
            "residue_indices": [],
            "flexibility_scores": [],
            "mean_flexibility": 0.0,
            "high_flexibility_threshold": 1.5,
            "n_flexible_residues": 0,
        }

    h_base = int(hashlib.sha256(result.sequence.encode()).hexdigest(), 16)
    scores: list[float] = []
    for i in range(seq_len):
        h_i = int(hashlib.sha256(f"{result.sequence}:flex{i}".encode()).hexdigest(), 16)
        # Terminals tend to be more flexible
        terminal_boost = 1.5 if (i < 5 or i >= seq_len - 5) else 0.0
        score = round(0.2 + (h_i & 0xFF) / 0xFF * 2.8 + terminal_boost, 3)
        scores.append(min(score, 5.0))

    threshold = 1.5
    mean_flex = round(sum(scores) / seq_len, 3)
    n_flex = sum(1 for s in scores if s > threshold)

    return {
        "residue_indices": list(range(1, seq_len + 1)),
        "flexibility_scores": scores,
        "mean_flexibility": mean_flex,
        "high_flexibility_threshold": threshold,
        "n_flexible_residues": n_flex,
    }
