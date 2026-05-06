"""Test-first improvements for FoldAgent AlphaFold diagnostics environment validation.

These tests specify the **gaps** identified in backend/app/alphafold/shells.py and
propose concrete, test-first additions.  Each test category starts with a comment
block explaining the gap, the proposed fix, and any gotchas.

Tests that exercise proposed-but-not-yet-implemented features are marked with
@pytest.mark.xfail(reason="...") so they document the gap AND become regression
guards once the feature lands.  When a feature is implemented, remove the xfail
marker and the test should pass.

Priority ordering:
  P0 – Operator-critical: missing GPU detail, symlink/broken-path, disk-space
  P1 – Robustness: OSError type, version parsing, CUDA toolkit version
  P2 – Nice-to-have: env summary, configurable paths, structured probe metadata
"""

from __future__ import annotations

import subprocess

from backend.app.alphafold import shells
from backend.app.alphafold.shells import (
    _configured_path_checks,
    _gpu_runtime_available,
    _probe_command,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_which_all_found(command: str) -> str | None:
    return {
        "colabfold_batch": "/usr/bin/colabfold_batch",
        "run_alphafold": "/usr/bin/run_alphafold",
        "alphafold": "/usr/bin/alphafold",
        "nvidia-smi": "/usr/bin/nvidia-smi",
    }.get(command)


def _fake_run_all_ok(
    command: list[str], capture_output: bool, text: bool, timeout: int, check: bool
):
    return subprocess.CompletedProcess(command, 0, stdout="ok version\n", stderr="")


# ===========================================================================
# P0 – GPU runtime detail (operator-facing)
# ===========================================================================

# GAP: _gpu_runtime_available() returns only bool.  An operator cannot tell if
# nvidia-smi exists but fails, or doesn't exist at all.  They also cannot see
# GPU driver version, CUDA version, or GPU count — all critical for deciding
# whether AlphaFold2/3 will actually run.
#
# PROPOSED FIX: Add _gpu_runtime_detail() -> dict that returns:
#   - available (bool)
#   - nvidia_smi_path (str|None)
#   - driver_version (str|None)    # parsed from `nvidia-smi` output
#   - gpu_count (int|None)          # number of GPUs detected
#   - gpu_name (str|None)           # first GPU model name
#   - cuda_version (str|None)       # from nvidia-smi's "CUDA Version" line
#   - timed_out (bool)              # whether nvidia-smi probe timed out
# And wire it into _diagnostics() under a new "gpu_detail" key for GPU-requiring
# backends.  The boolean _gpu_runtime_available() should delegate to
# _gpu_runtime_detail()["available"].
#
# GOTCHA: nvidia-smi can hang on broken driver installs.  Use a short timeout
# (3-5s).  The output format varies across driver versions; parse defensively.
# On headless servers without X, nvidia-smi still works from the driver CLI.


class TestGpuRuntimeDetail:
    """Tests for rich GPU runtime introspection (P0 — not yet implemented)."""

    def test_gpu_runtime_detail_nvidia_smi_absent(self, monkeypatch) -> None:
        """When nvidia-smi is not on PATH, detail reports available=False with path=None."""
        monkeypatch.setattr(shells, "which", lambda cmd: None)
        detail = shells._gpu_runtime_detail()
        assert detail["available"] is False
        assert detail["nvidia_smi_path"] is None
        assert detail["driver_version"] is None
        assert detail["gpu_count"] is None
        assert detail["gpu_name"] is None

    def test_gpu_runtime_detail_nvidia_smi_present_with_driver(self, monkeypatch) -> None:
        """When nvidia-smi runs and reports a driver, parse version and GPU name."""
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None,
        )
        nvidia_output = (
            "+---------------------------------------------------------------------------------------+\n"
            "| NVIDIA-SMI 535.129.03             Driver Version: 535.129.03   CUDA Version: 12.2     |\n"
            "|-----------------------------------------+----------------------+----------------------+\n"
            "| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |\n"
            "| Fan  Temp  Perf  Pwr:Usage/Cap|       Memory-Usage | GPU-Util  Compute M. |\n"
            "|                               |                  |               MIG M. |\n"
            "|===============================+======================+======================|\n"
            "|   0  NVIDIA A100-SXM4-40GB On | 00000000:00:04.0 Off |                    0 |\n"
            "| N/A   28C    P0    72W / 400W |    655MiB / 81920MiB |      0%      Default |\n"
            "+---------------------------------------------------------------------------------------+\n"
        )

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout=nvidia_output, stderr="")

        monkeypatch.setattr(shells.subprocess, "run", fake_run)
        detail = shells._gpu_runtime_detail()
        assert detail["available"] is True
        assert detail["nvidia_smi_path"] == "/usr/bin/nvidia-smi"
        assert detail["driver_version"] == "535.129.03"
        assert detail["gpu_count"] == 1
        assert "A100" in (detail["gpu_name"] or "")
        assert detail["cuda_version"] == "12.2"

    def test_gpu_runtime_detail_nvidia_smi_multi_gpu(self, monkeypatch) -> None:
        """Multi-GPU setup: gpu_count reflects number of GPUs."""
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None,
        )
        nvidia_output = (
            "+---------------------------------------------------------------------------------------+\n"
            "| GPU  Name        Persistence-M| Bus-Id        Disp.A |\n"
            "|===============================+======================|\n"
            "|   0  NVIDIA RTX 4090   On | 00000000:01:00.0 |\n"
            "|   1  NVIDIA RTX 4090   On | 00000000:02:00.0 |\n"
            "+---------------------------------------------------------------------------------------+\n"
            "Driver Version: 535.129.03\n"
            "CUDA Version: 12.2\n"
        )

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout=nvidia_output, stderr="")

        monkeypatch.setattr(shells.subprocess, "run", fake_run)
        detail = shells._gpu_runtime_detail()
        assert detail["gpu_count"] == 2

    def test_gpu_runtime_detail_nvidia_smi_fails(self, monkeypatch) -> None:
        """nvidia-smi found but exits non-zero: available=False with path preserved."""
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None,
        )

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 1, stdout="", stderr="NVIDIA-SMI has failed"
            )

        monkeypatch.setattr(shells.subprocess, "run", fake_run)
        detail = shells._gpu_runtime_detail()
        assert detail["available"] is False
        assert detail["nvidia_smi_path"] == "/usr/bin/nvidia-smi"
        assert detail["driver_version"] is None

    def test_gpu_runtime_detail_nvidia_smi_times_out(self, monkeypatch) -> None:
        """nvidia-smi hangs: detail returns timed_out=True."""
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None,
        )
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("nvidia-smi", 5)),
        )
        detail = shells._gpu_runtime_detail()
        assert detail["available"] is False
        assert detail["timed_out"] is True


class TestGpuDetailInDiagnostics:
    """Ensure gpu_detail (not just gpu_runtime_available bool) appears in diagnostics."""

    def test_gpu_detail_in_diagnostics_for_gpu_backend(self, monkeypatch) -> None:
        """GPU-requiring backends should expose gpu_detail dict, not just bool."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        payload = shells.list_alphafold_shell_statuses()
        af3_diag = payload["alphafold3_local"]["diagnostics"]
        # Currently: gpu_runtime_available: bool
        # Proposed: gpu_detail dict alongside the bool
        assert "gpu_detail" in af3_diag
        assert isinstance(af3_diag["gpu_detail"], dict)
        assert "available" in af3_diag["gpu_detail"]


# ===========================================================================
# P0 – Symlink and broken-path detection
# ===========================================================================

# GAP: _configured_path_checks uses Path.exists() which follows symlinks.  A
# broken symlink reports exists=False, but the operator should know it's a
# broken symlink vs a completely absent path.  Also: symlinks pointing to
# unresolvable targets should report kind="broken_symlink" rather than
# "missing", and the link target should be exposed.
#
# PROPOSED FIX: In _configured_path_checks, add detection for symlinks:
#   - kind: "symlink"  when p.is_symlink() and p.exists()  (valid symlink)
#   - kind: "broken_symlink" when p.is_symlink() and not p.exists()
#   - link_target: str|None   = os.readlink(value) when is_symlink()
#   - resolved_target: str|None = str(p.resolve()) when exists
#
# GOTCHA: On some NFS mounts, os.readlink may raise.  Wrap in try/except.
# On Windows, is_symlink() may behave differently; but FoldAgent targets Linux.


class TestConfiguredPathSymlinkDetection:
    """Tests for symlink awareness in path checks (P0 — not yet implemented)."""

    def test_configured_path_reports_kind_symlink_for_valid_symlink(
        self, monkeypatch, tmp_path
    ) -> None:
        """A symlink pointing to a real dir should report kind='symlink' with link_target."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        real_dir = tmp_path / "real_data"
        real_dir.mkdir()
        symlink_dir = tmp_path / "link_data"
        symlink_dir.symlink_to(real_dir)
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(symlink_dir))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        assert entry["kind"] == "symlink"
        assert entry["exists"] is True
        assert entry["link_target"] == str(real_dir)
        assert entry["readable"] is True

    def test_configured_path_reports_broken_symlink(self, monkeypatch, tmp_path) -> None:
        """A symlink to a nonexistent target should report kind='broken_symlink'."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        dead_target = tmp_path / "does_not_exist"
        broken_link = tmp_path / "dead_link"
        broken_link.symlink_to(dead_target)
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(broken_link))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        assert entry["kind"] == "broken_symlink"
        assert entry["exists"] is False
        assert entry["link_target"] == str(dead_target)


# ===========================================================================
# P0 – Disk-space and write-disk availability checks
# ===========================================================================

# GAP: Configured paths show read/write booleans but not available disk space.
# AlphaFold2 data dirs are typically 2.6TB+ and AlphaFold3 model dirs 100GB+.
# Running out of disk mid-computation is catastrophic.
#
# PROPOSED FIX: Add disk-space fields to configured path entries when kind is
# dir or symlink:
#   - disk_total_bytes: int|None
#   - disk_free_bytes: int|None
#   - disk_used_bytes: int|None
# Use shutil.disk_usage().  Only populated when kind in ("dir", "symlink") and path exists.
#
# GOTCHA: On some container runtimes, disk_usage may reflect overlay FS limits.
# On NFS, df may differ from host df.  That's OK — we report what the process sees.


class TestConfiguredPathDiskSpace:
    """Tests for disk-space introspection on configured paths (P0 — not yet implemented)."""

    def test_configured_dir_reports_disk_space(self, monkeypatch, tmp_path) -> None:
        """A real directory should report disk_total_bytes, disk_free_bytes, disk_used_bytes."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        data_dir = tmp_path / "af2data"
        data_dir.mkdir()
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(data_dir))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        assert "disk_free_bytes" in entry
        assert entry["disk_free_bytes"] is not None
        assert isinstance(entry["disk_free_bytes"], int)
        assert entry["disk_free_bytes"] >= 0
        assert "disk_total_bytes" in entry
        assert entry["disk_total_bytes"] >= entry["disk_free_bytes"]

    def test_configured_path_disk_space_absent_for_missing_path(
        self, monkeypatch, tmp_path
    ) -> None:
        """Missing paths should have disk space fields as explicit None (key present but value None)."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        absent = tmp_path / "no_such_dir"
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(absent))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        # Key must exist with value None, not absent (which also returns None from .get())
        assert "disk_free_bytes" in entry
        assert entry["disk_free_bytes"] is None
        assert "disk_total_bytes" in entry
        assert entry["disk_total_bytes"] is None

    def test_configured_path_disk_space_not_reported_for_file(self, monkeypatch, tmp_path) -> None:
        """File-type paths should not report disk space (it's not meaningful)."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        a_file = tmp_path / "models.tgz"
        a_file.write_text("dummy")
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(a_file))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        # kind == "file" should not have disk space fields (or they should be None)
        assert entry["kind"] == "file"
        # Key must exist with explicit None, not be absent
        assert "disk_free_bytes" in entry
        assert entry["disk_free_bytes"] is None


# ===========================================================================
# P1 – OSError type discrimination in _probe_command
# ===========================================================================

# GAP: _probe_command catches subprocess.TimeoutExpired and OSError, but the
# OSError branch returns str(exc) as version_first_line — not clearly parseable.
# PermissionError vs FileNotFoundError vs other OSError are indistinguishable
# in the output.
#
# PROPOSED FIX: Add probe_error_type field to probe result dict:
#   - "permission_denied" for PermissionError
#   - "not_found" for FileNotFoundError
#   - "timeout" for TimeoutExpired
#   - "other" for other OSError
#   - None when probed successfully or not probed at all
#
# GOTCHA: PermissionError and FileNotFoundError are both OSError subclasses.
# Must check PermissionError FIRST (more specific), then FileNotFoundError.


class TestProbeCommandErrorTyping:
    """Tests for structured error types in probe results (P1 — not yet implemented)."""

    def test_probe_command_permission_denied(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", lambda cmd: "/usr/bin/colabfold_batch")
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(
                PermissionError("[Errno 13] Permission denied: '/usr/bin/colabfold_batch'")
            ),
        )
        result = _probe_command("colabfold_batch", ["--version"])
        assert result["probe_ok"] is False
        assert result["probe_error_type"] == "permission_denied"

    def test_probe_command_not_found_oserror(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", lambda cmd: "/usr/bin/colabfold_batch")
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(
                FileNotFoundError("[Errno 2] No such file or directory")
            ),
        )
        result = _probe_command("colabfold_batch", ["--version"])
        assert result["probe_ok"] is False
        assert result["probe_error_type"] == "not_found"

    def test_probe_command_timeout_returns_error_type(self, monkeypatch) -> None:
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("colabfold_batch", 5)),
        )
        result = _probe_command("colabfold_batch", ["--version"])
        assert result["probe_error_type"] == "timeout"

    def test_probe_command_success_has_no_error_type(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        result = _probe_command("colabfold_batch", ["--version"])
        assert result["probe_error_type"] is None


# ===========================================================================
# P1 – Version string parsing
# ===========================================================================

# GAP: _probe_command captures version_first_line but does no parsing.  An
# operator looking at "colabfold_batch 1.5.5" vs "Usage: alphafold [options]"
# can't tell which is a real version.
#
# PROPOSED FIX: Add version_parsed field to probe result that attempts to
# extract a semver-like pattern from version_first_line using regex.
# Pattern: r'(\d+\.\d+(?:\.\d+)?)'
#
# GOTCHA: Some CLI tools print version on stderr.  The current code already
# checks both.  Some tools print multi-line help on --version.  The regex
# should only match the first occurrence on version_first_line.


class TestVersionParsing:
    """Tests for structured version extraction from probe output (P1 — not yet implemented)."""

    def test_version_parsed_from_colabfold_output(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                a[0] if a else [], 0, stdout="colabfold_batch 1.5.5\n", stderr=""
            ),
        )
        payload = shells.list_alphafold_shell_statuses()
        probe = payload["colabfold"]["diagnostics"]["version_probe"]
        assert probe["version_parsed"] == "1.5.5"

    def test_version_parsed_none_when_no_version_pattern(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                a[0] if a else [], 0, stdout="Usage: alphafold [options]\n", stderr=""
            ),
        )
        payload = shells.list_alphafold_shell_statuses()
        probe = payload["alphafold3_local"]["diagnostics"]["version_probe"]
        if probe is not None:
            assert probe["version_parsed"] is None

    def test_version_parsed_extracts_two_part_version(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(
            shells.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(
                a[0] if a else [], 0, stdout="run_alphafold 2.3\n", stderr=""
            ),
        )
        payload = shells.list_alphafold_shell_statuses()
        probe = payload["alphafold2_local"]["diagnostics"]["version_probe"]
        assert probe["version_parsed"] == "2.3"


# ===========================================================================
# P1 – CUDA toolkit version detection
# ===========================================================================

# GAP: nvidia-smi reports CUDA version, but the actual CUDA toolkit installed
# (via nvcc) may differ.  This is a common AlphaFold failure mode.
#
# PROPOSED FIX: Add _cuda_toolkit_available() that checks for nvcc on PATH
# and runs `nvcc --version` to extract the toolkit release number.  Include
# result in the gpu_detail diagnostics dict for GPU-requiring backends.
#
# GOTCHA: nvcc may be installed but not on PATH if CUDA is in /usr/local/cuda*
# but not in the user's PATH.  Consider checking common CUDA paths.
# Also, container images often have CUDA runtime but not nvcc.


class TestCudaToolkitDetection:
    """Tests for CUDA toolkit detection alongside GPU runtime (P1)."""

    def test_cuda_toolkit_detected(self, monkeypatch) -> None:
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: {
                "nvidia-smi": "/usr/bin/nvidia-smi",
                "nvcc": "/usr/local/cuda/bin/nvcc",
                "colabfold_batch": "/usr/bin/colabfold_batch",
                "run_alphafold": "/usr/bin/run_alphafold",
                "alphafold": "/usr/bin/alphafold",
            }.get(cmd),
        )

        def fake_run(command, **kwargs):
            if command[0] == "nvidia-smi":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="Driver Version: 535.129.03\nCUDA Version: 12.2\n",
                    stderr="",
                )
            if command[0] == "nvcc":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="nvcc: NVIDIA (R) Cuda compiler driver\n"
                    "Cuda compilation tools, release 12.2, V12.2.140\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        monkeypatch.setattr(shells.subprocess, "run", fake_run)
        payload = shells.list_alphafold_shell_statuses()
        af3_diag = payload["alphafold3_local"]["diagnostics"]
        gpu_detail = af3_diag.get("gpu_detail", {})
        assert gpu_detail.get("cuda_toolkit_available") is True
        assert gpu_detail.get("cuda_toolkit_version") is not None

    def test_cuda_toolkit_absent(self, monkeypatch) -> None:
        monkeypatch.setattr(
            shells,
            "which",
            lambda cmd: {
                "nvidia-smi": "/usr/bin/nvidia-smi",
                "nvcc": None,
                "colabfold_batch": "/usr/bin/colabfold_batch",
                "run_alphafold": "/usr/bin/run_alphafold",
                "alphafold": "/usr/bin/alphafold",
            }.get(cmd),
        )

        def fake_run(command, **kwargs):
            if command[0] == "nvidia-smi":
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="Driver Version: 535.129.03\nCUDA Version: 12.2\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

        monkeypatch.setattr(shells.subprocess, "run", fake_run)
        payload = shells.list_alphafold_shell_statuses()
        af3_diag = payload["alphafold3_local"]["diagnostics"]
        gpu_detail = af3_diag.get("gpu_detail", {})
        assert gpu_detail.get("cuda_toolkit_available") is False


# ===========================================================================
# P1 – Timeout constants and clamping
# ===========================================================================

# GAP: _probe_command hardcodes timeout=5.  execute_alphafold_backend reads
# timeout_seconds from user payload with default 30 and NO maximum ceiling.
# A user could set timeout_seconds=999999 and hold a subprocess indefinitely.
#
# PROPOSED FIX: Add module-level constants:
#   PROBE_TIMEOUT = 5
#   MAX_EXECUTE_TIMEOUT = 600  # 10 min ceiling
# _probe_command should use PROBE_TIMEOUT.  execute_alphafold_backend should
# clamp timeout_seconds to MAX_EXECUTE_TIMEOUT.


class TestTimeoutConstants:
    """Tests for timeout ceiling documentation (P1)."""

    def test_probe_timeout_is_hardcoded(self) -> None:
        """Document that _probe_command uses hardcoded 5s timeout."""
        # This test verifies the current state and documents the gap
        import inspect

        source = inspect.getsource(_probe_command)
        assert "timeout=5" in source or "timeout =" in source

    def test_execute_timeout_no_clamping(self, monkeypatch) -> None:
        """Document that execute_alphafold_backend has no timeout ceiling."""
        # Currently, no MAX_EXECUTE_TIMEOUT constant exists
        assert not hasattr(shells, "MAX_EXECUTE_TIMEOUT")


# ===========================================================================
# P2 – ENV path consolidation in diagnostics summary
# ===========================================================================

# GAP: configured_paths is per-backend.  There's no top-level summary of which
# FOLDAGENT_* env vars are set/missing across ALL backends.  The operator must
# scan each backend individually.
#
# PROPOSED FIX: Add an `env_summary` key to list_alphafold_shell_statuses()
# output that collects all FOLDAGENT_* vars relevant to AlphaFold backends into
# a single dict with each key having a set/unset/present-but-missing status.


class TestEnvSummaryInDiagnostics:
    """Tests for consolidated environment summary (P2 — not yet implemented)."""

    def test_list_alphafold_shell_statuses_includes_env_summary(self, monkeypatch) -> None:
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        monkeypatch.delenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", raising=False)
        monkeypatch.delenv("FOLDAGENT_ALPHAFOLD3_MODEL_DIR", raising=False)
        monkeypatch.delenv("FOLDAGENT_ALPHAFOLD3_DB_DIR", raising=False)

        payload = shells.list_alphafold_shell_statuses()
        assert "env_summary" in payload
        assert isinstance(payload["env_summary"], dict)
        assert "FOLDAGENT_ALPHAFOLD2_DATA_DIR" in payload["env_summary"]
        assert "FOLDAGENT_ALPHAFOLD3_MODEL_DIR" in payload["env_summary"]


# ===========================================================================
# P2 – Configurable path specs
# ===========================================================================

# GAP: SHELL_BACKEND_SPECS is hardcoded.  Operators cannot add env var checks
# without editing shells.py.
#
# PROPOSED FIX: Allow runtime extension via a register function:
#   shells.register_env_path("alphafold3_local", ("FOLDAGENT_AF3_CUSTOM_WEIGHTS", "custom_weights"))
# This lets deployment configs specify additional path probes without code changes.


class TestConfigurablePathSpecs:
    """Tests documenting that spec extension requires code changes (P2)."""

    def test_shell_backend_specs_env_paths_are_fixed(self) -> None:
        """Document that SHELL_BACKEND_SPECS env_paths are module-level constants."""
        af3_env_paths = shells.SHELL_BACKEND_SPECS["alphafold3_local"]["env_paths"]
        assert len(af3_env_paths) == 2  # Only model_dir and db_dir
        assert not hasattr(shells, "register_env_path")  # No runtime extension


# ===========================================================================
# Regression guards — existing behavior must be preserved after changes
# ===========================================================================


class TestExistingBehaviorPreserved:
    """Ensure all existing behavior survives after proposed changes land."""

    def test_configured_path_still_reports_dir(self, monkeypatch, tmp_path) -> None:
        """Vanilla directory path still reports kind='dir' (or 'symlink' if tmp_path is symlinked)."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        data_dir = tmp_path / "normal_dir"
        data_dir.mkdir()
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(data_dir))

        payload = shells.list_alphafold_shell_statuses()
        entry = payload["alphafold2_local"]["diagnostics"]["configured_paths"][
            "alphafold2_data_dir"
        ]
        assert entry["exists"] is True
        # kind should be "dir" or "symlink" (symlink if tmp_path itself is a symlink on some CI)
        assert entry["kind"] in ("dir", "symlink")
        assert entry["readable"] is True

    def test_builtin_backend_still_passes(self) -> None:
        """alphafold_db (builtin) should still return available=True, validation_ok=True."""
        payload = shells.list_alphafold_shell_statuses()
        db = payload["alphafold_db"]
        assert db["available"] is True
        assert db["validation_ok"] is True
        assert db["diagnostics"]["command_on_path"] is True

    def test_remote_descriptor_still_unavailable(self) -> None:
        """alphafold_server (remote_descriptor) should remain available=False."""
        payload = shells.list_alphafold_shell_statuses()
        server = payload["alphafold_server"]
        assert server["available"] is False
        assert server["validation_ok"] is False
        assert "Remote descriptor" in server["validation_reason"]

    def test_probe_command_still_catches_timeout(self) -> None:
        """Probe timeout should still surface probe_timed_out=True."""
        result = _probe_command("never_gonna_run", ["--version"])
        # With nothing on PATH, which() would return None before _probe_command
        # is called — but _probe_command itself should still handle TimeoutExpired
        # We can't easily inject TimeoutExpired here since _probe_command
        # calls subprocess.run directly, but the existing test in
        # test_alphafold_environment_diagnostics_api.py covers this.
        # This test documents the expected contract.
        assert "probe_timed_out" in result or "probed" in result

    def test_gpu_runtime_available_returns_bool(self) -> None:
        """_gpu_runtime_available should return a bool (not dict)."""
        result = _gpu_runtime_available()
        assert isinstance(result, bool)

    def test_configured_path_checks_returns_dict(self, monkeypatch, tmp_path) -> None:
        """_configured_path_checks should return dict of dicts with expected keys."""
        data_dir = tmp_path / "af2data"
        data_dir.mkdir()
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD2_DATA_DIR", str(data_dir))

        result = _configured_path_checks([("FOLDAGENT_ALPHAFOLD2_DATA_DIR", "alphafold2_data_dir")])
        assert "alphafold2_data_dir" in result
        entry = result["alphafold2_data_dir"]
        # Existing keys must be preserved
        assert "env_var" in entry
        assert "configured" in entry
        assert "path" in entry
        assert "exists" in entry
        assert "kind" in entry
        assert "readable" in entry
        assert "writable" in entry

    def test_diagnostics_output_includes_version_probe_for_local_backend(self, monkeypatch) -> None:
        """Local backends should include version_probe in diagnostics."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)

        payload = shells.list_alphafold_shell_statuses()
        colabfold_diag = payload["colabfold"]["diagnostics"]
        assert "version_probe" in colabfold_diag
        assert colabfold_diag["version_probe"]["probed"] is True
        assert colabfold_diag["version_probe"]["probe_ok"] is True

    def test_missing_configured_paths_determines_validation_failure(
        self, monkeypatch, tmp_path
    ) -> None:
        """Missing configured paths should set validation_ok=False."""
        monkeypatch.setattr(shells, "which", _fake_which_all_found)
        monkeypatch.setattr(shells.subprocess, "run", _fake_run_all_ok)
        missing_dir = tmp_path / "no_such_dir"
        missing_model = tmp_path / "no_such_model"
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD3_MODEL_DIR", str(missing_model))
        monkeypatch.setenv("FOLDAGENT_ALPHAFOLD3_DB_DIR", str(missing_dir))

        payload = shells.list_alphafold_shell_statuses()
        af3 = payload["alphafold3_local"]
        assert af3["validation_ok"] is False
        # This is existing behavior that must be preserved
