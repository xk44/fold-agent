from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from backend.app.main import app
from skills.shared.neovax_client import NeoVaxClient


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

    def post(self, path, json=None, headers=None, params=None):
        self.calls.append(("POST", path, json, params))
        return _DummyResponse({"path": path, "json": json, "params": params}, path=path)

    def delete(self, path, headers=None, params=None):
        self.calls.append(("DELETE", path, None, params))
        return _DummyResponse({"path": path, "params": params}, path=path)



def test_redact_case_uses_current_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.redact_case("case-123", redaction_level="deidentify", confirm=True, reason="privacy")

    assert payload["path"] == "/cases/case-123/redact"
    assert payload["json"] == {"redaction_level": "deidentify", "confirm": True, "reason": "privacy"}



def test_redact_subject_uses_current_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.redact_subject("case-123", "sub-456", redaction_level="anonymous", confirm=True, reason="owner request")

    assert payload["path"] == "/cases/case-123/subjects/sub-456/redact"
    assert payload["json"] == {"redaction_level": "anonymous", "confirm": True, "reason": "owner request"}



def test_delete_case_uses_current_route() -> None:
    client = NeoVaxClient(base_url="http://localhost:8000")
    recorder = _Recorder()
    client.client = recorder

    payload = client.delete_case("case-123", confirm=True, hard_delete=False, reason="cleanup")

    assert payload["path"] == "/cases/case-123"
    assert payload["params"] == {"confirm": True, "hard_delete": False, "reason": "cleanup"}



def test_redact_case_endpoint_exists() -> None:
    client = TestClient(app)
    created_case = client.post("/cases", json={"species": "demo", "diagnosis_summary": "redact route case"})
    case_id = created_case.json()["id"]

    response = client.post(
        f"/cases/{case_id}/redact",
        json={"redaction_level": "deidentify", "confirm": True, "reason": "privacy"},
    )
    assert response.status_code == 200
    assert response.json()["case_id"] == case_id
    assert response.json()["redaction_level"] == "deidentify"



def test_redact_subject_endpoint_exists() -> None:
    client = TestClient(app)
    created_case = client.post("/cases", json={"species": "demo", "diagnosis_summary": "subject redact route case"})
    case_id = created_case.json()["id"]
    created_subject = client.post(
        f"/cases/{case_id}/subjects",
        json={"anonymized_display_name": "Rosie-demo", "metadata_json": {"species": "dog"}, "privacy_flags": {"redacted": False}},
    )
    subject_id = created_subject.json()["id"]

    response = client.post(
        f"/cases/{case_id}/subjects/{subject_id}/redact",
        json={"redaction_level": "deidentify", "confirm": True, "reason": "owner request"},
    )
    assert response.status_code == 200
    assert response.json()["subject_id"] == subject_id
    assert response.json()["redaction_level"] == "deidentify"



def test_delete_case_endpoint_exists() -> None:
    client = TestClient(app)
    created_case = client.post("/cases", json={"species": "demo", "diagnosis_summary": "delete route case"})
    case_id = created_case.json()["id"]

    response = client.delete(f"/cases/{case_id}", params={"confirm": True, "hard_delete": False, "reason": "cleanup"})
    assert response.status_code == 200
    assert response.json()["case_id"] == case_id
    assert response.json()["deleted"] is True
