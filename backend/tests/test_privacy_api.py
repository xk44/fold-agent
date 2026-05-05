"""Tests for Phase 3 privacy module endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _create_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "privacy test"})
    assert resp.status_code == 201
    return resp.json()["id"]


class TestCasePrivacySummary:
    def test_returns_privacy_summary(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/cases/{case_id}/privacy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["case_id"] == case_id
        assert "redaction_level" in body
        assert "consent_status" in body
        assert "encryption_at_rest" in body
        assert "retention_days" in body

    def test_404_for_missing_case(self, client: TestClient) -> None:
        resp = client.get("/cases/nonexistent/privacy")
        assert resp.status_code == 404


class TestCaseDataDirectory:
    def test_create_data_dir(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.post(f"/cases/{case_id}/data-dir")
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] is True
        assert case_id in body["path"]

    def test_list_data_files_empty(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/cases/{case_id}/data-files")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCloudUploadCheck:
    def test_cloud_disabled_by_default(self, client: TestClient) -> None:
        resp = client.get("/privacy/cloud-upload-check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is False
        assert "disabled" in body["reason"].lower()

    def test_cloud_check_with_backend(self, client: TestClient) -> None:
        resp = client.get("/privacy/cloud-upload-check?backend_name=alphafold_server")
        assert resp.status_code == 200
        body = resp.json()
        assert body["allowed"] is False


class TestRetentionPolicy:
    def test_no_expired_artifacts(self, client: TestClient) -> None:
        resp = client.get("/privacy/retention/expired")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAuditExport:
    def test_export_json(self, client: TestClient) -> None:
        _create_case(client)
        resp = client.get("/audit/export?format=json")
        assert resp.status_code == 200
        body = json.loads(resp.text)
        assert "audit_log" in body
        assert "exported_at" in body
        assert len(body["audit_log"]) > 0

    def test_export_markdown(self, client: TestClient) -> None:
        _create_case(client)
        resp = client.get("/audit/export?format=markdown")
        assert resp.status_code == 200
        assert "# FoldAgent Audit Log Export" in resp.text

    def test_export_filtered_by_case(self, client: TestClient) -> None:
        case_id = _create_case(client)
        resp = client.get(f"/audit/export?format=json&case_id={case_id}")
        assert resp.status_code == 200
        body = json.loads(resp.text)
        for entry in body["audit_log"]:
            assert entry["case_id"] == case_id
