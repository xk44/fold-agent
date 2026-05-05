from fastapi.testclient import TestClient


def test_subject_crud_and_case_bundle_linkage(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "dog", "diagnosis_summary": "Subject linkage case"},
    )
    case_id = create_case.json()["id"]

    create_subject = client.post(
        f"/cases/{case_id}/subjects",
        json={
            "anonymized_display_name": "Rosie-demo",
            "metadata_json": {"age_years": 9, "species": "dog"},
            "privacy_flags": {"redacted": True},
        },
    )
    assert create_subject.status_code == 201
    subject = create_subject.json()
    assert subject["case_id"] == case_id
    assert subject["anonymized_display_name"] == "Rosie-demo"

    list_subjects = client.get(f"/cases/{case_id}/subjects")
    assert list_subjects.status_code == 200
    subjects = list_subjects.json()
    assert len(subjects) == 1
    assert subjects[0]["id"] == subject["id"]

    bundle = client.get(f"/cases/{case_id}/bundle").json()
    assert len(bundle["subjects"]) == 1
    assert bundle["subjects"][0]["id"] == subject["id"]


def test_subject_creation_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.post(
        "/cases/missing-case/subjects",
        json={"anonymized_display_name": "Ghost"},
    )

    assert response.status_code == 404
