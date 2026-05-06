from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import AuditLog, CandidateAntigen, Case, Report, Sample, Subject, Variant
from backend.app.seed_demo import seed_demo_database


def test_seed_demo_database_bootstraps_case_graph(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'seed_demo.db'}"

    summary = seed_demo_database(database_url, reset=True)

    assert summary["species"] == "demo"
    assert summary["sample_count"] == 2
    assert summary["variant_count"] >= 1
    assert summary["candidate_count"] >= 1
    assert summary["report_count"] >= 2
    assert summary["created"] is True

    engine = create_engine(database_url)
    with Session(engine) as db:
        case = db.get(Case, summary["case_id"])
        assert case is not None
        assert db.query(Subject).filter(Subject.case_id == case.id).count() == 1
        assert db.query(Sample).filter(Sample.case_id == case.id).count() == 2
        assert db.query(Variant).filter(Variant.case_id == case.id).count() >= 1
        assert db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case.id).count() >= 1
        report_types = {
            report.report_type
            for report in db.query(Report).filter(Report.case_id == case.id).all()
        }
        assert {"candidate_review", "ethics_package"}.issubset(report_types)
        actions = [
            entry.action for entry in db.query(AuditLog).filter(AuditLog.case_id == case.id).all()
        ]
        assert "demo.seeded" in actions


def test_seed_demo_database_is_idempotent_without_reset(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'seed_demo_idempotent.db'}"

    first = seed_demo_database(database_url, reset=True)
    second = seed_demo_database(database_url, reset=False)

    assert second["case_id"] == first["case_id"]
    assert second["sample_count"] == first["sample_count"] == 2
    assert second["report_count"] == first["report_count"] == 2
    assert second["created"] is False
