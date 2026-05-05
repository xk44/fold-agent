from fastapi.testclient import TestClient


def test_register_sample_with_subject_linkage(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "dog", "diagnosis_summary": "Sample subject linkage case"},
    )
    case_id = create_case.json()["id"]

    create_subject = client.post(
        f"/cases/{case_id}/subjects",
        json={
            "anonymized_display_name": "Rosie-demo",
            "metadata_json": {"species": "dog"},
        },
    )
    subject_id = create_subject.json()["id"]

    create_sample = client.post(
        f"/cases/{case_id}/samples",
        json={
            "subject_id": subject_id,
            "sample_type": "tumor",
            "file_paths": {"fastq": "/tmp/demo.fastq.gz"},
            "checksum": "subject123",
        },
    )
    assert create_sample.status_code == 201
    sample = create_sample.json()
    assert sample["case_id"] == case_id
    assert sample["subject_id"] == subject_id

    list_samples = client.get(f"/cases/{case_id}/samples")
    assert list_samples.status_code == 200
    samples = list_samples.json()
    assert len(samples) == 1
    assert samples[0]["subject_id"] == subject_id


def test_register_sample_rejects_subject_from_other_case(client: TestClient) -> None:
    case_a = client.post("/cases", json={"species": "demo", "diagnosis_summary": "case a"}).json()["id"]
    case_b = client.post("/cases", json={"species": "demo", "diagnosis_summary": "case b"}).json()["id"]

    subject_id = client.post(
        f"/cases/{case_a}/subjects",
        json={"anonymized_display_name": "Cross-case subject"},
    ).json()["id"]

    response = client.post(
        f"/cases/{case_b}/samples",
        json={"subject_id": subject_id, "sample_type": "tumor"},
    )

    assert response.status_code == 404
