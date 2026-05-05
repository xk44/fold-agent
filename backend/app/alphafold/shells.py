"""Real AlphaFold backend shell/build stubs with typed request parsing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from shutil import which

PROBE_TIMEOUT = 5

from backend.app.alphafold.alphafold2_local import build_alphafold2_local_command
from backend.app.alphafold.alphafold3_local import build_alphafold3_local_command
from backend.app.alphafold.alphafold_db import build_alphafold_db_command, build_alphafold_db_result
from backend.app.alphafold.alphafold_server import build_alphafold_server_command
from backend.app.alphafold.base import list_backends
from backend.app.alphafold.colabfold import build_colabfold_command
from backend.app.alphafold.schemas import parse_alphafold_request


@dataclass
class AlphaFoldShellStatus:
    name: str
    command: str
    available: bool
    path: str | None
    validation_ok: bool
    notes: str
    validation_reason: str = ""
    version_string: str | None = None
    version_probe_ok: bool = False
    probe_timed_out: bool = False


@dataclass
class AlphaFoldDryRun:
    backend: str
    mode: str
    command: list[str]
    available: bool
    validation_ok: bool
    notes: str
    validation_reason: str = ""
    diagnostics: dict | None = None


@dataclass
class AlphaFoldExecution:
    backend: str
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
    validation_reason: str = ""


SHELL_BACKEND_SPECS = {
    "colabfold": {
        "command": "colabfold_batch",
        "notes": "ColabFold shell stub.",
        "probe_args": ["--version"],
        "env_paths": [],
        "builtin": False,
        "remote_descriptor": False,
    },
    "local_colabfold": {
        "command": "colabfold_batch",
        "notes": "LocalColabFold shell stub.",
        "probe_args": ["--version"],
        "env_paths": [],
        "builtin": False,
        "remote_descriptor": False,
    },
    "alphafold2_local": {
        "command": "run_alphafold",
        "notes": "AlphaFold2 local shell stub.",
        "probe_args": ["--help"],
        "env_paths": [("NEOVAX_ALPHAFOLD2_DATA_DIR", "alphafold2_data_dir")],
        "builtin": False,
        "remote_descriptor": False,
    },
    "alphafold3_local": {
        "command": "alphafold",
        "notes": "AlphaFold3 local shell stub.",
        "probe_args": ["--help"],
        "env_paths": [
            ("NEOVAX_ALPHAFOLD3_MODEL_DIR", "alphafold3_model_dir"),
            ("NEOVAX_ALPHAFOLD3_DB_DIR", "alphafold3_db_dir"),
        ],
        "builtin": False,
        "remote_descriptor": False,
    },
    "alphafold_server": {
        "command": "alphafold_server_submit",
        "notes": "Remote AlphaFold Server descriptor; external upload required.",
        "probe_args": [],
        "env_paths": [],
        "builtin": False,
        "remote_descriptor": True,
    },
    "alphafold_db": {
        "command": "alphafold_db_lookup",
        "notes": "AlphaFold DB reference lookup backend.",
        "probe_args": [],
        "env_paths": [],
        "builtin": True,
        "remote_descriptor": False,
    },
}


def _parse_version(text: str | None) -> str | None:
    """Extract first semver-like version from text using pattern d.d[.d]."""
    if not text:
        return None
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return m.group(1) if m else None


def _probe_command(command: str, probe_args: list[str]) -> dict:
    if not probe_args:
        return {
            "probed": False,
            "probe_ok": False,
            "exit_code": None,
            "version_first_line": None,
            "version_parsed": None,
            "probe_timed_out": False,
            "probe_error_type": None,
        }
    try:
        completed = subprocess.run(
            [command, *probe_args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        first_line = (completed.stdout or completed.stderr or "").strip().splitlines()
        vfl = first_line[0] if first_line else None
        return {
            "probed": True,
            "probe_ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "version_first_line": vfl,
            "version_parsed": _parse_version(vfl),
            "probe_timed_out": False,
            "probe_error_type": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "probed": True,
            "probe_ok": False,
            "exit_code": None,
            "version_first_line": None,
            "version_parsed": None,
            "probe_timed_out": True,
            "probe_error_type": "timeout",
        }
    except PermissionError as exc:
        return {
            "probed": True,
            "probe_ok": False,
            "exit_code": None,
            "version_first_line": str(exc),
            "version_parsed": None,
            "probe_timed_out": False,
            "probe_error_type": "permission_denied",
        }
    except FileNotFoundError as exc:
        return {
            "probed": True,
            "probe_ok": False,
            "exit_code": None,
            "version_first_line": str(exc),
            "version_parsed": None,
            "probe_timed_out": False,
            "probe_error_type": "not_found",
        }
    except OSError as exc:
        return {
            "probed": True,
            "probe_ok": False,
            "exit_code": None,
            "version_first_line": str(exc),
            "version_parsed": None,
            "probe_timed_out": False,
            "probe_error_type": "other",
        }


def _gpu_runtime_detail() -> dict:
    """Return rich GPU runtime introspection dict."""
    smi_path = which("nvidia-smi")
    base: dict = {
        "available": False,
        "nvidia_smi_path": smi_path,
        "driver_version": None,
        "gpu_count": None,
        "gpu_name": None,
        "cuda_version": None,
        "timed_out": False,
        "cuda_toolkit_available": False,
        "cuda_toolkit_version": None,
    }
    if smi_path is None:
        return base
    try:
        completed = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return base
        out = completed.stdout or ""
        # Parse driver version
        m = re.search(r"Driver Version:\s*([\d.]+)", out)
        if m:
            base["driver_version"] = m.group(1)
        # Parse CUDA version
        m = re.search(r"CUDA Version:\s*([\d.]+)", out)
        if m:
            base["cuda_version"] = m.group(1)
        # Count GPUs: lines like "|   0  NVIDIA ..." or "|   1  NVIDIA ..."
        gpu_lines = re.findall(r"^\|\s+\d+\s+(NVIDIA\s+\S[^\|]+?)\s*(?:On|Off)\s*\|", out, re.MULTILINE)
        if gpu_lines:
            base["gpu_count"] = len(gpu_lines)
            base["gpu_name"] = gpu_lines[0].strip()
        base["available"] = True
    except subprocess.TimeoutExpired:
        base["timed_out"] = True
        return base
    except OSError:
        return base

    # CUDA toolkit via nvcc
    nvcc_path = which("nvcc")
    if nvcc_path:
        try:
            nvcc_result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if nvcc_result.returncode == 0:
                nvcc_out = nvcc_result.stdout or ""
                m = re.search(r"release\s+([\d.]+)", nvcc_out)
                if m:
                    base["cuda_toolkit_available"] = True
                    base["cuda_toolkit_version"] = m.group(1)
                else:
                    base["cuda_toolkit_available"] = True
        except (OSError, subprocess.TimeoutExpired):
            pass

    return base


def _gpu_runtime_available() -> bool:
    return which("nvidia-smi") is not None


def _configured_path_checks(env_paths: list[tuple[str, str]]) -> dict[str, dict]:
    checks: dict[str, dict] = {}
    for env_name, label in env_paths:
        value = os.getenv(env_name)
        if not value:
            checks[label] = {
                "env_var": env_name,
                "configured": False,
                "path": value,
                "exists": None,
                "kind": None,
                "readable": None,
                "writable": None,
                "link_target": None,
                "resolved_target": None,
                "disk_total_bytes": None,
                "disk_free_bytes": None,
                "disk_used_bytes": None,
            }
            continue

        p = Path(value)
        is_symlink = p.is_symlink()
        exists = p.exists()

        # Determine kind
        if is_symlink and exists:
            kind = "symlink"
        elif is_symlink and not exists:
            kind = "broken_symlink"
        elif exists and p.is_dir():
            kind = "dir"
        elif exists and p.is_file():
            kind = "file"
        elif exists:
            kind = "other"
        else:
            kind = "missing"

        # Symlink targets
        link_target = None
        resolved_target = None
        if is_symlink:
            try:
                link_target = str(Path(os.readlink(value)))
            except OSError:
                pass
            if exists:
                try:
                    resolved_target = str(p.resolve())
                except OSError:
                    pass

        # Readable / writable
        readable = os.access(value, os.R_OK) if exists else None
        writable = os.access(value, os.W_OK) if exists else None

        # Disk space — only for dir/symlink (valid, existing)
        disk_total: int | None = None
        disk_free: int | None = None
        disk_used: int | None = None
        if exists and kind in ("dir", "symlink"):
            try:
                usage = shutil.disk_usage(value)
                disk_total = usage.total
                disk_free = usage.free
                disk_used = usage.used
            except OSError:
                pass

        checks[label] = {
            "env_var": env_name,
            "configured": True,
            "path": value,
            "exists": exists,
            "kind": kind,
            "readable": readable,
            "writable": writable,
            "link_target": link_target,
            "resolved_target": resolved_target,
            "disk_total_bytes": disk_total,
            "disk_free_bytes": disk_free,
            "disk_used_bytes": disk_used,
        }
    return checks


def _build_shell_status(name: str) -> AlphaFoldShellStatus:
    spec = SHELL_BACKEND_SPECS[name]
    if spec["builtin"]:
        return AlphaFoldShellStatus(
            name=name,
            command=spec["command"],
            available=True,
            path="builtin",
            validation_ok=True,
            notes=spec["notes"],
            validation_reason="Built-in reference backend; no local executable required.",
            version_string="builtin",
            version_probe_ok=True,
            probe_timed_out=False,
        )
    if spec["remote_descriptor"]:
        return AlphaFoldShellStatus(
            name=name,
            command=spec["command"],
            available=False,
            path=None,
            validation_ok=False,
            notes=spec["notes"],
            validation_reason="Remote descriptor only; local executable validation is not available.",
            version_string=None,
            version_probe_ok=False,
            probe_timed_out=False,
        )

    path = which(spec["command"])
    available = path is not None
    if not available:
        return AlphaFoldShellStatus(
            name=name,
            command=spec["command"],
            available=False,
            path=None,
            validation_ok=False,
            notes=spec["notes"],
            validation_reason=f"Command '{spec['command']}' not found on PATH.",
            version_string=None,
            version_probe_ok=False,
            probe_timed_out=False,
        )

    probe = _probe_command(spec["command"], spec["probe_args"])
    metadata = list_backends().get(name, {})
    gpu_required = bool(metadata.get("requires_gpu"))
    gpu_ok = _gpu_runtime_available() if gpu_required else True
    configured_paths = _configured_path_checks(spec["env_paths"])
    missing_paths = [
        key for key, value in configured_paths.items() if value["configured"] and value["exists"] is False
    ]

    validation_ok = bool(probe["probe_ok"]) and gpu_ok and not missing_paths
    if not probe["probe_ok"]:
        validation_reason = "Command found on PATH but executable probe failed."
    elif not gpu_ok:
        validation_reason = "Command probe succeeded but GPU runtime was not detected."
    elif missing_paths:
        validation_reason = "Command probe succeeded but configured AlphaFold paths are missing."
    else:
        validation_reason = "Command probe succeeded and local prerequisites look present."

    return AlphaFoldShellStatus(
        name=name,
        command=spec["command"],
        available=True,
        path=path,
        validation_ok=validation_ok,
        notes=spec["notes"],
        validation_reason=validation_reason,
        version_string=probe["version_first_line"],
        version_probe_ok=bool(probe["probe_ok"]),
        probe_timed_out=bool(probe["probe_timed_out"]),
    )


def _diagnostics(name: str, metadata: AlphaFoldShellStatus) -> dict:
    spec = SHELL_BACKEND_SPECS[name]
    metadata_lookup = list_backends().get(name, {})
    gpu_required = bool(metadata_lookup.get("requires_gpu"))
    configured_paths = _configured_path_checks(spec["env_paths"])
    version_probe = {
        "probed": metadata.available and not spec["builtin"] and not spec["remote_descriptor"],
        "probe_ok": metadata.version_probe_ok,
        "version_first_line": metadata.version_string,
        "version_parsed": _parse_version(metadata.version_string),
        "probe_timed_out": metadata.probe_timed_out,
        "probe_error_type": None,
    }
    gpu_detail = _gpu_runtime_detail() if gpu_required else None
    base = {
        "command_on_path": metadata.available,
        "command_name": metadata.command,
        "version_probe": None if spec["builtin"] or spec["remote_descriptor"] else version_probe,
        "gpu_runtime_available": _gpu_runtime_available() if gpu_required else None,
        "gpu_detail": gpu_detail,
        "configured_paths": configured_paths,
    }
    if name in {"colabfold", "local_colabfold"}:
        return {
            **base,
            "host_url_supported": True,
            "supports_a3m_input": True,
            "supports_multimer_fasta_colon_syntax": True,
            "supports_templates_flag": True,
            "supports_num_recycle": True,
        }
    if name == "alphafold3_local":
        return {
            **base,
            "requires_json_input": True,
            "supports_input_dir": True,
            "parses_output_directory": True,
            "harvests_model_cif_artifacts": True,
            "harvests_summary_confidences": True,
        }
    if name == "alphafold2_local":
        return {
            **base,
            "supports_fasta_input": True,
            "supports_data_dir": True,
            "supports_max_template_date": True,
        }
    if name == "alphafold_server":
        return {
            **base,
            "requires_external_upload_acknowledgement": True,
            "supports_remote_json_submission": True,
        }
    if name == "alphafold_db":
        return {
            **base,
            "supports_accession_lookup": True,
            "returns_reference_structure_metadata": True,
        }
    return base


def get_shell_backend_status(name: str) -> AlphaFoldShellStatus:
    if name not in SHELL_BACKEND_SPECS:
        raise KeyError(name)
    return _build_shell_status(name)


_ENV_SUMMARY_VARS = [
    "NEOVAX_ALPHAFOLD2_DATA_DIR",
    "NEOVAX_ALPHAFOLD3_MODEL_DIR",
    "NEOVAX_ALPHAFOLD3_DB_DIR",
]


def _build_env_summary() -> dict[str, dict]:
    summary: dict[str, dict] = {}
    for var in _ENV_SUMMARY_VARS:
        value = os.getenv(var)
        if value is None:
            summary[var] = {"status": "unset", "value": None}
        else:
            p = Path(value)
            summary[var] = {
                "status": "set",
                "value": value,
                "exists": p.exists(),
            }
    return summary


def list_alphafold_shell_statuses() -> dict[str, dict]:
    combined = list_backends()
    for name in SHELL_BACKEND_SPECS:
        metadata = get_shell_backend_status(name)
        combined[name] = {
            **combined.get(name, {"name": name}),
            **asdict(metadata),
            "diagnostics": _diagnostics(name, metadata),
        }
    combined["env_summary"] = _build_env_summary()
    return combined


def build_alphafold_command(backend_name: str, payload: dict) -> tuple[AlphaFoldShellStatus, list[str]]:
    if backend_name not in SHELL_BACKEND_SPECS:
        raise KeyError(backend_name)
    backend = get_shell_backend_status(backend_name)
    request = parse_alphafold_request(backend_name, payload)
    if backend_name in {"colabfold", "local_colabfold"}:
        command = build_colabfold_command(request)
    elif backend_name == "alphafold2_local":
        command = build_alphafold2_local_command(request)
    elif backend_name == "alphafold3_local":
        command = build_alphafold3_local_command(request)
    elif backend_name == "alphafold_server":
        command = build_alphafold_server_command(request)
    elif backend_name == "alphafold_db":
        command = build_alphafold_db_command(request)
    else:
        raise KeyError(backend_name)
    return backend, command


def build_alphafold_dry_run(backend_name: str, payload: dict) -> AlphaFoldDryRun:
    backend, command = build_alphafold_command(backend_name, payload)
    return AlphaFoldDryRun(
        backend=backend.name,
        mode="dry_run",
        command=command,
        available=backend.available,
        validation_ok=backend.validation_ok,
        notes=backend.notes,
        validation_reason=backend.validation_reason,
        diagnostics=_diagnostics(backend_name, backend),
    )


def execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
    backend, command = build_alphafold_command(backend_name, payload)
    request = parse_alphafold_request(backend_name, payload)
    if backend_name == "alphafold_db":
        return AlphaFoldExecution(
            backend=backend.name,
            mode="execute",
            command=command,
            available=True,
            validation_ok=True,
            notes=backend.notes,
            status="completed",
            stdout=__import__("json").dumps(build_alphafold_db_result(request)),
            stderr="",
            timed_out=False,
            return_code=0,
            validation_reason=backend.validation_reason,
        )
    if not backend.available:
        return AlphaFoldExecution(
            backend=backend.name,
            mode="execute",
            command=command,
            available=False,
            validation_ok=False,
            notes=backend.notes,
            status="unavailable",
            stdout="",
            stderr=f"Command '{backend.command}' not found on PATH.",
            timed_out=False,
            return_code=None,
            validation_reason=backend.validation_reason,
        )

    timeout = int(payload.get("timeout_seconds", 30))
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return AlphaFoldExecution(
            backend=backend.name,
            mode="execute",
            command=command,
            available=True,
            validation_ok=backend.validation_ok,
            notes=backend.notes,
            status="completed" if completed.returncode == 0 else "failed",
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
            return_code=completed.returncode,
            validation_reason=backend.validation_reason,
        )
    except subprocess.TimeoutExpired as exc:
        return AlphaFoldExecution(
            backend=backend.name,
            mode="execute",
            command=command,
            available=True,
            validation_ok=backend.validation_ok,
            notes=backend.notes,
            status="failed",
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"Command timed out after {timeout} seconds.",
            timed_out=True,
            return_code=None,
            validation_reason=backend.validation_reason,
        )
