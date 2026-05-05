from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.report_preview import format_bundle_preview


def test_format_bundle_preview_surfaces_summary_sections() -> None:
    preview = format_bundle_preview(
        {
            "case": {"id": "case-123", "species": "demo", "diagnosis_summary": "bundle summary"},
            "samples": [{"id": "s1"}],
            "variants": [{"id": "v1", "gene": "KIT", "review_status": "unreviewed"}],
            "candidates": [{"id": "c1", "variant_id": "v1", "review_status": "unreviewed"}],
            "reports": [{"id": "r1", "report_type": "candidate_review"}],
            "audit_log": [{"id": "a1"}],
            "latest_pipeline_run": {"status": "completed", "completed_steps": 4, "total_steps": 4},
            "safety_label": "Research candidate only — not administerable",
        }
    )

    assert "Case Bundle" in preview
    assert "Diagnosis summary: bundle summary" in preview
    assert "Counts" in preview
    assert "Top genes" in preview
    assert "Latest reports" in preview
    assert "Pipeline status" in preview
