import json

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution


def test_structure_job_crud_and_alphafold_run_linkage(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Structure job case"},
    )
    case_id = create_case.json()["id"]

    variant = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr7:140453136 A>T",
            "gene": "BRAF",
            "protein_change": "p.V600E",
            "annotation_source": "manual_entry",
        },
    ).json()
    candidate = client.post(
        f"/cases/{case_id}/candidates",
        json={
            "variant_id": variant["id"],
            "mhc_context": "HLA-A*02:01",
            "peptide_metadata": {"sequence": "BRAFV600E", "length": 9},
        },
    ).json()

    create_job = client.post(
        f"/cases/{case_id}/structure-jobs",
        json={
            "candidate_id": candidate["id"],
            "backend_used": "mock",
            "input_hash": "abc123",
            "status": "queued",
        },
    )
    assert create_job.status_code == 201
    job = create_job.json()
    assert job["case_id"] == case_id
    assert job["candidate_id"] == candidate["id"]
    assert job["backend_used"] == "mock"

    list_jobs = client.get(f"/cases/{case_id}/structure-jobs")
    assert list_jobs.status_code == 200
    jobs = list_jobs.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job["id"]

    fetch_job = client.get(f"/structure-jobs/{job['id']}")
    assert fetch_job.status_code == 200
    assert fetch_job.json()["id"] == job["id"]

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps({"structure": {"backend": backend_name, "status": "completed", "pdb_file": "/tmp/demo_out/predicted_structure.pdb"}}),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    run_response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "candidate_id": candidate["id"],
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "demo-job",
        },
    )
    assert run_response.status_code == 200

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "alphafold.job.started" in actions
    assert "alphafold.job.completed" in actions
    assert "alphafold.backend.run" in actions

    jobs_after = client.get(f"/cases/{case_id}/structure-jobs").json()
    assert len(jobs_after) == 2
    linked = [item for item in jobs_after if item["backend_used"] == "colabfold"]
    assert linked
    assert linked[0]["candidate_id"] == candidate["id"]
    assert linked[0]["status"] == "completed"
    assert linked[0]["output_path"] == "/tmp/demo_out/predicted_structure.pdb"


def test_structure_job_creation_rejects_unknown_candidate(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Structure job case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        f"/cases/{case_id}/structure-jobs",
        json={"candidate_id": "missing-candidate", "backend_used": "mock"},
    )

    assert response.status_code == 404
