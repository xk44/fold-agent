from fastapi.testclient import TestClient


def test_ethics_package_report_contains_structured_sections(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "dog", "diagnosis_summary": "Ethics structured case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/ethics-package").json()
    content = report["content_json"]

    assert content["consent_templates"]
    assert content["privacy_notices"]
    assert content["risk_benefit_summary"]
    assert content["professional_oversight_checklist"]
    assert content["jurisdiction_warning"]


def test_ethics_package_markdown_export_contains_expert_style_sections(client: TestClient) -> None:
    create_case = client.post(
        "/cases",
        json={"species": "human", "diagnosis_summary": "Ethics markdown case"},
    )
    case_id = create_case.json()["id"]

    report = client.post(f"/cases/{case_id}/reports/ethics-package").json()
    markdown = client.get(f"/reports/{report['id']}/export?format=markdown").json()["content_text"]

    assert "## Consent templates" in markdown
    assert "## Privacy notices" in markdown
    assert "## Risk and benefit summary" in markdown
    assert "## Professional oversight checklist" in markdown
    assert "## Jurisdiction warning" in markdown
