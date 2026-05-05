from fastapi.testclient import TestClient


def test_colabfold_dry_run_accepts_host_url_and_num_recycle(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/colabfold/dry-run",
        json={
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
            "case_id": "demo-case",
            "host_url": "https://msa.example.org",
            "num_recycle": 6,
            "num_seeds": 3,
            "use_templates": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "colabfold"
    assert payload["command"][0] == "colabfold_batch"
    assert "--host-url" in payload["command"]
    assert "https://msa.example.org" in payload["command"]
    assert "--num-recycle" in payload["command"]
    assert "6" in payload["command"]
    assert "--num-seeds" in payload["command"]
    assert "3" in payload["command"]
    assert "--templates" in payload["command"]


def test_alphafold3_dry_run_accepts_json_input_mode(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/alphafold3_local/dry-run",
        json={
            "job_name": "af3-demo",
            "input_kind": "json",
            "json_path": "/tmp/af3-input.json",
            "model_dir": "/models/af3",
            "db_dir": "/db/af3",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "alphafold3_local"
    assert payload["command"][0] == "alphafold"
    assert "--json_path" in payload["command"]
    assert "/tmp/af3-input.json" in payload["command"]
    assert "--model_dir" in payload["command"]
    assert "/models/af3" in payload["command"]
    assert "--db_dir" in payload["command"]
    assert "/db/af3" in payload["command"]


def test_alphafold_dry_run_surfaces_validation_reason_and_diagnostics(client: TestClient) -> None:
    response = client.post(
        "/alphafold/backends/colabfold/dry-run",
        json={
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "dryrun-diagnostics",
            "case_id": "demo-case",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "validation_reason" in payload
    assert "diagnostics" in payload
    assert "version_probe" in payload["diagnostics"]
    assert "command_on_path" in payload["diagnostics"]


def test_alphafold_server_is_listed_with_remote_metadata(client: TestClient) -> None:
    response = client.get("/alphafold/backends")
    assert response.status_code == 200

    payload = response.json()
    assert "alphafold_server" in payload
    assert payload["alphafold_server"]["mode"] == "cloud"
    assert payload["alphafold_server"]["requires_external_upload"] is True
    assert payload["alphafold_server"]["supports_rna_dna_ligands"] is True
