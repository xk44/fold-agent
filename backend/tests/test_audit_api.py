from fastapi.testclient import TestClient


def test_case_and_sample_actions_are_audit_logged(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Audit case"},
    )
    case_id = create_case.json()["id"]

    update_case = client.patch(
        f"/cases/{case_id}",
        json={"review_status": "needs_data"},
    )
    assert update_case.status_code == 200

    create_sample = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "tumor", "checksum": "audit123"},
    )
    assert create_sample.status_code == 201

    audit_response = client.get(f"/audit/{case_id}")
    assert audit_response.status_code == 200
    entries = audit_response.json()

    actions = [entry["action"] for entry in entries]
    assert "case.created" in actions
    assert "case.updated" in actions
    assert "sample.registered" in actions or "sample.uploaded" in actions
    assert all(entry["case_id"] == case_id for entry in entries)


def test_safety_preflight_is_audit_logged_without_case_id(client: TestClient) -> None:
    response = client.post(
        "/safety/preflight",
        json={
            "action": "submit_alphafold_job",
            "species_mode": "demo",
            "involves_external_upload": True,
        },
    )
    assert response.status_code == 200

    audit_response = client.get("/audit/system")
    assert audit_response.status_code == 200
    entries = audit_response.json()

    matching = [entry for entry in entries if entry["action"] == "safety.preflight"]
    assert matching
    assert matching[0]["case_id"] is None
    assert matching[0]["safety_gate_result"] == "requires_approval"
