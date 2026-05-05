from fastapi.testclient import TestClient


def test_pipeline_and_alphafold_shell_stub_status_endpoints(client: TestClient) -> None:
    pipeline_response = client.get("/pipeline/adapters")
    assert pipeline_response.status_code == 200
    pipeline_payload = pipeline_response.json()
    assert "bwa_mem2" in pipeline_payload
    assert "pvactools" in pipeline_payload
    assert "available" in pipeline_payload["bwa_mem2"]
    assert "command" in pipeline_payload["bwa_mem2"]

    alphafold_response = client.get("/alphafold/backends")
    assert alphafold_response.status_code == 200
    alphafold_payload = alphafold_response.json()
    assert "mock" in alphafold_payload
    assert "colabfold" in alphafold_payload
    assert "available" in alphafold_payload["colabfold"]
    assert "validation_ok" in alphafold_payload["colabfold"]
