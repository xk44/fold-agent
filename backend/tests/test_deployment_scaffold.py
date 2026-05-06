"""Tests for deployment/runtime scaffold components.

Validates:
- Dockerfile exists and is well-formed
- .dockerignore excludes critical paths
- docker-compose.yml has required services
- Celery worker module can be imported (with broker config)
- Worker tasks are registered and enforce safety preflight
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Dockerfile validation
# ---------------------------------------------------------------------------


class TestDockerfile:
    """Validate the Dockerfile exists and contains required constructs."""

    @pytest.fixture(autouse=True)
    def _load_dockerfile(self) -> None:
        self.dockerfile = PROJECT_ROOT / "Dockerfile"
        self.content = self.dockerfile.read_text(encoding="utf-8")

    def test_dockerfile_exists(self) -> None:
        assert self.dockerfile.is_file(), "Dockerfile must exist at project root"

    def test_dockerfile_has_python_base(self) -> None:
        assert "python:3.11" in self.content, "Dockerfile must use Python 3.11 base image"

    def test_dockerfile_has_non_root_user(self) -> None:
        assert "USER foldagent" in self.content, "Dockerfile must run as non-root user"

    def test_dockerfile_has_healthcheck(self) -> None:
        assert "HEALTHCHECK" in self.content, "Dockerfile must define a HEALTHCHECK"

    def test_dockerfile_exposes_port(self) -> None:
        assert "EXPOSE" in self.content, "Dockerfile must EXPOSE canonical ports"
        assert "EXPOSE 8010 8502" in self.content

    def test_dockerfile_copies_backend(self) -> None:
        assert "backend/" in self.content, "Dockerfile must COPY backend source"

    def test_dockerfile_installs_package(self) -> None:
        assert "pip install" in self.content, "Dockerfile must install the Python package"

    def test_dockerfile_has_single_stage_or_multi_stage(self) -> None:
        has_multi = "AS builder" in self.content and "AS runtime" in self.content
        has_single = "FROM python:" in self.content
        assert has_multi or has_single, "Dockerfile must have a valid build structure"


# ---------------------------------------------------------------------------
# .dockerignore validation
# ---------------------------------------------------------------------------


class TestDockerignore:
    """Validate .dockerignore excludes paths that would bloat the image."""

    @pytest.fixture(autouse=True)
    def _load_dockerignore(self) -> None:
        self.dockerignore = PROJECT_ROOT / ".dockerignore"
        self.lines = (
            self.dockerignore.read_text(encoding="utf-8").splitlines()
            if self.dockerignore.is_file()
            else []
        )

    def test_dockerignore_exists(self) -> None:
        assert self.dockerignore.is_file(), ".dockerignore must exist"

    def test_excludes_venv(self) -> None:
        assert ".venv/" in self.lines, ".dockerignore must exclude .venv/"

    def test_excludes_git(self) -> None:
        assert ".git/" in self.lines, ".dockerignore must exclude .git/"

    def test_excludes_pycache(self) -> None:
        assert "__pycache__/" in self.lines, ".dockerignore must exclude __pycache__/"

    def test_excludes_docs(self) -> None:
        assert "docs/" in self.lines, ".dockerignore must exclude docs/"

    def test_excludes_env(self) -> None:
        assert ".env" in self.lines, ".dockerignore must exclude .env"


# ---------------------------------------------------------------------------
# docker-compose.yml validation
# ---------------------------------------------------------------------------


class TestDockerCompose:
    """Validate docker-compose.yml has required services and structure."""

    @pytest.fixture(autouse=True)
    def _load_compose(self) -> None:
        self.compose_file = PROJECT_ROOT / "docker-compose.yml"
        self.content = self.compose_file.read_text(encoding="utf-8")

    def test_compose_exists(self) -> None:
        assert self.compose_file.is_file(), "docker-compose.yml must exist"

    def test_has_app_service(self) -> None:
        assert "app:" in self.content, "docker-compose must define 'app' service"

    def test_has_dashboard_service(self) -> None:
        assert "dashboard:" in self.content, "docker-compose must define 'dashboard' service"

    def test_app_has_healthcheck(self) -> None:
        assert "healthcheck:" in self.content, "app service must have healthcheck"

    def test_uses_dockerfile(self) -> None:
        assert "Dockerfile" in self.content, "services must build from Dockerfile"

    def test_app_exposes_8010(self) -> None:
        assert "8010:8010" in self.content, "app must expose canonical API port 8010"

    def test_dashboard_exposes_8502(self) -> None:
        assert "8502:8502" in self.content, "dashboard must expose canonical dashboard port 8502"

    def test_dashboard_depends_on_app_healthy(self) -> None:
        assert "condition: service_healthy" in self.content, (
            "dashboard should wait for app to be healthy"
        )

    def test_has_env_file(self) -> None:
        assert "env_file:" in self.content, "services should use env_file for .env"

    def test_no_deprecated_version_field(self) -> None:
        # The 'version' key is deprecated in modern compose
        lines = self.content.splitlines()
        for line in lines:
            assert not line.strip().startswith("version:"), (
                "docker-compose.yml should not use deprecated 'version' field"
            )

    def test_has_redis_service_in_worker_profile(self) -> None:
        # Redis is gated behind the 'worker' Compose profile (opt-in)
        assert "redis:" in self.content, (
            "docker-compose must include redis service for worker support"
        )
        assert "profiles:" in self.content, (
            "redis/worker services should use Compose profiles for opt-in activation"
        )
        assert "- worker" in self.content, (
            "redis/worker services should belong to the 'worker' profile"
        )

    def test_has_worker_service_in_worker_profile(self) -> None:
        assert "worker:" in self.content, "docker-compose must include worker service scaffold"
        assert "celery" in self.content, "worker service must invoke celery"

    def test_redis_has_healthcheck(self) -> None:
        assert "redis-cli" in self.content, (
            "redis service must define a healthcheck using redis-cli"
        )

    def test_worker_depends_on_redis_and_app(self) -> None:
        """Worker service must depend on both redis and app (verified via YAML parse)."""
        import yaml

        compose = yaml.safe_load(self.content)
        services = compose.get("services", {})
        worker = services.get("worker", {})
        depends = worker.get("depends_on", {})
        assert "redis" in depends, "worker service must depend_on redis"
        assert "app" in depends, "worker service must depend_on app"

    def test_redis_volume_defined(self) -> None:
        assert "redis_data:" in self.content, (
            "docker-compose should define a named volume for Redis data persistence"
        )

    def test_worker_profile_is_opt_in(self) -> None:
        """Redis and worker services must be gated by the 'worker' profile."""
        import yaml

        compose = yaml.safe_load(self.content)
        assert compose is not None, "docker-compose.yml must be valid YAML"
        services = compose.get("services", {})

        # Core services must NOT have profiles
        for svc in ("app", "dashboard"):
            profiles = services.get(svc, {}).get("profiles")
            assert profiles is None, f"'{svc}' should not have profiles (must start by default)"

        # Worker stack services MUST have the 'worker' profile
        for svc in ("redis", "worker"):
            profiles = services.get(svc, {}).get("profiles")
            assert profiles is not None, f"'{svc}' must have profiles (opt-in)"
            assert "worker" in profiles, f"'{svc}' must be in 'worker' profile"

    def test_worker_service_connectivity(self) -> None:
        """Worker service must reference redis and app in depends_on."""
        import yaml

        compose = yaml.safe_load(self.content)
        services = compose.get("services", {})
        worker = services.get("worker", {})
        depends = worker.get("depends_on", {})
        assert "redis" in depends, "worker must depend_on redis"
        assert "app" in depends, "worker must depend_on app"


# ---------------------------------------------------------------------------
# .env.example validation
# ---------------------------------------------------------------------------


class TestEnvExample:
    """Validate .env.example documents the worker stack configuration."""

    @pytest.fixture(autouse=True)
    def _load_env_example(self) -> None:
        self.env_file = PROJECT_ROOT / ".env.example"
        self.content = self.env_file.read_text(encoding="utf-8") if self.env_file.is_file() else ""

    def test_env_example_exists(self) -> None:
        assert self.env_file.is_file(), ".env.example must exist"

    def test_worker_backend_var_documented(self) -> None:
        assert "FOLDAGENT_BACKGROUND_JOB_BACKEND" in self.content, (
            ".env.example must document FOLDAGENT_BACKGROUND_JOB_BACKEND"
        )

    def test_redis_url_documented(self) -> None:
        assert "FOLDAGENT_REDIS_URL" in self.content, (
            ".env.example must document FOLDAGENT_REDIS_URL"
        )

    def test_celery_broker_url_documented(self) -> None:
        assert "FOLDAGENT_CELERY_BROKER_URL" in self.content, (
            ".env.example must document FOLDAGENT_CELERY_BROKER_URL"
        )

    def test_celery_result_backend_documented(self) -> None:
        assert "FOLDAGENT_CELERY_RESULT_BACKEND" in self.content, (
            ".env.example must document FOLDAGENT_CELERY_RESULT_BACKEND"
        )

    def test_auto_default_documented(self) -> None:
        assert "auto" in self.content, (
            ".env.example should mention 'auto' as the default BACKGROUND_JOB_BACKEND"
        )

    def test_threadpool_option_documented(self) -> None:
        assert "threadpool" in self.content, ".env.example should document the 'threadpool' option"


# ---------------------------------------------------------------------------
# Celery worker module validation
# ---------------------------------------------------------------------------


class TestWorkerModule:
    """Validate the Celery worker module can be imported and configured."""

    def test_worker_package_exists(self) -> None:
        worker_pkg = PROJECT_ROOT / "backend" / "app" / "worker"
        assert worker_pkg.is_dir(), "backend/app/worker/ must be a package"
        assert (worker_pkg / "__init__.py").is_file(), "worker package needs __init__.py"
        assert (worker_pkg / "tasks.py").is_file(), "worker package needs tasks.py"

    def test_worker_warns_without_broker(self) -> None:
        """Worker must warn (not crash) when no broker is configured."""
        import subprocess
        import sys

        env = os.environ.copy()
        for key in (
            "FOLDAGENT_REDIS_URL",
            "FOLDAGENT_CELERY_BROKER_URL",
            "FOLDAGENT_CELERY_RESULT_BACKEND",
        ):
            env.pop(key, None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from backend.app.worker import app; "
                "assert app is None, 'app should be None without broker'",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, (
            f"Worker import should succeed without broker. stderr: {result.stderr}"
        )

    @pytest.mark.skipif(
        not __import__("importlib").util.find_spec("celery"),
        reason="celery not installed (pip install -e '.[worker]')",
    )
    def test_worker_imports_with_broker(self) -> None:
        """Worker must configure Celery when broker URL is provided."""
        import subprocess
        import sys

        env = os.environ.copy()
        env["FOLDAGENT_CELERY_BROKER_URL"] = "redis://localhost:6379/0"
        env["FOLDAGENT_CELERY_RESULT_BACKEND"] = "redis://localhost:6379/1"

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from backend.app.worker import app; print(app.conf.broker_url)",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"Worker must import with broker config: {result.stderr}"
        assert "redis://localhost:6379/0" in result.stdout

    def test_worker_tasks_module_has_registered_tasks(self) -> None:
        """Tasks module should define pipeline_run and structure_prediction."""
        tasks_file = PROJECT_ROOT / "backend" / "app" / "worker" / "tasks.py"
        content = tasks_file.read_text(encoding="utf-8")
        assert "pipeline_run" in content, "tasks.py must define pipeline_run task"
        assert "structure_prediction" in content, "tasks.py must define structure_prediction task"

    def test_pipeline_run_task_enforces_safety(self) -> None:
        """The pipeline_run task must check safety preflight."""
        tasks_file = PROJECT_ROOT / "backend" / "app" / "worker" / "tasks.py"
        content = tasks_file.read_text(encoding="utf-8")
        assert "preflight_action" in content, "pipeline_run must call preflight_action"
        assert "PreflightResult" in content, "pipeline_run must check PreflightResult"


# ---------------------------------------------------------------------------
# Makefile target validation
# ---------------------------------------------------------------------------


class TestMakefile:
    """Validate Makefile has required targets for Docker operations."""

    @pytest.fixture(autouse=True)
    def _load_makefile(self) -> None:
        self.makefile = PROJECT_ROOT / "Makefile"
        self.content = self.makefile.read_text(encoding="utf-8")

    def test_makefile_exists(self) -> None:
        assert self.makefile.is_file(), "Makefile must exist"

    def test_has_docker_build_target(self) -> None:
        assert "docker-build:" in self.content, "Makefile must have docker-build target"

    def test_has_docker_up_target(self) -> None:
        assert "docker-up:" in self.content, "Makefile must have docker-up target"

    def test_has_docker_down_target(self) -> None:
        assert "docker-down:" in self.content, "Makefile must have docker-down target"

    def test_has_docker_logs_target(self) -> None:
        assert "docker-logs:" in self.content, "Makefile must have docker-logs target"

    def test_has_docker_health_target(self) -> None:
        assert "docker-health:" in self.content, "Makefile must have docker-health target"

    def test_has_worker_target(self) -> None:
        assert "worker:" in self.content, "Makefile must have worker target"

    def test_worker_target_uses_celery(self) -> None:
        # The worker target should invoke celery, not just echo a stub message
        lines = self.content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("worker:"):
                # Find the command line(s) following the target
                cmd_lines = []
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("\t"):
                        cmd_lines.append(lines[j])
                    elif lines[j].strip() == "" or lines[j][0].isalpha():
                        break
                cmd = "\n".join(cmd_lines)
                assert "celery" in cmd, f"worker target must invoke celery, got: {cmd}"
                break


class TestMakefileWorkflowTargets:
    """Validate Makefile has e2e and smoke targets for workflow followthrough."""

    @pytest.fixture(autouse=True)
    def _load_makefile(self) -> None:
        self.makefile = PROJECT_ROOT / "Makefile"
        self.content = self.makefile.read_text(encoding="utf-8")
        self.lines = self.content.splitlines()

    def test_has_test_e2e_target(self) -> None:
        assert "test-e2e:" in self.content, "Makefile must have test-e2e target"

    def test_test_e2e_invokes_pytest_on_e2e_files(self) -> None:
        """test-e2e should run the e2e test files specifically."""
        cmd = self._extract_target_commands("test-e2e")
        assert "pytest" in cmd, f"test-e2e must invoke pytest, got: {cmd}"
        assert "test_e2e_core_lifecycle_api" in cmd or "test_e2e_synthetic_demo_api" in cmd, (
            f"test-e2e should reference e2e test files, got: {cmd}"
        )

    def test_has_smoke_target(self) -> None:
        assert "smoke:" in self.content, "Makefile must have smoke target"

    def test_smoke_invokes_pytest_with_exclusion_filter(self) -> None:
        """smoke should exclude slow/integration/e2e for a fast sanity check."""
        cmd = self._extract_target_commands("smoke")
        assert "pytest" in cmd, f"smoke must invoke pytest, got: {cmd}"
        assert "not slow" in cmd, f"smoke should exclude slow tests, got: {cmd}"
        assert "not integration" in cmd, f"smoke should exclude integration tests, got: {cmd}"
        assert "not e2e" in cmd, f"smoke should exclude e2e tests, got: {cmd}"

    def test_test_e2e_and_smoke_in_phony(self) -> None:
        """Both targets should be declared .PHONY."""
        phony_line = self.lines[0]
        assert "test-e2e" in phony_line, "test-e2e must be in .PHONY declaration"
        assert "smoke" in phony_line, "smoke must be in .PHONY declaration"

    def _extract_target_commands(self, target: str) -> str:
        """Extract command lines for a given Makefile target."""
        cmd_lines = []
        found = False
        for line in self.lines:
            if line.startswith(f"{target}:"):
                found = True
                continue
            if found:
                if line.startswith("\t"):
                    cmd_lines.append(line)
                elif line.strip() == "":
                    continue
                else:
                    break
        return "\n".join(cmd_lines)
