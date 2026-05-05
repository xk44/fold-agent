"""Autoresearch software benchmark.

Runs a set of synthetic pipeline tasks against a running NeoVax API instance
to measure execution time, memory, and success rate. This is a **toy software
benchmark** — it does not process real patient data or produce clinically
meaningful outputs.

RESEARCH ONLY — NOT FOR CLINICAL USE.
"""

from __future__ import annotations

import time
import tracemalloc
from dataclasses import dataclass, field

try:
    import httpx as _httpx  # type: ignore[import-untyped]
    _HAS_HTTPX = True
except ModuleNotFoundError:
    _HAS_HTTPX = False


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    total_time: float
    """Wall-clock seconds for the full benchmark suite."""

    step_times: dict[str, float] = field(default_factory=dict)
    """Per-step wall-clock seconds."""

    memory_peak_mb: float = 0.0
    """Peak RSS memory during the run in megabytes."""

    success_rate: float = 0.0
    """Fraction of synthetic tasks that completed successfully (0.0–1.0)."""

    steps_run: int = 0
    """Total number of steps attempted."""

    steps_passed: int = 0
    """Steps that returned HTTP 2xx."""


# ---------------------------------------------------------------------------
# Benchmark tasks
# ---------------------------------------------------------------------------

_SYNTHETIC_SPECIES = "demo"
_SYNTHETIC_DIAGNOSIS = "Autoresearch synthetic benchmark case"
_SYNTHETIC_SUPERVISOR = "Autoresearch Bot"


def _timed(label: str, fn, step_times: dict[str, float]):
    """Run *fn*, record elapsed time under *label*, return (result, ok)."""
    t0 = time.perf_counter()
    try:
        result = fn()
        elapsed = time.perf_counter() - t0
        step_times[label] = elapsed
        return result, True
    except Exception:
        elapsed = time.perf_counter() - t0
        step_times[label] = elapsed
        return None, False


def run_benchmark(api_base: str) -> BenchmarkResult:
    """Execute the synthetic benchmark suite against *api_base*.

    Performs:
    1. Create a synthetic case
    2. Add a synthetic sample
    3. Trigger a mock pipeline run
    4. Generate a candidate review report

    Returns a :class:`BenchmarkResult` with timing and success metrics.

    If *httpx* is not installed, returns a stub result with
    ``success_rate=0.0`` and a note in ``step_times``.
    """
    if not _HAS_HTTPX:
        return BenchmarkResult(
            total_time=0.0,
            step_times={"error": "httpx not installed"},
            memory_peak_mb=0.0,
            success_rate=0.0,
            steps_run=0,
            steps_passed=0,
        )

    client = _httpx.Client(base_url=api_base, timeout=30.0)
    step_times: dict[str, float] = {}
    steps_run = 0
    steps_passed = 0

    tracemalloc.start()
    wall_start = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Step 1: create case
    # ------------------------------------------------------------------ #
    steps_run += 1
    case_resp, ok = _timed(
        "create_case",
        lambda: client.post(
            "/cases",
            json={
                "species": _SYNTHETIC_SPECIES,
                "diagnosis_summary": _SYNTHETIC_DIAGNOSIS,
                "supervising_professional": _SYNTHETIC_SUPERVISOR,
            },
        ),
        step_times,
    )
    if not ok or case_resp is None or case_resp.status_code >= 300:
        wall_total = time.perf_counter() - wall_start
        _, mem_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return BenchmarkResult(
            total_time=wall_total,
            step_times=step_times,
            memory_peak_mb=mem_peak / 1024 / 1024,
            success_rate=0.0,
            steps_run=steps_run,
            steps_passed=0,
        )
    steps_passed += 1
    case_id: str = case_resp.json()["id"]

    # ------------------------------------------------------------------ #
    # Step 2: add sample
    # ------------------------------------------------------------------ #
    steps_run += 1
    sample_resp, ok = _timed(
        "add_sample",
        lambda: client.post(
            f"/cases/{case_id}/samples",
            json={
                "sample_type": "tumor",
                "collection_date": "2024-01-01",
            },
        ),
        step_times,
    )
    if ok and sample_resp is not None and sample_resp.status_code < 300:
        steps_passed += 1

    # ------------------------------------------------------------------ #
    # Step 3: trigger mock pipeline
    # ------------------------------------------------------------------ #
    steps_run += 1
    pipeline_resp, ok = _timed(
        "run_pipeline",
        lambda: client.post(f"/cases/{case_id}/pipeline/run"),
        step_times,
    )
    if ok and pipeline_resp is not None and pipeline_resp.status_code < 300:
        steps_passed += 1

    # ------------------------------------------------------------------ #
    # Step 4: generate report
    # ------------------------------------------------------------------ #
    steps_run += 1
    report_resp, ok = _timed(
        "generate_report",
        lambda: client.post(f"/cases/{case_id}/reports/candidate-review"),
        step_times,
    )
    if ok and report_resp is not None and report_resp.status_code < 300:
        steps_passed += 1

    # ------------------------------------------------------------------ #
    # Collect results
    # ------------------------------------------------------------------ #
    wall_total = time.perf_counter() - wall_start
    _, mem_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return BenchmarkResult(
        total_time=wall_total,
        step_times=step_times,
        memory_peak_mb=mem_peak / 1024 / 1024,
        success_rate=steps_passed / steps_run if steps_run > 0 else 0.0,
        steps_run=steps_run,
        steps_passed=steps_passed,
    )
