from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.variant_explorer import build_variant_linkout_targets


def test_build_variant_linkout_targets_prefers_best_related_candidate_and_structure() -> None:
    assert build_variant_linkout_targets(None) == {}

    empty = build_variant_linkout_targets(
        {"id": "var-empty", "case_id": "case-1"},
        candidates=[],
        reports=[],
        artifacts=[],
        structure_jobs=[],
    )
    assert empty == {"case_id": "case-1"}

    linkouts = build_variant_linkout_targets(
        {
            "id": "var-1",
            "case_id": "case-1",
            "gene": "KIT",
            "protein_change": "p.V600E",
        },
        candidates=[
            {
                "id": "cand-1",
                "case_id": "case-1",
                "variant_id": "var-1",
                "review_status": "needs_data",
                "structure_evidence": {"ranking_score": 0.71, "model_cif": "/tmp/older.cif"},
                "created_at": "2026-04-22T00:00:00Z",
            },
            {
                "id": "cand-2",
                "case_id": "case-1",
                "variant_id": "var-1",
                "review_status": "expert_accepted_for_further_research",
                "structure_evidence": {"ranking_score": 0.91, "model_cif": "/tmp/best.cif"},
                "created_at": "2026-04-23T00:00:00Z",
            },
            {
                "id": "cand-x",
                "case_id": "case-1",
                "variant_id": "other",
                "review_status": "unreviewed",
                "structure_evidence": {"ranking_score": 0.99},
            },
        ],
        reports=[
            {"id": "report-1", "report_type": "candidate_review", "generated_at": "2026-04-23T00:00:00Z"},
            {"id": "report-2", "report_type": "ethics_package", "generated_at": "2026-04-24T00:00:00Z"},
        ],
        artifacts=[
            {"path": "/tmp/best.cif"},
            {"path": "/tmp/other.txt", "report_id": "report-1"},
        ],
        structure_jobs=[
            {"id": "sj-1", "candidate_id": "cand-1", "created_at": "2026-04-22T00:00:00Z"},
            {"id": "sj-2", "candidate_id": "cand-2", "created_at": "2026-04-23T00:00:00Z"},
        ],
    )

    assert linkouts["candidate_id"] == "cand-2"
    assert linkouts["structure_job_id"] == "sj-2"
    assert linkouts["report_id"] == "report-1"
    assert linkouts["artifact_path"] == "/tmp/best.cif"
