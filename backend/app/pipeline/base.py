"""FoldAgent Pipeline Module

Defines the PipelineStep base class and mock implementations for the MVP.
Real bioinformatics tool wrappers will replace mocks behind the same interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result from running a pipeline step."""

    step_name: str
    step_version: str
    status: StepStatus
    outputs: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_professional_review: bool = True
    safety_label: str = "Research candidate only — not administerable"
    tool_versions: dict = field(default_factory=dict)
    reproducibility_manifest: dict = field(default_factory=dict)
    duration_seconds: Optional[float] = None


class PipelineStep(ABC):
    """Abstract base class for all pipeline steps.

    Every bioinformatics tool wrapper, mock or real, must implement this
    interface. This ensures consistent logging, safety labeling, and
    reproducibility across all pipeline steps.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this pipeline step."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Version string for this pipeline step implementation."""
        ...

    @property
    def requires_professional_review(self) -> bool:
        """Whether this step's outputs require professional review."""
        return True

    @property
    def safety_label(self) -> str:
        """Safety label applied to all outputs from this step."""
        return "Research candidate only — not administerable"

    @abstractmethod
    async def run(self, inputs: dict) -> StepResult:
        """Execute this pipeline step.

        Args:
            inputs: Dictionary containing input data and configuration.

        Returns:
            StepResult with outputs, status, and metadata.
        """
        ...

    @abstractmethod
    async def validate_environment(self) -> bool:
        """Check that the required tools and environment are available.

        Returns:
            True if the environment is ready, False otherwise.
        """
        ...

    def collect_outputs(self, result: StepResult) -> dict:
        """Collect and format outputs from a completed step.

        Args:
            result: The StepResult from running this step.

        Returns:
            Dictionary of formatted outputs with safety labels applied.
        """
        outputs = result.outputs.copy()
        outputs["_safety_label"] = self.safety_label
        outputs["_requires_professional_review"] = self.requires_professional_review
        return outputs

    def create_reproducibility_manifest(self, inputs: dict) -> dict:
        """Create a manifest capturing all information needed to reproduce this step.

        Args:
            inputs: The original inputs to this step.

        Returns:
            Dictionary with tool version, parameters, and input hashes.
        """
        import hashlib
        import json

        return {
            "step_name": self.name,
            "step_version": self.version,
            "tool_versions": self._get_tool_versions(),
            "input_hash": hashlib.sha256(
                json.dumps(inputs, sort_keys=True, default=str).encode()
            ).hexdigest(),
        }

    def _get_tool_versions(self) -> dict:
        """Return versions of external tools used by this step.

        Override in subclasses that wrap real tools.
        """
        return {}


# --- Mock Implementations ---


class MockAlignmentStep(PipelineStep):
    """Mock alignment step for demo and testing."""

    @property
    def name(self) -> str:
        return "mock_alignment"

    @property
    def version(self) -> str:
        return "0.1.0-mock"

    async def run(self, inputs: dict) -> StepResult:
        logger.info("mock_alignment_running", case_id=inputs.get("case_id"))
        return StepResult(
            step_name=self.name,
            step_version=self.version,
            status=StepStatus.COMPLETED,
            outputs={
                "aligned_reads": "mock_aligned.bam",
                "alignment_stats": {"total_reads": 1000000, "mapped_reads": 980000, "mapping_rate": 0.98},
                "warning": "This is a mock alignment for demonstration only. No real genomic data was processed.",
            },
            reproducibility_manifest=self.create_reproducibility_manifest(inputs),
        )

    async def validate_environment(self) -> bool:
        return True  # Mock always validates


class MockVariantCallingStep(PipelineStep):
    """Mock variant calling step for demo and testing."""

    @property
    def name(self) -> str:
        return "mock_variant_calling"

    @property
    def version(self) -> str:
        return "0.1.0-mock"

    async def run(self, inputs: dict) -> StepResult:
        logger.info("mock_variant_calling_running", case_id=inputs.get("case_id"))
        return StepResult(
            step_name=self.name,
            step_version=self.version,
            status=StepStatus.COMPLETED,
            outputs={
                "variants_called": 42,
                "somatic_variants": 15,
                "variant_file": "mock_variants.vcf",
                "warning": "This is mock variant calling for demonstration only. No real variant data was processed.",
            },
            reproducibility_manifest=self.create_reproducibility_manifest(inputs),
        )

    async def validate_environment(self) -> bool:
        return True


class MockAnnotationStep(PipelineStep):
    """Mock annotation step for demo and testing."""

    @property
    def name(self) -> str:
        return "mock_annotation"

    @property
    def version(self) -> str:
        return "0.1.0-mock"

    async def run(self, inputs: dict) -> StepResult:
        logger.info("mock_annotation_running", case_id=inputs.get("case_id"))
        return StepResult(
            step_name=self.name,
            step_version=self.version,
            status=StepStatus.COMPLETED,
            outputs={
                "annotated_variants": 42,
                "missense_variants": 8,
                "annotation_source": "mock_vep",
                "warning": "This is mock annotation for demonstration only. No real annotation was performed.",
            },
            reproducibility_manifest=self.create_reproducibility_manifest(inputs),
        )

    async def validate_environment(self) -> bool:
        return True


class MockCandidatePrioritizationStep(PipelineStep):
    """Mock candidate prioritization step for demo and testing."""

    @property
    def name(self) -> str:
        return "mock_candidate_prioritization"

    @property
    def version(self) -> str:
        return "0.1.0-mock"

    async def run(self, inputs: dict) -> StepResult:
        logger.info("mock_candidate_prioritization_running", case_id=inputs.get("case_id"))
        return StepResult(
            step_name=self.name,
            step_version=self.version,
            status=StepStatus.COMPLETED,
            outputs={
                "candidates_identified": 5,
                "top_candidates": [
                    {
                        "gene": "TP53",
                        "protein_change": "p.R175H",
                        "prediction_score": 0.92,
                        "mhc_affinity_nm": 15.3,
                        "uncertainty_flag": "No expression validation data available",
                    },
                    {
                        "gene": "KRAS",
                        "protein_change": "p.G12D",
                        "prediction_score": 0.88,
                        "mhc_affinity_nm": 22.1,
                        "uncertainty_flag": "DLA typing not performed; MHC context is predicted only",
                    },
                ],
                "warning": "These are mock candidate antigens for demonstration only. No real prediction was performed. Professional review required.",
            },
            reproducibility_manifest=self.create_reproducibility_manifest(inputs),
        )

    async def validate_environment(self) -> bool:
        return True


# --- Pipeline Orchestration ---


MOCK_PIPELINE_STEPS = [
    MockAlignmentStep(),
    MockVariantCallingStep(),
    MockAnnotationStep(),
    MockCandidatePrioritizationStep(),
]


async def run_mock_pipeline(case_id: str) -> list[StepResult]:
    """Run the mock pipeline for a case.

    This is the default pipeline for demo mode. Real bioinformatics
    tool wrappers will use the same interface.
    """
    results = []
    inputs = {"case_id": case_id}

    for step in MOCK_PIPELINE_STEPS:
        logger.info("pipeline_step_starting", step=step.name, case_id=case_id)
        result = await step.run(inputs)
        results.append(result)

        if result.status == StepStatus.FAILED:
            logger.error("pipeline_step_failed", step=step.name, case_id=case_id, errors=result.errors)
            break

        # Pass outputs as inputs to next step
        inputs.update(result.outputs)

    logger.info("pipeline_completed", case_id=case_id, steps_completed=len(results))
    return results