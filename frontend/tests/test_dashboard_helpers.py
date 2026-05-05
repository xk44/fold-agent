from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.dashboard_helpers import (
    build_case_governance_summary,
    build_provenance_summary,
    build_subject_governance_rows,
    classify_health_status,
    flatten_candidate_rows,
    format_health_status_summary,
    is_task_overdue,
    parse_due_date,
    task_sort_key,
)


def test_classify_health_status_distinguishes_ok_degraded_and_unreachable() -> None:
    assert classify_health_status({"status": "ok", "db_status": "ok"}) == "ok"
    assert (
        classify_health_status(
            {
                "status": "degraded",
                "db_status": "degraded",
                "missing_tables": ["background_jobs", "cases"],
            }
        )
        == "degraded"
    )
    assert classify_health_status(None, error="Connection refused") == "unreachable"


def test_format_health_status_summary_surfaces_degraded_db_snapshot() -> None:
    summary = format_health_status_summary(
        {
            "status": "degraded",
            "db_status": "degraded",
            "database_url": "sqlite:///./neovax.db",
            "db_init_mode": "create_all",
            "tables_present": 0,
            "tables_expected": 14,
            "missing_tables": ["background_jobs", "cases"],
            "extra_tables": [],
            "error": "no such table: cases",
        }
    )

    assert "API degraded" in summary
    assert "DB degraded" in summary
    assert "0 / 14 tables present" in summary
    assert "missing: background_jobs, cases" in summary
    assert "db_init_mode: create_all" in summary
    assert "database: sqlite:///./neovax.db" in summary
    assert "error: no such table: cases" in summary


def test_format_health_status_summary_handles_unreachable_error() -> None:
    summary = format_health_status_summary(None, error="Connection refused")

    assert summary == "API unreachable: Connection refused"


def test_parse_due_date_accepts_trailing_z() -> None:
    parsed = parse_due_date("2026-04-21T12:30:00Z")

    assert parsed == datetime(2026, 4, 21, 12, 30, tzinfo=timezone.utc)


def test_parse_due_date_returns_none_for_invalid_value() -> None:
    assert parse_due_date("not-a-date") is None
    assert parse_due_date(None) is None


def test_is_task_overdue_true_only_for_open_past_due_tasks() -> None:
    now = datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)

    assert is_task_overdue({"due_date": "2026-04-20T12:00:00Z", "status": "pending"}, now=now) is True
    assert is_task_overdue({"due_date": "2026-04-20T12:00:00Z", "status": "done"}, now=now) is False
    assert is_task_overdue({"due_date": None, "status": "pending"}, now=now) is False


def test_task_sort_key_orders_due_tasks_before_undated_then_title() -> None:
    tasks = [
        {"id": "3", "title": "zeta", "due_date": None},
        {"id": "2", "title": "beta", "due_date": "2026-04-22T00:00:00Z"},
        {"id": "1", "title": "alpha", "due_date": "2026-04-21T00:00:00Z"},
    ]

    ordered = sorted(tasks, key=task_sort_key)

    assert [task["id"] for task in ordered] == ["1", "2", "3"]


def test_flatten_candidate_rows_handles_nested_fields_and_missing_sections() -> None:
    rows = flatten_candidate_rows(
        [
            {
                "id": "cand-1",
                "variant_id": "var-1",
                "mhc_context": "HLA-A*02:01",
                "peptide_metadata": {"sequence": "SIINFEKL"},
                "prediction_scores": {"binding_rank": 0.4, "immunogenicity": 0.7},
                "structure_evidence": {
                    "backend": "alphafold3_local",
                    "alphafold_status": "completed",
                    "ranking_score": 0.91,
                    "ptm": 0.82,
                    "iptm": 0.74,
                    "pdb_file": "model.pdb",
                    "source_url": "https://example.test/model",
                },
                "review_status": "pending",
                "last_parsed_execution_id": "exec-1",
            },
            {"id": "cand-2", "variant_id": "var-2"},
        ]
    )

    assert rows[0]["peptide_sequence"] == "SIINFEKL"
    assert rows[0]["structure_backend"] == "alphafold3_local"
    assert rows[0]["model_cif"] == "model.pdb"
    assert rows[1]["structure_backend"] is None
    assert rows[1]["binding_rank"] is None


def test_build_provenance_summary_collects_unique_sources_scores_and_execution_ids() -> None:
    summary = build_provenance_summary(
        variants=[
            {"quality_metrics": {"parsed_from": "vcf"}, "last_parsed_execution_id": "exec-1"},
            {"quality_metrics": {"parsed_from": "vcf"}, "last_parsed_execution_id": "exec-2"},
        ],
        candidates=[
            {
                "prediction_scores": {"parsed_from": "netmhcpan"},
                "structure_evidence": {
                    "backend": "alphafold3_local",
                    "alphafold_status": "completed",
                    "ranking_score": 0.91,
                    "ptm": 0.81,
                    "iptm": 0.71,
                },
                "last_parsed_execution_id": "exec-2",
            },
            {
                "prediction_scores": {"parsed_from": "mixmhc"},
                "structure_evidence": {
                    "backend": "alphafold_db",
                    "alphafold_status": "cached",
                    "ranking_score": 0.87,
                    "ptm": 0.79,
                    "iptm": 0.69,
                },
                "last_parsed_execution_id": "exec-3",
            },
        ],
    )

    assert summary["variant_sources"] == ["vcf"]
    assert summary["candidate_sources"] == ["mixmhc", "netmhcpan"]
    assert summary["structure_backends"] == ["alphafold3_local", "alphafold_db"]
    assert summary["structure_statuses"] == ["cached", "completed"]
    assert summary["best_ranking_score"] == 0.91
    assert summary["best_ptm"] == 0.81
    assert summary["best_iptm"] == 0.71
    assert summary["combined_execution_ids"] == ["exec-1", "exec-2", "exec-3"]


def test_build_provenance_summary_returns_defaults_for_empty_inputs() -> None:
    summary = build_provenance_summary([], [])

    assert summary["variant_sources"] == []
    assert summary["candidate_sources"] == []
    assert summary["combined_execution_ids"] == []
    assert summary["best_ranking_score"] == "n/a"
    assert summary["best_ptm"] == "n/a"
    assert summary["best_iptm"] == "n/a"


def test_build_case_governance_summary_counts_redacted_subjects_and_linked_samples() -> None:
    summary = build_case_governance_summary(
        {
            "species": "dog",
            "consent_status": "received",
            "review_status": "in_review",
            "supervising_professional": "Dr. Demo",
            "diagnosis_summary": "melanoma",
        },
        subjects=[
            {"id": "sub-1", "privacy_flags": {"redacted": True}},
            {"id": "sub-2", "privacy_flags": {}, "redaction_level": "deidentify"},
        ],
        samples=[
            {"id": "s1", "subject_id": "sub-1"},
            {"id": "s2", "subject_id": "sub-1"},
            {"id": "s3", "subject_id": "sub-2"},
            {"id": "s4", "subject_id": None},
        ],
    )

    assert summary == {
        "species": "dog",
        "consent_status": "received",
        "review_status": "in_review",
        "redaction_level": "full",
        "subject_count": 2,
        "linked_sample_count": 3,
        "redacted_subject_count": 2,
        "supervising_professional": "Dr. Demo",
        "diagnosis_summary": "melanoma",
    }


def test_build_subject_governance_rows_surfaces_privacy_notes_and_linked_sample_types() -> None:
    rows = build_subject_governance_rows(
        subjects=[
            {
                "id": "sub-1",
                "anonymized_display_name": "Rosie-demo",
                "privacy_flags": {"redacted": True},
                "metadata_json": {"species": "dog", "intake_notes": "left flank biopsy"},
                "created_at": "2026-04-19T09:00:00Z",
            },
            {
                "id": "sub-2",
                "anonymized_display_name": "Open-demo",
                "privacy_flags": {},
                "redaction_level": "deidentify",
                "metadata_json": {"species": "dog"},
            },
        ],
        samples=[
            {"id": "s1", "subject_id": "sub-1", "sample_type": "tumor"},
            {"id": "s2", "subject_id": "sub-1", "sample_type": "rna"},
            {"id": "s3", "subject_id": "sub-2", "sample_type": "normal"},
        ],
    )

    assert rows[0]["display_name"] == "Rosie-demo"
    assert rows[0]["privacy_mode"] == "redacted"
    assert rows[0]["species"] == "dog"
    assert rows[0]["linked_samples"] == 2
    assert rows[0]["sample_types"] == "rna, tumor"
    assert rows[0]["intake_notes"] == "left flank biopsy"
    assert rows[1]["privacy_mode"] == "deidentify"
    assert rows[1]["sample_types"] == "normal"
