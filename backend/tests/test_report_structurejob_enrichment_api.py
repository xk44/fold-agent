import json

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_report_markdown_export_includes_richer_alphafold_fields(
    client: TestClient, monkeypatch
) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Rich markdown case"},
    )
    case_id = create_case.json()["id"]
    candidate_id = client.get(f"/cases/{case_id}/candidates").json()[0]["id"]

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["alphafold", "--json_path", "/tmp/af3.json"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "structure": {
                        "backend": backend_name,
                        "status": "completed",
                        "model_cif": "/tmp/af3_out/best_model.cif",
                        "summary_confidences_json": "/tmp/af3_out/best_summary_confidences.json",
                        "source_url": "https://alphafold.ebi.ac.uk/entry/P04637",
                        "output_format": "mmcif",
                        "ranking_score": 0.91,
                        "ptm": 0.72,
                        "iptm": 0.88,
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr(
        "backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend
    )
    run = client.post(
        "/alphafold/backends/alphafold3_local/run",
        json={
            "case_id": case_id,
            "candidate_id": candidate_id,
            "job_name": "af3-rich",
            "input_kind": "json",
            "json_path": "/tmp/af3.json",
        },
    )
    assert run.status_code == 200

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    markdown = client.get(f"/reports/{report['id']}/export?format=markdown").json()["content_text"]
    assert "Ranking score: 0.91" in markdown
    assert "pTM: 0.72" in markdown
    assert "ipTM: 0.88" in markdown
    assert "Model CIF: /tmp/af3_out/best_model.cif" in markdown
    assert "Source URL: https://alphafold.ebi.ac.uk/entry/P04637" in markdown


def test_structure_job_detail_captures_richer_reference_fields(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Structure detail case"},
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

    assert detail["output_path"].endswith("AF-P04637-F1-model_v4.cif")
    assert detail["confidence_metrics"]["source_url"].endswith("/entry/P04637")
    assert detail["confidence_metrics"]["output_format"] == "mmcif"
    assert detail["confidence_metrics"]["accession"] == "P04637"
