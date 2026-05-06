"""Tests for Phase 10 lab coordination endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "lab coord test"})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestChecklists:
    def test_get_checklists(self, client: TestClient) -> None:
        resp = client.get("/lab/checklists")
        assert resp.status_code == 200
        body = resp.json()
        assert "sequencing_provider" in body
        assert "rna_manufacturing" in body
        assert "secure_handoff" in body
        assert "email_privacy_warning" in body
        assert len(body["sequencing_provider"]) > 0

    def test_university_outreach_template(self, client: TestClient) -> None:
        resp = client.get("/lab/templates/university-outreach")
        assert resp.status_code == 200
        assert "Research Collaboration" in resp.json()["template"]


class TestOutreachEmail:
    def test_draft_email(self, client: TestClient) -> None:
        resp = client.post(
            "/lab/templates/outreach-email",
            json={
                "service_type": "WES sequencing",
                "contact_name": "Dr. Smith",
                "species": "dog",
                "case_id": "test-123",
                "diagnosis_summary": "Canine melanoma",
                "service_description": "Whole-exome sequencing of tumor/normal pair",
                "sender_name": "Test Researcher",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "Dr. Smith" in body["email_draft"]
        assert "privacy_warning" in body


class TestLabContacts:
    def test_create_and_list_contacts(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.post(
            f"/cases/{case_id}/lab/contacts",
            json={
                "name": "Dr. Jane Doe",
                "role": "Veterinary Oncologist",
                "organization": "Pet Hospital",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Dr. Jane Doe"

        contacts = client.get(f"/cases/{case_id}/lab/contacts").json()
        assert len(contacts) == 1
        assert contacts[0]["role"] == "Veterinary Oncologist"


class TestCostTracker:
    def test_create_and_summarize_costs(self, client: TestClient) -> None:
        case_id = _create_case(client)
        client.post(
            f"/cases/{case_id}/lab/costs",
            json={
                "category": "Sequencing",
                "description": "WES tumor/normal",
                "amount_cents": 150000,
            },
        )
        client.post(
            f"/cases/{case_id}/lab/costs",
            json={
                "category": "Structure",
                "description": "AlphaFold compute",
                "amount_cents": 5000,
            },
        )
        summary = client.get(f"/cases/{case_id}/lab/costs").json()
        assert summary["total_cents"] == 155000
        assert summary["entry_count"] == 2
        assert "Sequencing" in summary["by_category"]


class TestTimeline:
    def test_create_and_list_timeline(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.post(
            f"/cases/{case_id}/lab/timeline",
            json={
                "title": "Submit samples to sequencing lab",
                "owner": "PI",
                "status": "pending",
            },
        )
        assert resp.status_code == 200

        entries = client.get(f"/cases/{case_id}/lab/timeline").json()
        assert len(entries) == 1
        assert entries[0]["title"] == "Submit samples to sequencing lab"


class TestDocumentRequests:
    def test_create_and_list_requests(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.post(
            f"/cases/{case_id}/lab/document-requests",
            json={
                "document_type": "Veterinary consent form",
                "requested_from": "Dr. Doe",
            },
        )
        assert resp.status_code == 200

        requests = client.get(f"/cases/{case_id}/lab/document-requests").json()
        assert len(requests) == 1
        assert requests[0]["document_type"] == "Veterinary consent form"


class TestSummaryPacket:
    def test_summary_packet(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/cases/{case_id}/lab/summary-packet")
        assert resp.status_code == 200
        body = resp.json()
        assert body["case_id"] == case_id
        assert "privacy_warning" in body
        assert "disclaimer" in body
