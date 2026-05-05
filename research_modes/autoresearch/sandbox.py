"""Autoresearch sandbox utilities.

Provides a git-backed experiment sandbox that automatically reverts on test
failure, plus an append-only experiment log.

RESEARCH ONLY — NOT FOR CLINICAL USE.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GitSandbox
# ---------------------------------------------------------------------------

class GitSandbox:
    """Creates a temporary git branch for experiments and reverts on failure.

    Usage::

        sandbox = GitSandbox(repo_root=Path("."))
        sandbox.enter()
        # ... make changes ...
        sandbox.revert()   # or just let exit() handle it
        sandbox.exit()

    Or as a context manager::

        with GitSandbox(repo_root=Path(".")) as sb:
            # work happens on sb.branch_name
            pass  # reverts automatically on exception
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path.cwd()
        self.branch_name: str = f"autoresearch-exp-{uuid.uuid4().hex[:8]}"
        self._original_branch: str = ""
        self._entered: bool = False
        self._changes: list[str] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

    def _current_branch(self) -> str:
        result = self._git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enter(self) -> "GitSandbox":
        """Checkout a new experiment branch."""
        self._original_branch = self._current_branch()
        self._git("checkout", "-b", self.branch_name)
        self._entered = True
        return self

    def track_change(self, path: str) -> None:
        """Record a file path that was modified during the experiment."""
        if path not in self._changes:
            self._changes.append(path)

    def revert(self) -> None:
        """Undo all changes and return to the original branch."""
        if not self._entered:
            return
        # Restore any tracked files from the original branch
        if self._changes:
            self._git("checkout", self._original_branch, "--", *self._changes)
        # Switch back
        self._git("checkout", self._original_branch)
        # Delete experiment branch
        self._git("branch", "-D", self.branch_name)
        self._entered = False

    def exit(self, reverted: bool = False) -> None:
        """Switch back to original branch (without reverting file content)."""
        if not self._entered:
            return
        self._git("checkout", self._original_branch)
        if not reverted:
            # Clean up the experiment branch
            self._git("branch", "-D", self.branch_name)
        self._entered = False

    # Context manager support
    def __enter__(self) -> "GitSandbox":
        return self.enter()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if exc_type is not None:
            self.revert()
        else:
            self.exit()
        return False  # do not suppress exceptions


# ---------------------------------------------------------------------------
# run_with_auto_revert
# ---------------------------------------------------------------------------

def run_with_auto_revert(
    test_command: str,
    changes: list[str],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Apply *changes*, run *test_command*, revert if any tests fail.

    Parameters
    ----------
    test_command:
        Shell command to execute (e.g. ``"pytest backend/tests -x -q"``).
    changes:
        List of file paths modified by the experiment.
    repo_root:
        Root of the git repository. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict with keys:
        - ``success`` (bool): True if tests passed.
        - ``test_output`` (str): Combined stdout + stderr.
        - ``reverted`` (bool): True if changes were rolled back.
    """
    root = repo_root or Path.cwd()
    sandbox = GitSandbox(repo_root=root)

    try:
        sandbox.enter()
        for path in changes:
            sandbox.track_change(path)

        result = subprocess.run(
            test_command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        passed = result.returncode == 0
        output = (result.stdout or "") + (result.stderr or "")

        if not passed:
            sandbox.revert()
            return {"success": False, "test_output": output, "reverted": True}

        sandbox.exit()
        return {"success": True, "test_output": output, "reverted": False}

    except Exception:
        sandbox.revert()
        raise


# ---------------------------------------------------------------------------
# ExperimentLog
# ---------------------------------------------------------------------------

@dataclass
class ExperimentRecord:
    experiment_id: str
    metric: str
    before: float
    after: float
    changes: list[str]
    reverted: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "metric": self.metric,
            "before": self.before,
            "after": self.after,
            "changes": self.changes,
            "reverted": self.reverted,
            "timestamp": self.timestamp,
        }


class ExperimentLog:
    """Append-only, JSON file-backed experiment history.

    Parameters
    ----------
    log_path:
        Path to the JSON log file. Created on first write if absent.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or Path("experiment_log.json")
        self._records: list[ExperimentRecord] = []
        self._load()

    def _load(self) -> None:
        if self.log_path.exists():
            try:
                data = json.loads(self.log_path.read_text())
                for item in data:
                    self._records.append(
                        ExperimentRecord(
                            experiment_id=item["experiment_id"],
                            metric=item["metric"],
                            before=item["before"],
                            after=item["after"],
                            changes=item.get("changes", []),
                            reverted=item.get("reverted", False),
                            timestamp=item.get("timestamp", 0.0),
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                self._records = []

    def _save(self) -> None:
        self.log_path.write_text(
            json.dumps([r.to_dict() for r in self._records], indent=2)
        )

    def record(
        self,
        experiment_id: str,
        metric: str,
        before: float,
        after: float,
        changes: list[str],
        *,
        reverted: bool = False,
    ) -> None:
        """Append one experiment record and persist to disk."""
        rec = ExperimentRecord(
            experiment_id=experiment_id,
            metric=metric,
            before=before,
            after=after,
            changes=changes,
            reverted=reverted,
        )
        self._records.append(rec)
        self._save()

    def get_history(self) -> list[dict[str, Any]]:
        """Return all records as a list of dicts."""
        return [r.to_dict() for r in self._records]
