from fastapi.testclient import TestClient


def test_agent_task_crud_flow(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent task case"},
    )
    case_id = create_case.json()["id"]

    create_task = client.post(
        "/agent/tasks",
        json={
            "case_id": case_id,
            "framework": "hermes",
            "skill_name": "hermes-task-routed-subagents",
            "status": "running",
            "logs": {"session": "swarm-1", "summary": "delegated triage"},
            "artifacts": {"plan": "artifact://plan-1"},
        },
    )
    assert create_task.status_code == 201
    task = create_task.json()
    assert task["case_id"] == case_id
    assert task["framework"] == "hermes"
    assert task["skill_name"] == "hermes-task-routed-subagents"
    assert task["status"] == "running"
    assert task["logs"]["session"] == "swarm-1"

    list_tasks = client.get(f"/cases/{case_id}/agent-tasks")
    assert list_tasks.status_code == 200
    tasks = list_tasks.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]

    patch_task = client.patch(
        f"/agent-tasks/{task['id']}",
        json={
            "status": "completed",
            "logs": {"session": "swarm-1", "summary": "done"},
            "artifacts": {"plan": "artifact://plan-1", "report": "artifact://report-1"},
        },
    )
    assert patch_task.status_code == 200
    updated = patch_task.json()
    assert updated["status"] == "completed"
    assert updated["logs"]["summary"] == "done"
    assert updated["artifacts"]["report"] == "artifact://report-1"


def test_agent_tasks_global_routes_support_case_optional_records(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Global agent task case"},
    )
    case_id = create_case.json()["id"]

    case_task = client.post(
        "/agent/tasks",
        json={
            "case_id": case_id,
            "framework": "hermes",
            "skill_name": "run_full_neovax_case_review",
            "status": "pending",
        },
    )
    assert case_task.status_code == 201

    global_task = client.post(
        "/agent/tasks",
        json={
            "framework": "openclaw",
            "skill_name": "monitor_case_progress",
            "status": "queued",
        },
    )
    assert global_task.status_code == 201
    global_payload = global_task.json()
    assert global_payload["case_id"] is None

    list_all = client.get("/agent/tasks")
    assert list_all.status_code == 200
    all_tasks = list_all.json()
    assert {item["id"] for item in all_tasks} == {case_task.json()["id"], global_payload["id"]}

    list_case_filtered = client.get(f"/agent/tasks?case_id={case_id}")
    assert list_case_filtered.status_code == 200
    case_filtered = list_case_filtered.json()
    assert [item["id"] for item in case_filtered] == [case_task.json()["id"]]

    fetched = client.get(f"/agent/tasks/{global_payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == global_payload["id"]

    legacy_fetched = client.get(f"/agent-tasks/{global_payload['id']}")
    assert legacy_fetched.status_code == 200
    assert legacy_fetched.json()["id"] == global_payload["id"]


def test_missing_case_agent_task_list_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/agent-tasks")

    assert response.status_code == 404


def test_missing_agent_task_update_returns_404(client: TestClient) -> None:
    response = client.patch("/agent-tasks/missing-task", json={"status": "completed"})

    assert response.status_code == 404


def test_current_agent_task_update_route_alias_works(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent task alias case"},
    )
    case_id = create_case.json()["id"]
    create_task = client.post(
        "/agent/tasks",
        json={
            "case_id": case_id,
            "framework": "hermes",
            "skill_name": "hermes-task-routed-subagents",
            "status": "pending",
        },
    )
    task_id = create_task.json()["id"]

    response = client.patch(f"/agent/tasks/{task_id}", json={"status": "completed"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_human_case_agent_task_create_blocked_by_sequence_gate(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Human agent task case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/agent/tasks",
        json={
            "case_id": case_id,
            "framework": "hermes",
            "skill_name": "run_full_neovax_case_review",
            "status": "pending",
        },
    )

    assert response.status_code == 403
    assert response.json()["safety_status"] == "requires_approval"


def test_human_case_agent_task_dry_run_blocked_by_sequence_gate(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Human agent task dry-run case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/agent/tasks/dry-run",
        json={
            "case_id": case_id,
            "framework": "claude_code",
            "skill_name": "run_full_neovax_case_review",
            "status": "pending",
        },
    )

    assert response.status_code == 403
    assert response.json()["safety_status"] == "requires_approval"

    events = client.get("/agent/events?limit=50").text
    assert "event: expert.review.required" in events



def test_agent_skills_endpoint_lists_repo_skill_inventory(client: TestClient) -> None:
    response = client.get("/agent/skills")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) >= 27
    assert any(item["skill_name"] == "run_full_neovax_case_review" for item in payload)
    frameworks = {item["framework"] for item in payload}
    assert {"claude_code", "openclaw", "hermes"}.issubset(frameworks)
    first = payload[0]
    assert "framework" in first
    assert "skill_path" in first
    assert "available" in first
    assert "description" in first
    assert "safety_boundaries" in first
    assert "required_api_endpoints" in first

    neovax_skill = next(item for item in payload if item["skill_name"] == "run_full_neovax_case_review")
    assert "research coordination under professional oversight" in neovax_skill["description"].lower()
    assert any("not administerable" in item.lower() for item in neovax_skill["safety_boundaries"])
    assert any(endpoint == "POST /safety/preflight" for endpoint in neovax_skill["required_api_endpoints"])



def test_agent_task_dry_run_returns_preview_without_persisting(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent task dry-run case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/agent/tasks/dry-run",
        json={
            "case_id": case_id,
            "framework": "claude_code",
            "skill_name": "run_full_neovax_case_review",
            "status": "pending",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["case_exists"] is True
    assert payload["framework"] == "claude_code"
    assert payload["skill_name"] == "run_full_neovax_case_review"
    assert payload["skill_available"] is True

    list_tasks = client.get(f"/cases/{case_id}/agent-tasks")
    assert list_tasks.status_code == 200
    assert list_tasks.json() == []



def test_agent_events_sse_stream_lists_recent_audit_events(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Agent event stream case"},
    )
    case_id = create_case.json()["id"]
    client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "tumor", "checksum": "agent-event-sample"},
    )
    client.post(
        f"/cases/{case_id}/agent-tasks",
        json={"framework": "hermes", "skill_name": "run_full_neovax_case_review", "status": "pending"},
    )
    client.post(f"/cases/{case_id}/reports/candidate-review")

    response = client.get("/agent/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: case.created" in body
    assert "event: sample.registered" in body or "event: sample.uploaded" in body
    assert "event: agent_task.created" in body
    assert "event: report.generated" in body
    assert f'"case_id": "{case_id}"' in body



def test_shared_skill_assets_exist() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert (root / "skills" / "shared" / "openapi.json").exists()
    assert (root / "skills" / "shared" / "report_templates" / "candidate_review.md").exists()
    assert (root / "skills" / "shared" / "report_templates" / "ethics_package.md").exists()
