from fastapi.testclient import TestClient


def test_download_saved_artifact_returns_file_content(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Artifact download case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    saved = client.post(f"/reports/{report['id']}/save?format=markdown").json()

    response = client.get(f"/artifacts/file?path={saved['path']}")
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert report["id"] in response.text or case_id in response.text


def test_download_artifact_rejects_path_outside_artifact_root(client: TestClient) -> None:
    response = client.get("/artifacts/file?path=/etc/passwd")

    assert response.status_code == 403
