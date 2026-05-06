from fastapi.testclient import TestClient


def test_candidate_review_report_surfaces_richer_alphafold_metrics(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Rich report case"},
    )
    case_id = create_case.json()["id"]

    candidates = client.get(f"/cases/{case_id}/candidates").json()
    candidate_id = candidates[0]["id"]
    candidate = client.get(f"/cases/{case_id}/candidates").json()[0]
    payload = {
        "review_status": candidate["review_status"],
        "expert_review_notes": candidate.get("expert_review_notes"),
    }
    update = client.patch(
        f"/candidates/{candidate_id}/review",
        json=payload,
    )
    assert update.status_code == 200

    # enrich existing candidate via direct case run path already exposed elsewhere in API behavior
    client.post(
        "/alphafold/backends/alphafold_db/run",
        json={
            "case_id": case_id,
            "candidate_id": candidate_id,
            "accession": "P04637",
            "job_name": "tp53-ref",
        },
    )

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    content = report["content_json"]

    assert content["structure_backend"] == "alphafold_db"
    assert content["structure_status"] == "completed"
    assert content["model_cif"].endswith("AF-P04637-F1-model_v4.cif")
    assert content["source_url"].endswith("/entry/P04637")
    assert content["output_format"] == "mmcif"


def test_candidate_review_report_surfaces_af3_scores(client: TestClient, monkeypatch) -> None:
    import json

    from backend.app.alphafold.shells import AlphaFoldExecution

    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AF3 report case"},
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
                        "ranking_score": 0.91,
                        "ptm": 0.72,
                        "iptm": 0.88,
                        "chain_pair_iptm": [[0.72, 0.88], [0.88, 0.71]],
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
    content = report["content_json"]
    assert content["ranking_score"] == 0.91
    assert content["ptm"] == 0.72
    assert content["iptm"] == 0.88
    assert content["chain_pair_iptm"] == [[0.72, 0.88], [0.88, 0.71]]
