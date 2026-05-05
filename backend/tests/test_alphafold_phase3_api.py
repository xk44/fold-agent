import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_alphafold3_run_rejects_missing_json_path_with_422(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/alphafold3_local/run",
        json={
            "job_name": "af3-invalid",
            "input_kind": "json",
        },
    )

    assert response.status_code == 422
    assert "json_path" in response.text


def test_alphafold3_output_directory_is_parsed_when_stdout_is_empty(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AF3 output dir parse case"},
    )
    case_id = create_case.json()["id"]
    candidate_id = client.get(f"/cases/{case_id}/candidates").json()[0]["id"]

    output_dir = tmp_path / "hello_fold"
    output_dir.mkdir()
    (output_dir / "hello_fold_model.cif").write_text("data_demo\n", encoding="utf-8")
    (output_dir / "hello_fold_summary_confidences.json").write_text(
        json.dumps(
            {
                "ptm": 0.61,
                "iptm": 0.83,
                "ranking_score": 0.87,
                "chain_pair_iptm": [[0.61, 0.83], [0.83, 0.62]],
            }
        ),
        encoding="utf-8",
    )

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
            "job_name": "hello_fold",
            "input_kind": "json",
            "json_path": "/tmp/af3.json",
        },
    )
    assert run.status_code == 200

    structure_evidence = client.get(f"/cases/{case_id}/candidates").json()[0]["structure_evidence"]
    assert structure_evidence["model_cif"] == str(output_dir / "hello_fold_model.cif")
    assert structure_evidence["summary_confidences_json"] == str(output_dir / "hello_fold_summary_confidences.json")
    assert structure_evidence["ptm"] == 0.61
    assert structure_evidence["iptm"] == 0.83
    assert structure_evidence["ranking_score"] == 0.87
