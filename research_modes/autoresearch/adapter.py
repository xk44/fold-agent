"""Autoresearch adapter.

Karpathy-inspired agent loop adapter: proposes small, verifiable software
optimization experiments, evaluates results, and enforces the hard boundary
between allowed and prohibited metrics.

RESEARCH ONLY — NOT FOR CLINICAL USE.
"""

from __future__ import annotations

import uuid
from typing import Any

from research_modes.autoresearch.config import (
    PROHIBITED_METRICS,
    is_metric_allowed,
)


class AutoresearchAdapter:
    """Propose, evaluate, and safety-gate autoresearch experiments.

    The adapter follows Karpathy's autoresearch pattern:
    - Keep proposals small and verifiable.
    - Only optimize what you can measure safely.
    - Never let the optimizer redefine the measurement criteria.

    The ``is_safe()`` check is the hard gate — any proposal that touches a
    prohibited metric is refused before any code runs.
    """

    # ------------------------------------------------------------------
    # Proposal
    # ------------------------------------------------------------------

    def propose_experiment(
        self, metric: str, current_value: float
    ) -> dict[str, Any]:
        """Suggest an optimization experiment for *metric*.

        This is a stub implementation that returns a structured proposal.
        Real implementations would invoke an LLM or search procedure here.

        Returns
        -------
        dict with keys:
            - ``experiment_id`` (str): UUID for tracking.
            - ``metric`` (str): Metric being targeted.
            - ``current_value`` (float): Baseline value.
            - ``hypothesis`` (str): Plain-English description.
            - ``proposed_change`` (str): What to modify.
            - ``blocked`` (bool): True if metric is prohibited.
            - ``block_reason`` (str | None): Why it was blocked.
        """
        experiment_id = str(uuid.uuid4())

        if not is_metric_allowed(metric):
            return {
                "experiment_id": experiment_id,
                "metric": metric,
                "current_value": current_value,
                "hypothesis": None,
                "proposed_change": None,
                "blocked": True,
                "block_reason": (
                    f"Metric '{metric}' is prohibited. "
                    "Autoresearch may only optimize software/infrastructure metrics."
                ),
            }

        # Stub: generate a generic proposal
        hypothesis = (
            f"Reducing overhead in the step that drives '{metric}' "
            f"from {current_value:.4g} may improve performance."
        )
        proposed_change = (
            f"Profile the pipeline step that most contributes to '{metric}' "
            "and apply caching or parallelism where safe."
        )

        return {
            "experiment_id": experiment_id,
            "metric": metric,
            "current_value": current_value,
            "hypothesis": hypothesis,
            "proposed_change": proposed_change,
            "blocked": False,
            "block_reason": None,
        }

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_experiment(
        self, experiment_id: str, results: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate the outcome of a completed experiment.

        Parameters
        ----------
        experiment_id:
            The UUID returned by :meth:`propose_experiment`.
        results:
            Dict containing at minimum ``metric``, ``before``, ``after``,
            ``test_passed`` (bool), and optionally ``notes``.

        Returns
        -------
        dict with keys:
            - ``experiment_id``
            - ``metric``
            - ``improvement`` (float): after - before (negative = better for time/memory)
            - ``improvement_pct`` (float | None)
            - ``recommendation`` (str): "accept" | "reject" | "inconclusive"
            - ``test_passed`` (bool)
        """
        metric = results.get("metric", "unknown")
        before = float(results.get("before", 0.0))
        after = float(results.get("after", 0.0))
        test_passed = bool(results.get("test_passed", False))

        improvement = after - before
        improvement_pct: float | None = None
        if before != 0.0:
            improvement_pct = (improvement / abs(before)) * 100.0

        # For time/memory metrics, lower is better
        lower_is_better = any(
            kw in metric for kw in ("time", "memory", "usage")
        )
        improved = (improvement < 0) if lower_is_better else (improvement > 0)

        if not test_passed:
            recommendation = "reject"
        elif improved:
            recommendation = "accept"
        else:
            recommendation = "inconclusive"

        return {
            "experiment_id": experiment_id,
            "metric": metric,
            "improvement": improvement,
            "improvement_pct": improvement_pct,
            "recommendation": recommendation,
            "test_passed": test_passed,
        }

    # ------------------------------------------------------------------
    # Safety gate
    # ------------------------------------------------------------------

    def is_safe(self, proposal: dict[str, Any]) -> bool:
        """Return True only if the proposal does not touch prohibited metrics.

        Checks:
        1. The proposal's ``blocked`` flag.
        2. The ``metric`` field against the prohibited list.
        3. Any ``proposed_change`` text for references to prohibited metrics.
        """
        if proposal.get("blocked", False):
            return False

        metric = proposal.get("metric", "")
        if not is_metric_allowed(metric):
            return False

        # Guard against free-text references to prohibited metrics
        proposed_change = str(proposal.get("proposed_change") or "").lower()
        for prohibited in PROHIBITED_METRICS:
            if prohibited.replace("_", " ") in proposed_change:
                return False

        return True
