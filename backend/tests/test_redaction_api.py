"""Tests for case data deletion and redaction workflow.

Covers POST /cases/{id}/redact, DELETE /cases/{id}, and POST /cases/{id}/subjects/{sid}/redact
endpoints that apply redaction levels, scramble PII, and log to audit.
"""

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_demo_case(client: TestClient) -> str:
    response = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Redaction test case"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_subject(client: TestClient, case_id: str, name: str = "Test-Subject") -> str:
    response = client.post(
        f"/cases/{case_id}/subjects",
        json={
            "anonymized_display_name": name,
            "metadata_json": {"species": "dog", "intake_notes": "Private info here"},
            "privacy_flags": {"redacted": False},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_sample(client: TestClient, case_id: str, subject_id: str | None = None) -> str:
    payload = {"sample_type": "tumor", "source_lab": "Lab-A"}
    if subject_id:
        payload["subject_id"] = subject_id
    response = client.post(
        f"/cases/{case_id}/samples",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()["id"]


# ---------------------------------------------------------------------------
# Case-level redaction
# ---------------------------------------------------------------------------

class TestCaseRedaction:
    """Tests for POST /cases/{id}/redact."""

    def test_redact_case_to_deidentify_level(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        subject_id = _create_subject(client, case_id)
        _create_sample(client, case_id, subject_id=subject_id)

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "deidentify", "confirm": True, "reason": "GDPR compliance"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["case_id"] == case_id
        assert body["redaction_level"] == "deidentify"
        assert body["subjects_updated"] >= 1

        # Verify case redaction_level set
        case_response = client.get(f"/cases/{case_id}")
        assert case_response.json()["redaction_level"] == "deidentify"

        # Verify subject redaction_level set
        subjects = client.get(f"/cases/{case_id}/subjects").json()
        assert subjects[0]["redaction_level"] == "deidentify"

        # Verify audit log entry
        audit_response = client.get(f"/audit/{case_id}")
        actions = [e["action"] for e in audit_response.json()]
        assert "case.redacted" in actions

    def test_redact_case_to_anonymous_level(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        _create_subject(client, case_id, name="Sensitive Name")

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "anonymous", "confirm": True, "reason": "Anonymisation"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["redaction_level"] == "anonymous"

        subjects = client.get(f"/cases/{case_id}/subjects").json()
        assert subjects[0]["redaction_level"] == "anonymous"
        # anonymous replaces display name
        assert subjects[0]["anonymized_display_name"] != "Sensitive Name"

    def test_redact_case_requires_confirm(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "deidentify", "confirm": False},
        )
        assert response.status_code == 400
        assert "confirm" in response.json()["detail"].lower() or "confirmation" in response.json()["detail"].lower()

    def test_redact_case_rejects_invalid_level(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "invalid_level", "confirm": True},
        )
        assert response.status_code == 422

    def test_redact_missing_case_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/cases/nonexistent-case-id/redact",
            json={"redaction_level": "deidentify", "confirm": True},
        )
        assert response.status_code == 404

    def test_redact_case_logs_reason_in_audit(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "deidentify", "confirm": True, "reason": "Data minimisation"},
        )
        assert response.status_code == 200

        audit_response = client.get(f"/audit/{case_id}")
        entries = audit_response.json()
        redact_entries = [e for e in entries if e["action"] == "case.redacted"]
        assert len(redact_entries) >= 1
        assert redact_entries[0]["details"]["reason"] == "Data minimisation"
        assert redact_entries[0]["details"]["redaction_level"] == "deidentify"

    def test_redact_case_to_deleted_marks_soft_delete(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        _create_subject(client, case_id)

        response = client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "deleted", "confirm": True, "reason": "Right to erasure"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["redaction_level"] == "deleted"

        case_data = client.get(f"/cases/{case_id}").json()
        assert case_data["redaction_level"] == "deleted"

    def test_redact_case_deidentify_scrambles_subject_names(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        _create_subject(client, case_id, name="Original Patient Name")

        client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "deidentify", "confirm": True},
        )

        subjects = client.get(f"/cases/{case_id}/subjects").json()
        # Display name should be replaced with a deidentified placeholder
        assert subjects[0]["anonymized_display_name"] != "Original Patient Name"
        assert subjects[0]["anonymized_display_name"].startswith("REDACTED-")

    def test_redact_case_anonymous_clears_metadata_and_privacy(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        _create_subject(client, case_id)

        client.post(
            f"/cases/{case_id}/redact",
            json={"redaction_level": "anonymous", "confirm": True},
        )

        subjects = client.get(f"/cases/{case_id}/subjects").json()
        # metadata_json and privacy_flags should be cleared
        assert subjects[0]["metadata_json"] is None or subjects[0]["metadata_json"] == {}
        assert subjects[0]["privacy_flags"] is None or subjects[0]["privacy_flags"] == {}


# ---------------------------------------------------------------------------
# Subject-level redaction
# ---------------------------------------------------------------------------

class TestSubjectRedaction:
    """Tests for POST /cases/{id}/subjects/{sid}/redact."""

    def test_redact_subject_to_deidentify(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        subject_id = _create_subject(client, case_id)

        response = client.post(
            f"/cases/{case_id}/subjects/{subject_id}/redact",
            json={"redaction_level": "deidentify", "confirm": True, "reason": "Subject request"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject_id"] == subject_id
        assert body["redaction_level"] == "deidentify"

        subjects = client.get(f"/cases/{case_id}/subjects").json()
        assert subjects[0]["redaction_level"] == "deidentify"

    def test_redact_subject_requires_confirm(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        subject_id = _create_subject(client, case_id)

        response = client.post(
            f"/cases/{case_id}/subjects/{subject_id}/redact",
            json={"redaction_level": "deidentify", "confirm": False},
        )
        assert response.status_code == 400

    def test_redact_missing_subject_returns_404(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.post(
            f"/cases/{case_id}/subjects/nonexistent/redact",
            json={"redaction_level": "deidentify", "confirm": True},
        )
        assert response.status_code == 404

    def test_redact_subject_logs_to_audit(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        subject_id = _create_subject(client, case_id)

        response = client.post(
            f"/cases/{case_id}/subjects/{subject_id}/redact",
            json={"redaction_level": "anonymous", "confirm": True},
        )
        assert response.status_code == 200

        audit_response = client.get(f"/audit/{case_id}")
        entries = audit_response.json()
        sub_redacts = [e for e in entries if e["action"] == "subject.redacted"]
        assert len(sub_redacts) >= 1


# ---------------------------------------------------------------------------
# Case deletion
# ---------------------------------------------------------------------------

class TestCaseDeletion:
    """Tests for DELETE /cases/{id}."""

    def test_delete_case_soft_deletes_and_audits(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.delete(
            f"/cases/{case_id}",
            params={"confirm": True, "reason": "Right to erasure"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["case_id"] == case_id
        assert body["deleted"] is True

        # Case should still exist but marked as deleted redaction level
        case_data = client.get(f"/cases/{case_id}").json()
        assert case_data["redaction_level"] == "deleted"

        audit_response = client.get(f"/audit/{case_id}")
        actions = [e["action"] for e in audit_response.json()]
        assert "case.deleted" in actions

    def test_delete_case_requires_confirm(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.delete(
            f"/cases/{case_id}",
            params={"confirm": False},
        )
        assert response.status_code == 400

    def test_delete_missing_case_returns_404(self, client: TestClient) -> None:
        response = client.delete(
            "/cases/nonexistent-id",
            params={"confirm": True},
        )
        assert response.status_code == 404

    def test_delete_case_hard_delete_option(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)

        response = client.delete(
            f"/cases/{case_id}",
            params={"confirm": True, "hard_delete": True, "reason": "Purge test data"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True

        # Hard delete: case should no longer be fetchable
        get_response = client.get(f"/cases/{case_id}")
        assert get_response.status_code == 404

    def test_case_read_includes_redaction_level_default(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        case_data = client.get(f"/cases/{case_id}").json()
        assert case_data["redaction_level"] == "full"

    def test_subject_read_includes_redaction_level_default(self, client: TestClient) -> None:
        case_id = _create_demo_case(client)
        _create_subject(client, case_id)
        subjects = client.get(f"/cases/{case_id}/subjects").json()
        assert subjects[0]["redaction_level"] == "full"