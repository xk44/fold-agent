from fastapi.testclient import TestClient


def test_pipeline_shell_execution_returns_graceful_unavailable_status(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Shell execution case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/pipeline/adapters/vep/run",
        json={
            "case_id": case_id,
            "input_vcf": "/tmp/mock.vcf",
            "output_path": "/tmp/mock.vep.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "vep"
    assert payload["mode"] == "execute"
    assert payload["status"] in {"unavailable", "completed", "failed"}
    assert payload["command"][0] == "vep"
    assert "stdout" in payload
    assert "stderr" in payload
    assert "timed_out" in payload

    audit = client.get(f"/audit/{case_id}")
    actions = [entry["action"] for entry in audit.json()]
    assert "pipeline.adapter.run" in actions

    artifacts = client.get(f"/cases/{case_id}/artifacts").json()
    artifact_types = {artifact["artifact_type"] for artifact in artifacts}
    assert "execution_log" in artifact_types
    assert "execution_output" in artifact_types


def test_pvactools_shell_execution_returns_command_and_status(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "pVAC shell case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/pipeline/adapters/pvactools/run",
        json={
            "case_id": case_id,
            "input_vcf": "/tmp/mock.vcf",
            "sample_name": "demo-sample",
            "output_path": "/tmp/pvac-output",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "pvactools"
    assert payload["mode"] == "execute"
    assert payload["command"][0] == "pvacseq"
    assert payload["status"] in {"unavailable", "completed", "failed"}


def test_unknown_pipeline_shell_execution_returns_404(client: TestClient) -> None:
    response = client.post("/pipeline/adapters/unknown/run", json={})

    assert response.status_code == 404
