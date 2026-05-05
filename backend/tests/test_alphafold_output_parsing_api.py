import json

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_alphafold_shell_output_parsing_updates_candidate_structure_evidence(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AlphaFold parsed case"},
    )
    case_id = create_case.json()["id"]

    # Ensure synthetic candidate exists before parsing update
    candidates_before = client.get(f"/cases/{case_id}/candidates").json()
    assert candidates_before[0]["structure_evidence"]["alphafold_status"] == "mock_available"

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        assert backend_name == "colabfold"
        return AlphaFoldExecution(
            backend="colabfold",
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "structure": {
                        "backend": "colabfold",
                        "status": "completed",
                        "pdb_file": "/tmp/demo_out/predicted_structure.pdb",
                        "pLDDT_mean": 91.2,
                        "pAE_mean": 4.8,
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    run_response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
        },
    )
    assert run_response.status_code == 200

    candidates_after = client.get(f"/cases/{case_id}/candidates").json()
    structure_evidence = candidates_after[0]["structure_evidence"]
    assert structure_evidence["alphafold_status"] == "completed"
    assert structure_evidence["backend"] == "colabfold"
    assert structure_evidence["pdb_file"] == "/tmp/demo_out/predicted_structure.pdb"
    assert structure_evidence["pLDDT_mean"] == 91.2
    assert structure_evidence["pAE_mean"] == 4.8
    executions = client.get(f"/cases/{case_id}/executions").json()
    af_execution = next(item for item in executions if item["runner_name"] == "colabfold")
    assert candidates_after[0]["last_parsed_execution_id"] == af_execution["id"]


def test_candidate_report_reflects_parsed_alphafold_status(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "AlphaFold report case"},
    )
    case_id = create_case.json()["id"]

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps({"structure": {"backend": backend_name, "status": "completed", "pLDDT_mean": 88.4}}),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
        },
    )

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    assert report["content_json"]["structure_status"] == "completed"
    assert report["content_json"]["structure_backend"] == "colabfold"
