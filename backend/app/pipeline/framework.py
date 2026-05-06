"""Phase 5 Pipeline Step Framework.

Provides abstract base, concrete step stubs, runner, error handling, and retry
utilities for the FoldAgent bioinformatics pipeline.
"""

from __future__ import annotations

import functools
import logging
import re
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO
from typing import Any

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


def _run_subprocess(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """Run a subprocess, returning (returncode, stdout, stderr).

    Never raises — all errors are surfaced via the return values.
    """
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        return -1, exc.stdout or "", exc.stderr or f"timed out after {timeout}s"
    except OSError as exc:
        return -1, "", str(exc)


class AlignmentStep(PipelineStep):
    """BWA MEM alignment wrapper."""

    @property
    def name(self) -> str:
        return "alignment"

    @property
    def description(self) -> str:
        return "Align reads to reference genome using BWA MEM"

    def execute(self, input_data: dict) -> dict:
        fallback = {
            "tool": "bwa",
            "version": "unknown",
            "aligned_bam": "output.bam",
            "mapping_rate": 0.98,
            "fallback": True,
        }

        bwa_path = shutil.which("bwa")
        if not bwa_path:
            return fallback

        reference = input_data.get("reference")
        fastq_1 = input_data.get("fastq_1")
        if not reference or not fastq_1:
            return {**fallback, "error": "missing 'reference' or 'fastq_1' in input_data"}

        cmd = [bwa_path, "mem"]
        threads = input_data.get("threads")
        if threads:
            cmd.extend(["-t", str(threads)])
        read_group = input_data.get("read_group")
        if read_group:
            cmd.extend(["-R", read_group])
        cmd.append(reference)
        cmd.append(fastq_1)
        fastq_2 = input_data.get("fastq_2")
        if fastq_2:
            cmd.append(fastq_2)

        output_bam = input_data.get("output_bam", "output.bam")

        samtools_path = shutil.which("samtools")
        if not samtools_path:
            return {**fallback, "error": "samtools not found on PATH"}

        # Pipe: bwa mem ... | samtools sort -o output.bam
        # Use two Popen objects to avoid shell=True
        timeout = input_data.get("timeout_seconds", 3600)
        try:
            bwa_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            sort_proc = subprocess.Popen(
                [samtools_path, "sort", "-o", output_bam],
                stdin=bwa_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Allow bwa_proc to receive SIGPIPE if sort_proc exits early
            bwa_proc.stdout.close()  # type: ignore[union-attr]
            sort_stdout, sort_stderr = sort_proc.communicate(timeout=timeout)
            bwa_proc.wait(timeout=10)
            bwa_stderr = bwa_proc.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
            rc_bwa = bwa_proc.returncode
            rc_sort = sort_proc.returncode
        except subprocess.TimeoutExpired:
            return {
                "tool": "bwa",
                "error": "bwa mem | samtools sort timed out",
                "fallback": False,
            }
        except OSError as exc:
            return {
                "tool": "bwa",
                "error": str(exc),
                "fallback": False,
            }

        stderr = bwa_stderr
        if rc_bwa != 0:
            return {
                "tool": "bwa",
                "error": f"bwa mem exited with code {rc_bwa}",
                "stderr": stderr,
                "fallback": False,
            }
        if rc_sort != 0:
            return {
                "tool": "bwa",
                "error": f"samtools sort exited with code {rc_sort}",
                "stderr": sort_stderr.decode(errors="replace"),
                "fallback": False,
            }

        import os

        if not os.path.exists(output_bam):
            return {
                "tool": "bwa",
                "error": f"expected BAM not found after sort: {output_bam}",
                "fallback": False,
            }

        # Index the BAM
        idx_rc, _, idx_err = _run_subprocess([samtools_path, "index", output_bam], timeout=300)
        if idx_rc != 0:
            logger.warning("samtools index failed: %s", idx_err)

        # Parse mapping rate from bwa mem stderr summary lines like:
        #   "N reads; of these: ... N (X%) were mapped"
        mapping_rate = 0.0
        for line in stderr.splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)\s*%.*mapped", line, re.IGNORECASE)
            if m:
                try:
                    mapping_rate = float(m.group(1)) / 100.0
                except ValueError:
                    pass
                break

        return {
            "tool": "bwa",
            "aligned_bam": output_bam,
            "mapping_rate": mapping_rate,
            "stdout": "",
            "stderr": stderr,
            "fallback": False,
        }


class VariantCallingStep(PipelineStep):
    """Mutect2 somatic variant calling wrapper."""

    @property
    def name(self) -> str:
        return "variant_calling"

    @property
    def description(self) -> str:
        return "Call somatic variants using GATK Mutect2"

    def execute(self, input_data: dict) -> dict:
        fallback = {
            "tool": "gatk-mutect2",
            "version": "unknown",
            "variants_vcf": "variants.vcf",
            "somatic_variants": 0,
            "fallback": True,
        }

        gatk_path = shutil.which("gatk")
        if not gatk_path:
            return fallback

        input_bam = input_data.get("aligned_bam") or input_data.get("input_bam")
        if not input_bam:
            return {**fallback, "error": "missing 'aligned_bam' or 'input_bam' in input_data"}

        output_vcf = input_data.get("output_vcf", "variants.vcf")
        cmd = [gatk_path, "Mutect2", "-I", input_bam, "-O", output_vcf]

        reference = input_data.get("reference")
        if reference:
            cmd.extend(["-R", reference])
        normal_bam = input_data.get("normal_bam")
        if normal_bam:
            # --normal-sample expects a sample name, not a BAM path.
            # Prefer explicit normal_sample field; fall back to extracting from
            # the BAM @RG SM: tag; if samtools is unavailable, default to "NORMAL".
            normal_sample = input_data.get("normal_sample")
            if not normal_sample:
                samtools_path = shutil.which("samtools")
                if samtools_path:
                    try:
                        rg_result = subprocess.run(
                            [samtools_path, "view", "-H", normal_bam],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            check=False,
                        )
                        for rg_line in rg_result.stdout.splitlines():
                            if rg_line.startswith("@RG"):
                                for field in rg_line.split("\t"):
                                    if field.startswith("SM:"):
                                        normal_sample = field[3:].strip()
                                        break
                            if normal_sample:
                                break
                    except (OSError, subprocess.TimeoutExpired):
                        pass
            if not normal_sample:
                normal_sample = "NORMAL"
            cmd.extend(["-I", normal_bam, "--normal-sample", normal_sample])
        tumor_sample = input_data.get("tumor_sample")
        if tumor_sample:
            cmd.extend(["--tumor-sample", tumor_sample])
        intervals = input_data.get("intervals")
        if intervals:
            cmd.extend(["-L", intervals])
        panel_of_normals = input_data.get("panel_of_normals")
        if panel_of_normals:
            cmd.extend(["--panel-of-normals", panel_of_normals])
        germline_resource = input_data.get("germline_resource")
        if germline_resource:
            cmd.extend(["--germline-resource", germline_resource])

        rc, stdout, stderr = _run_subprocess(cmd, timeout=input_data.get("timeout_seconds", 7200))
        if rc != 0:
            return {
                "tool": "gatk-mutect2",
                "error": f"gatk Mutect2 exited with code {rc}",
                "stderr": stderr,
                "fallback": False,
            }

        # Count variant records from the output VCF file (non-header lines)
        import os

        somatic_count = 0
        if os.path.exists(output_vcf):
            try:
                with open(output_vcf) as _vcf:
                    somatic_count = sum(
                        1 for line in _vcf if line.strip() and not line.startswith("#")
                    )
            except OSError:
                pass
        else:
            logger.warning("Mutect2 output VCF not found: %s", output_vcf)

        return {
            "tool": "gatk-mutect2",
            "variants_vcf": output_vcf,
            "somatic_variants": somatic_count,
            "stdout": stdout,
            "stderr": stderr,
            "fallback": False,
        }


class AnnotationStep(PipelineStep):
    """VEP variant annotation wrapper."""

    @property
    def name(self) -> str:
        return "annotation"

    @property
    def description(self) -> str:
        return "Annotate variants using Ensembl VEP"

    def execute(self, input_data: dict) -> dict:
        fallback = {
            "tool": "vep",
            "version": "unknown",
            "annotated_vcf": "annotated.vcf",
            "annotated_variants": 0,
            "fallback": True,
        }

        vep_path = shutil.which("vep")
        if not vep_path:
            return fallback

        input_vcf = input_data.get("variants_vcf") or input_data.get("input_vcf")
        if not input_vcf:
            return {**fallback, "error": "missing 'variants_vcf' or 'input_vcf' in input_data"}

        output_vcf = input_data.get("annotated_vcf", "annotated.vcf")
        cmd = [vep_path, "--input_file", input_vcf, "--output_file", output_vcf]

        cache_dir = input_data.get("cache_dir")
        if cache_dir:
            cmd.extend(["--dir_cache", cache_dir])
        assembly = input_data.get("assembly")
        if assembly:
            cmd.extend(["--assembly", assembly])
        fork = input_data.get("fork")
        if fork:
            cmd.extend(["--fork", str(fork)])
        if input_data.get("everything"):
            cmd.append("--everything")
        if input_data.get("hgvs"):
            cmd.append("--hgvs")
        if input_data.get("symbol", True):
            cmd.append("--symbol")
        if input_data.get("canonical", True):
            cmd.append("--canonical")

        rc, stdout, stderr = _run_subprocess(cmd, timeout=input_data.get("timeout_seconds", 3600))
        if rc != 0:
            return {
                "tool": "vep",
                "error": f"vep exited with code {rc}",
                "stderr": stderr,
                "fallback": False,
            }

        # VEP writes output to a file; count annotated variants from the output file.
        # Fall back to parsing "Lines of output written: N" from stderr.
        import os

        annotated_count = 0
        if os.path.exists(output_vcf):
            try:
                with open(output_vcf) as _vcf:
                    annotated_count = sum(
                        1 for line in _vcf if line.strip() and not line.startswith("#")
                    )
            except OSError:
                pass
        else:
            logger.warning("VEP output file not found: %s", output_vcf)
            # Try to parse "Lines of output written: N" from stderr as fallback
            for line in stderr.splitlines():
                m = re.search(r"Lines of output written:\s*(\d+)", line, re.IGNORECASE)
                if m:
                    try:
                        annotated_count = int(m.group(1))
                    except ValueError:
                        pass
                    break

        return {
            "tool": "vep",
            "annotated_vcf": output_vcf,
            "annotated_variants": annotated_count,
            "stdout": stdout,
            "stderr": stderr,
            "fallback": False,
        }


def _parse_netmhcpan_output(stdout: str) -> list[dict]:
    """Parse NetMHCpan tab-separated prediction output.

    NetMHCpan writes rows like:
      Pos  HLA          Peptide    ... IC50   %Rank_EL  ...
    Returns a list of prediction dicts.
    """
    predictions: list[dict] = []
    in_data = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Header row detection
        if "Peptide" in line and "IC50" in line:
            in_data = True
            continue
        if not in_data:
            continue
        # Skip separator rows (dashes)
        if set(line.replace(" ", "").replace("-", "")) == set():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            predictions.append(
                {
                    "allele": parts[1] if len(parts) > 1 else "unknown",
                    "peptide": parts[2] if len(parts) > 2 else "",
                    "ic50": float(parts[-3]) if len(parts) > 3 else 0.0,
                    "rank": float(parts[-2]) if len(parts) > 2 else 1.0,
                }
            )
        except (ValueError, IndexError):
            continue
    return predictions


class BindingPredictionStep(PipelineStep):
    """NetMHCpan MHC class I binding prediction wrapper."""

    @property
    def name(self) -> str:
        return "binding_prediction"

    @property
    def description(self) -> str:
        return "Predict MHC class I binding affinity using NetMHCpan"

    def execute(self, input_data: dict) -> dict:
        fallback = {
            "tool": "netMHCpan",
            "version": "unknown",
            "candidates": [],
            "fallback": True,
        }

        netmhcpan_path = shutil.which("netMHCpan")
        if not netmhcpan_path:
            return fallback

        peptides: list[str] = input_data.get("peptides", [])
        alleles: list[str] = input_data.get("alleles", [])
        if not peptides or not alleles:
            return {**fallback, "error": "missing 'peptides' or 'alleles' in input_data"}

        # Write peptides to a temp file; always clean up in finally
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pep", delete=False) as pep_file:
                pep_file.write("\n".join(peptides) + "\n")
                pep_path = pep_file.name
        except OSError as exc:
            return {**fallback, "error": f"could not create peptide temp file: {exc}"}

        try:
            cmd = [
                netmhcpan_path,
                "-f",
                pep_path,
                "-a",
                ",".join(alleles),
                "-BA",  # include binding affinity
            ]

            rc, stdout, stderr = _run_subprocess(
                cmd, timeout=input_data.get("timeout_seconds", 1800)
            )
            if rc != 0:
                return {
                    "tool": "netMHCpan",
                    "error": f"netMHCpan exited with code {rc}",
                    "stderr": stderr,
                    "fallback": False,
                }

            candidates = _parse_netmhcpan_output(stdout)
            return {
                "tool": "netMHCpan",
                "candidates": candidates,
                "candidate_count": len(candidates),
                "stdout": stdout,
                "stderr": stderr,
                "fallback": False,
            }
        finally:
            import os as _os

            try:
                _os.unlink(pep_path)
            except OSError:
                pass


def _parse_netmhciipan_output(stdout: str) -> list[dict]:
    """Parse NetMHCIIpan prediction output.

    NetMHCIIpan output rows contain allele, peptide, IC50, and rank columns.
    Returns a list of prediction dicts.
    """
    predictions: list[dict] = []
    in_data = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "Peptide" in line and ("IC50" in line or "Rank" in line):
            in_data = True
            continue
        if not in_data:
            continue
        if set(line.replace(" ", "").replace("-", "")) == set():
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            ic50 = float(parts[-3]) if len(parts) > 3 else 0.0
            rank = float(parts[-2]) if len(parts) > 2 else 1.0
            predictions.append(
                {
                    "allele": parts[0],
                    "peptide": parts[1] if len(parts) > 1 else "",
                    "ic50": ic50,
                    "rank": rank,
                    "strong_binder": ic50 < 500,
                    "weak_binder": ic50 < 2000,
                }
            )
        except (ValueError, IndexError):
            continue
    return predictions


class NetMHCIIpanStep(PipelineStep):
    """NetMHCIIpan MHC class II binding prediction wrapper."""

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

        netmhciipan_path = shutil.which("netMHCIIpan")
        if not netmhciipan_path:
            # Fallback: deterministic mock scores
            predictions = []
            for allele in alleles:
                for i, peptide in enumerate(peptides):
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
                "version": "unknown",
                "predictions": predictions,
                "peptide_count": len(peptides),
                "allele_count": len(alleles),
                "fallback": True,
            }

        # Write peptides to a temp file; always clean up in finally
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pep", delete=False) as pep_file:
                pep_file.write("\n".join(peptides) + "\n")
                pep_path = pep_file.name
        except OSError as exc:
            return {
                "tool": "netmhciipan",
                "error": f"could not create peptide temp file: {exc}",
                "fallback": False,
            }

        try:
            cmd = [
                netmhciipan_path,
                "-f",
                pep_path,
                "-a",
                ",".join(alleles),
                "-BA",
            ]

            rc, stdout, stderr = _run_subprocess(
                cmd, timeout=input_data.get("timeout_seconds", 1800)
            )
            if rc != 0:
                return {
                    "tool": "netmhciipan",
                    "error": f"netMHCIIpan exited with code {rc}",
                    "stderr": stderr,
                    "fallback": False,
                }

            predictions = _parse_netmhciipan_output(stdout)
            return {
                "tool": "netmhciipan",
                "predictions": predictions,
                "peptide_count": len(peptides),
                "allele_count": len(alleles),
                "stdout": stdout,
                "stderr": stderr,
                "fallback": False,
            }
        finally:
            import os as _os

            try:
                _os.unlink(pep_path)
            except OSError:
                pass


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
                raise TypeError(
                    f"TPM value for gene '{gene}' must be numeric, got {type(tpm).__name__}"
                )
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

        # Collect binding predictions from prior steps (class I and class II)
        class1_preds: list[dict] = input_data.get("candidates", [])  # BindingPredictionStep
        class2_preds: list[dict] = input_data.get("predictions", [])  # NetMHCIIpanStep
        all_preds = class1_preds + class2_preds

        # Build per-allele binding summary from available predictions
        allele_binding: dict[str, dict] = {}
        for pred in all_preds:
            allele = pred.get("allele", "")
            if not allele:
                continue
            entry = allele_binding.setdefault(
                allele,
                {
                    "prediction_count": 0,
                    "strong_binders": 0,
                    "weak_binders": 0,
                    "best_ic50": float("inf"),
                    "best_rank": float("inf"),
                },
            )
            entry["prediction_count"] += 1
            ic50 = pred.get("ic50", float("inf"))
            rank = pred.get("rank", float("inf"))
            if ic50 < entry["best_ic50"]:
                entry["best_ic50"] = ic50
            if rank < entry["best_rank"]:
                entry["best_rank"] = rank
            if pred.get("strong_binder"):
                entry["strong_binders"] += 1
            if pred.get("weak_binder"):
                entry["weak_binders"] += 1

        metadata: list[dict[str, Any]] = []
        for allele in alleles:
            locus = _parse_locus(allele)
            supertype = lookup.get(allele, "unknown")
            entry: dict[str, Any] = {
                "allele": allele,
                "locus": locus,
                "species": resolved_species,
                "supertype": supertype,
                "known": allele in lookup,
            }
            if allele in allele_binding:
                binding = allele_binding[allele]
                entry["binding_summary"] = {
                    "prediction_count": binding["prediction_count"],
                    "strong_binders": binding["strong_binders"],
                    "weak_binders": binding["weak_binders"],
                    "best_ic50": binding["best_ic50"]
                    if binding["best_ic50"] != float("inf")
                    else None,
                    "best_rank": binding["best_rank"]
                    if binding["best_rank"] != float("inf")
                    else None,
                }
            metadata.append(entry)

        return {
            "species": resolved_species,
            "allele_metadata": metadata,
            "allele_count": len(alleles),
            "known_count": sum(1 for m in metadata if m["known"]),
            "alleles_with_binding_data": sum(1 for m in metadata if "binding_summary" in m),
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
                for remaining in self.steps[len(results) :]:
                    results.append(StepResult(step_name=remaining.name, status="skipped"))
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
        future_to_idx = {pool.submit(step.run, context): idx for idx, step in enumerate(steps)}
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
