from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.main import app


def test_openapi_includes_enriched_metadata_for_alphafold_and_reports() -> None:
    schema = app.openapi()

    alphafold_run = schema["paths"]["/alphafold/backends/{backend_name}/run"]["post"]
    assert alphafold_run["summary"]
    assert "AlphaFold" in alphafold_run["summary"]
    assert alphafold_run["description"]
    assert "alphafold3_local" in alphafold_run["description"]
    assert alphafold_run["requestBody"]["content"]["application/json"]["example"]
    assert "409" in alphafold_run["responses"]
    validation_409 = alphafold_run["responses"]["409"]
    assert "description" in validation_409
    assert "validation" in validation_409["description"].lower()
    example_409 = validation_409["content"]["application/json"]["example"]
    assert example_409["backend_name"] == "colabfold"
    assert example_409["validation_ok"] is False
    assert "validation_reason" in example_409
    assert (
        validation_409["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AlphaFoldValidationErrorResponse"
    )

    report_generate = schema["paths"]["/cases/{case_id}/reports/candidate-review"]["post"]
    assert report_generate["summary"]
    assert "candidate review" in report_generate["summary"].lower()
    assert report_generate["description"]
    assert "research-only" in report_generate["description"].lower()

    report_export = schema["paths"]["/reports/{report_id}/export"]["get"]
    assert report_export["summary"]
    assert report_export["description"]
    assert any(param["name"] == "format" for param in report_export["parameters"])

    bundle_export = schema["paths"]["/cases/{case_id}/bundle/export"]["get"]
    assert bundle_export["summary"]
    assert bundle_export["description"]
