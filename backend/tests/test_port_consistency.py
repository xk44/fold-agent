"""Regression tests for canonical local runtime ports.

FoldAgent local development intentionally avoids port 8000 because that port is
commonly occupied on this workstation.  Keep the API, dashboard, Docker, CORS,
and docs/runbook defaults aligned so live verification does not split-brain.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.app.config import Settings
from backend.app.main import app
from skills.shared.foldagent_client import DEFAULT_BASE_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_API_PORT = "8010"
CANONICAL_DASHBOARD_PORT = "8502"


def _makefile_assignment(name: str) -> str:
    for line in (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name} ?="):
            return line.split("?=", 1)[1].strip()
    raise AssertionError(f"missing Makefile assignment for {name}")


def _cors_origins() -> list[str]:
    for middleware in app.user_middleware:
        if getattr(middleware.cls, "__name__", "") == "CORSMiddleware":
            origins = middleware.kwargs.get("allow_origins", [])
            assert isinstance(origins, list)
            return [str(origin) for origin in origins]
    raise AssertionError("CORSMiddleware is not registered")


def test_makefile_defaults_use_canonical_local_ports() -> None:
    assert _makefile_assignment("API_PORT") == CANONICAL_API_PORT
    assert _makefile_assignment("DASHBOARD_PORT") == CANONICAL_DASHBOARD_PORT


def test_shared_client_default_matches_canonical_api_port() -> None:
    assert f"http://localhost:{CANONICAL_API_PORT}" == DEFAULT_BASE_URL


def test_settings_expose_canonical_ports_and_cors_origins() -> None:
    settings = Settings()

    assert settings.api_port == 8010
    assert settings.dashboard_port == 8502
    assert f"http://localhost:{CANONICAL_DASHBOARD_PORT}" in settings.cors_origins
    assert f"http://127.0.0.1:{CANONICAL_DASHBOARD_PORT}" in settings.cors_origins


def test_fastapi_cors_allows_canonical_dashboard_origins() -> None:
    origins = _cors_origins()

    assert f"http://localhost:{CANONICAL_DASHBOARD_PORT}" in origins
    assert f"http://127.0.0.1:{CANONICAL_DASHBOARD_PORT}" in origins


def test_dockerfile_uses_canonical_api_and_dashboard_ports() -> None:
    content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert f"EXPOSE {CANONICAL_API_PORT} {CANONICAL_DASHBOARD_PORT}" in content
    assert f"http://localhost:{CANONICAL_API_PORT}/health" in content
    assert '"--port", "8010"' in content
    assert '"--port", "8000"' not in content


def test_docker_compose_uses_canonical_ports() -> None:
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    app_service = services["app"]
    dashboard_service = services["dashboard"]

    assert f"--port {CANONICAL_API_PORT}" in app_service["command"]
    assert app_service["ports"] == [
        f"127.0.0.1:{CANONICAL_API_PORT}:{CANONICAL_API_PORT}"
    ]
    assert f"FOLDAGENT_API_PORT={CANONICAL_API_PORT}" in app_service["environment"]
    assert (
        f"localhost:{CANONICAL_API_PORT}/health"
        in app_service["healthcheck"]["test"][-1]
    )

    assert f"--server.port {CANONICAL_DASHBOARD_PORT}" in dashboard_service["command"]
    assert dashboard_service["ports"] == [
        f"127.0.0.1:{CANONICAL_DASHBOARD_PORT}:{CANONICAL_DASHBOARD_PORT}"
    ]
    assert (
        f"FOLDAGENT_DASHBOARD_PORT={CANONICAL_DASHBOARD_PORT}"
        in dashboard_service["environment"]
    )
    assert (
        f"FOLDAGENT_API_URL=http://app:{CANONICAL_API_PORT}"
        in dashboard_service["environment"]
    )
    assert (
        f"localhost:{CANONICAL_DASHBOARD_PORT}/_stcore/health"
        in dashboard_service["healthcheck"]["test"][-1]
    )


def test_docs_and_env_example_document_canonical_defaults() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    walkthrough = (PROJECT_ROOT / "docs/VERIFICATION_WALKTHROUGH.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "FOLDAGENT_API_PORT=8010" in env_example
    assert "FOLDAGENT_DASHBOARD_PORT=8502" in env_example
    assert "FOLDAGENT_CORS_ORIGINS" in env_example
    assert "| Dashboard  | `DASHBOARD_PORT`  | `8502`" in walkthrough
    assert "http://127.0.0.1:8502" in walkthrough
    assert "http://127.0.0.1:8502" in readme
