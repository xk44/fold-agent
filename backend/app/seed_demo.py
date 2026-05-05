"""Seed FoldAgent demo data into the configured database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.config import SpeciesMode, settings
from backend.app.db import build_engine, build_session_factory
from backend.app.mock_analysis import ensure_mock_analysis_data
from backend.app.models import Base, Case, Report, Sample, SampleTypeEnum, Subject
from backend.app.reports import RESEARCH_LABEL, build_candidate_review_report, build_ethics_package_report
from backend.app.safety.audit import log_action

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CASE = ROOT / "examples" / "synthetic_demo_case.json"


def load_demo_payload() -> dict:
    if not EXAMPLE_CASE.exists():
        raise SystemExit(f"Missing demo case file: {EXAMPLE_CASE}")
    return json.loads(EXAMPLE_CASE.read_text())


def _find_existing_case(db: Session, payload: dict) -> Case | None:
    case_payload = payload.get("case", {})
    diagnosis_summary = case_payload.get("diagnosis_summary")
    supervising_professional = case_payload.get("supervising_professional")
    return (
        db.query(Case)
        .filter(
            Case.species == SpeciesMode(case_payload.get("species", SpeciesMode.DEMO.value)),
            Case.diagnosis_summary == diagnosis_summary,
            Case.supervising_professional == supervising_professional,
        )
        .order_by(Case.created_at.asc())
        .first()
    )


def _seed_case_graph(db: Session, payload: dict) -> dict:
    case_payload = payload["case"]
    subject_payload = payload["subject"]
    sample_payloads = payload.get("samples", [])

    case = _find_existing_case(db, payload)
    created = False
    if case is None:
        case = Case(
            id=str(uuid4()),
            species=SpeciesMode(case_payload.get("species", SpeciesMode.DEMO.value)),
            diagnosis_summary=case_payload.get("diagnosis_summary"),
            supervising_professional=case_payload.get("supervising_professional"),
            consent_status=case_payload.get("consent_status", "demo"),
            review_status=case_payload.get("review_status", "unreviewed"),
        )
        db.add(case)
        db.flush()
        created = True

    subject = (
        db.query(Subject)
        .filter(
            Subject.case_id == case.id,
            Subject.anonymized_display_name == subject_payload["anonymized_display_name"],
        )
        .first()
    )
    if subject is None:
        subject = Subject(
            id=str(uuid4()),
            case_id=case.id,
            anonymized_display_name=subject_payload["anonymized_display_name"],
            metadata_json=subject_payload.get("metadata"),
            privacy_flags={"synthetic_demo": True},
        )
        db.add(subject)
        db.flush()

    existing_samples = {
        (sample.sample_type.value, sample.checksum): sample
        for sample in db.query(Sample).filter(Sample.case_id == case.id).all()
    }
    for sample_payload in sample_payloads:
        key = (sample_payload["sample_type"], sample_payload.get("checksum"))
        if key in existing_samples:
            continue
        db.add(
            Sample(
                id=str(uuid4()),
                case_id=case.id,
                subject_id=subject.id,
                sample_type=SampleTypeEnum(sample_payload["sample_type"]),
                file_paths=sample_payload.get("file_paths"),
                checksum=sample_payload.get("checksum"),
                source_lab=sample_payload.get("source_lab"),
                custody_metadata={"synthetic_demo": True},
            )
        )
    db.flush()

    variants, candidates = ensure_mock_analysis_data(db, case)

    existing_report_types = {
        report.report_type for report in db.query(Report).filter(Report.case_id == case.id).all()
    }
    if "candidate_review" not in existing_report_types:
        generated = build_candidate_review_report(case, candidates)
        db.add(
            Report(
                id=str(uuid4()),
                case_id=case.id,
                report_type=generated["report_type"],
                generated_by="seed_demo",
                content_json=generated["content_json"],
                safety_label=RESEARCH_LABEL,
            )
        )
    if "ethics_package" not in existing_report_types:
        generated = build_ethics_package_report(case)
        db.add(
            Report(
                id=str(uuid4()),
                case_id=case.id,
                report_type=generated["report_type"],
                generated_by="seed_demo",
                content_json=generated["content_json"],
                safety_label=RESEARCH_LABEL,
            )
        )

    log_action(
        db,
        case_id=case.id,
        actor="seed_demo",
        action="demo.seeded" if created else "demo.seed_verified",
        inputs={"source": str(EXAMPLE_CASE)},
        outputs={
            "case_id": case.id,
            "sample_count": db.query(Sample).filter(Sample.case_id == case.id).count(),
            "variant_count": len(variants),
            "candidate_count": len(candidates),
        },
        details={"synthetic_demo": True},
    )
    db.commit()

    return {
        "case_id": case.id,
        "species": case.species.value,
        "subject_id": subject.id,
        "sample_count": db.query(Sample).filter(Sample.case_id == case.id).count(),
        "variant_count": len(variants),
        "candidate_count": len(candidates),
        "report_count": db.query(Report).filter(Report.case_id == case.id).count(),
        "created": created,
    }


def seed_demo_database(database_url: str | None = None, *, reset: bool = False) -> dict:
    payload = load_demo_payload()
    url = database_url or settings.database_url
    engine = build_engine(url)
    session_factory = build_session_factory(url)

    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with session_factory() as db:
        return _seed_case_graph(db, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed FoldAgent synthetic demo data")
    parser.add_argument("--database-url", default=None, help="Override database URL for seeding")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = seed_demo_database(args.database_url, reset=args.reset)
    print("FoldAgent demo seed complete")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
