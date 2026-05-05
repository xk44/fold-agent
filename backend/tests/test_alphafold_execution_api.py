from fastapi.testclient import TestClient


def test_alphafold_shell_execution_returns_409_when_backend_validation_fails(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
            "case_id": "demo-case",
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["backend_name"] == "colabfold"
    assert payload["validation_ok"] is False
    assert "failed environment validation" in payload["detail"]
    assert "validation_reason" in payload

    executions = client.get("/cases/demo-case/executions")
    assert executions.status_code == 404 or executions.status_code == 200


def test_unknown_alphafold_shell_execution_returns_404(client: TestClient) -> None:
    response = client.post("/alphafold/backends/unknown/run", json={})

    assert response.status_code == 404
