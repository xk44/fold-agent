"""Phase 5 Pipeline Step Framework.

Provides abstract base, concrete step stubs, runner, error handling, and retry
utilities for the FoldAgent bioinformatics pipeline.
"""

from __future__ import annotations

import time
import functools
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PipelineError(Exception):
    """Base exception for pipeline errors."""


class StepFailedError(PipelineError):
    """Raised when a pipeline step fails."""


class StepTimeoutError(PipelineError, TimeoutError):
    """Raised when a pipeline step times out."""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class ErrorCategory(str, Enum):
    input_error = "input_error"
    tool_missing = "tool_missing"
    runtime_error = "runtime_error"
    timeout = "timeout"
    resource_error = "resource_error"


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Result from executing a pipeline step."""

    step_name: str
    status: str  # "success" | "failed" | "skipped"
    output: dict = field(default_factory=dict)
    error: str | None = None
    duration_seconds: float | None = None
    stdout: str = ""
    stderr: str = ""
    error_category: ErrorCategory | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_category": self.error_category.value if self.error_category else None,
        }


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


def with_retry(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (RuntimeError, TimeoutError),
) -> Callable:
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of total attempts (including the first).
        backoff_factor: Multiplier for the wait time between retries.
        retry_on: Exception types that trigger a retry.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = 1.0
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        logger.debug(
                            "Retrying %s after attempt %d (delay %.1fs): %s",
                            getattr(func, "__name__", func),
                            attempt + 1,
                            delay,
                            exc,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class PipelineStep(ABC):
    """Abstract base class for all Phase 5 pipeline steps."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this step."""

    @property
    def description(self) -> str:
        """Human-readable description of this step."""
        return ""

    @abstractmethod
    def execute(self, input_data: dict) -> dict:
        """Run the step logic.

        Args:
            input_data: Inputs from the pipeline context.

        Returns:
            Output dictionary to be merged into the pipeline context.
        """

    def run(self, input_data: dict) -> StepResult:
        """Execute the step with timing, error handling, and stream capture."""
        stdout_buf = StringIO()
        stderr_buf = StringIO()
        start = time.monotonic()
        try:
            output = self.execute(input_data)
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="success",
                output=output,
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
            )
        except StepTimeoutError as exc:
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="failed",
                error=str(exc),
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                error_category=ErrorCategory.timeout,
            )
        except FileNotFoundError as exc:
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="failed",
                error=str(exc),
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                error_category=ErrorCategory.tool_missing,
            )
        except (ValueError, TypeError, KeyError) as exc:
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="failed",
                error=str(exc),
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                error_category=ErrorCategory.input_error,
            )
        except MemoryError as exc:
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="failed",
                error=str(exc),
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                error_category=ErrorCategory.resource_error,
            )
        except Exception as exc:  # noqa: BLE001
            duration = time.monotonic() - start
            return StepResult(
                step_name=self.name,
                status="failed",
                error=str(exc),
                duration_seconds=round(duration, 4),
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                error_category=ErrorCategory.runtime_error,
            )


# ---------------------------------------------------------------------------
# Concrete step stubs
# ---------------------------------------------------------------------------


class AlignmentStep(PipelineStep):
    """BWA-MEM2 alignment wrapper stub."""

    @property
    def name(self) -> str:
        return "alignment"

    @property
    def description(self) -> str:
        return "Align reads to reference genome using BWA-MEM2 (stub)"

    def execute(self, input_data: dict) -> dict:
        return {
            "tool": "bwa-mem2",
            "version": "2.2.1",
            "aligned_bam": "output.bam",
            "mapping_rate": 0.98,
            "note": "BWA-MEM2 stub — no real alignment performed",
        }


class VariantCallingStep(PipelineStep):
    """Mutect2 somatic variant calling wrapper stub."""

    @property
    def name(self) -> str:
        return "variant_calling"

    @property
    def description(self) -> str:
        return "Call somatic variants using GATK Mutect2 (stub)"

    def execute(self, input_data: dict) -> dict:
        return {
            "tool": "gatk-mutect2",
            "version": "4.4.0",
            "variants_vcf": "variants.vcf",
            "somatic_variants": 0,
            "note": "Mutect2 stub — no real variant calling performed",
        }


class AnnotationStep(PipelineStep):
    """VEP variant annotation wrapper stub."""

    @property
    def name(self) -> str:
        return "annotation"

    @property
    def description(self) -> str:
        return "Annotate variants using Ensembl VEP (stub)"

    def execute(self, input_data: dict) -> dict:
        return {
            "tool": "vep",
            "version": "111",
            "annotated_vcf": "annotated.vcf",
            "annotated_variants": 0,
            "note": "VEP stub — no real annotation performed",
        }


class BindingPredictionStep(PipelineStep):
    """NetMHCpan / pVACtools neoantigen binding prediction wrapper stub."""

    @property
    def name(self) -> str:
        return "binding_prediction"

    @property
    def description(self) -> str:
        return "Predict MHC binding affinity using NetMHCpan/pVACtools (stub)"

    def execute(self, input_data: dict) -> dict:
        return {
            "tool": "pvactools",
            "version": "4.0.0",
            "candidates": [],
            "note": "NetMHCpan/pVACtools stub — no real binding prediction performed",
        }


class NetMHCIIpanStep(PipelineStep):
    """NetMHCIIpan MHC class II binding prediction wrapper stub."""

    @property
    def name(self) -> str:
        return "netmhciipan"

    @property
    def description(self) -> str:
        return "NetMHCIIpan — MHC class II binding prediction"

    def execute(self, input_data: dict) -> dict:
        if "peptides" not in input_data:
            raise ValueError("Missing required input field: 'peptides'")
        if "alleles" not in input_data:
            raise ValueError("Missing required input field: 'alleles'")

        peptides: list[str] = input_data["peptides"]
        alleles: list[str] = input_data["alleles"]

        if not isinstance(peptides, list):
            raise TypeError("'peptides' must be a list")
        if not isinstance(alleles, list):
            raise TypeError("'alleles' must be a list")

        predictions = []
        for allele in alleles:
            for i, peptide in enumerate(peptides):
                # Deterministic mock scores based on string lengths
                ic50 = 50.0 + (len(peptide) * 10.0) + (len(allele) * 2.5)
                rank = round(1.0 / (1.0 + i * 0.5 + len(alleles) * 0.1), 4)
                predictions.append(
                    {
                        "allele": allele,
                        "peptide": peptide,
                        "ic50": round(ic50, 2),
                        "rank": rank,
                        "strong_binder": ic50 < 500,
                        "weak_binder": ic50 < 2000,
                    }
                )

        return {
            "tool": "netmhciipan",
            "version": "4.3",
            "predictions": predictions,
            "peptide_count": len(peptides),
            "allele_count": len(alleles),
            "note": "NetMHCIIpan stub — no real MHC class II binding prediction performed",
        }


class RNAExpressionValidationStep(PipelineStep):
    """RNA-seq expression validation — filters low-expression candidates."""

    #: Genes with TPM below this threshold are flagged as low-expression.
    LOW_EXPRESSION_THRESHOLD: float = 1.0

    @property
    def name(self) -> str:
        return "rna_expression_validation"

    @property
    def description(self) -> str:
        return "RNA expression validation — filters low-expression candidates"

    def execute(self, input_data: dict) -> dict:
        if "expression_data" not in input_data:
            raise ValueError("Missing required input field: 'expression_data'")

        expression_data: dict = input_data["expression_data"]

        if not isinstance(expression_data, dict):
            raise TypeError("'expression_data' must be a dict mapping gene → TPM")

        validated_genes: list[str] = []
        low_expression_genes: list[str] = []

        for gene, tpm in expression_data.items():
            if not isinstance(tpm, (int, float)):
                raise TypeError(f"TPM value for gene '{gene}' must be numeric, got {type(tpm).__name__}")
            if tpm >= self.LOW_EXPRESSION_THRESHOLD:
                validated_genes.append(gene)
            else:
                low_expression_genes.append(gene)

        return {
            "validated_genes": validated_genes,
            "low_expression_genes": low_expression_genes,
            "filtered_count": len(low_expression_genes),
            "total_genes": len(expression_data),
            "threshold_tpm": self.LOW_EXPRESSION_THRESHOLD,
            "note": "RNA expression validation stub — TPM threshold applied",
        }


# ---------------------------------------------------------------------------
# MHC/HLA/DLA allele lookup tables
# ---------------------------------------------------------------------------

_HLA_SUPERTYPES: dict[str, str] = {
    "HLA-DRB1*01:01": "DR1",
    "HLA-DRB1*03:01": "DR3",
    "HLA-DRB1*04:01": "DR4",
    "HLA-DRB1*07:01": "DR7",
    "HLA-DRB1*11:01": "DR11",
    "HLA-DRB1*13:01": "DR13",
    "HLA-DRB1*15:01": "DR15",
    "HLA-DQA1*01:01": "DQ1",
    "HLA-DQB1*02:01": "DQ2",
    "HLA-DQB1*03:01": "DQ3",
    "HLA-DPB1*02:01": "DP2",
    "HLA-DPB1*04:01": "DP4",
}

_DLA_SUPERTYPES: dict[str, str] = {
    "DLA-DRB1*001:01": "DLA-DR1",
    "DLA-DRB1*002:01": "DLA-DR2",
    "DLA-DRB1*009:01": "DLA-DR9",
    "DLA-DQA1*001:01": "DLA-DQ1",
    "DLA-DQB1*002:01": "DLA-DQ2",
    "DLA-DPB1*001:01": "DLA-DP1",
}

_LOCUS_PATTERN_MAP: list[tuple[str, str]] = [
    ("DRB1", "DRB1"),
    ("DQA1", "DQA1"),
    ("DQB1", "DQB1"),
    ("DPB1", "DPB1"),
    ("DPA1", "DPA1"),
]


def _parse_locus(allele: str) -> str:
    """Extract locus identifier from an allele string."""
    for key, locus in _LOCUS_PATTERN_MAP:
        if key in allele:
            return locus
    return "unknown"


class MHCMetadataStep(PipelineStep):
    """MHC/HLA/DLA allele metadata lookup stub."""

    @property
    def name(self) -> str:
        return "mhc_metadata"

    @property
    def description(self) -> str:
        return "MHC/HLA/DLA metadata — allele classification and supertype lookup"

    def execute(self, input_data: dict) -> dict:
        if "species" not in input_data:
            raise ValueError("Missing required input field: 'species'")
        if "alleles" not in input_data:
            raise ValueError("Missing required input field: 'alleles'")

        species: str = input_data["species"]
        alleles: list[str] = input_data["alleles"]

        if not isinstance(alleles, list):
            raise TypeError("'alleles' must be a list of allele strings")

        species_lower = species.lower()
        if species_lower in ("human", "homo_sapiens", "homo sapiens"):
            lookup = _HLA_SUPERTYPES
            resolved_species = "human"
        elif species_lower in ("dog", "canis_lupus_familiaris", "canis lupus familiaris", "canine"):
            lookup = _DLA_SUPERTYPES
            resolved_species = "dog"
        else:
            lookup = {}
            resolved_species = species

        metadata: list[dict[str, Any]] = []
        for allele in alleles:
            locus = _parse_locus(allele)
            supertype = lookup.get(allele, "unknown")
            metadata.append(
                {
                    "allele": allele,
                    "locus": locus,
                    "species": resolved_species,
                    "supertype": supertype,
                    "known": allele in lookup,
                }
            )

        return {
            "species": resolved_species,
            "allele_metadata": metadata,
            "allele_count": len(alleles),
            "known_count": sum(1 for m in metadata if m["known"]),
            "note": "MHC/HLA/DLA metadata stub — hardcoded lookup tables",
        }


# Ordered list of all stub steps exposed to the API
FRAMEWORK_STEPS: list[PipelineStep] = [
    AlignmentStep(),
    VariantCallingStep(),
    AnnotationStep(),
    BindingPredictionStep(),
    NetMHCIIpanStep(),
    RNAExpressionValidationStep(),
    MHCMetadataStep(),
]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


class PipelineRunner:
    """Runs pipeline steps sequentially, stopping on first failure."""

    def __init__(self, steps: list[PipelineStep]) -> None:
        self.steps = steps

    def run(self, input_data: dict | None = None) -> list[StepResult]:
        """Execute steps in order.

        Args:
            input_data: Initial pipeline context; updated after each step.

        Returns:
            List of StepResult in execution order.
        """
        context = dict(input_data or {})
        results: list[StepResult] = []
        for step in self.steps:
            result = step.run(context)
            results.append(result)
            if result.status == "failed":
                # Mark remaining steps as skipped
                for remaining in self.steps[len(results):]:
                    results.append(
                        StepResult(step_name=remaining.name, status="skipped")
                    )
                break
            context.update(result.output)
        return results


def run_parallel_steps(
    steps: list[PipelineStep],
    input_data: dict | None = None,
    max_workers: int = 4,
) -> list[StepResult]:
    """Run steps concurrently using a ThreadPoolExecutor.

    Steps are independent — each receives the same initial input_data.

    Args:
        steps: Steps to run in parallel.
        input_data: Shared input context passed to every step.
        max_workers: Maximum number of worker threads.

    Returns:
        List of StepResult in submission order.
    """
    context = dict(input_data or {})
    results: list[StepResult | None] = [None] * len(steps)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {
            pool.submit(step.run, context): idx for idx, step in enumerate(steps)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[idx] = StepResult(
                    step_name=steps[idx].name,
                    status="failed",
                    error=str(exc),
                    error_category=ErrorCategory.runtime_error,
                )

    return [r for r in results if r is not None]
