from fastapi.testclient import TestClient


def test_list_artifacts_for_case_returns_saved_report_and_bundle(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Artifact browser case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    client.post(f"/reports/{report['id']}/save?format=markdown")
    client.post(f"/cases/{case_id}/bundle/save?format=json")

    response = client.get(f"/cases/{case_id}/artifacts")
    assert response.status_code == 200
    artifacts = response.json()

    assert len(artifacts) == 2
    artifact_types = {artifact["artifact_type"] for artifact in artifacts}
    assert artifact_types == {"report", "bundle"}
    assert all(artifact["id"] for artifact in artifacts)
    assert all(artifact["case_id"] == case_id for artifact in artifacts)
    assert all(artifact["filename"] for artifact in artifacts)
    assert all(
        artifact["download_url"].startswith("/artifacts/file?path=") for artifact in artifacts
    )
    assert all(artifact["file_size"] > 0 for artifact in artifacts)
    assert all(artifact["saved_at"] for artifact in artifacts)
    assert {artifact["mime_type"] for artifact in artifacts} == {
        "application/json",
        "text/markdown; charset=utf-8",
    }


def test_list_artifacts_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.get("/cases/missing-case/artifacts")

    assert response.status_code == 404
