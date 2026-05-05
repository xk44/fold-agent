from fastapi.testclient import TestClient


def test_case_crud_flow(client: TestClient) -> None:
    create_response = client.post(
        "/cases",
        json={
            "species": "demo",
            "diagnosis_summary": "Synthetic mast cell tumor case",
            "supervising_professional": "Dr. Demo",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["species"] == "demo"
    assert created["diagnosis_summary"] == "Synthetic mast cell tumor case"
    assert created["supervising_professional"] == "Dr. Demo"
    assert created["consent_status"] == "pending"
    assert created["review_status"] == "unreviewed"
    assert created["id"]

    list_response = client.get("/cases")
    assert list_response.status_code == 200
    cases = list_response.json()
    assert any(case["id"] == created["id"] for case in cases)

    get_response = client.get(f"/cases/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]

    patch_response = client.patch(
        f"/cases/{created['id']}",
        json={"review_status": "needs_data", "consent_status": "received"},
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["review_status"] == "needs_data"
    assert updated["consent_status"] == "received"


def test_get_missing_case_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case-id")

    assert response.status_code == 404


def test_create_case_rejects_invalid_species(client: TestClient) -> None:
    response = client.post(
        "/cases",
        json={"species": "cat", "diagnosis_summary": "invalid species"},
    )

    assert response.status_code == 422



def test_patch_case_rejects_null_for_required_fields(client: TestClient) -> None:
    create_response = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Synthetic review case"},
    )
    case_id = create_response.json()["id"]

    response = client.patch(
        f"/cases/{case_id}",
        json={"consent_status": None},
    )

    assert response.status_code == 422
