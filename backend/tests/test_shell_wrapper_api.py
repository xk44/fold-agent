from fastapi.testclient import TestClient


def test_pipeline_shell_adapter_dry_run_returns_command_manifest(client: TestClient) -> None:
    response = client.post(
        "/pipeline/adapters/vep/dry-run",
        json={
            "case_id": "demo-case",
            "input_vcf": "/tmp/mock.vcf",
            "output_path": "/tmp/mock.vep.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "vep"
    assert payload["mode"] == "dry_run"
    assert payload["command"][0] == "vep"
    assert "/tmp/mock.vcf" in payload["command"]
    assert payload["available"] is False
    assert payload["validation_ok"] is False


def test_pvactools_shell_adapter_dry_run_returns_command_manifest(client: TestClient) -> None:
    response = client.post(
        "/pipeline/adapters/pvactools/dry-run",
        json={
            "case_id": "demo-case",
            "input_vcf": "/tmp/mock.vcf",
            "sample_name": "demo-sample",
            "output_path": "/tmp/pvac-output",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter"] == "pvactools"
    assert payload["command"][0] == "pvacseq"
    assert "demo-sample" in payload["command"]


def test_alphafold_shell_backend_dry_run_returns_command_manifest(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/colabfold/dry-run",
        json={
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
            "case_id": "demo-case",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "colabfold"
    assert payload["mode"] == "dry_run"
    assert payload["command"][0] == "colabfold_batch"
    assert payload["validation_ok"] is False
    assert "validation_reason" in payload
    assert "diagnostics" in payload


def test_unknown_shell_adapter_returns_404(client: TestClient) -> None:
    response = client.post("/pipeline/adapters/unknown/dry-run", json={})

    assert response.status_code == 404
