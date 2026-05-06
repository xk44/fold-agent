import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.candidate_review_table import (
    apply_candidate_column_preset,
    build_candidate_column_presets,
    build_candidate_detail,
    build_candidate_linkout_targets,
    build_candidate_review_summary,
    filter_candidates,
    format_candidate_option,
    sort_candidates,
)


def test_filter_candidates_by_status_mhc_score_ranges_and_none_defaults() -> None:
    candidates = [
        {
            "id": "cand-1",
            "mhc_context": "HLA-A*02:01",
            "review_status": "unreviewed",
            "prediction_scores": {"binding_rank": 0.04},
            "structure_evidence": {"ranking_score": 0.93},
        },
        {
            "id": "cand-2",
            "mhc_context": "HLA-B*07:02",
            "review_status": "needs_data",
            "prediction_scores": {},
            "structure_evidence": {},
        },
        {
            "id": "cand-3",
            "mhc_context": "HLA-A*02:01",
            "review_status": "expert_accepted_for_further_research",
            "prediction_scores": {"binding_rank": 0.08},
            "structure_evidence": {"ranking_score": 0.88},
        },
    ]

    filtered = filter_candidates(
        candidates,
        review_status="all",
        mhc_context="HLA-A*02:01",
        ranking_score_min=0.9,
        binding_rank_max=0.05,
    )
    assert [item["id"] for item in filtered] == ["cand-1"]
    assert filter_candidates(None, review_status="all", mhc_context="all") == []

    no_range_filter = filter_candidates(
        candidates,
        review_status="all",
        mhc_context="all",
        ranking_score_min=None,
        binding_rank_max=None,
    )
    assert [item["id"] for item in no_range_filter] == ["cand-1", "cand-2", "cand-3"]


def test_sort_candidates_prefers_requested_numeric_keys_and_missing_values_last() -> None:
    candidates = [
        {
            "id": "cand-1",
            "structure_evidence": {"ranking_score": 0.7},
            "prediction_scores": {"binding_rank": 0.08},
        },
        {
            "id": "cand-2",
            "structure_evidence": {"ranking_score": 0.91},
            "prediction_scores": {"binding_rank": 0.12},
        },
        {"id": "cand-3", "prediction_scores": {"binding_rank": 0.03}},
        {"id": "cand-4"},
    ]

    by_ranking = sort_candidates(candidates, sort_key="ranking_score", reverse=True)
    assert [item["id"] for item in by_ranking] == ["cand-2", "cand-1", "cand-3", "cand-4"]

    by_binding = sort_candidates(candidates, sort_key="binding_rank", reverse=False)
    assert [item["id"] for item in by_binding] == ["cand-3", "cand-1", "cand-2", "cand-4"]


def test_build_candidate_detail_flattens_nested_sections_and_handles_defaults() -> None:
    detail = build_candidate_detail(
        {
            "id": "cand-1",
            "variant_id": "var-1",
            "mhc_context": "HLA-A*02:01",
            "peptide_metadata": {"sequence": "SIINFEKL", "length": 8},
            "prediction_scores": {"binding_rank": 0.4, "immunogenicity": 0.7},
            "expression_evidence": {"tpm": 12.5},
            "structure_evidence": {
                "ranking_score": 0.91,
                "ptm": 0.82,
                "backend": "alphafold3_local",
                "model_cif": "/tmp/model.cif",
            },
            "uncertainty_flags": {"low_coverage": True},
            "review_status": "needs_data",
        }
    )

    assert detail["peptide_sequence"] == "SIINFEKL"
    assert detail["peptide_length"] == 8
    assert detail["binding_rank"] == 0.4
    assert detail["immunogenicity"] == 0.7
    assert detail["expression_tpm"] == 12.5
    assert detail["structure_ranking_score"] == 0.91
    assert detail["structure_backend"] == "alphafold3_local"
    assert detail["structure_model_path"] == "/tmp/model.cif"
    assert detail["uncertainty_low_coverage"] is True
    assert build_candidate_detail(None) == {}


def test_build_candidate_review_summary_and_option_formatting() -> None:
    candidates = [
        {
            "id": "cand-1",
            "mhc_context": "HLA-A*02:01",
            "review_status": "unreviewed",
            "structure_evidence": {"ranking_score": 0.7},
        },
        {
            "id": "cand-2",
            "mhc_context": None,
            "review_status": "needs_data",
            "structure_evidence": {"ranking_score": 0.91},
        },
        {
            "id": "cand-3",
            "mhc_context": "HLA-A*02:01",
            "review_status": "expert_accepted_for_further_research",
        },
    ]

    summary = build_candidate_review_summary(candidates)
    assert summary["total"] == 3
    assert summary["by_status"]["unreviewed"] == 1
    assert summary["by_status"]["needs_data"] == 1
    assert summary["has_accepted"] is True
    assert summary["best_ranking_score"] == 0.91
    assert format_candidate_option(candidates[0]) == "HLA-A*02:01 · unreviewed · cand-1"
    assert format_candidate_option(candidates[1]) == "candidate · needs_data · cand-2"


def test_candidate_column_presets_and_linkouts_cover_review_targets() -> None:
    presets = build_candidate_column_presets()
    assert "review" in presets
    assert "structure" in presets

    rows = [
        {
            "mhc_context": "HLA-A*02:01",
            "peptide_sequence": "SIINFEKL",
            "binding_rank": 0.04,
            "immunogenicity": 0.8,
            "ranking_score": 0.93,
            "structure_backend": "alphafold3_local",
            "structure_status": "completed",
            "review_status": "unreviewed",
            "last_parsed_execution_id": "exec-1",
        }
    ]
    trimmed = apply_candidate_column_preset(rows, "review")
    assert list(trimmed[0].keys()) == presets["review"]

    assert build_candidate_linkout_targets(None) == {}

    linkouts = build_candidate_linkout_targets(
        {
            "id": "cand-1",
            "case_id": "case-1",
            "structure_evidence": {"model_cif": "/tmp/model.cif"},
        },
        reports=[
            {
                "id": "report-older",
                "report_type": "candidate_review",
                "generated_at": "2026-04-22T00:00:00Z",
            },
            {
                "id": "report-1",
                "report_type": "candidate_review",
                "generated_at": "2026-04-23T00:00:00Z",
            },
            {
                "id": "report-2",
                "report_type": "ethics_package",
                "generated_at": "2026-04-24T00:00:00Z",
            },
        ],
        artifacts=[
            {"path": "/tmp/model.cif"},
            {"path": "/tmp/other.txt", "report_id": "report-1"},
        ],
        structure_jobs=[
            {"id": "sj-older", "candidate_id": "cand-1", "created_at": "2026-04-22T00:00:00Z"},
            {"id": "sj-1", "candidate_id": "cand-1", "created_at": "2026-04-23T00:00:00Z"},
        ],
    )
    assert linkouts["candidate_id"] == "cand-1"
    assert linkouts["structure_job_id"] == "sj-1"
    assert linkouts["report_id"] == "report-1"
    assert linkouts["artifact_path"] == "/tmp/model.cif"
