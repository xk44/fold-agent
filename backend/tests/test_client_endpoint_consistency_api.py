from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from skills.shared.neovax_client import AlphaFoldValidationError, NeoVaxClient
from fastapi.testclient import TestClient
from backend.app.main import app


class _DummyResponse:
    def __init__(self, payload: dict | list | None = None, status_code: int = 200, path: str = "/"):
        self._payload = payload if payload is not None else {"ok": True}
        self.status_code = status_code
        self._path = path

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", f"http://localhost:8000{self._path}")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("boom", request=request, response=response)
        return None

    def json(self):
        return self._payload


class _Recorder:
    def __init__(self):
        self.calls = []
        self.next_post_response = None

    def post(self, path, json=None, params=None, headers=None):
        self.calls.append(("POST", path, json, params))
        if self.next_post_response is not None:
            response = self.next_post_response
            self.next_post_response = None
            return response
        return _DummyResponse({"path": path, "json": json, "params": params}, path=path)

    def get(self, path, params=None, headers=None):
        self.calls.append(("GET", path, None, params))
        return _DummyResponse({"path": path, "params": params}, path=path)


def test_submit_alphafold_job_uses_backend_run_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.submit_alphafold_job(
        sequence="MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
        backend="colabfold",
        case_id="case-123",
    )

    assert payload["path"] == "/alphafold/backends/colabfold/run"
    assert payload["json"]["case_id"] == "case-123"


def test_alphafold_backend_run_raises_structured_validation_error() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    recorder.next_post_response = _DummyResponse(
        {
            "detail": "AlphaFold backend 'colabfold' failed environment validation: Command 'colabfold_batch' not found on PATH.",
            "backend_name": "colabfold",
            "validation_ok": False,
            "validation_reason": "Command 'colabfold_batch' not found on PATH.",
        },
        status_code=409,
        path="/alphafold/backends/colabfold/run",
    )
    client.client = recorder

    try:
        client.alphafold_backend_run("colabfold", {"case_id": "case-123", "sequence": "ABC"})
        assert False, "expected AlphaFoldValidationError"
    except AlphaFoldValidationError as exc:
        assert exc.payload["backend_name"] == "colabfold"
        assert exc.payload["validation_reason"] == "Command 'colabfold_batch' not found on PATH."


def test_get_alphafold_job_uses_structure_job_detail_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.get_alphafold_job("job-123")

    assert payload["path"] == "/structure-jobs/job-123"


def test_create_agent_task_uses_current_agent_tasks_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.create_agent_task("case-123", framework="hermes", skill_name="demo-skill")

    assert payload["path"] == "/cases/case-123/agent-tasks"


def test_get_agent_task_endpoint_exists() -> None:
    client = TestClient(app)
    create_case = client.post("/cases", json={"species": "demo", "diagnosis_summary": "Agent task route case"})
    case_id = create_case.json()["id"]

    created = client.post(
        f"/cases/{case_id}/agent-tasks",
        json={"framework": "hermes", "skill_name": "demo-skill", "status": "pending"},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    fetched = client.get(f"/agent-tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == task_id
