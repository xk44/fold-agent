"""Autoresearch metric configuration.

Defines the hard boundary between software metrics that autoresearch is
permitted to optimize and clinical/safety metrics that are permanently
prohibited. This boundary is enforced programmatically — it is not advisory.

RESEARCH ONLY — NOT FOR CLINICAL USE.
"""

from __future__ import annotations

from enum import Enum


class MetricCategory(str, Enum):
    allowed = "allowed"
    prohibited = "prohibited"


# Metrics autoresearch MAY optimize (software / infrastructure only)
ALLOWED_METRICS: list[str] = [
    "pipeline_execution_time_s",
    "step_execution_time_s",
    "memory_usage_mb",
    "memory_peak_mb",
    "step_success_rate",
    "candidate_count",
    "annotation_completeness",
    "cache_hit_rate",
    "prediction_throughput",
    "test_pass_rate",
    "code_coverage",
]

# Metrics autoresearch MUST NEVER optimize (clinical / safety)
PROHIBITED_METRICS: list[str] = [
    "clinical_outcome",
    "treatment_efficacy",
    "survival_rate",
    "overall_survival",
    "progression_free_survival",
    "binding_affinity_threshold",
    "immunogenicity_threshold",
    "safety_gate_pass_rate",
    "preflight_pass_rate",
    "mrna_gate_pass_rate",
    "patient_selection_criteria",
    "animal_selection_criteria",
    "dosage_parameter",
    "treatment_dose",
    "formulation_parameter",
    "injection_volume",
    "adverse_event_rate",
]


def is_metric_allowed(metric_name: str) -> bool:
    """Return True if *metric_name* is in the allowed set.

    Exact match only — substring matching is intentionally avoided to prevent
    gaming via name variants.
    """
    return metric_name in ALLOWED_METRICS


def get_all_metrics() -> dict[str, list[str]]:
    """Return all metrics grouped by category."""
    return {
        MetricCategory.allowed: list(ALLOWED_METRICS),
        MetricCategory.prohibited: list(PROHIBITED_METRICS),
    }
