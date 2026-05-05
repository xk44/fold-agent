"""FoldAgent AlphaFold Backend Abstraction (Phase 6).

Provides:
- AlphaFoldBackend ABC with predict() / validate() contract
- Concrete stub backends (mock + 6 stubs)
- StructureCache with SHA-256 input hashing
- BackendSelector with fallback/cloud permission gates
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PredictionResult:
    pdb_data: str | None
    confidence: dict
    backend_name: str
    duration_seconds: float
    cached: bool = False


@dataclass
class BackendValidation:
    name: str
    available: bool
    reason: str
    gpu_required: bool
    cloud: bool
    privacy_risk: str  # "none", "low", "medium", "high"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class AlphaFoldBackend(ABC):
    """Abstract base for all AlphaFold-family structure prediction backends."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def predict(self, sequence: str, options: dict) -> PredictionResult: ...

    def validate(self) -> BackendValidation:
        """Check if this backend is available and configured.

        Subclasses should override to perform real environment checks.
        Default implementation returns unavailable.
        """
        return BackendValidation(
            name=self.name,
            available=False,
            reason="validate() not implemented",
            gpu_required=False,
            cloud=False,
            privacy_risk="none",
        )


# ---------------------------------------------------------------------------
# Concrete backends
# ---------------------------------------------------------------------------


def _synthetic_pdb(sequence: str) -> str:
    """Generate minimal synthetic PDB text for testing/mock purposes."""
    lines: list[str] = [
        "REMARK  FoldAgent mock structure — not a real prediction",
        "REMARK  sequence length: " + str(len(sequence)),
    ]
    for i, aa in enumerate(sequence[:50], start=1):
        plddt = round(random.uniform(60.0, 95.0), 2)
        lines.append(
            f"ATOM  {i:5d}  CA  {aa:3s} A{i:4d}    "
            f"   0.000   0.000   0.000  1.00 {plddt:5.2f}           C"
        )
    lines.append("END")
    return "\n".join(lines)


class MockBackend(AlphaFoldBackend):
    """Always-available mock backend that returns synthetic PDB + pLDDT scores."""

    @property
    def name(self) -> str:
        return "mock"

    def validate(self) -> BackendValidation:
        return BackendValidation(
            name=self.name,
            available=True,
            reason="Mock backend is always available",
            gpu_required=False,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        pdb = _synthetic_pdb(sequence)
        confidence = {
            "pLDDT_mean": round(random.uniform(70.0, 92.0), 2),
            "pLDDT_min": round(random.uniform(55.0, 70.0), 2),
            "pLDDT_max": round(random.uniform(90.0, 99.0), 2),
            "pAE_mean": round(random.uniform(5.0, 18.0), 2),
            "model_version": "mock-v1.0",
            "warning": "Mock prediction — not real structure data.",
        }
        duration = time.monotonic() - t0
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=duration,
        )


class ColabFoldBackend(AlphaFoldBackend):
    """Stub for the ColabFold CLI (colabfold_batch)."""

    @property
    def name(self) -> str:
        return "colabfold"

    def validate(self) -> BackendValidation:
        path = shutil.which("colabfold_batch")
        available = path is not None
        return BackendValidation(
            name=self.name,
            available=available,
            reason=f"colabfold_batch found at {path}" if available else "colabfold_batch not found on PATH",
            gpu_required=True,
            cloud=False,
            privacy_risk="low",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        v = self.validate()
        if not v.available:
            raise RuntimeError(f"ColabFold not available: {v.reason}")
        raise NotImplementedError("ColabFoldBackend.predict() is a stub — real execution not yet wired")


class LocalColabFoldBackend(AlphaFoldBackend):
    """Stub for a locally-installed ColabFold (localcolabfold)."""

    @property
    def name(self) -> str:
        return "local_colabfold"

    def validate(self) -> BackendValidation:
        path = shutil.which("colabfold_batch")
        # Distinguish from system colabfold by checking common local install dirs
        import os

        local_paths = [
            os.path.expanduser("~/localcolabfold/colabfold-conda/bin/colabfold_batch"),
            os.path.expanduser("~/.local/bin/colabfold_batch"),
        ]
        local_found = any(shutil.os.path.isfile(p) for p in local_paths)
        available = local_found or path is not None
        reason = (
            "localcolabfold installation found"
            if local_found
            else ("colabfold_batch on PATH (may be system)" if path else "colabfold_batch not found")
        )
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("LocalColabFoldBackend.predict() is a stub")


class AlphaFold2LocalBackend(AlphaFoldBackend):
    """Stub for a local AlphaFold2 installation."""

    @property
    def name(self) -> str:
        return "alphafold2_local"

    def validate(self) -> BackendValidation:
        import os

        af2_paths = [
            os.path.expanduser("~/alphafold"),
            "/opt/alphafold",
            "/usr/local/alphafold",
        ]
        found = any(shutil.os.path.isdir(p) for p in af2_paths)
        return BackendValidation(
            name=self.name,
            available=found,
            reason="AlphaFold2 directory found" if found else "AlphaFold2 installation directory not found",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("AlphaFold2LocalBackend.predict() is a stub")


class AlphaFold3LocalBackend(AlphaFoldBackend):
    """Stub for a local AlphaFold3 installation."""

    @property
    def name(self) -> str:
        return "alphafold3_local"

    def validate(self) -> BackendValidation:
        import os

        af3_paths = [
            os.path.expanduser("~/alphafold3"),
            "/opt/alphafold3",
            "/usr/local/alphafold3",
        ]
        found = any(shutil.os.path.isdir(p) for p in af3_paths)
        return BackendValidation(
            name=self.name,
            available=found,
            reason="AlphaFold3 directory found" if found else "AlphaFold3 installation directory not found",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("AlphaFold3LocalBackend.predict() is a stub")


class AlphaFoldServerBackend(AlphaFoldBackend):
    """Stub for the AlphaFold Server (cloud, external upload, high privacy risk)."""

    @property
    def name(self) -> str:
        return "alphafold_server"

    def validate(self) -> BackendValidation:
        # Always "available" as a remote service (network required, not installed locally)
        return BackendValidation(
            name=self.name,
            available=True,
            reason="AlphaFold Server is a remote service; network access required",
            gpu_required=False,
            cloud=True,
            privacy_risk="high",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("AlphaFoldServerBackend.predict() is a stub — external upload required")


class AlphaFoldDBBackend(AlphaFoldBackend):
    """Stub for the AlphaFold Protein Structure Database (UniProt lookup)."""

    @property
    def name(self) -> str:
        return "alphafold_db"

    def validate(self) -> BackendValidation:
        return BackendValidation(
            name=self.name,
            available=True,
            reason="AlphaFold DB is a remote database; network access required",
            gpu_required=False,
            cloud=True,
            privacy_risk="low",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("AlphaFoldDBBackend.predict() is a stub — UniProt accession lookup not yet wired")


class Boltz1Backend(AlphaFoldBackend):
    """Boltz-1 — MIT-licensed AF3-class structure prediction (protein + ligand + nucleic acid)."""

    @property
    def name(self) -> str:
        return "boltz1"

    def validate(self) -> BackendValidation:
        path = shutil.which("boltz")
        available = path is not None
        return BackendValidation(
            name=self.name,
            available=available,
            reason=f"boltz found at {path}" if available else "boltz binary not found on PATH",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        pdb = _synthetic_pdb(sequence)
        confidence: dict[str, Any] = {
            "pLDDT_mean": round(random.uniform(75.0, 93.0), 2),
            "pLDDT_min": round(random.uniform(60.0, 75.0), 2),
            "pLDDT_max": round(random.uniform(91.0, 99.0), 2),
            "pTM": round(random.uniform(0.70, 0.95), 4),
            "model_version": "boltz1-stub",
            "warning": "Boltz-1 stub — not a real prediction.",
        }
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


class Boltz2Backend(AlphaFoldBackend):
    """Boltz-2 — structure + binding affinity prediction (MIT license)."""

    @property
    def name(self) -> str:
        return "boltz2"

    def validate(self) -> BackendValidation:
        path = shutil.which("boltz")
        available = path is not None
        return BackendValidation(
            name=self.name,
            available=available,
            reason=f"boltz found at {path}" if available else "boltz binary not found on PATH",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        pdb = _synthetic_pdb(sequence)
        confidence: dict[str, Any] = {
            "pLDDT_mean": round(random.uniform(75.0, 93.0), 2),
            "pLDDT_min": round(random.uniform(60.0, 75.0), 2),
            "pLDDT_max": round(random.uniform(91.0, 99.0), 2),
            "pTM": round(random.uniform(0.70, 0.95), 4),
            "binding_affinity_kcal": round(random.uniform(-12.0, -4.0), 3),
            "supports_affinity": True,
            "model_version": "boltz2-stub",
            "warning": "Boltz-2 stub — not a real prediction.",
        }
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


class ESMFoldBackend(AlphaFoldBackend):
    """ESMFold — fast single-sequence structure prediction (no MSA, ~60x faster)."""

    @property
    def name(self) -> str:
        return "esmfold"

    def validate(self) -> BackendValidation:
        import importlib.util

        binary_path = shutil.which("esmfold")
        module_available = importlib.util.find_spec("esm") is not None
        available = binary_path is not None or module_available
        reason: str
        if binary_path:
            reason = f"esmfold binary found at {binary_path}"
        elif module_available:
            reason = "esm Python module available"
        else:
            reason = "esmfold binary and esm Python module not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        pdb = _synthetic_pdb(sequence)
        confidence: dict[str, Any] = {
            "pLDDT_mean": round(random.uniform(72.0, 90.0), 2),
            "pLDDT_min": round(random.uniform(55.0, 72.0), 2),
            "pLDDT_max": round(random.uniform(88.0, 99.0), 2),
            "fast_mode": True,
            "msa_used": False,
            "model_version": "esmfold-stub",
            "warning": "ESMFold stub — not a real prediction.",
        }
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


class OpenFoldBackend(AlphaFoldBackend):
    """OpenFold — trainable AF2 reimplementation (Apache 2.0)."""

    @property
    def name(self) -> str:
        return "openfold"

    def validate(self) -> BackendValidation:
        import importlib.util
        import os

        openfold_paths = [
            os.path.expanduser("~/openfold"),
            "/opt/openfold",
            "/usr/local/openfold",
        ]
        dir_found = any(os.path.isdir(p) for p in openfold_paths)
        module_available = importlib.util.find_spec("openfold") is not None
        available = dir_found or module_available
        if dir_found:
            reason = "OpenFold installation directory found"
        elif module_available:
            reason = "openfold Python module available"
        else:
            reason = "OpenFold installation not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("OpenFoldBackend.predict() is a stub")


class RFdiffusionBackend(AlphaFoldBackend):
    """RFdiffusion — generative protein backbone design."""

    _VALID_DESIGN_MODES = {"binder", "scaffold", "symmetric", "enzyme"}

    @property
    def name(self) -> str:
        return "rfdiffusion"

    def validate(self) -> BackendValidation:
        import importlib.util
        import os

        paths = [
            os.path.expanduser("~/RFdiffusion"),
            "/opt/RFdiffusion",
        ]
        dir_found = any(os.path.isdir(p) for p in paths)
        binary_path = shutil.which("rfdiffusion")
        module_available = importlib.util.find_spec("rfdiffusion") is not None
        available = dir_found or binary_path is not None or module_available
        if binary_path:
            reason = f"rfdiffusion binary found at {binary_path}"
        elif dir_found:
            reason = "RFdiffusion installation directory found"
        elif module_available:
            reason = "rfdiffusion Python module available"
        else:
            reason = "RFdiffusion installation not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        design_mode = options.get("design_mode", "binder")
        if design_mode not in self._VALID_DESIGN_MODES:
            raise ValueError(
                f"Invalid design_mode {design_mode!r}. "
                f"Must be one of: {sorted(self._VALID_DESIGN_MODES)}"
            )
        pdb = _synthetic_pdb(sequence)
        confidence: dict[str, Any] = {
            "design_mode": design_mode,
            "pLDDT_mean": round(random.uniform(70.0, 90.0), 2),
            "model_version": "rfdiffusion-stub",
            "warning": "RFdiffusion stub — designed backbone, not a real prediction.",
        }
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


class ProteinMPNNBackend(AlphaFoldBackend):
    """ProteinMPNN — inverse folding / sequence design from backbone."""

    @property
    def name(self) -> str:
        return "proteinmpnn"

    def validate(self) -> BackendValidation:
        import importlib.util
        import os

        paths = [
            os.path.expanduser("~/ProteinMPNN"),
            "/opt/ProteinMPNN",
        ]
        dir_found = any(os.path.isdir(p) for p in paths)
        binary_path = shutil.which("protein_mpnn")
        module_available = importlib.util.find_spec("protein_mpnn") is not None
        available = dir_found or binary_path is not None or module_available
        if binary_path:
            reason = f"protein_mpnn binary found at {binary_path}"
        elif dir_found:
            reason = "ProteinMPNN installation directory found"
        elif module_available:
            reason = "protein_mpnn Python module available"
        else:
            reason = "ProteinMPNN installation not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        """Takes PDB backbone as input (sequence param used as proxy), returns optimized sequences."""
        t0 = time.monotonic()
        # In real use, `sequence` would be the backbone PDB path/data; stub generates sequences
        designed_sequences = [
            "".join(random.choices("ACDEFGHIKLMNPQRSTVWY", k=len(sequence)))
            for _ in range(options.get("num_sequences", 3))
        ]
        confidence: dict[str, Any] = {
            "designed_sequences": designed_sequences,
            "mean_log_prob": round(random.uniform(-1.5, -0.3), 4),
            "model_version": "proteinmpnn-stub",
            "warning": "ProteinMPNN stub — not real inverse folding.",
        }
        return PredictionResult(
            pdb_data=None,  # Output is sequences, not PDB
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


class Chai1Backend(AlphaFoldBackend):
    """Chai-1 — multi-modal structure prediction (Chai Discovery)."""

    @property
    def name(self) -> str:
        return "chai1"

    def validate(self) -> BackendValidation:
        import importlib.util

        binary_path = shutil.which("chai")
        module_available = importlib.util.find_spec("chai_lab") is not None
        available = binary_path is not None or module_available
        if binary_path:
            reason = f"chai binary found at {binary_path}"
        elif module_available:
            reason = "chai_lab Python module available"
        else:
            reason = "Chai-1 installation not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="low",  # proprietary license, data may be logged
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        raise NotImplementedError("Chai1Backend.predict() is a stub")


class RFdiffusion2Backend(AlphaFoldBackend):
    """RFdiffusion2 — de novo enzyme design from reaction description."""

    @property
    def name(self) -> str:
        return "rfdiffusion2"

    def validate(self) -> BackendValidation:
        import importlib.util
        import os

        paths = [
            os.path.expanduser("~/RFdiffusion2"),
            "/opt/RFdiffusion2",
        ]
        dir_found = any(os.path.isdir(p) for p in paths)
        binary_path = shutil.which("rfdiffusion2")
        module_available = importlib.util.find_spec("rfdiffusion2") is not None
        available = dir_found or binary_path is not None or module_available
        if binary_path:
            reason = f"rfdiffusion2 binary found at {binary_path}"
        elif dir_found:
            reason = "RFdiffusion2 installation directory found"
        elif module_available:
            reason = "rfdiffusion2 Python module available"
        else:
            reason = "RFdiffusion2 installation not found"
        return BackendValidation(
            name=self.name,
            available=available,
            reason=reason,
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        t0 = time.monotonic()
        reaction_description = options.get("reaction_description", "")
        pdb = _synthetic_pdb(sequence)
        confidence: dict[str, Any] = {
            "pLDDT_mean": round(random.uniform(68.0, 88.0), 2),
            "reaction_description": reaction_description,
            "model_version": "rfdiffusion2-stub",
            "warning": "RFdiffusion2 stub — not real enzyme design.",
        }
        return PredictionResult(
            pdb_data=pdb,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_ALL_BACKENDS: list[AlphaFoldBackend] = [
    MockBackend(),
    ColabFoldBackend(),
    LocalColabFoldBackend(),
    AlphaFold2LocalBackend(),
    AlphaFold3LocalBackend(),
    AlphaFoldServerBackend(),
    AlphaFoldDBBackend(),
    Boltz1Backend(),
    Boltz2Backend(),
    ESMFoldBackend(),
    OpenFoldBackend(),
    RFdiffusionBackend(),
    ProteinMPNNBackend(),
    Chai1Backend(),
    RFdiffusion2Backend(),
]

_BACKEND_MAP: dict[str, AlphaFoldBackend] = {b.name: b for b in _ALL_BACKENDS}

# Priority order for fallback selection (local first, cloud last)
_LOCAL_PRIORITY: list[str] = [
    "mock",
    "local_colabfold",
    "colabfold",
    "alphafold2_local",
    "alphafold3_local",
    "boltz1",
    "boltz2",
    "esmfold",
    "openfold",
    "rfdiffusion",
    "proteinmpnn",
    "rfdiffusion2",
    "chai1",
]
_CLOUD_PRIORITY: list[str] = [
    "alphafold_db",
    "alphafold_server",
]


def get_backend(name: str) -> AlphaFoldBackend:
    if name not in _BACKEND_MAP:
        raise KeyError(f"Unknown backend: {name!r}. Available: {list(_BACKEND_MAP)}")
    return _BACKEND_MAP[name]


# ---------------------------------------------------------------------------
# Structure cache
# ---------------------------------------------------------------------------


def _make_input_hash(sequence: str, options: dict) -> str:
    payload = json.dumps({"sequence": sequence, "options": options}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class _CacheStats:
    hits: int = 0
    misses: int = 0


_cache_store: dict[str, PredictionResult] = {}
_cache_stats = _CacheStats()


class StructureCache:
    """In-memory structure prediction cache keyed by SHA-256 input hash."""

    def get(self, input_hash: str) -> PredictionResult | None:
        result = _cache_store.get(input_hash)
        if result is not None:
            _cache_stats.hits += 1
            return result
        _cache_stats.misses += 1
        return None

    def put(self, input_hash: str, result: PredictionResult) -> None:
        _cache_store[input_hash] = result

    @staticmethod
    def stats() -> dict[str, int]:
        return {"hits": _cache_stats.hits, "misses": _cache_stats.misses, "size": len(_cache_store)}

    @staticmethod
    def clear() -> None:
        _cache_store.clear()
        _cache_stats.hits = 0
        _cache_stats.misses = 0


_structure_cache = StructureCache()


def predict_with_cache(backend: AlphaFoldBackend, sequence: str, options: dict) -> PredictionResult:
    """Run prediction through the shared in-memory cache."""
    input_hash = _make_input_hash(f"{backend.name}:{sequence}", options)
    cached = _structure_cache.get(input_hash)
    if cached is not None:
        return PredictionResult(
            pdb_data=cached.pdb_data,
            confidence=cached.confidence,
            backend_name=cached.backend_name,
            duration_seconds=cached.duration_seconds,
            cached=True,
        )
    result = backend.predict(sequence, options)
    _structure_cache.put(input_hash, result)
    return result


# ---------------------------------------------------------------------------
# Backend selector
# ---------------------------------------------------------------------------


class BackendSelector:
    """Select a backend with optional fallback and cloud permission gates."""

    def select_backend(
        self,
        preferred: str | None,
        allow_cloud: bool,
        allow_fallback: bool,
    ) -> AlphaFoldBackend:
        """Return an available backend.

        Args:
            preferred: name of desired backend, or None to auto-select
            allow_cloud: if False, cloud backends are rejected even as fallback
            allow_fallback: if False, only the preferred backend is tried; raises if unavailable
        """
        if preferred is not None:
            backend = get_backend(preferred)  # KeyError if unknown
            validation = backend.validate()
            if validation.available:
                if validation.cloud and not allow_cloud:
                    raise PermissionError(
                        f"Backend '{preferred}' is a cloud service and allow_cloud=False"
                    )
                return backend
            if not allow_fallback:
                raise RuntimeError(
                    f"Preferred backend '{preferred}' is not available: {validation.reason}"
                )
            # Fall through to fallback selection below

        # Build candidate list in priority order
        candidates: list[str] = list(_LOCAL_PRIORITY)
        if allow_cloud:
            candidates.extend(_CLOUD_PRIORITY)

        for name in candidates:
            if preferred is not None and name == preferred:
                continue  # already tried above
            b = _BACKEND_MAP.get(name)
            if b is None:
                continue
            v = b.validate()
            if v.available:
                if v.cloud and not allow_cloud:
                    continue
                return b

        raise RuntimeError(
            "No available backend found. "
            f"allow_cloud={allow_cloud}, allow_fallback={allow_fallback}"
        )

    def get_all_backend_statuses(self) -> list[BackendValidation]:
        return [b.validate() for b in _ALL_BACKENDS]


_selector = BackendSelector()
