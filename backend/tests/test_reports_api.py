from fastapi.testclient import TestClient


def test_generate_candidate_review_report_and_fetch_it(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Report candidate case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(f"/cases/{case_id}/reports/candidate-review")
    assert response.status_code == 201
    report = response.json()
    assert report["case_id"] == case_id
    assert report["report_type"] == "candidate_review"
    assert report["safety_label"] == "Research candidate only — not administerable"
    assert "not medical advice" in report["content_text"].lower()

    fetch = client.get(f"/reports/{report['id']}")
    assert fetch.status_code == 200
    assert fetch.json()["id"] == report["id"]


def test_generate_ethics_package_report_and_audit_log(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "dog", "diagnosis_summary": "Ethics package case"},
    )
    case_id = create_case.json()["id"]

    response = client.post(f"/cases/{case_id}/reports/ethics-package")
    assert response.status_code == 201
    report = response.json()
    assert report["report_type"] == "ethics_package"
    assert "professional oversight" in report["content_text"].lower()

    list_response = client.get(f"/cases/{case_id}/reports")
    assert list_response.status_code == 200
    listed_reports = list_response.json()
    assert len(listed_reports) == 1
    assert listed_reports[0]["id"] == report["id"]

    markdown_export = client.get(f"/reports/{report['id']}/export?format=markdown")
    assert markdown_export.status_code == 200
    assert markdown_export.json()["format"] == "markdown"
    assert "professional oversight" in markdown_export.json()["content_text"].lower()

    json_export = client.get(f"/reports/{report['id']}/export?format=json")
    assert json_export.status_code == 200
    assert json_export.json()["format"] == "json"
    assert json_export.json()["content_json"]["species"] == "dog"

    audit = client.get(f"/audit/{case_id}")
    assert audit.status_code == 200
    actions = [entry["action"] for entry in audit.json()]
    assert "report.generated" in actions
    assert "report.exported" in actions


def test_generate_report_for_missing_case_returns_404(client: TestClient) -> None:
    response = client.post("/cases/missing-case/reports/candidate-review")

    assert response.status_code == 404


def test_report_export_rejects_unknown_format(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Export format case"},
    )
    case_id = create_case.json()["id"]
    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()

    response = client.get(f"/reports/{report['id']}/export?format=pdf")

    assert response.status_code == 422


def test_case_bundle_export_contains_case_audit_reports_and_pipeline(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Bundle export case"},
    )
    case_id = create_case.json()["id"]

    client.post(f"/cases/{case_id}/samples", json={"sample_type": "tumor", "checksum": "bundle123"})
    client.post(f"/cases/{case_id}/pipeline/run")
    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()

    response = client.get(f"/cases/{case_id}/bundle")
    assert response.status_code == 200
    bundle = response.json()

    assert bundle["case"]["id"] == case_id
    assert bundle["latest_pipeline_run"]["case_id"] == case_id
    assert len(bundle["reports"]) >= 1
    assert any(item["id"] == report["id"] for item in bundle["reports"])
    assert len(bundle["audit_log"]) >= 1
    assert len(bundle["samples"]) == 1
    assert bundle["safety_label"] == "Research candidate only — not administerable"

    markdown_bundle = client.get(f"/cases/{case_id}/bundle/export?format=markdown")
    assert markdown_bundle.status_code == 200
    assert markdown_bundle.json()["format"] == "markdown"
    markdown_text = markdown_bundle.json()["content_text"]
    assert case_id in markdown_text
    assert "Top candidate gene:" in markdown_text
    assert "KIT" in markdown_text
    assert "Latest report types:" in markdown_text
    assert "candidate_review" in markdown_text
    assert "Latest review statuses:" in markdown_text

    json_bundle = client.get(f"/cases/{case_id}/bundle/export?format=json")
    assert json_bundle.status_code == 200
    assert json_bundle.json()["format"] == "json"
    assert json_bundle.json()["content_json"]["case"]["id"] == case_id

    saved_report = client.post(f"/reports/{report['id']}/save?format=markdown")
    assert saved_report.status_code == 200
    report_artifact = saved_report.json()
    assert report_artifact["format"] == "markdown"
    assert report_artifact["path"].endswith(".md")

    saved_bundle = client.post(f"/cases/{case_id}/bundle/save?format=json")
    assert saved_bundle.status_code == 200
    bundle_artifact = saved_bundle.json()
    assert bundle_artifact["format"] == "json"
    assert bundle_artifact["path"].endswith(".json")

    audit = client.get(f"/audit/{case_id}")
    actions = [entry["action"] for entry in audit.json()]
    assert "bundle.exported" in actions
    assert "bundle.exported.readable" in actions
    assert "report.saved" in actions
    assert "bundle.saved" in actions
