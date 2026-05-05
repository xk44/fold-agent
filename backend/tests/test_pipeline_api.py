from fastapi.testclient import TestClient


def test_run_mock_pipeline_and_read_status(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Pipeline demo case"},
    )
    case_id = create_case.json()["id"]

    first_run_response = client.post(f"/cases/{case_id}/pipeline/run")
    assert first_run_response.status_code == 201
    first_payload = first_run_response.json()
    assert first_payload["case_id"] == case_id
    assert first_payload["status"] == "completed"
    assert first_payload["total_steps"] == 4
    assert first_payload["completed_steps"] == 4
    assert len(first_payload["steps"]) == 4

    second_run_response = client.post(f"/cases/{case_id}/pipeline/run")
    assert second_run_response.status_code == 201
    second_payload = second_run_response.json()
    assert second_payload["id"] != first_payload["id"]

    status_response = client.get(f"/cases/{case_id}/pipeline/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["case_id"] == case_id
    assert status_payload["status"] == "completed"
    assert status_payload["steps"][0]["step_name"] == "mock_alignment"
    assert status_payload["steps"][-1]["step_name"] == "mock_candidate_prioritization"
    assert status_payload["id"] == second_payload["id"]

    history_response = client.get(f"/cases/{case_id}/pipeline/history")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert len(history_payload) == 2
    assert history_payload[0]["id"] == second_payload["id"]
    assert history_payload[1]["id"] == first_payload["id"]


def test_pipeline_status_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/pipeline/status")

    assert response.status_code == 404



def test_pipeline_run_is_audit_logged(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Pipeline audit case"},
    )
    case_id = create_case.json()["id"]

    run_response = client.post(f"/cases/{case_id}/pipeline/run")
    assert run_response.status_code == 201

    audit_response = client.get(f"/audit/{case_id}")
    assert audit_response.status_code == 200
    actions = [entry["action"] for entry in audit_response.json()]
    assert "pipeline.started" in actions
    assert "pipeline.completed" in actions
    assert actions.count("pipeline.step.completed") == 4
