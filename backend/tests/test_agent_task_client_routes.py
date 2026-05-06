import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from backend.app.main import app
from skills.shared.foldagent_client import FoldAgentClient


class _DummyResponse:
    def __init__(self, payload=None, path: str = "/", status_code: int = 200):
        self._payload = payload or {"path": path}
        self.path = path
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Recorder:
    def __init__(self):
        self.calls = []

    def get(self, path, headers=None, params=None):
        self.calls.append(("GET", path, None, params))
        return _DummyResponse({"path": path, "params": params}, path=path)

    def post(self, path, json=None, headers=None, params=None):
        self.calls.append(("POST", path, json, params))
        return _DummyResponse({"path": path, "json": json, "params": params}, path=path)

    def patch(self, path, json=None, headers=None, params=None):
        self.calls.append(("PATCH", path, json, params))
        return _DummyResponse({"path": path, "json": json, "params": params}, path=path)


def test_update_agent_task_uses_current_route() -> None:
    client = FoldAgentClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.update_agent_task("task-123", status="completed")

    assert payload["path"] == "/agent-tasks/task-123"
    assert payload["json"] == {"status": "completed"}


def test_update_agent_task_endpoint_exists() -> None:
    client = TestClient(app)
    created_case = client.post(
        "/cases", json={"species": "demo", "diagnosis_summary": "agent update case"}
    )
    case_id = created_case.json()["id"]

    created_task = client.post(
        "/agent/tasks",
        json={
            "case_id": case_id,
            "framework": "hermes",
            "skill_name": "monitor_case_progress",
            "status": "pending",
        },
    )
    assert created_task.status_code == 201
    task_id = created_task.json()["id"]

    updated = client.patch(f"/agent/tasks/{task_id}", json={"status": "completed"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"
