"""Tests for artifact content hash integrity verification."""
import hashlib

from fastapi.testclient import TestClient


def test_saved_artifact_includes_content_hash(client: TestClient) -> None:
    """Saved artifacts should include a SHA-256 content_hash in their metadata."""
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Hash integrity case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    saved = client.post(f"/reports/{report['id']}/save?format=markdown").json()

    assert saved["content_hash"] is not None
    assert len(saved["content_hash"]) == 64  # SHA-256 hex digest length


def test_saved_bundle_includes_content_hash(client: TestClient) -> None:
    """Saved case bundles should include a SHA-256 content_hash."""
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Bundle hash case"},
    )
    case_id = create_case.json()["id"]

    saved = client.post(f"/cases/{case_id}/bundle/save?format=json").json()
    assert saved["content_hash"] is not None
    assert len(saved["content_hash"]) == 64


def test_download_artifact_succeeds_when_hash_matches(client: TestClient) -> None:
    """Download should succeed when on-disk content matches stored hash."""
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Hash match case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    saved = client.post(f"/reports/{report['id']}/save?format=markdown").json()

    response = client.get(f"/artifacts/file?path={saved['path']}")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]


def test_download_artifact_rejects_tampered_file(client: TestClient) -> None:
    """Download must return 409 when on-disk content no longer matches stored hash."""
    from pathlib import Path

    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Hash mismatch case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    saved = client.post(f"/reports/{report['id']}/save?format=markdown").json()

    # Tamper with the file on disk
    artifact_path = Path(saved["path"])
    original_content = artifact_path.read_text()
    tampered_content = original_content + "\nTAMPERED DATA INJECTED"
    artifact_path.write_text(tampered_content, encoding="utf-8")

    response = client.get(f"/artifacts/file?path={saved['path']}")
    assert response.status_code == 409
    assert "integrity" in response.json()["detail"].lower()
    assert "hash mismatch" in response.json()["detail"].lower()


def test_content_hash_is_correct_sha256(client: TestClient) -> None:
    """Verify that the stored content_hash is the actual SHA-256 of the file content."""
    from pathlib import Path

    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Hash verification case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    saved = client.post(f"/reports/{report['id']}/save?format=markdown").json()

    artifact_path = Path(saved["path"])
    disk_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert saved["content_hash"] == disk_hash


def test_list_artifacts_includes_content_hash(client: TestClient) -> None:
    """Artifacts listed for a case should include the content_hash field."""
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "List hash case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    client.post(f"/reports/{report['id']}/save?format=markdown")

    response = client.get(f"/cases/{case_id}/artifacts")
    assert response.status_code == 200
    artifacts = response.json()
    assert len(artifacts) >= 1
    for artifact in artifacts:
        assert "content_hash" in artifact
        assert artifact["content_hash"] is not None
        assert len(artifact["content_hash"]) == 64
