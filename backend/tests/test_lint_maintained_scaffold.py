"""Tests for maintained-file lint scaffold.

This keeps CI honest while the broader repo still has legacy lint debt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestLintMaintainedTarget:
    @pytest.fixture(autouse=True)
    def _load_makefile(self) -> None:
        self.makefile = PROJECT_ROOT / "Makefile"
        self.content = self.makefile.read_text(encoding="utf-8")
        self.lines = self.content.splitlines()

    def test_makefile_has_lint_maintained_target(self) -> None:
        assert "lint-maintained:" in self.content

    def test_lint_maintained_target_runs_ruff_black_mypy(self) -> None:
        in_target = False
        commands: list[str] = []
        for line in self.lines:
            if line.startswith("lint-maintained:"):
                in_target = True
                continue
            if in_target:
                if line.startswith("\t"):
                    commands.append(line.strip())
                elif line.strip() == "":
                    continue
                else:
                    break
        joined = "\n".join(commands)
        assert "ruff check" in joined
        assert "black --check" in joined
        assert "mypy" in joined
        assert "backend/tests/test_ci_precommit_scaffold.py" in joined
        assert "backend/tests/test_port_consistency.py" in joined


class TestCIMaintainedLintUsage:
    @pytest.fixture(autouse=True)
    def _load_ci(self) -> None:
        self.workflow = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        self.content = self.workflow.read_text(encoding="utf-8")

    def test_ci_uses_lint_maintained_blocking_step(self) -> None:
        assert "make lint-maintained" in self.content

    def test_ci_keeps_full_lint_non_blocking(self) -> None:
        assert "continue-on-error: true" in self.content
        assert "make lint" in self.content


class TestPreCommitMaintainedScope:
    @pytest.fixture(autouse=True)
    def _load_precommit(self) -> None:
        self.config = PROJECT_ROOT / ".pre-commit-config.yaml"
        self.content = self.config.read_text(encoding="utf-8")

    def test_precommit_scopes_python_hooks_to_maintained_files(self) -> None:
        assert "backend/tests/test_ci_precommit_scaffold.py" in self.content
        assert "backend/tests/test_deployment_scaffold.py" in self.content
        assert "backend/tests/test_port_consistency.py" in self.content

    def test_precommit_yaml_hook_keeps_ci_files(self) -> None:
        assert ".github/workflows/ci.yml" in self.content
        assert ".pre-commit-config.yaml" in self.content
