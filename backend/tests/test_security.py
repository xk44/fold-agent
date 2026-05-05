"""Tests for FoldAgent security module and RBAC (Phase 19)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.app.rbac import Role, Permission, ROLE_PERMISSIONS, check_permission, get_role_permissions
from backend.app.security import (
    build_upload_confirmation,
    generate_sbom,
    scan_for_secrets,
    scan_skill_directory,
    verify_audit_chain,
    verify_data_deletion,
)


# ---------------------------------------------------------------------------
# SBOM
# ---------------------------------------------------------------------------

class TestSBOM:
    def test_sbom_returns_cyclonedx_structure(self) -> None:
        sbom = generate_sbom()
        assert sbom["bomFormat"] == "CycloneDX-lite"
        assert "components" in sbom
        assert "metadata" in sbom
        assert sbom["metadata"]["component"]["name"] == "foldagent"

    def test_sbom_has_components(self) -> None:
        sbom = generate_sbom()
        assert sbom["total_components"] > 0
        comp = sbom["components"][0]
        assert "name" in comp
        assert "version" in comp
        assert "license" in comp


# ---------------------------------------------------------------------------
# Secrets scanning
# ---------------------------------------------------------------------------

class TestSecretsScanning:
    def test_clean_text_passes(self) -> None:
        assert scan_for_secrets("Hello world, no secrets here.") == []

    def test_detects_aws_key(self) -> None:
        text = "aws_key = AKIAIOSFODNN7EXAMPLE"
        findings = scan_for_secrets(text)
        assert any(f["pattern_name"] == "aws_access_key" for f in findings)

    def test_detects_private_key(self) -> None:
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAK..."
        findings = scan_for_secrets(text)
        assert any(f["pattern_name"] == "private_key_header" for f in findings)

    def test_detects_github_token(self) -> None:
        text = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        findings = scan_for_secrets(text)
        assert any(f["pattern_name"] == "github_token" for f in findings)

    def test_detects_password(self) -> None:
        text = "password = 'my_super_secret_pw'"
        findings = scan_for_secrets(text)
        assert any(f["pattern_name"] == "password_in_text" for f in findings)

    def test_severity_is_present(self) -> None:
        text = "AKIAIOSFODNN7EXAMPLE"
        findings = scan_for_secrets(text)
        assert findings[0]["severity"] in {"critical", "high", "medium", "low"}

    def test_preview_truncated(self) -> None:
        findings = scan_for_secrets("AKIAIOSFODNN7EXAMPLE")
        assert len(findings[0]["matched_text_preview"]) <= 50


# ---------------------------------------------------------------------------
# Skill directory scanner
# ---------------------------------------------------------------------------

class TestSkillScanner:
    def test_nonexistent_path(self) -> None:
        result = scan_skill_directory("/nonexistent/path")
        assert result["safe"] is False
        assert result["findings"][0]["type"] == "error"

    def test_clean_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "SKILL.md").write_text("# Skill\nHello")
            result = scan_skill_directory(tmpdir)
            assert result["safe"] is True

    def test_detects_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "bad.py").write_text("import requests\nrequests.get('http://evil.com')")
            result = scan_skill_directory(tmpdir)
            assert any(f["type"] == "network_call" for f in result["findings"])

    def test_detects_hardcoded_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "conf.py").write_text("URL = 'https://some-long-service-url.example.com/api/v1'")
            result = scan_skill_directory(tmpdir)
            assert any(f["type"] == "hardcoded_url" for f in result["findings"])


# ---------------------------------------------------------------------------
# Upload confirmation
# ---------------------------------------------------------------------------

class TestUploadConfirmation:
    def test_basic_confirmation(self) -> None:
        result = build_upload_confirmation("lab-server", "3 VCF files")
        assert result["requires_explicit_consent"] is True
        assert result["destination"] == "lab-server"
        assert len(result["warnings"]) >= 4

    def test_cloud_backend_extra_warning(self) -> None:
        result = build_upload_confirmation("alphafold_server", "peptide sequence")
        assert any("cloud" in w.lower() for w in result["warnings"])

    def test_has_confirmation_id(self) -> None:
        result = build_upload_confirmation("dest", "data")
        assert len(result["confirmation_id"]) > 10


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

class TestRBAC:
    def test_admin_has_all_permissions(self) -> None:
        perms = get_role_permissions("admin")
        assert len(perms) == len(Permission)

    def test_readonly_limited(self) -> None:
        perms = get_role_permissions("readonly")
        assert "create_case" not in perms
        assert "view_cases" in perms

    def test_researcher_can_run_pipeline(self) -> None:
        assert check_permission("researcher", "run_pipeline") is True

    def test_readonly_cannot_delete(self) -> None:
        assert check_permission("readonly", "delete_case") is False

    def test_unknown_role_returns_false(self) -> None:
        assert check_permission("superadmin", "create_case") is False

    def test_unknown_permission_returns_false(self) -> None:
        assert check_permission("admin", "fly_to_moon") is False

    def test_reviewer_permissions(self) -> None:
        perms = get_role_permissions("reviewer")
        assert "view_cases" in perms
        assert "delete_case" not in perms
        assert "export_data" in perms


# ---------------------------------------------------------------------------
# Audit chain + deletion (DB-dependent, use client fixture)
# ---------------------------------------------------------------------------

class TestAuditChain:
    def test_empty_case_valid(self, client) -> None:
        resp = client.get("/security/audit-chain/nonexistent-case-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["total_entries"] == 0

    def test_case_with_audit_entries(self, client) -> None:
        case_resp = client.post("/cases", json={"species": "dog", "subject_id": "SEC-001"})
        case_id = case_resp.json()["id"]
        resp = client.get(f"/security/audit-chain/{case_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries"] >= 1


class TestDeletionVerification:
    def test_nonexistent_case_fully_deleted(self, client) -> None:
        resp = client.get("/security/deletion-check/nonexistent-id")
        assert resp.status_code == 200
        assert resp.json()["fully_deleted"] is True

    def test_existing_case_not_deleted(self, client) -> None:
        case_resp = client.post("/cases", json={"species": "dog", "subject_id": "SEC-002"})
        case_id = case_resp.json()["id"]
        resp = client.get(f"/security/deletion-check/{case_id}")
        data = resp.json()
        assert data["fully_deleted"] is False
        assert "cases" in data["remaining_records"]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestSecurityAPI:
    def test_sbom_endpoint(self, client) -> None:
        resp = client.get("/security/sbom")
        assert resp.status_code == 200
        assert resp.json()["bomFormat"] == "CycloneDX-lite"

    def test_scan_secrets_endpoint(self, client) -> None:
        resp = client.post("/security/scan-secrets", json={"text": "AKIAIOSFODNN7EXAMPLE"})
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_scan_secrets_clean(self, client) -> None:
        resp = client.post("/security/scan-secrets", json={"text": "just normal text"})
        assert resp.status_code == 200
        assert resp.json()["clean"] is True

    def test_scan_skill_endpoint(self, client) -> None:
        resp = client.post("/security/scan-skill", json={"path": "/nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["safe"] is False

    def test_upload_confirmation_endpoint(self, client) -> None:
        resp = client.post("/security/upload-confirmation", json={
            "destination": "alphafold_server",
            "data_summary": "peptide sequences",
        })
        assert resp.status_code == 200
        assert resp.json()["requires_explicit_consent"] is True

    def test_roles_endpoint(self, client) -> None:
        resp = client.get("/security/roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "admin" in data["roles"]
        assert "readonly" in data["roles"]

    def test_role_detail_endpoint(self, client) -> None:
        resp = client.get("/security/roles/researcher")
        assert resp.status_code == 200
        assert "run_pipeline" in resp.json()["permissions"]

    def test_role_unknown_404(self, client) -> None:
        resp = client.get("/security/roles/superadmin")
        assert resp.status_code == 404

    def test_check_permission_endpoint(self, client) -> None:
        resp = client.post("/security/check-permission", json={
            "role": "admin",
            "permission": "delete_case",
        })
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_check_permission_denied(self, client) -> None:
        resp = client.post("/security/check-permission", json={
            "role": "readonly",
            "permission": "delete_case",
        })
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False
