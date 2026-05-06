"""Tests for demo mode (Phase 21).

Covers:
  - create_demo_case: all models populated
  - create_synthetic_dataset: correct count, varying completeness
  - reset_demo_data: all demo records cleared
  - GET /demo/status
  - POST /demo/create-case
  - POST /demo/create-dataset
  - POST /demo/reset
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.demo import create_demo_case, create_synthetic_dataset, reset_demo_data
from backend.app.models import (
    CandidateAntigen,
    Case,
    Report,
    Sample,
    StructureJob,
    Subject,
    Variant,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> Session:
    return SessionLocal()


# ---------------------------------------------------------------------------
# Unit tests — create_demo_case
# ---------------------------------------------------------------------------


def test_create_demo_case_returns_summary() -> None:
    with _db() as db:
        result = create_demo_case(db)

    assert result["demo"] is True
    assert result["species"] == "dog"
    assert result["subject_display_name"] == "DEMO-ROSIE-001"
    assert result["case_id"] is not None
    assert result["subject_id"] is not None


def test_create_demo_case_populates_samples() -> None:
    with _db() as db:
        result = create_demo_case(db)
        count = db.query(Sample).filter(Sample.case_id == result["case_id"]).count()

    assert count == 3
    assert result["sample_count"] == 3


def test_create_demo_case_populates_variants() -> None:
    with _db() as db:
        result = create_demo_case(db)
        count = db.query(Variant).filter(Variant.case_id == result["case_id"]).count()

    assert count == 5
    assert result["variant_count"] == 5


def test_create_demo_case_populates_candidates() -> None:
    with _db() as db:
        result = create_demo_case(db)
        count = (
            db.query(CandidateAntigen).filter(CandidateAntigen.case_id == result["case_id"]).count()
        )

    assert count == 3
    assert result["candidate_count"] == 3


def test_create_demo_case_creates_structure_job() -> None:
    with _db() as db:
        result = create_demo_case(db)
        job = db.query(StructureJob).filter(StructureJob.case_id == result["case_id"]).first()

    assert job is not None
    assert job.backend_used == "mock"
    assert job.status.value == "completed"
    assert result["structure_job_id"] == job.id


def test_create_demo_case_creates_report() -> None:
    with _db() as db:
        result = create_demo_case(db)
        report = db.query(Report).filter(Report.case_id == result["case_id"]).first()

    assert report is not None
    assert result["report_id"] == report.id


def test_create_demo_case_creates_subject() -> None:
    with _db() as db:
        result = create_demo_case(db)
        subject = db.get(Subject, result["subject_id"])

    assert subject is not None
    assert subject.anonymized_display_name == "DEMO-ROSIE-001"


# ---------------------------------------------------------------------------
# Unit tests — create_synthetic_dataset
# ---------------------------------------------------------------------------


def test_create_synthetic_dataset_default_count() -> None:
    with _db() as db:
        results = create_synthetic_dataset(db, n_cases=3)

    assert len(results) == 3


def test_create_synthetic_dataset_custom_count() -> None:
    with _db() as db:
        results = create_synthetic_dataset(db, n_cases=5)

    assert len(results) == 5


def test_create_synthetic_dataset_first_case_is_full() -> None:
    with _db() as db:
        results = create_synthetic_dataset(db, n_cases=3)

    assert results[0]["completeness"] == "full"
    assert results[0]["sample_count"] == 3
    assert results[0]["variant_count"] == 5
    assert results[0]["candidate_count"] == 3


def test_create_synthetic_dataset_second_case_is_partial() -> None:
    with _db() as db:
        results = create_synthetic_dataset(db, n_cases=3)

    assert results[1]["completeness"] == "partial"
    assert results[1]["sample_count"] == 2
    assert results[1]["candidate_count"] == 1


def test_create_synthetic_dataset_third_case_is_minimal() -> None:
    with _db() as db:
        results = create_synthetic_dataset(db, n_cases=3)

    assert results[2]["completeness"] == "minimal"
    assert results[2]["sample_count"] == 1
    assert results[2]["candidate_count"] == 0


# ---------------------------------------------------------------------------
# Unit tests — reset_demo_data
# ---------------------------------------------------------------------------


def test_reset_demo_data_clears_cases() -> None:
    with _db() as db:
        result = create_demo_case(db)
        case_id = result["case_id"]

        reset_result = reset_demo_data(db)

        remaining = db.get(Case, case_id)
        assert remaining is None
        assert reset_result["demo_case_ids_found"] >= 1


def test_reset_demo_data_clears_all_child_records() -> None:
    with _db() as db:
        result = create_demo_case(db)
        case_id = result["case_id"]

        reset_demo_data(db)

        assert db.query(Sample).filter(Sample.case_id == case_id).count() == 0
        assert db.query(Variant).filter(Variant.case_id == case_id).count() == 0
        assert db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).count() == 0
        assert db.query(StructureJob).filter(StructureJob.case_id == case_id).count() == 0


def test_reset_demo_data_is_idempotent() -> None:
    with _db() as db:
        create_demo_case(db)
        reset_demo_data(db)
        # Second reset should not error
        result2 = reset_demo_data(db)
        assert result2["demo_case_ids_found"] == 0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_demo_status_endpoint(client: TestClient) -> None:
    resp = client.get("/demo/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "demo_mode" in body
    assert "disclaimer" in body
    assert isinstance(body["demo_mode"], bool)


def test_demo_create_case_endpoint(client: TestClient) -> None:
    resp = client.post("/demo/create-case")
    assert resp.status_code == 201
    body = resp.json()
    assert body["demo"] is True
    assert body["species"] == "dog"
    assert body["subject_display_name"] == "DEMO-ROSIE-001"
    assert body["sample_count"] == 3
    assert body["variant_count"] == 5
    assert body["candidate_count"] == 3
    assert body["structure_job_id"] is not None
    assert body["report_id"] is not None


def test_demo_create_dataset_endpoint(client: TestClient) -> None:
    resp = client.post("/demo/create-dataset?n_cases=3")
    assert resp.status_code == 201
    body = resp.json()
    assert body["count"] == 3
    assert len(body["cases"]) == 3
    assert "disclaimer" in body


def test_demo_create_dataset_custom_count(client: TestClient) -> None:
    resp = client.post("/demo/create-dataset?n_cases=2")
    assert resp.status_code == 201
    body = resp.json()
    assert body["count"] == 2


def test_demo_reset_endpoint(client: TestClient) -> None:
    # Create data first
    create_resp = client.post("/demo/create-case")
    assert create_resp.status_code == 201

    # Reset
    reset_resp = client.post("/demo/reset")
    assert reset_resp.status_code == 200
    body = reset_resp.json()
    assert body["status"] == "ok"
    assert "deleted" in body
    assert body["demo_case_ids_found"] >= 1
