from fastapi.testclient import TestClient


def test_candidate_review_report_contains_structured_sections(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Structured report case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    content = report["content_json"]

    assert content["candidate_table"]
    assert isinstance(content["candidate_table"], list)
    assert content["candidate_table"][0]["gene"]
    assert "missing_data_checklist" in content
    assert content["missing_data_checklist"]
    assert "tool_versions" in content
    assert content["tool_versions"]
    assert "safety_labels" in content
    assert content["safety_labels"]
    assert content["review_status"] == "unreviewed"


def test_candidate_review_markdown_export_contains_expert_style_sections(
    client: TestClient,
) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Markdown report case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/candidate-review").json()
    markdown = client.get(f"/reports/{report['id']}/export?format=markdown").json()["content_text"]

    assert "## Candidate antigens" in markdown
    assert "## Missing data checklist" in markdown
    assert "## Tool versions" in markdown
    assert "## Safety labels" in markdown
    assert "## Review status" in markdown
