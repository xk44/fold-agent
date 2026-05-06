from fastapi.testclient import TestClient


def test_safety_preflight_endpoint_blocks_unsafe_content(client: TestClient) -> None:
    response = client.post(
        "/safety/preflight",
        json={
            "action": "generate_report",
            "species_mode": "demo",
            "content": "This includes an injection instruction and dosing schedule.",
            "is_export": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "block"
    assert body["allowed"] is False
    assert body["blocked_patterns"]


def test_safety_preflight_endpoint_requires_approval_for_external_upload(
    client: TestClient,
) -> None:
    response = client.post(
        "/safety/preflight",
        json={
            "action": "submit_alphafold_job",
            "species_mode": "demo",
            "involves_external_upload": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_approval"
    assert body["needs_approval"] is True
    assert "External data upload" in body["reason"]


def test_safety_preflight_endpoint_rejects_invalid_mode(client: TestClient) -> None:
    response = client.post(
        "/safety/preflight",
        json={
            "action": "generate_report",
            "species_mode": "cat",
        },
    )

    assert response.status_code == 422
