import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.seed_demo import seed_demo_database

pytestmark = pytest.mark.e2e


def test_synthetic_demo_flow_covers_seed_pipeline_reports_safety_audit_and_agent_surfaces(client: TestClient) -> None:
    seeded = seed_demo_database(settings.database_url, reset=False)
    case_id = seeded["case_id"]

    cases = client.get("/cases")
    assert cases.status_code == 200
    assert any(item["id"] == case_id for item in cases.json())

    pipeline_run = client.post(f"/cases/{case_id}/pipeline/run")
    assert pipeline_run.status_code == 201

    pipeline_status = client.get(f"/cases/{case_id}/pipeline/status")
    assert pipeline_status.status_code == 200
    assert pipeline_status.json()["status"] == "completed"

    candidate_report = client.post(f"/cases/{case_id}/reports/candidate-review")
    assert candidate_report.status_code == 201
    ethics_report = client.post(f"/cases/{case_id}/reports/ethics-package")
    assert ethics_report.status_code == 201

    safety_block = client.post(
        "/safety/mrna-gate",
        json={
            "action": "export_sequence_package",
            "species_mode": "human",
            "is_export": True,
            "involves_sequence_data": True,
            "content": "AUGGCUACGUAGCUAGCUAG",
        },
    )
    assert safety_block.status_code == 200
    assert safety_block.json()["status"] == "block"

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "demo.seeded" in actions or "demo.seed_verified" in actions
    assert "pipeline.started" in actions
    assert "pipeline.completed" in actions
    assert "report.generated" in actions

    agent_skills = client.get("/agent/skills")
    assert agent_skills.status_code == 200
    assert any(item["skill_name"] == "run_full_foldagent_case_review" for item in agent_skills.json())

    agent_dry_run = client.post(
        "/agent/tasks/dry-run",
        json={
            "case_id": case_id,
            "framework": "claude_code",
            "skill_name": "run_full_foldagent_case_review",
            "status": "pending",
        },
    )
    assert agent_dry_run.status_code == 200
    assert agent_dry_run.json()["dry_run"] is True

    agent_events = client.get("/agent/events")
    assert agent_events.status_code == 200
    body = agent_events.text
    assert "event: case.created" in body or "event: report.generated" in body
