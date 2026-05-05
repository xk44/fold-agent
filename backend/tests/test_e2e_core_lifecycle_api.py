import json
import time

import pytest

from fastapi.testclient import TestClient

from backend.app.alphafold.shells import AlphaFoldExecution

pytestmark = pytest.mark.e2e


def _create_case(client: TestClient, *, species: str = "demo", diagnosis_summary: str = "E2E lifecycle case") -> str:
    response = client.post(
        "/cases",
        json={"species": species, "diagnosis_summary": diagnosis_summary},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _poll_job_until_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(30):
        payload = client.get(f"/jobs/{job_id}")
        assert payload.status_code == 200
        body = payload.json()
        if body["status"] in {"completed", "failed", "cancelled", "timed_out"}:
            return body
        time.sleep(0.1)
    return client.get(f"/jobs/{job_id}").json()


def test_e2e_case_lifecycle_covers_subject_sample_reviews_reports_bundle_and_audit(client: TestClient) -> None:
    case_id = _create_case(client, diagnosis_summary="E2E operator workflow")

    subject = client.post(
        f"/cases/{case_id}/subjects",
        json={
            "anonymized_display_name": "demo-subject",
            "metadata_json": {"species": "demo", "cohort": "synthetic"},
            "privacy_flags": {"redacted": True},
        },
    )
    assert subject.status_code == 201

    sample = client.post(
        f"/cases/{case_id}/samples",
        json={
            "sample_type": "tumor",
            "file_paths": {"vcf": "/tmp/e2e-demo.vcf"},
            "checksum": "e2e123",
            "source_lab": "NeoVax Demo Lab",
        },
    )
    assert sample.status_code == 201

    variants = client.get(f"/cases/{case_id}/variants")
    candidates = client.get(f"/cases/{case_id}/candidates")
    assert variants.status_code == 200
    assert candidates.status_code == 200
    variant = variants.json()[0]
    candidate = candidates.json()[0]

    variant_review = client.patch(
        f"/variants/{variant['id']}/review",
        json={"review_status": "needs_data", "expert_review_notes": "Need orthogonal validation"},
    )
    candidate_review = client.patch(
        f"/candidates/{candidate['id']}/review",
        json={"review_status": "expert_accepted_for_further_research", "expert_review_notes": "Best synthetic candidate"},
    )
    assert variant_review.status_code == 200
    assert candidate_review.status_code == 200

    candidate_report = client.post(f"/cases/{case_id}/reports/candidate-review")
    ethics_report = client.post(f"/cases/{case_id}/reports/ethics-package")
    assert candidate_report.status_code == 201
    assert ethics_report.status_code == 201
    candidate_report_id = candidate_report.json()["id"]

    markdown_export = client.get(f"/reports/{candidate_report_id}/export?format=markdown")
    assert markdown_export.status_code == 200
    assert markdown_export.json()["format"] == "markdown"
    assert "Candidate antigens" in markdown_export.json()["content_text"]

    saved_report = client.post(f"/reports/{candidate_report_id}/save?format=markdown")
    assert saved_report.status_code == 200
    assert saved_report.json()["path"].endswith(".md")

    bundle = client.get(f"/cases/{case_id}/bundle")
    assert bundle.status_code == 200
    bundle_payload = bundle.json()
    assert bundle_payload["case"]["id"] == case_id
    assert len(bundle_payload["subjects"]) == 1
    assert len(bundle_payload["samples"]) == 1
    assert len(bundle_payload["reports"]) == 2

    saved_bundle = client.post(f"/cases/{case_id}/bundle/save?format=json")
    assert saved_bundle.status_code == 200
    assert saved_bundle.json()["path"].endswith(".json")

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert {
        "case.created",
        "subject.created",
        "sample.registered",
        "variant.reviewed",
        "candidate.reviewed",
        "report.generated",
        "report.exported",
        "report.saved",
        "bundle.saved",
    }.issubset(actions)


def test_e2e_async_pipeline_flow_covers_job_polling_history_bundle_and_events(client: TestClient) -> None:
    case_id = _create_case(client, diagnosis_summary="E2E async pipeline")

    dispatch = client.post(f"/cases/{case_id}/pipeline/run-async", json={})
    assert dispatch.status_code == 202
    job_id = dispatch.json()["id"]

    final_job = _poll_job_until_terminal(client, job_id)
    assert final_job["status"] == "completed"
    assert final_job["job_type"] == "pipeline_run"

    listed_jobs = client.get(f"/jobs?case_id={case_id}")
    assert listed_jobs.status_code == 200
    assert any(job["id"] == job_id for job in listed_jobs.json())

    history = client.get(f"/cases/{case_id}/pipeline/history")
    assert history.status_code == 200
    assert history.json()[0]["status"] == "completed"

    bundle = client.get(f"/cases/{case_id}/bundle")
    assert bundle.status_code == 200
    assert bundle.json()["latest_pipeline_run"]["case_id"] == case_id

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert {"pipeline.async_dispatched", "background_job.created", "pipeline.started", "pipeline.completed"}.issubset(actions)

    event_stream = client.get("/agent/events")
    assert event_stream.status_code == 200
    body = event_stream.text
    assert "event: background_job.created" in body or "event: pipeline.completed" in body


def test_e2e_async_alphafold_flow_covers_background_job_and_structure_job_linkage(
    client: TestClient, monkeypatch
) -> None:
    case_id = _create_case(client, diagnosis_summary="E2E async alphafold")

    variant = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr7:140453136 A>T",
            "gene": "BRAF",
            "protein_change": "p.V600E",
            "annotation_source": "manual_entry",
        },
    )
    assert variant.status_code == 201
    candidate = client.post(
        f"/cases/{case_id}/candidates",
        json={
            "variant_id": variant.json()["id"],
            "mhc_context": "HLA-A*02:01",
            "peptide_metadata": {"sequence": "BRAFV600E", "length": 9},
        },
    )
    assert candidate.status_code == 201

    def fake_execute_alphafold_backend(backend_name: str, payload: dict) -> AlphaFoldExecution:
        return AlphaFoldExecution(
            backend=backend_name,
            mode="execute",
            command=["colabfold_batch", "/tmp/demo.fa", "/tmp/demo_out"],
            available=True,
            validation_ok=True,
            notes="simulated",
            status="completed",
            stdout=json.dumps(
                {
                    "structure": {
                        "backend": backend_name,
                        "status": "completed",
                        "pdb_file": "/tmp/demo_out/predicted_structure.pdb",
                    }
                }
            ),
            stderr="",
            timed_out=False,
            return_code=0,
        )

    monkeypatch.setattr("backend.app.main.execute_alphafold_backend", fake_execute_alphafold_backend)

    dispatch = client.post(
        "/alphafold/backends/colabfold/run-async",
        json={
            "case_id": case_id,
            "candidate_id": candidate.json()["id"],
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "e2e-af-job",
        },
    )
    assert dispatch.status_code == 202
    job_id = dispatch.json()["id"]

    final_job = _poll_job_until_terminal(client, job_id)
    assert final_job["status"] == "completed"
    assert final_job["job_type"] == "alphafold_backend"

    structure_jobs = client.get(f"/cases/{case_id}/structure-jobs")
    assert structure_jobs.status_code == 200
    linked_jobs = [job for job in structure_jobs.json() if job["backend_used"] == "colabfold"]
    assert linked_jobs
    latest_linked_job = linked_jobs[-1]
    assert latest_linked_job["candidate_id"] == candidate.json()["id"]
    assert latest_linked_job["status"] in {"completed", "failed"}
    assert latest_linked_job["output_path"] in {None, "/tmp/demo_out/predicted_structure.pdb"}

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert {"alphafold.async_dispatched", "background_job.created", "alphafold.job.started", "alphafold.job.completed", "alphafold.backend.completed"}.issubset(actions)
