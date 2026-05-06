"""Real bioinformatics adapter shell stubs.

These do not execute tools yet. They expose environment validation and dry-run
command manifests so the mock-first product can evolve into real wrappers.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from shutil import which

from backend.app.config import settings
from backend.app.pipeline.schemas import (
    BwaRequest,
    GatkMutect2Request,
    PvactoolsRequest,
    VepRequest,
)


@dataclass
class ShellAdapterStatus:
    name: str
    command: str
    available: bool
    path: str | None
    validation_ok: bool
    notes: str


@dataclass
class ShellDryRun:
    adapter: str
    mode: str
    command: list[str]
    available: bool
    validation_ok: bool
    notes: str


@dataclass
class ShellExecution:
    adapter: str
    mode: str
    command: list[str]
    available: bool
    validation_ok: bool
    notes: str
    status: str
    stdout: str
    stderr: str
    timed_out: bool
    return_code: int | None
    output_path: str | None = None


def _status(name: str, command: str, notes: str) -> ShellAdapterStatus:
    path = which(command)
    available = path is not None
    return ShellAdapterStatus(
        name=name,
        command=command,
        available=available,
        path=path,
        validation_ok=available,
        notes=notes,
    )


PIPELINE_ADAPTERS = {
    "bwa": _status("bwa", "bwa", "BWA short-read aligner shell stub."),
    "bwa_mem2": _status("bwa_mem2", "bwa-mem2", "BWA-MEM2 aligner shell stub."),
    "gatk_mutect2": _status("gatk_mutect2", "gatk", "GATK/Mutect2 shell stub."),
    "vep": _status("vep", "vep", "Ensembl VEP annotation shell stub."),
    "pvactools": _status("pvactools", "pvacseq", "pVACtools prioritization shell stub."),
}


def list_pipeline_adapter_statuses() -> dict[str, dict]:
    return {adapter.name: asdict(adapter) for adapter in PIPELINE_ADAPTERS.values()}


def build_pipeline_command(
    adapter_name: str, payload: dict
) -> tuple[ShellAdapterStatus, list[str], str | None]:
    if adapter_name not in PIPELINE_ADAPTERS:
        raise KeyError(adapter_name)

    adapter = PIPELINE_ADAPTERS[adapter_name]
    output_path = payload.get("output_path")

    # Apply config defaults where the payload does not specify values
    defaults = _adapter_defaults(adapter_name)
    merged = {**defaults, **payload}

    if adapter_name in {"bwa", "bwa_mem2"}:
        req = BwaRequest.model_validate(merged)
        command = [adapter.command, "mem"]
        if req.threads:
            command.extend(["-t", str(req.threads)])
        if req.read_group:
            command.extend(["-R", req.read_group])
        command.extend([req.reference, req.fastq_1])
        if req.fastq_2:
            command.append(req.fastq_2)
        output_path = req.output_bam

    elif adapter_name == "gatk_mutect2":
        req = GatkMutect2Request.model_validate(merged)
        command = [adapter.command, "Mutect2"]
        if req.reference:
            command.extend(["-R", req.reference])
        command.extend(["-I", req.input_bam])
        if req.normal_bam:
            # --normal-sample expects a sample name, not a BAM path.
            # Use explicit normal_sample if provided; otherwise extract from @RG SM: tag;
            # fall back to "NORMAL".
            normal_sample = merged.get("normal_sample") or ""
            if not normal_sample:
                samtools = which("samtools")
                if samtools:
                    try:
                        rg_proc = subprocess.run(
                            [samtools, "view", "-H", req.normal_bam],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            check=False,
                        )
                        for rg_line in rg_proc.stdout.splitlines():
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
            command.extend(["-I", req.normal_bam, "--normal-sample", normal_sample])
        if req.intervals:
            command.extend(["-L", req.intervals])
        if req.panel_of_normals:
            command.extend(["--panel-of-normals", req.panel_of_normals])
        if req.germline_resource:
            command.extend(["--germline-resource", req.germline_resource])
        if req.tumor_sample:
            command.extend(["--tumor-sample", req.tumor_sample])
        output_path = req.output_vcf or output_path
        if output_path:
            command.extend(["-O", output_path])

    elif adapter_name == "vep":
        req = VepRequest.model_validate(merged)
        command = [adapter.command, "--input_file", req.input_vcf]
        if req.cache_dir:
            command.extend(["--dir_cache", req.cache_dir])
        if req.assembly:
            command.extend(["--assembly", req.assembly])
        if req.fork:
            command.extend(["--fork", str(req.fork)])
        if req.everything:
            command.append("--everything")
        if req.hgvs:
            command.append("--hgvs")
        if req.symbol:
            command.append("--symbol")
        if req.canonical:
            command.append("--canonical")
        output_path = req.output_path or output_path
        if output_path:
            command.extend(["--output_file", output_path])

    elif adapter_name == "pvactools":
        req = PvactoolsRequest.model_validate(merged)
        command = [
            adapter.command,
            req.input_vcf,
            req.sample_name,
            ",".join(req.alleles),
            ",".join(req.prediction_algorithms or settings.pipeline_pvactools_algorithms),
        ]
        if req.output_dir:
            command.append(req.output_dir)
        if req.peptide_length:
            command.extend(["--peptide-length", str(req.peptide_length)])
        if req.netmhc_stab:
            command.append("--netmhc-stab")
        output_path = req.output_dir or output_path

    else:
        command = [adapter.command]

    return adapter, command, output_path


def _adapter_defaults(adapter_name: str) -> dict:
    """Return config-derived default arguments for an adapter."""
    defaults: dict = {
        "threads": settings.pipeline_default_threads,
        "memory_gb": settings.pipeline_default_memory_gb,
    }
    if adapter_name in {"bwa", "bwa_mem2"}:
        defaults["reference"] = settings.pipeline_bwa_reference
    elif adapter_name == "gatk_mutect2":
        defaults["reference"] = settings.pipeline_gatk_reference
        defaults["panel_of_normals"] = settings.pipeline_gatk_panel_of_normals
        defaults["germline_resource"] = settings.pipeline_gatk_germline_resource
    elif adapter_name == "vep":
        defaults["cache_dir"] = settings.pipeline_vep_cache_dir
        defaults["assembly"] = settings.pipeline_vep_assembly
        defaults["fork"] = settings.pipeline_vep_fork
    elif adapter_name == "pvactools":
        defaults["alleles"] = settings.pipeline_pvactools_alleles
        defaults["prediction_algorithms"] = settings.pipeline_pvactools_algorithms
    return defaults


def build_pipeline_dry_run(adapter_name: str, payload: dict) -> ShellDryRun:
    adapter, command, _ = build_pipeline_command(adapter_name, payload)
    return ShellDryRun(
        adapter=adapter.name,
        mode="dry_run",
        command=command,
        available=adapter.available,
        validation_ok=adapter.validation_ok,
        notes=adapter.notes,
    )


def execute_pipeline_adapter(adapter_name: str, payload: dict) -> ShellExecution:
    adapter, command, output_path = build_pipeline_command(adapter_name, payload)
    if not adapter.available:
        return ShellExecution(
            adapter=adapter.name,
            mode="execute",
            command=command,
            available=False,
            validation_ok=False,
            notes=adapter.notes,
            status="unavailable",
            stdout="",
            stderr=f"Command '{adapter.command}' not found on PATH.",
            timed_out=False,
            return_code=None,
            output_path=output_path,
        )

    timeout = int(payload.get("timeout_seconds", 30))
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return ShellExecution(
            adapter=adapter.name,
            mode="execute",
            command=command,
            available=True,
            validation_ok=True,
            notes=adapter.notes,
            status="completed" if completed.returncode == 0 else "failed",
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            return_code=completed.returncode,
            output_path=output_path,
        )
    except subprocess.TimeoutExpired as exc:
        return ShellExecution(
            adapter=adapter.name,
            mode="execute",
            command=command,
            available=True,
            validation_ok=True,
            notes=adapter.notes,
            status="failed",
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"Command timed out after {timeout} seconds.",
            timed_out=True,
            return_code=None,
            output_path=output_path,
        )
