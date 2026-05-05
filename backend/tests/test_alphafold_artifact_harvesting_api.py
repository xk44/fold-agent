import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_alphafold_run_harvests_model_and_summary_artifacts(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Artifact harvest case"},
    )
    case_id = create_case.json()["id"]
    candidate_id = client.get(f"/cases/{case_id}/candidates").json()[0]["id"]

    output_dir = tmp_path / "harvest_case"
    output_dir.mkdir()
    model_cif = output_dir / "harvest_case_model.cif"
    summary_json = output_dir / "harvest_case_summary_confidences.json"
    model_cif.write_text("data_harvest\n", encoding="utf-8")
    summary_json.write_text(json.dumps({"ptm": 0.66, "iptm": 0.84, "ranking_score": 0.89}), encoding="utf-8")

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["alphafold", "--json_path", "/tmp/af3.json"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps({"output_dir": str(output_dir)}),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    run = client.post(
        "/alphafold/backends/alphafold3_local/run",
        json={
            "case_id": case_id,
            "candidate_id": candidate_id,
            "job_name": "harvest_case",
            "input_kind": "json",
            "json_path": "/tmp/af3.json",
        },
    )
    assert run.status_code == 200

    executions = client.get(f"/cases/{case_id}/executions").json()
    execution = next(item for item in executions if item["runner_name"] == "alphafold3_local")
    artifact_types = {artifact["artifact_type"] for artifact in execution["artifacts"]}
    assert "alphafold_model_cif" in artifact_types
    assert "alphafold_summary_confidences" in artifact_types

    harvested_model = next(artifact for artifact in execution["artifacts"] if artifact["artifact_type"] == "alphafold_model_cif")
    harvested_summary = next(artifact for artifact in execution["artifacts"] if artifact["artifact_type"] == "alphafold_summary_confidences")
    assert harvested_model["path"].endswith(model_cif.name)
    assert harvested_summary["path"].endswith(summary_json.name)

    model_download = client.get(f"/artifacts/file?path={harvested_model['path']}")
    assert model_download.status_code == 200
    assert "data_harvest" in model_download.text


def test_structure_job_detail_exposes_linked_execution_artifacts(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Structure explorer case"},
    )
    case_id = create_case.json()["id"]
    candidate_id = client.get(f"/cases/{case_id}/candidates").json()[0]["id"]

    run = client.post(
        "/alphafold/backends/alphafold_db/run",
        json={
            "case_id": case_id,
            "candidate_id": candidate_id,
            "accession": "P04637",
            "job_name": "tp53-ref",
        },
    )
    assert run.status_code == 200

    jobs = client.get(f"/cases/{case_id}/structure-jobs").json()
    linked = next(item for item in jobs if item["backend_used"] == "alphafold_db")
    detail = client.get(f"/structure-jobs/{linked['id']}").json()

    assert detail["backend_used"] == "alphafold_db"
    assert detail["output_path"].endswith("AF-P04637-F1-model_v4.cif")
    assert detail["confidence_metrics"]["source_url"].endswith("/entry/P04637")
