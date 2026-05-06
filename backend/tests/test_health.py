from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.db import build_engine
from backend.app.main import app
from backend.app.models import Base

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "demo"


def test_health_includes_db_snapshot_when_schema_is_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "health-ready.db"
    eng = build_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=eng)

    with patch("backend.app.main.engine", eng):
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db_status"] == "ok"
    assert body["db_init_mode"] == "create_all"
    assert body["tables_present"] == body["tables_expected"]
    assert body["database_url"].endswith(str(db_path))


def test_health_returns_degraded_when_schema_tables_are_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "health-empty.db"
    eng = build_engine(f"sqlite:///{db_path}")

    with patch("backend.app.main.engine", eng):
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db_status"] == "degraded"
    assert "background_jobs" in body["missing_tables"]


def test_version_exposes_mock_defaults() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_mode"] == "mock"
    assert body["alphafold_backend"] == "mock"
