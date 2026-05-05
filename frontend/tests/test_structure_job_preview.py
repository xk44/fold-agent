from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.report_preview import format_structure_job_preview


def test_format_structure_job_preview_surfaces_key_fields() -> None:
    preview = format_structure_job_preview(
        {
            "id": "job-123",
            "backend_used": "alphafold3_local",
            "status": "completed",
            "output_path": "/tmp/best_model.cif",
            "confidence_metrics": {
                "ranking_score": 0.91,
                "ptm": 0.72,
                "iptm": 0.88,
                "source_url": "https://alphafold.ebi.ac.uk/entry/P04637",
                "summary_confidences_json": "/tmp/best_summary_confidences.json",
                "output_format": "mmcif",
            },
        }
    )

    assert "Structure Job" in preview
    assert "backend=alphafold3_local" in preview
    assert "status=completed" in preview
    assert "ranking_score=0.91" in preview
    assert "ptm=0.72" in preview
    assert "iptm=0.88" in preview
    assert "output_path=/tmp/best_model.cif" in preview
