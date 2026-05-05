"""NeoVax-Agent GPU Worker Profile — Infrastructure Stubs

GPU worker configuration profiles and availability checks.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class GPUWorkerConfig:
    """Configuration profile for a GPU-backed worker."""

    gpu_required: bool
    gpu_type: str  # nvidia / amd / any
    min_vram_gb: int
    docker_image: str | None = None


DEFAULT_GPU_PROFILES: dict[str, GPUWorkerConfig] = {
    "colabfold": GPUWorkerConfig(
        gpu_required=True,
        gpu_type="nvidia",
        min_vram_gb=8,
        docker_image="ghcr.io/sokrypton/colabfold:latest",
    ),
    "alphafold2_local": GPUWorkerConfig(
        gpu_required=True,
        gpu_type="nvidia",
        min_vram_gb=16,
        docker_image="ghcr.io/deepmind/alphafold:latest",
    ),
    "alphafold3_local": GPUWorkerConfig(
        gpu_required=True,
        gpu_type="nvidia",
        min_vram_gb=24,
        docker_image=None,
    ),
    "mock": GPUWorkerConfig(
        gpu_required=False,
        gpu_type="any",
        min_vram_gb=0,
        docker_image=None,
    ),
}


def check_gpu_availability() -> dict:
    """Stub: probe nvidia-smi to determine GPU availability.

    Returns a dict with keys: available, gpu_count, driver_version.
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": False, "gpu_count": 0, "driver_version": None}

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=count,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"available": False, "gpu_count": 0, "driver_version": None}
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
        if not lines:
            return {"available": True, "gpu_count": 0, "driver_version": None}
        parts = lines[0].split(",")
        gpu_count = int(parts[0].strip()) if parts[0].strip().isdigit() else len(lines)
        driver_version = parts[1].strip() if len(parts) > 1 else None
        return {"available": True, "gpu_count": gpu_count, "driver_version": driver_version}
    except Exception as exc:
        logger.warning("gpu_availability_check_failed", error=str(exc))
        return {"available": False, "gpu_count": 0, "driver_version": None}


def get_worker_profile(backend_name: str) -> GPUWorkerConfig | None:
    """Return the GPU worker profile for the given backend, or None."""
    return DEFAULT_GPU_PROFILES.get(backend_name)
