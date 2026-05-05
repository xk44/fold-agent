from fastapi.testclient import TestClient


def test_register_and_list_samples(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Synthetic sample case"},
    )
    case_id = create_case.json()["id"]

    create_sample = client.post(
        f"/cases/{case_id}/samples",
        json={
            "sample_type": "tumor",
            "file_paths": {"vcf": "/tmp/demo.vcf"},
            "checksum": "abc123",
            "source_lab": "Demo Lab",
        },
    )

    assert create_sample.status_code == 201
    sample = create_sample.json()
    assert sample["case_id"] == case_id
    assert sample["sample_type"] == "tumor"
    assert sample["file_paths"] == {"vcf": "/tmp/demo.vcf"}
    assert sample["checksum"] == "abc123"
    assert sample["source_lab"] == "Demo Lab"
    assert sample["id"]

    list_samples = client.get(f"/cases/{case_id}/samples")
    assert list_samples.status_code == 200
    samples = list_samples.json()
    assert len(samples) == 1
    assert samples[0]["id"] == sample["id"]

    checksum_response = client.get(f"/samples/{sample['id']}/checksum")
    assert checksum_response.status_code == 200
    checksum_payload = checksum_response.json()
    assert checksum_payload == {"sample_id": sample["id"], "checksum": "abc123"}


def test_register_sample_rejects_missing_case(client: TestClient) -> None:
    response = client.post(
        "/cases/missing-case/samples",
        json={"sample_type": "tumor"},
    )

    assert response.status_code == 404


def test_register_sample_rejects_invalid_sample_type(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Synthetic sample case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(
        f"/cases/{case_id}/samples",
        json={"sample_type": "plasma"},
    )

    assert response.status_code == 422
