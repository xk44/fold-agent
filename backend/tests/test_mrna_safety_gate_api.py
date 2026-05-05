from fastapi.testclient import TestClient


def test_mrna_gate_blocks_human_sequence_export_without_expert_mode(client: TestClient) -> None:
    response = client.post(
        "/safety/mrna-gate",
        json={
            "action": "export_sequence_package",
            "species_mode": "human",
            "is_export": True,
            "involves_sequence_data": True,
            "content": "AUGGCUACGUAGCUAGCUAG",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "block"
    assert body["blocked"] is True
    assert "Human mode" in body["reason"]



def test_mrna_gate_requires_approval_for_dog_sequence_access_without_expert_mode(client: TestClient) -> None:
    response = client.post(
        "/safety/mrna-gate",
        json={
            "action": "view_sequence_context",
            "species_mode": "dog",
            "involves_sequence_data": True,
            "content": "ATGGCCATTGTAATGGGCCGCTGAAAGGGTGCCCGATAG",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "requires_approval"
    assert body["needs_approval"] is True
    assert "expert mode" in body["reason"].lower()



def test_safety_preflight_uses_mrna_gate_reasoning(client: TestClient) -> None:
    response = client.post(
        "/safety/preflight",
        json={
            "action": "export_sequence_package",
            "species_mode": "human",
            "is_export": True,
            "involves_sequence_data": True,
            "content": "AUGGCUACGUAGCUAGCUAG",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "block"
    assert "Human mode" in body["reason"]
