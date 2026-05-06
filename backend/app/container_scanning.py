"""FoldAgent Container Image Scanning — Infrastructure Stubs

CLI command builders and output parsers for trivy/grype.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class ContainerScanConfig:
    """Configuration for a container image scan."""

    scanner: str  # trivy / grype / none
    fail_on_severity: str  # CRITICAL / HIGH / MEDIUM / LOW
    ignore_unfixed: bool


DEFAULT_SCAN_CONFIG = ContainerScanConfig(
    scanner="trivy",
    fail_on_severity="CRITICAL",
    ignore_unfixed=False,
)


def build_scan_command(image: str, config: ContainerScanConfig) -> str:
    """Return the CLI command to scan *image* using the configured scanner."""
    if config.scanner == "trivy":
        parts = [
            "trivy image",
            f"--severity {config.fail_on_severity}",
            "--exit-code 1",
        ]
        if config.ignore_unfixed:
            parts.append("--ignore-unfixed")
        parts.append(image)
        return " ".join(parts)

    if config.scanner == "grype":
        parts = [
            "grype",
            image,
            f"--fail-on {config.fail_on_severity.lower()}",
        ]
        if config.ignore_unfixed:
            parts.append("--only-fixed")
        return " ".join(parts)

    # scanner == "none" or unknown
    return f"echo 'No scanner configured for image: {image}'"


def parse_scan_results(output: str) -> dict:
    """Stub: parse raw scanner stdout into a structured result.

    A real implementation would parse trivy/grype JSON output.
    """
    lines = output.strip().splitlines()
    vulnerability_lines = [
        l for l in lines if any(sev in l.upper() for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"))
    ]
    return {
        "raw_output": output,
        "vulnerability_count": len(vulnerability_lines),
        "parsed": False,
        "note": "Stub parser — integrate with trivy/grype JSON output format.",
    }


def check_scanner_available() -> dict:
    """Check which container scanners are available on PATH."""
    trivy = shutil.which("trivy")
    grype = shutil.which("grype")
    available = []
    if trivy:
        available.append("trivy")
    if grype:
        available.append("grype")
    return {
        "trivy_available": trivy is not None,
        "trivy_path": trivy,
        "grype_available": grype is not None,
        "grype_path": grype,
        "any_available": len(available) > 0,
        "available_scanners": available,
    }
