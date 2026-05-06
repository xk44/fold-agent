"""Privacy Infrastructure — Phase 24 Tier 3

Federated prediction orchestration and differential privacy for cohort analysis.
RESEARCH USE ONLY.
"""

from __future__ import annotations

import hashlib
import math
import struct
import uuid
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Federated Structure Prediction
# ---------------------------------------------------------------------------


@dataclass
class FederatedNode:
    node_id: str
    institution: str
    data_residency: str  # "US" | "EU" | "APAC" | "local"
    available: bool
    capabilities: list[str]
    trust_level: str  # "full" | "partial" | "minimal"


@dataclass
class FederatedJob:
    job_id: str
    sequence_hash: str  # NOT the actual sequence
    participating_nodes: list[str]
    status: str  # "pending" | "aggregating" | "complete" | "failed"
    model_updates_received: int
    aggregated_result: dict | None
    privacy_budget_used: float


@dataclass
class FederatedResult:
    job_id: str
    consensus_plddt: float
    confidence_interval: tuple[float, float]
    contributing_nodes: int
    privacy_preserved: bool
    audit_trail: list[str]


MOCK_FEDERATION_NODES: dict[str, FederatedNode] = {
    "node_boston_01": FederatedNode(
        node_id="node_boston_01",
        institution="Boston Medical Center",
        data_residency="US",
        available=True,
        capabilities=["structure_prediction", "variant_analysis"],
        trust_level="full",
    ),
    "node_london_02": FederatedNode(
        node_id="node_london_02",
        institution="London Institute of Genomics",
        data_residency="EU",
        available=True,
        capabilities=["structure_prediction", "epitope_mapping"],
        trust_level="full",
    ),
    "node_tokyo_03": FederatedNode(
        node_id="node_tokyo_03",
        institution="Tokyo Biosciences Hub",
        data_residency="APAC",
        available=True,
        capabilities=["structure_prediction"],
        trust_level="partial",
    ),
    "node_sydney_04": FederatedNode(
        node_id="node_sydney_04",
        institution="Sydney Precision Medicine",
        data_residency="APAC",
        available=False,
        capabilities=["structure_prediction", "drug_docking"],
        trust_level="partial",
    ),
    "node_local_05": FederatedNode(
        node_id="node_local_05",
        institution="Local Research Node",
        data_residency="local",
        available=True,
        capabilities=["structure_prediction", "variant_analysis", "epitope_mapping"],
        trust_level="full",
    ),
}


def _hash_float(seed: str) -> float:
    """Deterministic float in [0, 1) from a string seed."""
    digest = hashlib.sha256(seed.encode()).digest()
    int_val = struct.unpack(">Q", digest[:8])[0]
    return int_val / (2**64)


def _hash_float_range(seed: str, lo: float, hi: float) -> float:
    return lo + _hash_float(seed) * (hi - lo)


def create_federated_job(
    sequence_hash: str,
    target_nodes: list[str] | None = None,
) -> FederatedJob:
    """Create a federated job distributing to available nodes.

    Only the sequence hash is distributed — never the actual sequence.
    """
    if target_nodes is None:
        participating = [nid for nid, node in MOCK_FEDERATION_NODES.items() if node.available]
    else:
        participating = [
            nid
            for nid in target_nodes
            if nid in MOCK_FEDERATION_NODES and MOCK_FEDERATION_NODES[nid].available
        ]

    job_id = str(uuid.UUID(bytes=hashlib.sha256(f"job:{sequence_hash}".encode()).digest()[:16]))

    return FederatedJob(
        job_id=job_id,
        sequence_hash=sequence_hash,
        participating_nodes=participating,
        status="pending",
        model_updates_received=0,
        aggregated_result=None,
        privacy_budget_used=0.0,
    )


def simulate_federated_round(job: FederatedJob) -> FederatedJob:
    """Simulate one round of federated averaging.

    Each node contributes a mock model update (pLDDT estimate + confidence).
    Actual sequences never leave each node — only gradient-like scalars.
    """
    updates_received = 0
    node_estimates: list[float] = []

    for node_id in job.participating_nodes:
        node = MOCK_FEDERATION_NODES.get(node_id)
        if node is None or not node.available:
            continue
        seed = f"update:{job.job_id}:{node_id}"
        estimate = _hash_float_range(seed, 60.0, 95.0)
        node_estimates.append(estimate)
        updates_received += 1

    if not node_estimates:
        return FederatedJob(
            job_id=job.job_id,
            sequence_hash=job.sequence_hash,
            participating_nodes=job.participating_nodes,
            status="failed",
            model_updates_received=0,
            aggregated_result=None,
            privacy_budget_used=job.privacy_budget_used,
        )

    mean_plddt = sum(node_estimates) / len(node_estimates)
    # Budget charge: 0.1 epsilon per round per node (deterministic)
    budget_charge = round(0.1 * updates_received, 6)

    return FederatedJob(
        job_id=job.job_id,
        sequence_hash=job.sequence_hash,
        participating_nodes=job.participating_nodes,
        status="aggregating",
        model_updates_received=updates_received,
        aggregated_result={"round_mean_plddt": mean_plddt, "node_estimates": node_estimates},
        privacy_budget_used=round(job.privacy_budget_used + budget_charge, 6),
    )


def aggregate_federated_results(job: FederatedJob) -> FederatedResult:
    """Aggregate model updates into consensus result, track privacy budget."""
    audit: list[str] = []

    if job.aggregated_result is None or job.model_updates_received == 0:
        audit.append("aggregation_failed:no_updates_received")
        return FederatedResult(
            job_id=job.job_id,
            consensus_plddt=0.0,
            confidence_interval=(0.0, 0.0),
            contributing_nodes=0,
            privacy_preserved=True,
            audit_trail=audit,
        )

    estimates: list[float] = job.aggregated_result.get("node_estimates", [])
    mean_plddt = sum(estimates) / len(estimates)

    # Confidence interval: ±1.96 * std / sqrt(n) (or fixed 5.0 if n<2)
    n = len(estimates)
    if n >= 2:
        variance = sum((x - mean_plddt) ** 2 for x in estimates) / n
        std = math.sqrt(variance)
        margin = 1.96 * std / math.sqrt(n)
    else:
        margin = 5.0

    ci = (round(mean_plddt - margin, 4), round(mean_plddt + margin, 4))

    audit.append(f"job_id:{job.job_id}")
    audit.append(f"sequence_hash:{job.sequence_hash}")
    audit.append(f"nodes_contributed:{job.model_updates_received}")
    audit.append(f"privacy_budget_used:{job.privacy_budget_used}")
    audit.append("sequences_never_transmitted:true")
    audit.append("model_updates_only:true")

    return FederatedResult(
        job_id=job.job_id,
        consensus_plddt=round(mean_plddt, 4),
        confidence_interval=ci,
        contributing_nodes=job.model_updates_received,
        privacy_preserved=True,
        audit_trail=audit,
    )


def get_federation_status() -> dict:
    """Return status of all federation nodes."""
    return {
        node_id: {
            "institution": node.institution,
            "data_residency": node.data_residency,
            "available": node.available,
            "capabilities": node.capabilities,
            "trust_level": node.trust_level,
        }
        for node_id, node in MOCK_FEDERATION_NODES.items()
    }


def run_federated_prediction(sequence_hash: str) -> FederatedResult:
    """Full federated pipeline: create job → run rounds → aggregate."""
    job = create_federated_job(sequence_hash)
    job = simulate_federated_round(job)
    result = aggregate_federated_results(job)
    return result


# ---------------------------------------------------------------------------
# Differential Privacy
# ---------------------------------------------------------------------------

PRIVACY_BUDGET_DEFAULT = 10.0


@dataclass
class DPConfig:
    epsilon: float = 1.0
    delta: float = 1e-5
    mechanism: str = "laplace"  # "laplace" | "gaussian"
    sensitivity: float = 1.0
    clip_min: float | None = None
    clip_max: float | None = None


@dataclass
class DPResult:
    original_value: float | None  # redacted by default — set to None
    noisy_value: float
    epsilon_used: float
    noise_magnitude: float
    confidence_interval: tuple[float, float]
    privacy_loss_cumulative: float


@dataclass
class CohortReport:
    cohort_size: int
    metric_name: str
    dp_results: list[DPResult]
    total_privacy_budget: float
    budget_remaining: float
    safe_to_release: bool


def _hash_normal(seed: str) -> float:
    """Deterministic approximate standard-normal sample via Box-Muller on hash."""
    h1 = hashlib.sha256(f"{seed}:u1".encode()).digest()
    h2 = hashlib.sha256(f"{seed}:u2".encode()).digest()
    u1 = (struct.unpack(">Q", h1[:8])[0] / (2**64 - 1)) or 1e-15  # avoid log(0)
    u2 = struct.unpack(">Q", h2[:8])[0] / (2**64)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def add_laplace_noise(value: float, sensitivity: float, epsilon: float) -> float:
    """Add Laplace noise. Deterministic: seed = (value, sensitivity, epsilon)."""
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    scale = sensitivity / epsilon
    seed = f"laplace:{value}:{sensitivity}:{epsilon}"
    # Laplace via inverse CDF from uniform in (-0.5, 0.5)
    u = _hash_float(seed) - 0.5  # in (-0.5, 0.5)
    noise = -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u) + 1e-15)
    return value + noise


def add_gaussian_noise(value: float, sensitivity: float, epsilon: float, delta: float) -> float:
    """Add Gaussian noise (Gaussian mechanism). Deterministic."""
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    if delta <= 0:
        raise ValueError("delta must be positive")
    # sigma via analytic Gaussian mechanism: sigma = sensitivity * sqrt(2*ln(1.25/delta)) / epsilon
    sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
    seed = f"gaussian:{value}:{sensitivity}:{epsilon}:{delta}"
    noise = sigma * _hash_normal(seed)
    return value + noise


def apply_dp(value: float, config: DPConfig) -> DPResult:
    """Apply differential privacy noise based on mechanism in config."""
    clipped = value
    if config.clip_min is not None:
        clipped = max(clipped, config.clip_min)
    if config.clip_max is not None:
        clipped = min(clipped, config.clip_max)

    if config.mechanism == "laplace":
        noisy = add_laplace_noise(clipped, config.sensitivity, config.epsilon)
        scale = config.sensitivity / config.epsilon
        margin = 1.96 * scale
    elif config.mechanism == "gaussian":
        noisy = add_gaussian_noise(clipped, config.sensitivity, config.epsilon, config.delta)
        sigma = config.sensitivity * math.sqrt(2 * math.log(1.25 / config.delta)) / config.epsilon
        margin = 1.96 * sigma
    else:
        raise ValueError(f"Unknown mechanism: {config.mechanism}")

    noise_magnitude = abs(noisy - clipped)
    ci = (round(noisy - margin, 6), round(noisy + margin, 6))

    return DPResult(
        original_value=None,  # redacted for privacy
        noisy_value=round(noisy, 6),
        epsilon_used=config.epsilon,
        noise_magnitude=round(noise_magnitude, 6),
        confidence_interval=ci,
        privacy_loss_cumulative=config.epsilon,
    )


def create_cohort_report(
    values: list[float],
    metric_name: str,
    config: DPConfig,
) -> CohortReport:
    """Apply DP to mean/count/sum of cohort values, track cumulative budget."""
    if not values:
        return CohortReport(
            cohort_size=0,
            metric_name=metric_name,
            dp_results=[],
            total_privacy_budget=PRIVACY_BUDGET_DEFAULT,
            budget_remaining=PRIVACY_BUDGET_DEFAULT,
            safe_to_release=False,
        )

    stats = {
        "mean": sum(values) / len(values),
        "count": float(len(values)),
        "sum": sum(values),
    }

    dp_results: list[DPResult] = []
    cumulative_epsilon = 0.0

    for stat_name, stat_val in stats.items():
        # Use a deterministic seed suffix per stat
        stat_config = DPConfig(
            epsilon=config.epsilon,
            delta=config.delta,
            mechanism=config.mechanism,
            sensitivity=config.sensitivity,
            clip_min=config.clip_min,
            clip_max=config.clip_max,
        )
        result = apply_dp(stat_val, stat_config)
        # Override noise seed to be stat-specific
        if config.mechanism == "laplace":
            noisy = add_laplace_noise(stat_val, config.sensitivity, config.epsilon)
            scale = config.sensitivity / config.epsilon
            margin = 1.96 * scale
        else:
            noisy = add_gaussian_noise(stat_val, config.sensitivity, config.epsilon, config.delta)
            sigma = (
                config.sensitivity * math.sqrt(2 * math.log(1.25 / config.delta)) / config.epsilon
            )
            margin = 1.96 * sigma

        noise_magnitude = abs(noisy - stat_val)
        ci = (round(noisy - margin, 6), round(noisy + margin, 6))

        dp_result = DPResult(
            original_value=None,
            noisy_value=round(noisy, 6),
            epsilon_used=config.epsilon,
            noise_magnitude=round(noise_magnitude, 6),
            confidence_interval=ci,
            privacy_loss_cumulative=round(cumulative_epsilon + config.epsilon, 6),
        )
        dp_results.append(dp_result)
        cumulative_epsilon += config.epsilon

    budget_used = cumulative_epsilon
    budget_remaining = max(0.0, PRIVACY_BUDGET_DEFAULT - budget_used)
    safe = budget_remaining > 0

    return CohortReport(
        cohort_size=len(values),
        metric_name=metric_name,
        dp_results=dp_results,
        total_privacy_budget=PRIVACY_BUDGET_DEFAULT,
        budget_remaining=round(budget_remaining, 6),
        safe_to_release=safe,
    )


def check_privacy_budget(epsilon_used: float, epsilon_total: float) -> dict:
    """Return budget status: remaining, fraction used, safe to continue."""
    remaining = max(0.0, epsilon_total - epsilon_used)
    fraction_used = epsilon_used / epsilon_total if epsilon_total > 0 else 1.0
    return {
        "epsilon_total": epsilon_total,
        "epsilon_used": epsilon_used,
        "epsilon_remaining": round(remaining, 6),
        "fraction_used": round(fraction_used, 6),
        "safe_to_continue": remaining > 0,
        "budget_exhausted": remaining <= 0,
    }


class PrivacyAccountant:
    """Tracks cumulative privacy budget (epsilon) across DP queries."""

    def __init__(self, total_budget: float = 10.0) -> None:
        self._total = total_budget
        self._spent = 0.0
        self._history: list[float] = []

    def spend(self, epsilon: float) -> bool:
        """Deduct epsilon from budget. Returns True if budget was available."""
        if epsilon <= 0:
            raise ValueError("epsilon to spend must be positive")
        if self._spent + epsilon > self._total + 1e-12:
            return False
        self._spent = round(self._spent + epsilon, 12)
        self._history.append(epsilon)
        return True

    def remaining(self) -> float:
        return max(0.0, round(self._total - self._spent, 12))

    def reset(self) -> None:
        self._spent = 0.0
        self._history = []

    def get_report(self) -> dict:
        return {
            "total_budget": self._total,
            "spent": round(self._spent, 12),
            "remaining": self.remaining(),
            "num_queries": len(self._history),
            "history": list(self._history),
            "budget_exhausted": self.remaining() <= 0,
        }
