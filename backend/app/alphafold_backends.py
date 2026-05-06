"""FoldAgent AlphaFold Backend Abstraction (Phase 6).

Provides:
- AlphaFoldBackend ABC with predict() / validate() contract
- Concrete stub backends (mock + 6 stubs)
- StructureCache with SHA-256 input hashing
- BackendSelector with fallback/cloud permission gates

Issue #12 note: This module coexists with backend/app/alphafold/ (shells + base).
  - THIS MODULE serves the /alphafold/v2/* API routes via main.py section 20+.
    It contains concrete Python backend implementations with real subprocess execution.
  - backend/app/alphafold/ serves the primary /alphafold/run/* routes (sections 1-19).
    It wraps CLI tools via shell descriptors and schema-validated command builders.
Neither system is dead code. Do not remove either without migrating its route group.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
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


def _synthetic_pdb(sequence: str, rng: random.Random | None = None) -> str:
    """Generate minimal synthetic PDB text for testing/mock purposes."""
    _rng = rng or random
    lines: list[str] = [
        "REMARK  FoldAgent mock structure — not a real prediction",
        "REMARK  sequence length: " + str(len(sequence)),
    ]
    for i, aa in enumerate(sequence[:50], start=1):
        plddt = round(_rng.uniform(60.0, 95.0), 2)
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
        # Issue #13: seed RNG from input hash so output is deterministic per sequence.
        rng = random.Random(hashlib.sha256(sequence.encode()).hexdigest())
        t0 = time.monotonic()
        pdb = _synthetic_pdb(sequence, rng=rng)
        confidence = {
            "pLDDT_mean": round(rng.uniform(70.0, 92.0), 2),
            "pLDDT_min": round(rng.uniform(55.0, 70.0), 2),
            "pLDDT_max": round(rng.uniform(90.0, 99.0), 2),
            "pAE_mean": round(rng.uniform(5.0, 18.0), 2),
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
            reason=f"colabfold_batch found at {path}"
            if available
            else "colabfold_batch not found on PATH",
            gpu_required=True,
            cloud=False,
            privacy_risk="low",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        binary = shutil.which("colabfold_batch") or os.environ.get("FOLDAGENT_COLABFOLD_PATH")
        if not binary:
            raise NotImplementedError(
                "ColabFold not found — install via `pip install colabfold` or set "
                "FOLDAGENT_COLABFOLD_PATH to the colabfold_batch binary path"
            )
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_colabfold_") as tmpdir:
            # Write FASTA input
            job_name = options.get("job_name", "query")
            fasta_path = Path(tmpdir) / f"{job_name}.fasta"
            fasta_path.write_text(f">{job_name}\n{sequence}\n", encoding="utf-8")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            cmd = [binary, str(fasta_path), str(output_dir)]
            if options.get("num_recycle") is not None:
                cmd.extend(["--num-recycle", str(options["num_recycle"])])
            if options.get("num_seeds") is not None:
                cmd.extend(["--num-seeds", str(options["num_seeds"])])
            if options.get("use_templates"):
                cmd.append("--templates")
            if options.get("host_url"):
                cmd.extend(["--host-url", options["host_url"]])
            if options.get("max_msa"):
                cmd.extend(["--max-msa", str(options["max_msa"])])

            timeout = int(options.get("timeout_seconds", 3600))
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"ColabFold timed out after {timeout}s") from exc
            except OSError as exc:
                raise RuntimeError(f"ColabFold failed to launch: {exc}") from exc

            if proc.returncode != 0:
                raise RuntimeError(f"ColabFold exited {proc.returncode}:\n{proc.stderr[:2000]}")

            # Find best ranked PDB (ColabFold writes rank_001_*.pdb or .cif)
            pdb_data: str | None = None
            confidence: dict[str, Any] = {}
            pdb_files = sorted(output_dir.rglob("*rank_001*.pdb"))
            cif_files = sorted(output_dir.rglob("*rank_001*.cif"))
            if pdb_files:
                pdb_data = pdb_files[0].read_text(encoding="utf-8", errors="replace")
            elif cif_files:
                pdb_data = cif_files[0].read_text(encoding="utf-8", errors="replace")

            # Parse scores JSON if present
            score_files = sorted(output_dir.rglob("*rank_001*.json"))
            if score_files:
                try:
                    scores = json.loads(score_files[0].read_text(encoding="utf-8"))
                    plddt = scores.get("plddt", [])
                    if plddt:
                        confidence["pLDDT_mean"] = round(sum(plddt) / len(plddt), 2)
                        confidence["pLDDT_min"] = round(min(plddt), 2)
                        confidence["pLDDT_max"] = round(max(plddt), 2)
                    if "ptm" in scores:
                        confidence["pTM"] = scores["ptm"]
                    if "pae" in scores:
                        pae_flat = [v for row in scores["pae"] for v in row]
                        confidence["pAE_mean"] = (
                            round(sum(pae_flat) / len(pae_flat), 2) if pae_flat else None
                        )
                except (json.JSONDecodeError, OSError):
                    pass

            if pdb_data is None:
                raise RuntimeError(
                    "ColabFold completed but no output PDB/CIF found in output directory"
                )

            confidence.setdefault("model_version", "colabfold")
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
            else (
                "colabfold_batch on PATH (may be system)" if path else "colabfold_batch not found"
            )
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
        # Prefer explicit env override, then common local install paths, then PATH
        binary = os.environ.get("FOLDAGENT_LOCALCOLABFOLD_PATH")
        if not binary:
            local_candidates = [
                os.path.expanduser("~/localcolabfold/colabfold-conda/bin/colabfold_batch"),
                os.path.expanduser("~/.local/bin/colabfold_batch"),
            ]
            for p in local_candidates:
                if os.path.isfile(p) and os.access(p, os.X_OK):
                    binary = p
                    break
        if not binary:
            binary = shutil.which("colabfold_batch")
        if not binary:
            raise NotImplementedError(
                "LocalColabFold not found — install via https://github.com/YoshitakaMo/localcolabfold "
                "or set FOLDAGENT_LOCALCOLABFOLD_PATH to the colabfold_batch binary path"
            )

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_localcf_") as tmpdir:
            job_name = options.get("job_name", "query")
            fasta_path = Path(tmpdir) / f"{job_name}.fasta"
            fasta_path.write_text(f">{job_name}\n{sequence}\n", encoding="utf-8")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            cmd = [binary, str(fasta_path), str(output_dir)]
            if options.get("num_recycle") is not None:
                cmd.extend(["--num-recycle", str(options["num_recycle"])])
            if options.get("num_seeds") is not None:
                cmd.extend(["--num-seeds", str(options["num_seeds"])])
            if options.get("use_templates"):
                cmd.append("--templates")
            if options.get("max_msa"):
                cmd.extend(["--max-msa", str(options["max_msa"])])

            timeout = int(options.get("timeout_seconds", 3600))
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"LocalColabFold timed out after {timeout}s") from exc
            except OSError as exc:
                raise RuntimeError(f"LocalColabFold failed to launch: {exc}") from exc

            if proc.returncode != 0:
                raise RuntimeError(
                    f"LocalColabFold exited {proc.returncode}:\n{proc.stderr[:2000]}"
                )

            pdb_data: str | None = None
            confidence: dict[str, Any] = {}
            pdb_files = sorted(output_dir.rglob("*rank_001*.pdb"))
            cif_files = sorted(output_dir.rglob("*rank_001*.cif"))
            if pdb_files:
                pdb_data = pdb_files[0].read_text(encoding="utf-8", errors="replace")
            elif cif_files:
                pdb_data = cif_files[0].read_text(encoding="utf-8", errors="replace")

            score_files = sorted(output_dir.rglob("*rank_001*.json"))
            if score_files:
                try:
                    scores = json.loads(score_files[0].read_text(encoding="utf-8"))
                    plddt = scores.get("plddt", [])
                    if plddt:
                        confidence["pLDDT_mean"] = round(sum(plddt) / len(plddt), 2)
                        confidence["pLDDT_min"] = round(min(plddt), 2)
                        confidence["pLDDT_max"] = round(max(plddt), 2)
                    if "ptm" in scores:
                        confidence["pTM"] = scores["ptm"]
                    if "pae" in scores:
                        pae_flat = [v for row in scores["pae"] for v in row]
                        confidence["pAE_mean"] = (
                            round(sum(pae_flat) / len(pae_flat), 2) if pae_flat else None
                        )
                except (json.JSONDecodeError, OSError):
                    pass

            if pdb_data is None:
                raise RuntimeError(
                    "LocalColabFold completed but no output PDB/CIF found in output directory"
                )

            confidence.setdefault("model_version", "localcolabfold")
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
            reason="AlphaFold2 directory found"
            if found
            else "AlphaFold2 installation directory not found",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        # Locate run_alphafold.py or run_alphafold binary
        binary = (
            os.environ.get("FOLDAGENT_ALPHAFOLD2_BINARY")
            or shutil.which("run_alphafold")
            or shutil.which("run_alphafold.py")
        )
        # Also check common AF2 install dirs for run_alphafold.py
        if not binary:
            af2_candidates = [
                os.path.expanduser("~/alphafold/run_alphafold.py"),
                "/opt/alphafold/run_alphafold.py",
                "/usr/local/alphafold/run_alphafold.py",
            ]
            for p in af2_candidates:
                if os.path.isfile(p):
                    binary = p
                    break
        if not binary:
            raise NotImplementedError(
                "AlphaFold2 not found — install from https://github.com/google-deepmind/alphafold "
                "or set FOLDAGENT_ALPHAFOLD2_BINARY to the run_alphafold.py path"
            )

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_af2_") as tmpdir:
            job_name = options.get("job_name", "query")
            fasta_path = Path(tmpdir) / f"{job_name}.fasta"
            fasta_path.write_text(f">{job_name}\n{sequence}\n", encoding="utf-8")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            # Determine invocation: .py script needs python, bare binary runs directly
            if binary.endswith(".py"):
                cmd = ["python", binary]
            else:
                cmd = [binary]

            cmd.extend(["--fasta_paths", str(fasta_path), "--output_dir", str(output_dir)])

            data_dir = options.get("data_dir") or os.environ.get("FOLDAGENT_ALPHAFOLD2_DATA_DIR")
            if data_dir:
                cmd.extend(["--data_dir", data_dir])
            if options.get("max_template_date"):
                cmd.extend(["--max_template_date", options["max_template_date"]])
            if options.get("model_preset"):
                cmd.extend(["--model_preset", options["model_preset"]])
            if options.get("db_preset"):
                cmd.extend(["--db_preset", options["db_preset"]])

            timeout = int(options.get("timeout_seconds", 7200))
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"AlphaFold2 timed out after {timeout}s") from exc
            except OSError as exc:
                raise RuntimeError(f"AlphaFold2 failed to launch: {exc}") from exc

            if proc.returncode != 0:
                raise RuntimeError(f"AlphaFold2 exited {proc.returncode}:\n{proc.stderr[:2000]}")

            # AF2 writes ranked PDBs: ranked_0.pdb is the top model
            pdb_data: str | None = None
            confidence: dict[str, Any] = {}

            # Output goes under output_dir/<job_name>/
            result_dir = output_dir / job_name
            ranked_pdb = result_dir / "ranked_0.pdb"
            if ranked_pdb.exists():
                pdb_data = ranked_pdb.read_text(encoding="utf-8", errors="replace")
            else:
                # Fallback: any PDB in the output tree
                pdbs = sorted(output_dir.rglob("ranked_0.pdb"))
                if not pdbs:
                    pdbs = sorted(output_dir.rglob("*.pdb"))
                if pdbs:
                    pdb_data = pdbs[0].read_text(encoding="utf-8", errors="replace")

            # Parse ranking_debug.json for pLDDT
            ranking_json = result_dir / "ranking_debug.json"
            if not ranking_json.exists():
                ranking_files = sorted(output_dir.rglob("ranking_debug.json"))
                if ranking_files:
                    ranking_json = ranking_files[0]
            if ranking_json.exists():
                try:
                    ranking = json.loads(ranking_json.read_text(encoding="utf-8"))
                    # ranking_debug.json has {"plddts": {"model_N": score, ...}}
                    plddts = ranking.get("plddts", {})
                    if plddts:
                        best_key = sorted(plddts, key=lambda k: plddts[k], reverse=True)[0]
                        confidence["pLDDT_mean"] = round(plddts[best_key], 2)
                except (json.JSONDecodeError, OSError, KeyError):
                    pass

            if pdb_data is None:
                raise RuntimeError(
                    "AlphaFold2 completed but no output PDB found in output directory"
                )

            confidence.setdefault("model_version", "alphafold2")
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
            reason="AlphaFold3 directory found"
            if found
            else "AlphaFold3 installation directory not found",
            gpu_required=True,
            cloud=False,
            privacy_risk="none",
        )

    def predict(self, sequence: str, options: dict) -> PredictionResult:
        binary = os.environ.get("FOLDAGENT_ALPHAFOLD3_BINARY") or shutil.which("alphafold")
        if not binary:
            af3_candidates = [
                os.path.expanduser("~/alphafold3/run_alphafold.py"),
                "/opt/alphafold3/run_alphafold.py",
                "/usr/local/alphafold3/run_alphafold.py",
            ]
            for p in af3_candidates:
                if os.path.isfile(p):
                    binary = p
                    break
        if not binary:
            raise NotImplementedError(
                "AlphaFold3 not found — install from https://github.com/google-deepmind/alphafold3 "
                "or set FOLDAGENT_ALPHAFOLD3_BINARY to the alphafold binary path"
            )

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_af3_") as tmpdir:
            job_name = options.get("job_name", "query")
            # Build AF3 JSON input
            af3_input = {
                "name": job_name,
                "modelSeeds": options.get("model_seeds", [1]),
                "sequences": [{"protein": {"id": "A", "sequence": sequence}}],
                "dialect": "alphafold3",
                "version": 4,
            }
            json_path = Path(tmpdir) / f"{job_name}.json"
            json_path.write_text(json.dumps(af3_input, indent=2), encoding="utf-8")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            if binary.endswith(".py"):
                cmd = ["python", binary]
            else:
                cmd = [binary]

            cmd.extend(["--json_path", str(json_path), "--output_dir", str(output_dir)])

            model_dir = options.get("model_dir") or os.environ.get("FOLDAGENT_ALPHAFOLD3_MODEL_DIR")
            db_dir = options.get("db_dir") or os.environ.get("FOLDAGENT_ALPHAFOLD3_DB_DIR")
            if model_dir:
                cmd.extend(["--model_dir", model_dir])
            if db_dir:
                cmd.extend(["--db_dir", db_dir])

            timeout = int(options.get("timeout_seconds", 7200))
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"AlphaFold3 timed out after {timeout}s") from exc
            except OSError as exc:
                raise RuntimeError(f"AlphaFold3 failed to launch: {exc}") from exc

            if proc.returncode != 0:
                raise RuntimeError(f"AlphaFold3 exited {proc.returncode}:\n{proc.stderr[:2000]}")

            confidence: dict[str, Any] = {}
            pdb_data: str | None = None

            # AF3 produces <job_name>_model.cif at the output_dir root
            job_dir = output_dir / job_name
            cif_candidates = sorted(
                (job_dir if job_dir.exists() else output_dir).rglob("*_model.cif")
            )
            if cif_candidates:
                pdb_data = cif_candidates[0].read_text(encoding="utf-8", errors="replace")

            # Parse summary confidences JSON
            summary_candidates = sorted(
                (job_dir if job_dir.exists() else output_dir).rglob("*_summary_confidences.json")
            )
            if summary_candidates:
                try:
                    summary = json.loads(summary_candidates[0].read_text(encoding="utf-8"))
                    for key in ("ptm", "iptm", "ranking_score", "fraction_disordered"):
                        if key in summary:
                            confidence[key] = summary[key]
                    # Derive pLDDT_mean from atom_plddts if available via confidences.json
                except (json.JSONDecodeError, OSError):
                    pass

            conf_candidates = sorted(
                (job_dir if job_dir.exists() else output_dir).rglob("*_confidences.json")
            )
            if conf_candidates:
                try:
                    conf = json.loads(conf_candidates[0].read_text(encoding="utf-8"))
                    plddts = conf.get("atom_plddts", [])
                    if plddts:
                        confidence["pLDDT_mean"] = round(sum(plddts) / len(plddts), 2)
                        confidence["pLDDT_min"] = round(min(plddts), 2)
                        confidence["pLDDT_max"] = round(max(plddts), 2)
                    pae = conf.get("pae", [])
                    if pae:
                        flat = [v for row in pae for v in row]
                        if flat:
                            confidence["pAE_mean"] = round(sum(flat) / len(flat), 2)
                except (json.JSONDecodeError, OSError):
                    pass

            if pdb_data is None:
                raise RuntimeError(
                    "AlphaFold3 completed but no output CIF found in output directory"
                )

            confidence.setdefault("model_version", "alphafold3")
            confidence["output_format"] = "mmcif"
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
        try:
            import httpx
        except ImportError as exc:
            raise NotImplementedError(
                "AlphaFoldServerBackend requires httpx — install via `pip install httpx`"
            ) from exc

        # AlphaFold Server: https://alphafoldserver.com
        # Submits a JSON job payload and polls for results.
        # Authentication cookie / API key must be set via FOLDAGENT_AFSERVER_COOKIE or
        # FOLDAGENT_AFSERVER_API_KEY env vars.
        base_url = os.environ.get("FOLDAGENT_AFSERVER_BASE_URL", "https://alphafoldserver.com")
        api_key = os.environ.get("FOLDAGENT_AFSERVER_API_KEY")
        auth_cookie = os.environ.get("FOLDAGENT_AFSERVER_COOKIE")
        if not api_key and not auth_cookie:
            raise NotImplementedError(
                "AlphaFold Server requires authentication — set FOLDAGENT_AFSERVER_API_KEY "
                "or FOLDAGENT_AFSERVER_COOKIE (session cookie from alphafoldserver.com)"
            )

        t0 = time.monotonic()
        job_name = options.get("job_name", "foldagent_job")

        # Build AlphaFold Server JSON payload (alphafoldserver dialect v1)
        job_payload = [
            {
                "name": job_name,
                "modelSeeds": options.get("model_seeds", []),
                "sequences": [
                    {
                        "proteinChain": {
                            "sequence": sequence,
                            "count": 1,
                        }
                    }
                ],
                "dialect": "alphafoldserver",
                "version": 1,
            }
        ]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        cookies: dict[str, str] = {}
        if api_key:
            headers["X-API-Key"] = api_key
        if auth_cookie:
            # auth_cookie may be a raw session value or "name=value" pair
            if "=" in auth_cookie:
                cname, _, cval = auth_cookie.partition("=")
                cookies[cname.strip()] = cval.strip()
            else:
                cookies["session"] = auth_cookie

        timeout_s = int(options.get("timeout_seconds", 300))
        poll_interval = float(options.get("poll_interval_seconds", 10.0))

        try:
            with httpx.Client(
                base_url=base_url,
                headers=headers,
                cookies=cookies,
                timeout=30.0,
            ) as client:
                # Submit job
                resp = client.post("/api/prediction", content=json.dumps(job_payload))
                resp.raise_for_status()
                submit_data = resp.json()

                # Extract job ID — server returns list of job descriptors
                if isinstance(submit_data, list) and submit_data:
                    job_id = submit_data[0].get("jobId") or submit_data[0].get("id")
                elif isinstance(submit_data, dict):
                    job_id = submit_data.get("jobId") or submit_data.get("id")
                else:
                    job_id = None

                if not job_id:
                    raise RuntimeError(
                        f"AlphaFold Server did not return a job ID. Response: {submit_data!r}"
                    )

                # Poll for completion
                deadline = t0 + timeout_s
                while True:
                    if time.monotonic() > deadline:
                        raise RuntimeError(
                            f"AlphaFold Server job {job_id!r} did not complete within {timeout_s}s"
                        )
                    status_resp = client.get(f"/api/prediction/{job_id}")
                    status_resp.raise_for_status()
                    status_data = status_resp.json()
                    status = (status_data.get("status") or "").lower()

                    if status in ("completed", "done", "success"):
                        break
                    if status in ("failed", "error", "cancelled"):
                        raise RuntimeError(
                            f"AlphaFold Server job {job_id!r} failed with status {status!r}"
                        )
                    time.sleep(poll_interval)

                # Download result CIF/PDB
                result_url = status_data.get("resultUrl") or f"/api/prediction/{job_id}/download"
                dl_resp = client.get(result_url)
                dl_resp.raise_for_status()
                pdb_data = dl_resp.text

                confidence: dict[str, Any] = {
                    "model_version": "alphafold_server",
                    "job_id": job_id,
                    "status": status,
                }
                # Extract confidence if the response includes JSON metrics
                try:
                    result_json = dl_resp.json()
                    for key in ("pLDDT_mean", "ptm", "iptm", "ranking_score"):
                        if key in result_json:
                            confidence[key] = result_json[key]
                    # If the download was CIF/PDB text, the json() call would fail
                    # which is handled by the except below
                except Exception:
                    pass

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"AlphaFold Server HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"AlphaFold Server network error: {exc}") from exc

        return PredictionResult(
            pdb_data=pdb_data,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


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
        try:
            import httpx
        except ImportError as exc:
            raise NotImplementedError(
                "AlphaFoldDBBackend requires httpx — install via `pip install httpx`"
            ) from exc

        # `sequence` is treated as a UniProt accession (e.g. "P00533") when it
        # looks like one; otherwise callers must pass accession in options.
        accession = options.get("accession") or sequence.strip()
        if not accession:
            raise ValueError("AlphaFoldDBBackend requires a UniProt accession")

        # Basic accession sanity check (UniProt format: 1-letter + 5 alphanum, or
        # newer 10-character format)
        import re as _re

        if not _re.match(r"^[A-Za-z0-9]{6,10}$", accession):
            raise ValueError(
                f"Invalid UniProt accession format: {accession!r}. "
                "Expected 6-10 alphanumeric characters (e.g. 'P00533')"
            )

        base_url = "https://alphafold.ebi.ac.uk"
        db_version = options.get("db_version", "v4")
        t0 = time.monotonic()

        try:
            with httpx.Client(base_url=base_url, timeout=60.0) as client:
                # Fetch metadata from the EBI API
                meta_resp = client.get(
                    f"/api/prediction/{accession}?key=AIzaSyCeurAJz7ZGjPQUtEaerUkBZ3TfmuXIVAw"
                )
                if meta_resp.status_code == 404:
                    raise RuntimeError(
                        f"UniProt accession {accession!r} not found in AlphaFold DB. "
                        "Check the accession is correct and the protein has a pre-computed structure."
                    )
                meta_resp.raise_for_status()
                entries = meta_resp.json()

                if not entries:
                    raise RuntimeError(
                        f"AlphaFold DB returned empty results for accession {accession!r}"
                    )

                entry = entries[0] if isinstance(entries, list) else entries
                cif_url = entry.get("cifUrl") or (
                    f"{base_url}/files/AF-{accession}-F1-model_{db_version}.cif"
                )
                pae_url = entry.get("paeDocUrl") or (
                    f"{base_url}/files/AF-{accession}-F1-predicted_aligned_error_{db_version}.json"
                )

                # Download CIF structure
                cif_resp = client.get(cif_url)
                cif_resp.raise_for_status()
                pdb_data = cif_resp.text

                # Download PAE JSON for confidence metrics
                confidence: dict[str, Any] = {
                    "model_version": entry.get("latestVersion") or db_version,
                    "accession": accession,
                    "source_url": f"{base_url}/entry/{accession}",
                    "output_format": "mmcif",
                }
                if entry.get("pLDDT") is not None:
                    confidence["pLDDT_mean"] = entry["pLDDT"]
                try:
                    pae_resp = client.get(pae_url)
                    if pae_resp.status_code == 200:
                        pae_data = pae_resp.json()
                        # EBI returns [{"predicted_aligned_error": [[...]], "max_predicted_aligned_error": N}]
                        if isinstance(pae_data, list) and pae_data:
                            pae_data = pae_data[0]
                        pae_matrix = pae_data.get("predicted_aligned_error", [])
                        if pae_matrix:
                            flat = [v for row in pae_matrix for v in row]
                            if flat:
                                confidence["pAE_mean"] = round(sum(flat) / len(flat), 2)
                        if "max_predicted_aligned_error" in pae_data:
                            confidence["pAE_max"] = pae_data["max_predicted_aligned_error"]
                except Exception:
                    pass  # PAE is optional; don't fail the whole prediction

        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"AlphaFold DB HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"AlphaFold DB network error: {exc}") from exc

        return PredictionResult(
            pdb_data=pdb_data,
            confidence=confidence,
            backend_name=self.name,
            duration_seconds=time.monotonic() - t0,
        )


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
        import importlib.util

        # Locate OpenFold inference script
        binary = (
            os.environ.get("FOLDAGENT_OPENFOLD_BINARY")
            or shutil.which("run_pretrained_openfold")
            or shutil.which("run_pretrained_openfold.py")
        )
        if not binary:
            of_candidates = [
                os.path.expanduser("~/openfold/run_pretrained_openfold.py"),
                "/opt/openfold/run_pretrained_openfold.py",
                "/usr/local/openfold/run_pretrained_openfold.py",
            ]
            for p in of_candidates:
                if os.path.isfile(p):
                    binary = p
                    break

        # Fallback: use openfold Python module directly if installed
        module_available = importlib.util.find_spec("openfold") is not None
        if not binary and not module_available:
            raise NotImplementedError(
                "OpenFold not found — install from https://github.com/aqlaboratory/openfold "
                "or set FOLDAGENT_OPENFOLD_BINARY to the run_pretrained_openfold.py path"
            )

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_openfold_") as tmpdir:
            job_name = options.get("job_name", "query")
            fasta_path = Path(tmpdir) / f"{job_name}.fasta"
            fasta_path.write_text(f">{job_name}\n{sequence}\n", encoding="utf-8")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            if binary:
                if binary.endswith(".py"):
                    cmd = ["python", binary]
                else:
                    cmd = [binary]

                cmd.extend([str(fasta_path), str(fasta_path)])  # fasta_dir + template_mmcif_dir
                cmd.extend(["--output_dir", str(output_dir)])

                data_dir = options.get("data_dir") or os.environ.get("FOLDAGENT_OPENFOLD_DATA_DIR")
                if data_dir:
                    cmd.extend(
                        [
                            "--uniref90_database_path",
                            os.path.join(data_dir, "uniref90/uniref90.fasta"),
                        ]
                    )
                    cmd.extend(
                        [
                            "--mgnify_database_path",
                            os.path.join(data_dir, "mgnify/mgy_clusters_2018_12.fa"),
                        ]
                    )
                    cmd.extend(["--pdb70_database_path", os.path.join(data_dir, "pdb70/pdb70")])

                model_device = options.get("model_device", "cuda:0")
                cmd.extend(["--model_device", model_device])

                jax_param_path = options.get("jax_param_path") or os.environ.get(
                    "FOLDAGENT_OPENFOLD_PARAM_PATH"
                )
                if jax_param_path:
                    cmd.extend(["--jax_param_path", jax_param_path])

                timeout = int(options.get("timeout_seconds", 7200))
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=timeout, check=False
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(f"OpenFold timed out after {timeout}s") from exc
                except OSError as exc:
                    raise RuntimeError(f"OpenFold failed to launch: {exc}") from exc

                if proc.returncode != 0:
                    raise RuntimeError(f"OpenFold exited {proc.returncode}:\n{proc.stderr[:2000]}")
            else:
                # Module-level invocation stub — openfold lacks a universal CLI entry point
                raise NotImplementedError(
                    "OpenFold Python module detected but no run_pretrained_openfold.py script found. "
                    "Set FOLDAGENT_OPENFOLD_BINARY to the inference script path."
                )

            pdb_data: str | None = None
            confidence: dict[str, Any] = {}

            # OpenFold writes PDB files to output_dir
            pdb_files = sorted(output_dir.rglob("*.pdb"))
            if pdb_files:
                pdb_data = pdb_files[0].read_text(encoding="utf-8", errors="replace")

            if pdb_data is None:
                raise RuntimeError("OpenFold completed but no output PDB found in output directory")

            # Extract pLDDT from PDB B-factor column (residue-level pLDDT in OpenFold)
            plddts = []
            for line in pdb_data.splitlines():
                if line.startswith("ATOM") and len(line) >= 66:
                    try:
                        plddts.append(float(line[60:66].strip()))
                    except ValueError:
                        pass
            if plddts:
                confidence["pLDDT_mean"] = round(sum(plddts) / len(plddts), 2)
                confidence["pLDDT_min"] = round(min(plddts), 2)
                confidence["pLDDT_max"] = round(max(plddts), 2)

            confidence.setdefault("model_version", "openfold")
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
        import importlib.util

        binary = os.environ.get("FOLDAGENT_CHAI1_BINARY") or shutil.which("chai")
        module_available = importlib.util.find_spec("chai_lab") is not None

        if not binary and not module_available:
            raise NotImplementedError(
                "Chai-1 not found — install via `pip install chai_lab` "
                "(https://github.com/chaidiscovery/chai-lab) or set "
                "FOLDAGENT_CHAI1_BINARY to the chai binary path"
            )

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="foldagent_chai1_") as tmpdir:
            job_name = options.get("job_name", "query")
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()

            pdb_data: str | None = None
            confidence: dict[str, Any] = {}

            if binary:
                # CLI invocation: chai fold --sequence <seq> --output-dir <dir>
                # Chai CLI accepts FASTA or inline sequence depending on version.
                fasta_path = Path(tmpdir) / f"{job_name}.fasta"
                fasta_path.write_text(f">{job_name}|protein\n{sequence}\n", encoding="utf-8")

                cmd = [binary, "fold", str(fasta_path), str(output_dir)]
                num_trunk_recycles = options.get("num_trunk_recycles")
                num_diffusion_samples = options.get("num_diffusion_samples")
                if num_trunk_recycles is not None:
                    cmd.extend(["--num-trunk-recycles", str(num_trunk_recycles)])
                if num_diffusion_samples is not None:
                    cmd.extend(["--num-diffusion-samples", str(num_diffusion_samples)])

                timeout = int(options.get("timeout_seconds", 3600))
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=timeout, check=False
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(f"Chai-1 timed out after {timeout}s") from exc
                except OSError as exc:
                    raise RuntimeError(f"Chai-1 failed to launch: {exc}") from exc

                if proc.returncode != 0:
                    raise RuntimeError(f"Chai-1 exited {proc.returncode}:\n{proc.stderr[:2000]}")

                # Chai-1 writes pred.model_idx_N.cif or .pdb to the output dir
                cif_files = sorted(output_dir.rglob("*.cif"))
                pdb_files = sorted(output_dir.rglob("*.pdb"))
                if cif_files:
                    pdb_data = cif_files[0].read_text(encoding="utf-8", errors="replace")
                elif pdb_files:
                    pdb_data = pdb_files[0].read_text(encoding="utf-8", errors="replace")

                # Parse scores npz if present (chai_lab outputs scores.model_idx_N.npz)
                try:
                    import numpy as _np

                    score_files = sorted(output_dir.rglob("scores.model_idx_*.npz"))
                    if score_files:
                        scores = _np.load(str(score_files[0]))
                        if "plddt" in scores:
                            plddts = scores["plddt"].tolist()
                            confidence["pLDDT_mean"] = round(sum(plddts) / len(plddts), 2)
                            confidence["pLDDT_min"] = round(min(plddts), 2)
                            confidence["pLDDT_max"] = round(max(plddts), 2)
                        if "ptm" in scores:
                            confidence["pTM"] = float(scores["ptm"])
                        if "iptm" in scores:
                            confidence["ipTM"] = float(scores["iptm"])
                except Exception:
                    pass

            elif module_available:
                # Python module invocation via chai_lab API
                try:
                    from pathlib import Path as _Path

                    import torch as _torch
                    from chai_lab.chai1 import run_inference

                    fasta_path = Path(tmpdir) / f"{job_name}.fasta"
                    fasta_path.write_text(f">{job_name}|protein\n{sequence}\n", encoding="utf-8")

                    output_paths = run_inference(
                        fasta_file=fasta_path,
                        output_dir=output_dir,
                        num_trunk_recycles=options.get("num_trunk_recycles", 3),
                        num_diffn_samples=options.get("num_diffusion_samples", 5),
                        seed=options.get("seed", 42),
                        device=_torch.device(options.get("device", "cuda:0")),
                        use_esm_embeddings=options.get("use_esm_embeddings", True),
                    )
                    # output_paths is a dict with "cif" and "scores" keys
                    cif_path = output_paths.get("cif") if isinstance(output_paths, dict) else None
                    if cif_path and Path(cif_path).exists():
                        pdb_data = Path(cif_path).read_text(encoding="utf-8", errors="replace")

                    scores_path = (
                        output_paths.get("scores") if isinstance(output_paths, dict) else None
                    )
                    if scores_path and Path(scores_path).exists():
                        try:
                            import numpy as _np

                            scores = _np.load(str(scores_path))
                            if "plddt" in scores:
                                plddts = scores["plddt"].tolist()
                                confidence["pLDDT_mean"] = round(sum(plddts) / len(plddts), 2)
                                confidence["pLDDT_min"] = round(min(plddts), 2)
                                confidence["pLDDT_max"] = round(max(plddts), 2)
                            if "ptm" in scores:
                                confidence["pTM"] = float(scores["ptm"])
                        except Exception:
                            pass

                    # Fallback: scan output dir for CIF
                    if pdb_data is None:
                        cif_files = sorted(output_dir.rglob("*.cif"))
                        if cif_files:
                            pdb_data = cif_files[0].read_text(encoding="utf-8", errors="replace")

                except ImportError as exc:
                    raise RuntimeError(
                        f"chai_lab module import failed: {exc}. "
                        "Ensure chai_lab and its dependencies (torch, etc.) are installed."
                    ) from exc
                except Exception as exc:
                    raise RuntimeError(f"Chai-1 inference failed: {exc}") from exc

            if pdb_data is None:
                raise RuntimeError(
                    "Chai-1 completed but no output CIF/PDB found in output directory"
                )

            confidence.setdefault("model_version", "chai1")
            confidence.setdefault("output_format", "mmcif")
            return PredictionResult(
                pdb_data=pdb_data,
                confidence=confidence,
                backend_name=self.name,
                duration_seconds=time.monotonic() - t0,
            )


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
