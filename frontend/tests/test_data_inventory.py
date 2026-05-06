import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.data_inventory import build_case_inventory_summary, build_inventory_rows


def test_build_case_inventory_summary_counts_core_entities() -> None:
    summary = build_case_inventory_summary(
        subjects=[{"id": "subject-1"}],
        samples=[{"id": "sample-1"}, {"id": "sample-2"}],
        variants=[{"id": "variant-1"}],
        candidates=[{"id": "candidate-1"}, {"id": "candidate-2"}],
        reports=[{"id": "report-1"}],
        structure_jobs=[{"id": "job-1"}],
        artifacts=[{"id": "artifact-1"}, {"id": "artifact-2"}, {"id": "artifact-3"}],
        executions=[{"id": "exec-1"}],
        audit_entries=[{"id": "audit-1"}, {"id": "audit-2"}, {"id": "audit-3"}, {"id": "audit-4"}],
    )

    assert summary == {
        "subjects": 1,
        "samples": 2,
        "variants": 1,
        "candidates": 2,
        "reports": 1,
        "structure_jobs": 1,
        "artifacts": 3,
        "executions": 1,
        "audit_entries": 4,
        "total_records": 16,
    }


def test_build_inventory_rows_formats_entity_specific_labels_and_status() -> None:
    rows = build_inventory_rows(
        subjects=[
            {
                "id": "subject-1",
                "anonymized_display_name": "Rosie-demo",
                "privacy_flags": {"redacted": True},
                "created_at": "2026-04-19T09:00:00Z",
            }
        ],
        samples=[
            {
                "id": "sample-1",
                "sample_type": "tumor",
                "source_lab": "Lab A",
                "created_at": "2026-04-19T10:00:00Z",
            }
        ],
        reports=[
            {
                "id": "report-1",
                "report_type": "candidate_review",
                "generated_at": "2026-04-19T11:00:00Z",
                "safety_label": "Research candidate only — not administerable",
            }
        ],
        artifacts=[
            {
                "id": "artifact-1",
                "artifact_type": "report_export",
                "filename": "report.md",
                "saved_at": "2026-04-19T12:00:00Z",
            }
        ],
        executions=[
            {
                "id": "exec-1",
                "adapter_name": "vep",
                "status": "completed",
                "started_at": "2026-04-19T13:00:00Z",
            }
        ],
    )

    assert [row["entity_type"] for row in rows] == [
        "execution",
        "artifact",
        "report",
        "sample",
        "subject",
    ]
    assert rows[0]["label"] == "vep"
    assert rows[0]["status"] == "completed"
    assert rows[1]["label"] == "report_export · report.md"
    assert rows[2]["label"] == "candidate_review"
    assert rows[3]["label"] == "tumor · Lab A"
    assert rows[4]["label"] == "Rosie-demo"
    assert rows[4]["status"] == "redacted"
