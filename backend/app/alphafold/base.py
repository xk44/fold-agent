"""FoldAgent AlphaFold Backend Abstraction

Defines the AlphaFoldBackend abstract class, metadata-only backend descriptors,
and MockAlphaFoldBackend for testing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class BackendMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    MOCK = "mock"


@dataclass
class StructureInputManifest:
    """Input manifest for a structure prediction job."""

    sequence: str
    sequence_type: str = "protein"
    job_name: str = ""
    case_id: str = ""
    candidate_id: str = ""


@dataclass
class StructureResult:
    """Result from a structure prediction job."""

    job_id: str
    backend_name: str
    status: str
    output_path: str | None = None
    confidence_metrics: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    safety_label: str = "Structure prediction only — not clinical validation"
    input_hash: str | None = None


class AlphaFoldBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def mode(self) -> BackendMode: ...

    @property
    def requires_gpu(self) -> bool:
        return False

    @property
    def requires_external_upload(self) -> bool:
        return False

    @property
    def supports_protein_only(self) -> bool:
        return True

    @property
    def supports_complexes(self) -> bool:
        return False

    @property
    def supports_rna_dna_ligands(self) -> bool:
        return False

    @property
    def license_notes(self) -> str:
        return ""

    @abstractmethod
    async def validate_environment(self) -> bool: ...

    @abstractmethod
    async def run_structure_prediction(
        self, manifest: StructureInputManifest
    ) -> StructureResult: ...

    @abstractmethod
    async def estimate_cost(self, manifest: StructureInputManifest) -> float | None: ...

    @abstractmethod
    async def estimate_runtime(self, manifest: StructureInputManifest) -> int | None: ...

    @abstractmethod
    async def collect_outputs(self, job_id: str) -> dict: ...


class StaticMetadataBackend(AlphaFoldBackend):
    def __init__(
        self,
        *,
        name: str,
        version: str,
        mode: BackendMode,
        requires_gpu: bool = False,
        requires_external_upload: bool = False,
        supports_protein_only: bool = True,
        supports_complexes: bool = False,
        supports_rna_dna_ligands: bool = False,
        license_notes: str = "",
    ) -> None:
        self._name = name
        self._version = version
        self._mode = mode
        self._requires_gpu = requires_gpu
        self._requires_external_upload = requires_external_upload
        self._supports_protein_only = supports_protein_only
        self._supports_complexes = supports_complexes
        self._supports_rna_dna_ligands = supports_rna_dna_ligands
        self._license_notes = license_notes

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @property
    def mode(self) -> BackendMode:
        return self._mode

    @property
    def requires_gpu(self) -> bool:
        return self._requires_gpu

    @property
    def requires_external_upload(self) -> bool:
        return self._requires_external_upload

    @property
    def supports_protein_only(self) -> bool:
        return self._supports_protein_only

    @property
    def supports_complexes(self) -> bool:
        return self._supports_complexes

    @property
    def supports_rna_dna_ligands(self) -> bool:
        return self._supports_rna_dna_ligands

    @property
    def license_notes(self) -> str:
        return self._license_notes

    async def validate_environment(self) -> bool:
        return False

    async def run_structure_prediction(self, manifest: StructureInputManifest) -> StructureResult:
        raise RuntimeError(f"Backend {self.name} is metadata-only in current FoldAgent phase")

    async def estimate_cost(self, manifest: StructureInputManifest) -> float | None:
        return None

    async def estimate_runtime(self, manifest: StructureInputManifest) -> int | None:
        return None

    async def collect_outputs(self, job_id: str) -> dict:
        return {"job_id": job_id, "backend": self.name}


class MockAlphaFoldBackend(AlphaFoldBackend):
    @property
    def name(self) -> str:
        return "mock"

    @property
    def version(self) -> str:
        return "0.1.0-mock"

    @property
    def mode(self) -> BackendMode:
        return BackendMode.MOCK

    async def validate_environment(self) -> bool:
        return True

    async def run_structure_prediction(self, manifest: StructureInputManifest) -> StructureResult:
        import hashlib

        logger.info(
            "mock_alphafold_running", sequence_len=len(manifest.sequence), case_id=manifest.case_id
        )
        job_id = str(uuid4())
        input_hash = hashlib.sha256(manifest.sequence.encode()).hexdigest()[:16]
        mock_confidence = {
            "pLDDT_mean": 87.3,
            "pLDDT_percentile": 78.0,
            "pAE_mean": 12.5,
            "model_version": "mock-v0.1.0",
            "warning": "Mock prediction. These are not real confidence metrics.",
        }
        return StructureResult(
            job_id=job_id,
            backend_name=self.name,
            status="completed",
            output_path=f"mock_structures/{job_id}/predicted_structure.pdb",
            confidence_metrics=mock_confidence,
            warnings=[
                "This is a mock structure prediction for demonstration only.",
                "No real AlphaFold computation was performed.",
                "Structure predictions are theoretical modeling only — not clinical validation.",
            ],
            input_hash=input_hash,
        )

    async def estimate_cost(self, manifest: StructureInputManifest) -> float | None:
        return 0.0

    async def estimate_runtime(self, manifest: StructureInputManifest) -> int | None:
        return 1

    async def collect_outputs(self, job_id: str) -> dict:
        return {
            "job_id": job_id,
            "pdb_file": f"mock_structures/{job_id}/predicted_structure.pdb",
            "confidence_metrics": {"pLDDT_mean": 87.3, "pAE_mean": 12.5},
            "safety_label": "Structure prediction only — not clinical validation",
            "warning": "Mock output. No real structure was computed.",
        }


_BACKENDS: dict[str, AlphaFoldBackend] = {}


def register_backend(backend: AlphaFoldBackend) -> None:
    _BACKENDS[backend.name] = backend
    logger.info("alphafold_backend_registered", name=backend.name, mode=backend.mode.value)


def get_backend(name: str) -> AlphaFoldBackend:
    if name not in _BACKENDS:
        raise KeyError(
            f"AlphaFold backend '{name}' not registered. Available: {list(_BACKENDS.keys())}"
        )
    return _BACKENDS[name]


def list_backends() -> dict[str, dict]:
    result = {}
    for name, backend in _BACKENDS.items():
        result[name] = {
            "name": backend.name,
            "version": backend.version,
            "mode": backend.mode.value,
            "requires_gpu": backend.requires_gpu,
            "requires_external_upload": backend.requires_external_upload,
            "supports_protein_only": backend.supports_protein_only,
            "supports_complexes": backend.supports_complexes,
            "supports_rna_dna_ligands": backend.supports_rna_dna_ligands,
            "license_notes": backend.license_notes,
        }
    return result


register_backend(MockAlphaFoldBackend())
register_backend(
    StaticMetadataBackend(
        name="colabfold",
        version="colabfold-shell",
        mode=BackendMode.LOCAL,
        requires_gpu=True,
        supports_complexes=True,
        license_notes="ColabFold local CLI wrapper; may use remote MMseqs services unless configured otherwise.",
    )
)
register_backend(
    StaticMetadataBackend(
        name="local_colabfold",
        version="localcolabfold-shell",
        mode=BackendMode.LOCAL,
        requires_gpu=True,
        supports_complexes=True,
        license_notes="LocalColabFold wrapper around colabfold_batch.",
    )
)
register_backend(
    StaticMetadataBackend(
        name="alphafold2_local",
        version="alphafold2-shell",
        mode=BackendMode.LOCAL,
        requires_gpu=True,
        supports_complexes=True,
        license_notes="Local AlphaFold2 CLI wrapper.",
    )
)
register_backend(
    StaticMetadataBackend(
        name="alphafold3_local",
        version="alphafold3-shell",
        mode=BackendMode.LOCAL,
        requires_gpu=True,
        supports_complexes=True,
        supports_rna_dna_ligands=True,
        license_notes="Local AlphaFold3 CLI wrapper using JSON/input-dir workflows.",
    )
)
register_backend(
    StaticMetadataBackend(
        name="alphafold_server",
        version="alphafold-server-remote",
        mode=BackendMode.CLOUD,
        requires_external_upload=True,
        supports_complexes=True,
        supports_rna_dna_ligands=True,
        license_notes="AlphaFold Server remote service. Non-commercial use with external upload and server-side quotas/terms.",
    )
)
register_backend(
    StaticMetadataBackend(
        name="alphafold_db",
        version="alphafold-db-reference",
        mode=BackendMode.CLOUD,
        supports_complexes=False,
        supports_rna_dna_ligands=False,
        license_notes="AlphaFold Protein Structure Database lookup/reference backend.",
    )
)
