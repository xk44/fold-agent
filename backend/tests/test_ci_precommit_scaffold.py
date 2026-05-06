"""Tests for CI and pre-commit scaffold files."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestPreCommitConfig:
    @pytest.fixture(autouse=True)
    def _load_config(self) -> None:
        self.config_file = PROJECT_ROOT / ".pre-commit-config.yaml"
        self.content = (
            self.config_file.read_text(encoding="utf-8") if self.config_file.is_file() else ""
        )

    def test_pre_commit_config_exists(self) -> None:
        assert self.config_file.is_file(), ".pre-commit-config.yaml must exist"

    def test_has_ruff_hooks(self) -> None:
        assert "ruff-check" in self.content or "ruff" in self.content

    def test_has_formatter_hook(self) -> None:
        assert "ruff-format" in self.content or "black" in self.content

    def test_has_mypy_hook(self) -> None:
        assert "mypy" in self.content


class TestGithubActionsCI:
    @pytest.fixture(autouse=True)
    def _load_workflow(self) -> None:
        self.workflow = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        self.content = self.workflow.read_text(encoding="utf-8") if self.workflow.is_file() else ""

    def test_ci_workflow_exists(self) -> None:
        assert self.workflow.is_file(), ".github/workflows/ci.yml must exist"

    def test_ci_triggers_on_push_and_pr(self) -> None:
        assert "push:" in self.content
        assert "pull_request:" in self.content

    def test_ci_uses_checkout_and_setup_python(self) -> None:
        assert "actions/checkout@" in self.content
        assert "actions/setup-python@" in self.content

    def test_ci_installs_project_with_dev_frontend_worker_extras(self) -> None:
        assert ".[dev,frontend,worker]" in self.content

    def test_ci_runs_pre_commit(self) -> None:
        assert "pre-commit run --all-files" in self.content

    def test_ci_runs_smoke_and_lint(self) -> None:
        assert "make smoke" in self.content
        assert "make lint" in self.content

    def test_ci_runs_full_pytest(self) -> None:
        assert "pytest -q" in self.content or "make test" in self.content

    def test_ci_runs_deployment_scaffold_test(self) -> None:
        assert (
            "test_deployment_scaffold.py" in self.content or "make test-deployment" in self.content
        )

    def test_ci_runs_port_consistency_scaffold_test(self) -> None:
        assert "test_port_consistency.py" in self.content or "make test-deployment" in self.content


class TestMakefileCITarget:
    @pytest.fixture(autouse=True)
    def _load_makefile(self) -> None:
        self.makefile = PROJECT_ROOT / "Makefile"
        self.content = self.makefile.read_text(encoding="utf-8")

    def test_makefile_has_ci_target(self) -> None:
        assert "ci:" in self.content, "Makefile must have ci target"

    def test_makefile_has_verify_local_target(self) -> None:
        assert "verify-local:" in self.content, "Makefile must have verify-local target"

    def test_makefile_has_ports_check_target(self) -> None:
        assert "ports-check:" in self.content, "Makefile must have ports-check target"

    def test_makefile_declares_docker_utility_targets_phony(self) -> None:
        phony_line = next(line for line in self.content.splitlines() if line.startswith(".PHONY:"))

        for target in (
            "docker-up-core",
            "docker-build-clean",
            "docker-logs-svc",
            "docker-health",
            "docker-prepare-volumes",
        ):
            assert target in phony_line

    def test_docker_up_targets_prepare_bind_mount_directories(self) -> None:
        assert "docker-up: docker-prepare-volumes" in self.content
        assert "docker-up-core: docker-prepare-volumes" in self.content
        assert "docker-prepare-volumes:" in self.content
        assert "chown -R 1000:1000" in self.content

    def test_ci_target_references_pre_commit_smoke_lint_and_pytest(self) -> None:
        lines = self.content.splitlines()
        in_ci = False
        commands: list[str] = []
        for line in lines:
            if line.startswith("ci:"):
                in_ci = True
                continue
            if in_ci:
                if line.startswith("\t"):
                    commands.append(line.strip())
                elif line.strip() == "":
                    continue
                else:
                    break
        joined = "\n".join(commands)
        assert "pre-commit run --all-files" in joined
        assert "make smoke" in joined
        assert "make lint" in joined
        assert "pytest -q" in joined
        assert "test_deployment_scaffold.py" in joined
        assert "test_ci_precommit_scaffold.py" in joined
        assert "test_lint_maintained_scaffold.py" in joined
        assert "test_port_consistency.py" in joined

    def test_smoke_verify_keeps_health_payload_when_api_is_degraded(self) -> None:
        lines = self.content.splitlines()
        health_lines = [
            line
            for line in lines
            if "/health" in line and "_stcore" not in line and "dashboard" not in line
        ]

        assert health_lines, "smoke-verify must check /health"
        assert any("curl -sS" in line for line in health_lines)
        assert not any("curl -sf" in line or "curl -f" in line for line in health_lines)
        assert any("HTTP" in line and ("200" in line and "503" in line) for line in health_lines)

    def test_smoke_verify_reports_dashboard_health_status_and_body(self) -> None:
        lines = self.content.splitlines()
        dashboard_health_lines = [
            line for line in lines if "_stcore/health" in line and "docker-health" not in line
        ]

        assert dashboard_health_lines, "smoke-verify must check dashboard health"
        joined = "\n".join(dashboard_health_lines)
        assert "curl -sS" in joined
        assert '-w "%{http_code}"' in joined
        assert "dashboard health HTTP" in joined
        assert "cat $$tmp" in joined or "cat $tmp" in joined

    def test_verify_local_target_runs_scaffold_and_dry_run_smokes(self) -> None:
        lines = self.content.splitlines()
        in_verify_local = False
        commands: list[str] = []
        for line in lines:
            if line.startswith("verify-local:"):
                in_verify_local = True
                continue
            if in_verify_local:
                if line.startswith("\t"):
                    commands.append(line.strip())
                elif line.strip() == "":
                    continue
                else:
                    break
        joined = "\n".join(commands)

        assert "make lint-maintained" in joined
        assert "make test-deployment" in joined
        assert "make ports-check" in joined
        assert "make -n smoke-verify" in joined
        assert "make -n docker-health" in joined

    def test_ports_check_target_reports_canonical_ports(self) -> None:
        lines = self.content.splitlines()
        in_ports_check = False
        commands: list[str] = []
        for line in lines:
            if line.startswith("ports-check:"):
                in_ports_check = True
                continue
            if in_ports_check:
                if line.startswith("\t"):
                    commands.append(line.strip())
                elif line.strip() == "":
                    continue
                else:
                    break
        joined = "\n".join(commands)

        assert "$(API_PORT)" in joined
        assert "$(DASHBOARD_PORT)" in joined
        assert "8010" in self.content
        assert "8502" in self.content
        assert "ss -ltnp" in joined or "lsof" in joined
