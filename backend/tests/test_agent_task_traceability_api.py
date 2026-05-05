from fastapi.testclient import TestClient


def test_case_bundle_includes_agent_tasks(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent bundle case"},
    )
    case_id = create_case.json()["id"]

    client.post(
        f"/cases/{case_id}/agent-tasks",
        json={
            "framework": "hermes",
            "skill_name": "hermes-task-routed-subagents",
            "status": "running",
            "logs": {"session": "swarm-2"},
            "artifacts": {"plan": "artifact://plan-2"},
        },
    )

    response = client.get(f"/cases/{case_id}/bundle")
    assert response.status_code == 200
    bundle = response.json()

    assert len(bundle["agent_tasks"]) == 1
    assert bundle["agent_tasks"][0]["framework"] == "hermes"
    assert bundle["agent_tasks"][0]["skill_name"] == "hermes-task-routed-subagents"


def test_unified_runs_view_includes_agent_task_events(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent runs case"},
    )
    case_id = create_case.json()["id"]

    created = client.post(
        f"/cases/{case_id}/agent-tasks",
        json={
            "framework": "hermes",
            "skill_name": "hermes-task-routed-subagents",
            "status": "running",
            "logs": {"session": "swarm-3", "summary": "triage"},
            "artifacts": {"plan": "artifact://plan-3"},
        },
    )
    task = created.json()

    response = client.get(f"/cases/{case_id}/runs")
    assert response.status_code == 200
    runs = response.json()

    agent_runs = [item for item in runs if item["run_kind"] == "agent_task"]
    assert len(agent_runs) == 1
    assert agent_runs[0]["id"] == task["id"]
    assert agent_runs[0]["name"] == "hermes-task-routed-subagents"
    assert agent_runs[0]["status"] == "running"
    assert agent_runs[0]["details"]["framework"] == "hermes"
    assert agent_runs[0]["details"]["logs"]["session"] == "swarm-3"


def test_bundle_export_json_includes_agent_tasks(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent export case"},
    )
    case_id = create_case.json()["id"]

    client.post(
        f"/cases/{case_id}/agent-tasks",
        json={
            "framework": "hermes",
            "skill_name": "hermes-task-routed-subagents",
            "status": "completed",
            "logs": {"summary": "done"},
            "artifacts": {"report": "artifact://report-2"},
        },
    )

    response = client.get(f"/cases/{case_id}/bundle/export?format=json")
    assert response.status_code == 200
    payload = response.json()

    assert payload["content_json"]["agent_tasks"][0]["status"] == "completed"
    assert payload["content_json"]["agent_tasks"][0]["artifacts"]["report"] == "artifact://report-2"
