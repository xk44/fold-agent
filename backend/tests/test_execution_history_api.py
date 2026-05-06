from fastapi.testclient import TestClient


def test_shell_execution_history_lists_pipeline_runs_and_skips_blocked_alphafold_runs(
    client: TestClient,
) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Execution history case"},
    )
    case_id = create_case.json()["id"]

    client.post(
        "/pipeline/adapters/vep/run",
        json={
            "case_id": case_id,
            "input_vcf": "/tmp/mock.vcf",
            "output_path": "/tmp/mock.vep.json",
        },
    )
    blocked = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
        },
    )
    assert blocked.status_code == 409

    response = client.get(f"/cases/{case_id}/executions")
    assert response.status_code == 200
    executions = response.json()

    assert len(executions) == 1
    assert executions[0]["runner_name"] == "vep"
    assert executions[0]["runner_kind"] == "pipeline_adapter"
    assert executions[0]["case_id"] == case_id
    assert "stdout" in executions[0]
    assert "stderr" in executions[0]
    assert executions[0]["artifacts"]
    assert any(
        artifact["artifact_type"] == "execution_log" for artifact in executions[0]["artifacts"]
    )
    assert any(artifact["id"] for artifact in executions[0]["artifacts"])


def test_execution_history_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/executions")

    assert response.status_code == 404
