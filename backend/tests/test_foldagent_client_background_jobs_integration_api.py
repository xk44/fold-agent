import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.db import SessionLocal
from backend.app.jobs import create_job
from skills.shared.foldagent_client import FoldAgentClient

POLL_SLEEP_SECONDS = 0.05
POLL_ATTEMPTS = 40


def _bind_shared_client(test_client: TestClient) -> FoldAgentClient:
    client = FoldAgentClient(base_url=str(test_client.base_url))
    client.client = test_client
    return client


def _create_demo_case(test_client: TestClient) -> str:
    response = test_client.post(
        "/cases", json={"species": "demo", "diagnosis_summary": "Shared client integration case"}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _poll_job_status(
    shared_client: FoldAgentClient, job_id: str, terminal_statuses: set[str] | None = None
) -> dict:
    statuses = terminal_statuses or {"completed", "failed", "cancelled", "timed_out"}
    latest = shared_client.get_background_job(job_id)
    for _ in range(POLL_ATTEMPTS):
        latest = shared_client.get_background_job(job_id)
        if latest["status"] in statuses:
            return latest
        time.sleep(POLL_SLEEP_SECONDS)
    return latest


def _poll_audit_actions(
    shared_client: FoldAgentClient, case_id: str, required_actions: set[str]
) -> list[str]:
    latest_actions = [entry["action"] for entry in shared_client.get_audit_log(case_id)]
    for _ in range(POLL_ATTEMPTS):
        latest_actions = [entry["action"] for entry in shared_client.get_audit_log(case_id)]
        if required_actions.issubset(set(latest_actions)):
            return latest_actions
        time.sleep(POLL_SLEEP_SECONDS)
    return latest_actions


def test_shared_client_cancel_and_list_background_jobs(client: TestClient) -> None:
    shared_client = _bind_shared_client(client)
    case_id = _create_demo_case(client)

    db = SessionLocal()
    try:
        job = create_job(
            db,
            case_id=case_id,
            job_type="pipeline_run",
            payload={"case_id": case_id},
            max_retries=1,
        )
        db.commit()
        job_id = job.id
    finally:
        db.close()

    listed = shared_client.list_background_jobs(case_id=case_id, status="pending")
    assert any(entry["id"] == job_id for entry in listed)

    cancelled = shared_client.cancel_background_job(job_id)
    assert cancelled["id"] == job_id
    assert cancelled["status"] == "cancelled"

    fetched = shared_client.get_background_job(job_id)
    assert fetched["status"] == "cancelled"


def test_shared_client_retry_background_job_auto_resubmits_pipeline_run(
    client: TestClient, monkeypatch
) -> None:
    shared_client = _bind_shared_client(client)
    case_id = _create_demo_case(client)
    call_count = {"count": 0}

    def fake_run_pipeline_sync(case_id_: str) -> dict:
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise RuntimeError("simulated pipeline failure")
        return {
            "status": "completed",
            "total_steps": 1,
            "completed_steps": 1,
            "steps": [
                {
                    "step_name": "mock_step",
                    "step_version": "test",
                    "status": "completed",
                    "outputs": {"case_id": case_id_},
                    "warnings": [],
                    "errors": [],
                }
            ],
        }

    monkeypatch.setattr("backend.app.main._run_pipeline_sync", fake_run_pipeline_sync)

    dispatch = client.post(
        f"/cases/{case_id}/pipeline/run-async",
        json={},
        params={"max_retries": 1},
    )
    assert dispatch.status_code == 202
    job_id = dispatch.json()["id"]

    failed = _poll_job_status(shared_client, job_id, {"failed"})
    assert failed["status"] == "failed"

    retried = shared_client.retry_background_job(job_id)
    assert retried["attempt"] == 2
    assert retried["status"] in {"pending", "running", "completed"}

    completed = _poll_job_status(shared_client, job_id, {"completed"})
    assert completed["status"] == "completed"
    assert completed["attempt"] == 2
    assert completed["result"]["status"] == "completed"
    assert call_count["count"] == 2

    audit_actions = _poll_audit_actions(
        shared_client,
        case_id,
        {"background_job.retried", "background_job.completed"},
    )
    assert "background_job.retried" in audit_actions
    assert "background_job.completed" in audit_actions


def test_shared_client_retry_background_job_auto_resubmits_alphafold_and_lists_structure_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    shared_client = _bind_shared_client(client)
    case_id = _create_demo_case(client)
    variant = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr7:140453136 A>T",
            "gene": "BRAF",
            "protein_change": "p.V600E",
        },
    ).json()
    candidate = client.post(
        f"/cases/{case_id}/candidates",
        json={"variant_id": variant["id"], "mhc_context": "HLA-A*02:01"},
    ).json()
    call_count = {"count": 0}

    def fake_run_alphafold_sync(backend_name: str, payload: dict) -> dict:
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise RuntimeError("simulated alphafold failure")
        return {
            "status": "completed",
            "command": [backend_name, "run"],
            "stdout": json.dumps(
                {
                    "structure": {
                        "backend": backend_name,
                        "pdb_file": "/tmp/mock-structure.pdb",
                        "ranking_score": 0.91,
                    }
                }
            ),
            "stderr": "",
            "return_code": 0,
            "timed_out": False,
            "structure": {
                "backend": backend_name,
                "pdb_file": "/tmp/mock-structure.pdb",
                "ranking_score": 0.91,
            },
        }

    monkeypatch.setattr("backend.app.main._run_alphafold_sync", fake_run_alphafold_sync)

    dispatch = client.post(
        "/alphafold/backends/mock/run-async",
        params={"max_retries": 1},
        json={
            "case_id": case_id,
            "candidate_id": candidate["id"],
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "shared-client-retry",
        },
    )
    assert dispatch.status_code == 202
    job_id = dispatch.json()["id"]

    failed = _poll_job_status(shared_client, job_id, {"failed"})
    assert failed["status"] == "failed"

    retried = shared_client.retry_background_job(job_id)
    assert retried["attempt"] == 2
    assert retried["status"] in {"pending", "running", "completed"}

    completed = _poll_job_status(shared_client, job_id, {"completed"})
    assert completed["status"] == "completed"
    assert completed["attempt"] == 2
    assert call_count["count"] == 2

    structure_jobs = shared_client.list_structure_jobs(case_id)
    assert len(structure_jobs) >= 1
    structure_job = shared_client.get_structure_job(structure_jobs[0]["id"])
    assert structure_job["backend_used"] == "mock"
    assert structure_job["confidence_metrics"]["ranking_score"] == 0.91
