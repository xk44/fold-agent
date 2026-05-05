from fastapi.testclient import TestClient

from backend.app.db import SessionLocal
from backend.app.models import Report
from backend.app.safety.preflight import PreflightResult


class DummyPreflightResult:
    def __init__(self, status: str, reason: str):
        self.status = status
        self.reason = reason
        self.blocked_patterns = []

    @property
    def allowed(self) -> bool:
        return self.status == PreflightResult.PASS

    @property
    def blocked(self) -> bool:
        return self.status == PreflightResult.BLOCK

    @property
    def needs_approval(self) -> bool:
        return self.status == PreflightResult.REQUIRES_APPROVAL


def _inject_unsafe_report_content(report_id: str, *, unsafe_text: str) -> None:
    with SessionLocal() as db:
        report = db.get(Report, report_id)
        assert report is not None
        payload = dict(report.content_json or {})
        payload["content_text"] = unsafe_text
        report.content_json = payload
        db.add(report)
        db.commit()


def _create_case_and_report(client: TestClient) -> tuple[str, str]:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Safety gate case"},
    )
    case_id = create_case.json()["id"]
    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    return case_id, report["id"]


def test_pipeline_run_blocked_by_safety_preflight(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Safety gate case"},
    )
    case_id = create_case.json()["id"]

    monkeypatch.setattr(
        "backend.app.main.preflight_action",
        lambda **_: DummyPreflightResult(PreflightResult.BLOCK, "blocked by test"),
    )

    response = client.post(f"/cases/{case_id}/pipeline/run")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "blocked by test"
    assert body["safety_status"] == PreflightResult.BLOCK
    assert body["safety_reason"] == "blocked by test"



def test_report_export_requires_approval_from_safety_preflight(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Report export gate case"},
    )
    case_id = create_case.json()["id"]
    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()

    monkeypatch.setattr(
        "backend.app.main.preflight_action",
        lambda **_: DummyPreflightResult(PreflightResult.REQUIRES_APPROVAL, "approval required by test"),
    )

    response = client.get(f"/reports/{report['id']}/export?format=markdown")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "approval required by test"
    assert body["safety_status"] == PreflightResult.REQUIRES_APPROVAL
    assert body["safety_reason"] == "approval required by test"


def test_report_export_blocks_unsafe_markdown_content(client: TestClient) -> None:
    _case_id, report_id = _create_case_and_report(client)
    _inject_unsafe_report_content(
        report_id,
        unsafe_text="Candidate summary includes a dosing schedule instruction for injection.",
    )

    response = client.get(f"/reports/{report_id}/export?format=markdown")

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.BLOCK
    assert body["blocked_patterns"]
    assert "prohibited output patterns" in body["detail"]


def test_report_save_blocks_unsafe_json_content(client: TestClient) -> None:
    _case_id, report_id = _create_case_and_report(client)
    _inject_unsafe_report_content(
        report_id,
        unsafe_text="This report contains a dosing schedule regimen for self-administer use.",
    )

    response = client.post(f"/reports/{report_id}/save?format=json")

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.BLOCK
    assert body["blocked_patterns"]


def test_bundle_export_blocks_unsafe_nested_report_content(client: TestClient) -> None:
    case_id, report_id = _create_case_and_report(client)
    _inject_unsafe_report_content(
        report_id,
        unsafe_text="Unsafe treatment protocol to inject the vaccine appears here.",
    )

    response = client.get(f"/cases/{case_id}/bundle/export?format=json")

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.BLOCK
    assert body["blocked_patterns"]



def test_bundle_save_blocked_by_safety_preflight(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Bundle save gate case"},
    )
    case_id = create_case.json()["id"]

    monkeypatch.setattr(
        "backend.app.main.preflight_action",
        lambda **_: DummyPreflightResult(PreflightResult.BLOCK, "bundle blocked by test"),
    )

    response = client.post(f"/cases/{case_id}/bundle/save?format=json")

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "bundle blocked by test"
    assert body["safety_status"] == PreflightResult.BLOCK
    assert body["safety_reason"] == "bundle blocked by test"

    events = client.get("/agent/events?limit=50")
    assert "event: safety.blocked" in events.text



def test_pipeline_run_human_case_blocked_by_sequence_gate(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Human sequencing pipeline case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(f"/cases/{case_id}/pipeline/run")

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.REQUIRES_APPROVAL
    assert "expert mode" in body["detail"].lower()



def test_pipeline_adapter_run_human_case_blocked_by_sequence_gate(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Human adapter pipeline case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        "/pipeline/adapters/vep/run",
        json={"case_id": case_id, "input_vcf": "/tmp/mock.vcf", "output_path": "/tmp/mock.vep.json"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.REQUIRES_APPROVAL
    assert "expert mode" in body["detail"].lower()



def test_alphafold_run_human_case_blocked_by_sequence_gate(client: TestClient, monkeypatch) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Human alphafold case"},
    )
    case_id = create_case.json()["id"]

    monkeypatch.setattr(
        "backend.app.main.execute_alphafold_backend",
        lambda *_args, **_kwargs: None,
    )

    response = client.post(
        "/alphafold/backends/colabfold/run",
        json={
            "case_id": case_id,
            "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
            "job_name": "human-sequence-job",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["safety_status"] == PreflightResult.REQUIRES_APPROVAL
    assert "expert mode" in body["detail"].lower()
