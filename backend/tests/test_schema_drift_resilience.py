from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db import engine
from backend.app.models import Base


def _create_demo_case(client: TestClient) -> str:
    response = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "schema drift resilience"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _drop_table(table_name: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE {table_name}"))


@pytest.fixture(autouse=True)
def _restore_schema_after_drop() -> Generator[None, None, None]:
    yield
    Base.metadata.create_all(bind=engine)


def test_list_cases_returns_empty_when_cases_table_missing(client: TestClient) -> None:
    _drop_table("cases")

    response = client.get("/cases")

    assert response.status_code == 200
    assert response.json() == []


def test_list_case_tasks_returns_empty_when_case_tasks_table_missing(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    _drop_table("case_tasks")

    response = client.get(f"/cases/{case_id}/tasks")

    assert response.status_code == 200
    assert response.json() == []


def test_list_samples_returns_empty_when_samples_table_missing(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    _drop_table("samples")

    response = client.get(f"/cases/{case_id}/samples")

    assert response.status_code == 200
    assert response.json() == []


def test_list_variants_returns_empty_when_variants_table_missing(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    _drop_table("variants")

    response = client.get(f"/cases/{case_id}/variants")

    assert response.status_code == 200
    assert response.json() == []


def test_list_candidates_returns_empty_when_candidate_table_missing(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    _drop_table("candidate_antigens")

    response = client.get(f"/cases/{case_id}/candidates")

    assert response.status_code == 200
    assert response.json() == []


def test_list_reports_returns_empty_when_reports_table_missing(client: TestClient) -> None:
    case_id = _create_demo_case(client)
    _drop_table("reports")

    response = client.get(f"/cases/{case_id}/reports")

    assert response.status_code == 200
    assert response.json() == []


def test_audit_returns_empty_when_audit_logs_table_missing(client: TestClient) -> None:
    _drop_table("audit_logs")

    response = client.get("/audit/system")

    assert response.status_code == 200
    assert response.json() == []
