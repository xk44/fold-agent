import json

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_alphafold_db_backend_is_listed_and_lookup_run_updates_candidate(client: TestClient) -> None:
    backends = client.get("/alphafold/backends")
    assert backends.status_code == 200
    payload = backends.json()
    assert "alphafold_db" in payload

    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AFDB lookup case"},
    )
    case_id = create_case.json()["id"]
    candidates_before = client.get(f"/cases/{case_id}/candidates").json()

    run = client.post(
        "/alphafold/backends/alphafold_db/run",
        json={
            "case_id": case_id,
            "candidate_id": candidates_before[0]["id"],
            "accession": "P04637",
            "job_name": "tp53-ref",
        },
    )
    assert run.status_code == 200
    run_payload = run.json()
    assert run_payload["backend"] == "alphafold_db"
    assert run_payload["status"] == "completed"

    candidates_after = client.get(f"/cases/{case_id}/candidates").json()
    structure_evidence = candidates_after[0]["structure_evidence"]
    assert structure_evidence["backend"] == "alphafold_db"
    assert structure_evidence["alphafold_status"] == "completed"
    assert structure_evidence["source_url"].endswith("/entry/P04637")
    assert structure_evidence["model_cif"].endswith("AF-P04637-F1-model_v4.cif")


def test_alphafold_server_run_requires_external_upload_acknowledgement(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AF server gating case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/alphafold/backends/alphafold_server/run",
        json={
            "case_id": case_id,
            "json_path": "/tmp/afserver.json",
            "job_name": "remote-job",
        },
    )

    assert response.status_code == 403
    assert "External data upload" in response.json()["detail"]


def test_richer_alphafold_output_parsing_persists_extended_metrics(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AF rich parse case"},
    )
    case_id = create_case.json()["id"]
    candidates_before = client.get(f"/cases/{case_id}/candidates").json()
    candidate_id = candidates_before[0]["id"]

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
                        "ranking_score": 0.91,
                        "ptm": 0.72,
                        "iptm": 0.88,
                        "chain_pair_iptm": [[0.72, 0.88], [0.88, 0.71]],
                        "pLDDT_mean": 92.4,
                        "pAE_mean": 3.1,
                    }
                }
            ),
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
            "job_name": "af3-rich",
            "input_kind": "json",
            "json_path": "/tmp/af3.json",
        },
    )
    assert run.status_code == 200

    candidates_after = client.get(f"/cases/{case_id}/candidates").json()
    structure_evidence = candidates_after[0]["structure_evidence"]
    assert structure_evidence["model_cif"] == "/tmp/af3_out/best_model.cif"
    assert structure_evidence["summary_confidences_json"] == "/tmp/af3_out/best_summary_confidences.json"
    assert structure_evidence["ranking_score"] == 0.91
    assert structure_evidence["ptm"] == 0.72
    assert structure_evidence["iptm"] == 0.88
    assert structure_evidence["chain_pair_iptm"] == [[0.72, 0.88], [0.88, 0.71]]

    jobs = client.get(f"/cases/{case_id}/structure-jobs").json()
    linked = next(item for item in jobs if item["backend_used"] == "alphafold3_local")
    assert linked["output_path"] == "/tmp/af3_out/best_model.cif"
    assert linked["confidence_metrics"]["ranking_score"] == 0.91
    assert linked["confidence_metrics"]["ptm"] == 0.72
    assert linked["confidence_metrics"]["iptm"] == 0.88
