"""FoldAgent Ensemble Prediction Module.

Provides multi-backend ensemble scoring and backend comparison utilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.alphafold_backends import (
    PredictionResult,
    get_backend,
    predict_with_cache,
)


@dataclass
class EnsembleResult:
    backends_used: list[str]
    results: list[PredictionResult]
    consensus_plddt: float | None
    agreement_score: float
    best_result: PredictionResult


def _mean_plddt(result: PredictionResult) -> float | None:
    """Extract mean pLDDT from a prediction result's confidence dict."""
    val = result.confidence.get("pLDDT_mean")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _plddt_correlation(values: list[float]) -> float:
    """Compute normalized agreement score (1 - CV) from a list of pLDDT values.

    Uses coefficient of variation as a proxy for structural agreement.
    Returns 1.0 when all backends agree perfectly, lower when they diverge.
    """
    if len(values) < 2:
        return 1.0
    n = len(values)
    mean = sum(values) / n
    if mean == 0.0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance**0.5
    cv = std / mean  # coefficient of variation
    # Convert: perfect agreement → 1.0, high disagreement → 0.0 (clamp at 0)
    return max(0.0, round(1.0 - cv, 4))


def run_ensemble(
    sequence: str,
    backends: list[str],
    options: dict,
) -> EnsembleResult:
    """Run prediction on each backend and compute ensemble consensus metrics.

    Args:
        sequence: amino-acid sequence string
        backends: list of backend names to run
        options: prediction options forwarded to each backend

    Returns:
        EnsembleResult with per-backend results and consensus metrics.

    Raises:
        ValueError: if no backends specified or none produce results.
        KeyError: if an unknown backend name is given.
    """
    if not backends:
        raise ValueError("backends list must not be empty")

    results: list[PredictionResult] = []
    errors: list[str] = []

    for name in backends:
        backend = get_backend(name)  # KeyError if unknown
        try:
            result = predict_with_cache(backend, sequence, options)
            results.append(result)
        except (NotImplementedError, RuntimeError) as exc:
            errors.append(f"{name}: {exc}")

    if not results:
        raise RuntimeError(f"All backends failed: {errors}")

    # Consensus pLDDT — average across backends that report it
    plddt_values = [v for r in results if (v := _mean_plddt(r)) is not None]
    consensus_plddt: float | None = (
        round(sum(plddt_values) / len(plddt_values), 4) if plddt_values else None
    )

    agreement_score = _plddt_correlation(plddt_values) if len(plddt_values) >= 2 else 1.0

    # Best result — highest mean pLDDT; fall back to first result if none report it
    best_result = max(
        results,
        key=lambda r: _mean_plddt(r) if _mean_plddt(r) is not None else -1.0,
    )

    return EnsembleResult(
        backends_used=[r.backend_name for r in results],
        results=results,
        consensus_plddt=consensus_plddt,
        agreement_score=agreement_score,
        best_result=best_result,
    )


def compare_backends(
    sequence: str,
    backends: list[str],
) -> dict:
    """Run all specified backends and return a per-backend comparison table.

    Args:
        sequence: amino-acid sequence string
        backends: list of backend names to compare

    Returns:
        dict with 'backends' list (per-backend stats) and summary fields.
    """
    if not backends:
        raise ValueError("backends list must not be empty")

    rows: list[dict] = []
    for name in backends:
        backend = get_backend(name)
        t0 = time.monotonic()
        try:
            result = predict_with_cache(backend, sequence, {})
            rows.append(
                {
                    "backend": name,
                    "available": True,
                    "pLDDT_mean": result.confidence.get("pLDDT_mean"),
                    "pTM": result.confidence.get("pTM"),
                    "duration_seconds": result.duration_seconds,
                    "cached": result.cached,
                    "error": None,
                }
            )
        except (NotImplementedError, RuntimeError) as exc:
            rows.append(
                {
                    "backend": name,
                    "available": False,
                    "pLDDT_mean": None,
                    "pTM": None,
                    "duration_seconds": round(time.monotonic() - t0, 4),
                    "cached": False,
                    "error": str(exc),
                }
            )

    successful = [r for r in rows if r["available"]]
    plddt_values = [r["pLDDT_mean"] for r in successful if r["pLDDT_mean"] is not None]

    return {
        "backends": rows,
        "total_backends": len(rows),
        "successful": len(successful),
        "failed": len(rows) - len(successful),
        "best_backend": (
            max(successful, key=lambda r: r["pLDDT_mean"] or -1.0)["backend"]
            if successful
            else None
        ),
        "consensus_plddt": (
            round(sum(plddt_values) / len(plddt_values), 4) if plddt_values else None
        ),
    }
