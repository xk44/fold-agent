"""Tests for Compliance & Safety Infrastructure — Phase 24 Tier 1.

Covers:
  - IRB gate pass/fail, missing fields, enforce gate
  - HIPAA safeguard matrix completeness, PHI separation
  - Hash-chained audit: append, verify, tamper detection
  - Watermark injection (PDB + reports), verify_watermark
  - Credential attestation, mode access checks, expiration
  - GDPR residency enforcement, cloud backend blocking
  - All API endpoints via TestClient
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.compliance import (
    CLOUD_BACKENDS,
    HIPAA_SAFEGUARDS_MATRIX,
    LOCAL_BACKENDS,
    THERAPEUTIC_MODES,
    WATERMARK_TEXT,
    DataResidency,
    DataResidencyError,
    HashChainedAuditLog,
    HIPAAComplianceReport,
    IRBGateError,
    IRBSubmission,
    PHIFieldType,
    ProfessionalCredential,
    ResidencyConfig,
    WatermarkedOutput,
    _attestation_store,
    assess_hipaa_compliance,
    attest_credentials,
    audit_log,
    check_irb_readiness,
    check_mode_access,
    enforce_irb_gate,
    enforce_residency,
    get_residency_config,
    separate_phi_fields,
    verify_watermark,
    watermark_pdb,
    watermark_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_submission(**overrides) -> IRBSubmission:
    base = dict(
        institution="Test University",
        irb_protocol_number="IRB-2024-001",
        pi_name="Dr. Researcher",
        data_use_agreement_signed=True,
        human_subjects_approval=True,
    )
    base.update(overrides)
    return IRBSubmission(**base)


# ---------------------------------------------------------------------------
# Feature 1: IRB readiness gate
# ---------------------------------------------------------------------------


class TestIRBReadinessCheck:
    def test_valid_submission_passes(self) -> None:
        result = check_irb_readiness(_valid_submission())
        assert result.passed is True
        assert result.missing_requirements == []

    def test_missing_institution_fails(self) -> None:
        result = check_irb_readiness(_valid_submission(institution=""))
        assert result.passed is False
        assert any("institution" in m for m in result.missing_requirements)

    def test_missing_irb_protocol_fails(self) -> None:
        result = check_irb_readiness(_valid_submission(irb_protocol_number=""))
        assert result.passed is False
        assert any("IRB protocol" in m for m in result.missing_requirements)

    def test_missing_pi_name_fails(self) -> None:
        result = check_irb_readiness(_valid_submission(pi_name=""))
        assert result.passed is False
        assert any("principal investigator" in m for m in result.missing_requirements)

    def test_unsigned_dua_fails(self) -> None:
        result = check_irb_readiness(_valid_submission(data_use_agreement_signed=False))
        assert result.passed is False
        assert any("data use agreement" in m for m in result.missing_requirements)

    def test_missing_human_subjects_approval_fails(self) -> None:
        result = check_irb_readiness(_valid_submission(human_subjects_approval=False))
        assert result.passed is False
        assert any("human subjects" in m for m in result.missing_requirements)

    def test_multiple_missing_fields_all_listed(self) -> None:
        result = check_irb_readiness(
            _valid_submission(institution="", irb_protocol_number="", pi_name="")
        )
        assert result.passed is False
        assert len(result.missing_requirements) >= 3

    def test_result_has_timestamp(self) -> None:
        result = check_irb_readiness(_valid_submission())
        assert result.timestamp
        assert "T" in result.timestamp  # ISO format

    def test_result_institution_populated(self) -> None:
        result = check_irb_readiness(_valid_submission(institution="MIT"))
        assert result.institution == "MIT"

    def test_veterinary_auth_optional(self) -> None:
        result = check_irb_readiness(_valid_submission(veterinary_authorization=True))
        assert result.passed is True
        assert result.veterinary_authorization is True


class TestEnforceIRBGate:
    def test_valid_submission_does_not_raise(self) -> None:
        enforce_irb_gate(_valid_submission())  # Should not raise

    def test_none_submission_raises(self) -> None:
        with pytest.raises(IRBGateError):
            enforce_irb_gate(None)

    def test_invalid_submission_raises(self) -> None:
        with pytest.raises(IRBGateError) as exc_info:
            enforce_irb_gate(_valid_submission(institution="", human_subjects_approval=False))
        assert "IRB readiness check failed" in str(exc_info.value)

    def test_error_includes_missing_requirements(self) -> None:
        with pytest.raises(IRBGateError) as exc_info:
            enforce_irb_gate(_valid_submission(pi_name=""))
        assert "principal investigator" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Feature 2: HIPAA safeguards
# ---------------------------------------------------------------------------


class TestHIPAASafeguardsMatrix:
    def test_all_phi_types_have_safeguards(self) -> None:
        for phi_type in PHIFieldType:
            assert phi_type in HIPAA_SAFEGUARDS_MATRIX, f"Missing safeguard for {phi_type}"

    def test_restricted_fields_are_encrypted(self) -> None:
        for phi_type, safeguard in HIPAA_SAFEGUARDS_MATRIX.items():
            if safeguard.access_level == "restricted":
                assert safeguard.encrypted, f"{phi_type} restricted but not encrypted"

    def test_all_phi_fields_are_audit_logged(self) -> None:
        for phi_type, safeguard in HIPAA_SAFEGUARDS_MATRIX.items():
            assert safeguard.audit_logged, f"{phi_type} not audit-logged"

    def test_ssn_is_restricted(self) -> None:
        assert HIPAA_SAFEGUARDS_MATRIX[PHIFieldType.ssn].access_level == "restricted"

    def test_genomic_sequence_is_restricted(self) -> None:
        assert HIPAA_SAFEGUARDS_MATRIX[PHIFieldType.genomic_sequence].access_level == "restricted"

    def test_retention_days_positive(self) -> None:
        for phi_type, safeguard in HIPAA_SAFEGUARDS_MATRIX.items():
            assert safeguard.retention_days > 0, f"{phi_type} has non-positive retention"


class TestAssessHIPAACompliance:
    def test_no_phi_fields_is_compliant(self) -> None:
        report = assess_hipaa_compliance(["tumor_size", "mutation_type", "allele_frequency"])
        assert report.compliant is True
        assert report.violations == []

    def test_phi_field_detected(self) -> None:
        report = assess_hipaa_compliance(["ssn", "tumor_size"])
        assert len(report.safeguards) >= 1
        assert any(s.field_type == PHIFieldType.ssn for s in report.safeguards)

    def test_recognizes_field_aliases(self) -> None:
        report = assess_hipaa_compliance(["date_of_birth", "phone_number"])
        types = [s.field_type for s in report.safeguards]
        assert PHIFieldType.dob in types
        assert PHIFieldType.phone in types

    def test_returns_hipaa_compliance_report(self) -> None:
        report = assess_hipaa_compliance(["email"])
        assert isinstance(report, HIPAAComplianceReport)

    def test_empty_fields_list(self) -> None:
        report = assess_hipaa_compliance([])
        assert report.compliant is True


class TestSeparatePHIFields:
    def test_separates_phi_from_non_phi(self) -> None:
        record = {"ssn": "123-45-6789", "tumor_size": 3.5, "email": "x@y.com", "stage": "II"}
        phi, non_phi = separate_phi_fields(record)
        assert "ssn" in phi
        assert "email" in phi
        assert "tumor_size" in non_phi
        assert "stage" in non_phi

    def test_empty_record(self) -> None:
        phi, non_phi = separate_phi_fields({})
        assert phi == {}
        assert non_phi == {}

    def test_all_non_phi(self) -> None:
        record = {"binding_score": 0.9, "peptide": "ACDEF"}
        phi, non_phi = separate_phi_fields(record)
        assert phi == {}
        assert non_phi == record

    def test_all_phi(self) -> None:
        record = {"name": "Jane Doe", "mrn": "12345"}
        phi, non_phi = separate_phi_fields(record)
        assert "name" in phi
        assert "mrn" in phi
        assert non_phi == {}


# ---------------------------------------------------------------------------
# Feature 3: Hash-chained audit log
# ---------------------------------------------------------------------------


class TestHashChainedAuditLog:
    def setup_method(self) -> None:
        audit_log.clear()

    def test_append_returns_entry(self) -> None:
        entry = audit_log.append("test_action", "user1", {"detail": "x"})
        assert entry.action == "test_action"
        assert entry.user == "user1"
        assert entry.entry_id

    def test_first_entry_uses_genesis_hash(self) -> None:
        entry = audit_log.append("init", "system", {})
        assert entry.previous_hash == "0" * 64

    def test_second_entry_chains_to_first(self) -> None:
        e1 = audit_log.append("action1", "user", {})
        e2 = audit_log.append("action2", "user", {})
        assert e2.previous_hash == e1.entry_hash

    def test_verify_chain_empty(self) -> None:
        valid, errors = audit_log.verify_chain()
        assert valid is True
        assert errors == []

    def test_verify_chain_valid(self) -> None:
        audit_log.append("a", "u", {"k": 1})
        audit_log.append("b", "u", {"k": 2})
        audit_log.append("c", "u", {"k": 3})
        valid, errors = audit_log.verify_chain()
        assert valid is True
        assert errors == []

    def test_tamper_detection_hash_mutation(self) -> None:
        audit_log.append("real", "user", {"data": "original"})
        audit_log.append("second", "user", {})
        # Tamper the first entry's hash
        audit_log._chain[0].entry_hash = "deadbeef" * 8
        valid, errors = audit_log.verify_chain()
        assert valid is False
        assert len(errors) > 0

    def test_tamper_detection_details_mutation(self) -> None:
        audit_log.append("real", "user", {"data": "original"})
        # Mutate details after the fact
        audit_log._chain[0].details["data"] = "tampered"
        valid, errors = audit_log.verify_chain()
        assert valid is False

    def test_get_entries_all(self) -> None:
        audit_log.append("a", "u", {})
        audit_log.append("b", "u", {})
        entries = audit_log.get_entries()
        assert len(entries) == 2

    def test_get_entries_since(self) -> None:
        e1 = audit_log.append("old", "u", {})
        e2 = audit_log.append("new", "u", {})
        # Filter from e2's timestamp
        entries = audit_log.get_entries(since=e2.timestamp)
        assert any(e.action == "new" for e in entries)

    def test_export_chain(self) -> None:
        audit_log.append("export_test", "user", {"info": "x"})
        exported = audit_log.export_chain()
        assert len(exported) == 1
        assert exported[0]["action"] == "export_test"
        assert "entry_hash" in exported[0]
        assert "previous_hash" in exported[0]

    def test_singleton_behavior(self) -> None:
        log1 = HashChainedAuditLog()
        log2 = HashChainedAuditLog()
        assert log1 is log2

    def test_clear(self) -> None:
        audit_log.append("a", "u", {})
        audit_log.clear()
        assert audit_log.get_entries() == []


# ---------------------------------------------------------------------------
# Feature 4: Clinical use watermark
# ---------------------------------------------------------------------------


class TestWatermarkPDB:
    def test_watermark_injected(self) -> None:
        result = watermark_pdb("ATOM      1  N   ALA A   1\n")
        assert WATERMARK_TEXT in result.data

    def test_remark_lines_present(self) -> None:
        result = watermark_pdb("ATOM      1  N   ALA A   1\n")
        assert "REMARK" in result.data

    def test_original_data_preserved(self) -> None:
        pdb = "ATOM      1  N   ALA A   1\n"
        result = watermark_pdb(pdb)
        assert pdb in result.data

    def test_format_is_pdb(self) -> None:
        result = watermark_pdb("ATOM\n")
        assert result.format == "pdb"

    def test_watermark_hash_is_sha256(self) -> None:
        result = watermark_pdb("ATOM\n")
        assert len(result.watermark_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.watermark_hash)

    def test_machine_readable_metadata(self) -> None:
        result = watermark_pdb("ATOM\n")
        assert result.machine_readable_metadata["clinical_use_prohibited"] is True
        assert result.machine_readable_metadata["format"] == "pdb"

    def test_returns_watermarked_output(self) -> None:
        assert isinstance(watermark_pdb("ATOM\n"), WatermarkedOutput)


class TestWatermarkReport:
    def test_html_watermark_injected(self) -> None:
        result = watermark_report("<p>Report</p>", format="html")
        assert WATERMARK_TEXT in result.data

    def test_html_contains_machine_readable_metadata(self) -> None:
        result = watermark_report("<p>Report</p>", format="html")
        assert "FOLDAGENT_WATERMARK" in result.data or "foldagent-watermark" in result.data.lower()

    def test_text_watermark_injected(self) -> None:
        result = watermark_report("Report text", format="text")
        assert WATERMARK_TEXT in result.data

    def test_original_content_preserved(self) -> None:
        content = "<p>original content here</p>"
        result = watermark_report(content, format="html")
        assert content in result.data

    def test_watermark_field_set(self) -> None:
        result = watermark_report("x")
        assert result.watermark == WATERMARK_TEXT

    def test_default_format_html(self) -> None:
        result = watermark_report("x")
        assert result.format == "html"


class TestVerifyWatermark:
    def test_watermarked_pdb_passes(self) -> None:
        result = watermark_pdb("ATOM\n")
        assert verify_watermark(result.data) is True

    def test_watermarked_report_passes(self) -> None:
        result = watermark_report("text")
        assert verify_watermark(result.data) is True

    def test_unwatermarked_data_fails(self) -> None:
        assert verify_watermark("plain text without watermark") is False

    def test_empty_string_fails(self) -> None:
        assert verify_watermark("") is False


# ---------------------------------------------------------------------------
# Feature 5: Credential attestation
# ---------------------------------------------------------------------------


class TestCredentialAttestation:
    def setup_method(self) -> None:
        _attestation_store.clear()

    def test_attest_phd_unlocks_drug_discovery(self) -> None:
        att = attest_credentials("user1", ProfessionalCredential.phd, "MIT")
        assert "drug_discovery" in att.modes_unlocked

    def test_attest_md_unlocks_vaccine_design(self) -> None:
        att = attest_credentials("user2", ProfessionalCredential.md, "Harvard")
        assert "vaccine_design" in att.modes_unlocked

    def test_attest_student_unlocks_nothing_therapeutic(self) -> None:
        att = attest_credentials("user3", ProfessionalCredential.student, "State U")
        for mode in THERAPEUTIC_MODES:
            assert mode not in att.modes_unlocked

    def test_attest_stores_institution(self) -> None:
        att = attest_credentials("user4", ProfessionalCredential.phd, "Caltech")
        assert att.institution == "Caltech"

    def test_attest_optional_license_number(self) -> None:
        att = attest_credentials(
            "user5", ProfessionalCredential.md, "MGH", license_number="MD12345"
        )
        assert att.license_number == "MD12345"

    def test_attest_without_license_number(self) -> None:
        att = attest_credentials("user6", ProfessionalCredential.phd, "Stanford")
        assert att.license_number is None

    def test_attest_has_expiry(self) -> None:
        att = attest_credentials("user7", ProfessionalCredential.phd, "MIT")
        assert att.expires_at > att.attested_at

    def test_attest_expires_in_365_days(self) -> None:
        att = attest_credentials("user8", ProfessionalCredential.phd, "MIT")
        from datetime import datetime

        attested = datetime.fromisoformat(att.attested_at)
        expires = datetime.fromisoformat(att.expires_at)
        delta = expires - attested
        assert 364 <= delta.days <= 366


class TestCheckModeAccess:
    def setup_method(self) -> None:
        _attestation_store.clear()

    def test_non_therapeutic_mode_always_allowed(self) -> None:
        allowed, reason = check_mode_access("anyone", "neoantigen")
        assert allowed is True

    def test_no_attestation_blocks_therapeutic(self) -> None:
        allowed, reason = check_mode_access("no_attest_user", "drug_discovery")
        assert allowed is False
        assert "attestation" in reason.lower()

    def test_phd_can_access_drug_discovery(self) -> None:
        attest_credentials("phd_user", ProfessionalCredential.phd, "MIT")
        allowed, reason = check_mode_access("phd_user", "drug_discovery")
        assert allowed is True

    def test_student_cannot_access_gene_therapy(self) -> None:
        attest_credentials("student_user", ProfessionalCredential.student, "State U")
        allowed, reason = check_mode_access("student_user", "gene_therapy")
        assert allowed is False

    def test_reason_string_non_empty(self) -> None:
        attest_credentials("u", ProfessionalCredential.phd, "X")
        _, reason = check_mode_access("u", "vaccine_design")
        assert reason

    def test_dvm_unlocks_enzyme_engineering_based_on_matrix(self) -> None:
        # dvm is not in enzyme_engineering requirements per spec
        attest_credentials("dvm_user", ProfessionalCredential.dvm, "VetSchool")
        allowed, _ = check_mode_access("dvm_user", "enzyme_engineering")
        # dvm not in enzyme_engineering requirements
        assert allowed is False

    def test_all_therapeutic_modes_blocked_without_attestation(self) -> None:
        for mode in THERAPEUTIC_MODES:
            allowed, _ = check_mode_access("no_attest", mode)
            assert allowed is False


# ---------------------------------------------------------------------------
# Feature 6: GDPR data residency
# ---------------------------------------------------------------------------


class TestDataResidency:
    def test_local_only_blocks_cloud(self) -> None:
        config = get_residency_config(DataResidency.local_only)
        for backend in CLOUD_BACKENDS:
            assert backend in config.blocked_backends

    def test_local_only_allows_local_backends(self) -> None:
        config = get_residency_config(DataResidency.local_only)
        for backend in LOCAL_BACKENDS:
            assert backend in config.allowed_backends

    def test_unrestricted_allows_all(self) -> None:
        config = get_residency_config(DataResidency.unrestricted)
        assert config.blocked_backends == []
        for backend in CLOUD_BACKENDS:
            assert backend in config.allowed_backends

    def test_eu_only_blocks_non_eu_cloud(self) -> None:
        config = get_residency_config(DataResidency.eu_only)
        for backend in CLOUD_BACKENDS:
            assert backend in config.blocked_backends

    def test_residency_config_has_reason(self) -> None:
        for residency in DataResidency:
            config = get_residency_config(residency)
            assert config.reason

    def test_returns_residency_config(self) -> None:
        assert isinstance(get_residency_config(DataResidency.local_only), ResidencyConfig)


class TestEnforceResidency:
    def test_local_only_blocks_alphafold_server(self) -> None:
        with pytest.raises(DataResidencyError):
            enforce_residency("alphafold_server", DataResidency.local_only)

    def test_local_only_allows_mock(self) -> None:
        enforce_residency("mock", DataResidency.local_only)  # Should not raise

    def test_unrestricted_allows_alphafold_server(self) -> None:
        enforce_residency("alphafold_server", DataResidency.unrestricted)  # Should not raise

    def test_error_message_contains_backend_name(self) -> None:
        with pytest.raises(DataResidencyError) as exc_info:
            enforce_residency("alphafold_db", DataResidency.local_only)
        assert "alphafold_db" in str(exc_info.value)

    def test_eu_only_blocks_alphafold_db(self) -> None:
        with pytest.raises(DataResidencyError):
            enforce_residency("alphafold_db", DataResidency.eu_only)

    def test_local_only_allows_colabfold(self) -> None:
        enforce_residency("colabfold", DataResidency.local_only)  # Should not raise


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestIRBCheckEndpoint:
    def test_post_irb_check_pass(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/irb-check",
            json={
                "institution": "Test University",
                "irb_protocol_number": "IRB-001",
                "pi_name": "Dr. Test",
                "data_use_agreement_signed": True,
                "human_subjects_approval": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is True

    def test_post_irb_check_fail_missing_dua(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/irb-check",
            json={
                "institution": "Test University",
                "irb_protocol_number": "IRB-001",
                "pi_name": "Dr. Test",
                "data_use_agreement_signed": False,
                "human_subjects_approval": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] is False
        assert len(data["missing_requirements"]) > 0


class TestHIPAAAssessEndpoint:
    def test_post_hipaa_assess_no_phi(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/hipaa-assess", json={"data_fields": ["binding_score", "peptide_sequence"]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compliant"] is True

    def test_post_hipaa_assess_with_phi(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/hipaa-assess", json={"data_fields": ["ssn", "name", "binding_score"]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["safeguards"]) >= 2


class TestHIPAASeparatePHIEndpoint:
    def test_post_hipaa_separate_phi(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/hipaa-separate-phi",
            json={"record": {"ssn": "123", "binding_score": 0.9, "email": "x@y.com"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "ssn" in data["phi_fields"]
        assert "email" in data["phi_fields"]
        assert "binding_score" in data["non_phi_fields"]


class TestAuditEndpoints:
    def test_append_and_verify(self, client: TestClient) -> None:
        # Clear first
        audit_log.clear()
        resp = client.post(
            "/compliance/audit/append",
            json={
                "action": "test_action",
                "user": "test_user",
                "details": {"key": "value"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "test_action"

    def test_verify_chain_endpoint(self, client: TestClient) -> None:
        audit_log.clear()
        audit_log.append("init", "system", {})
        resp = client.get("/compliance/audit/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert "valid" in data

    def test_get_entries_endpoint(self, client: TestClient) -> None:
        audit_log.clear()
        audit_log.append("ev1", "user", {})
        audit_log.append("ev2", "user", {})
        resp = client.get("/compliance/audit/entries")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) >= 2


class TestWatermarkEndpoints:
    def test_post_watermark_pdb(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/watermark-pdb", json={"pdb_data": "ATOM      1  N   ALA A   1\n"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert WATERMARK_TEXT in data["data"]

    def test_post_watermark_report(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/watermark-report",
            json={
                "report_text": "<p>Research report</p>",
                "format": "html",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert WATERMARK_TEXT in data["data"]


class TestAttestationEndpoints:
    def setup_method(self) -> None:
        _attestation_store.clear()

    def test_post_attest_credentials(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/attest-credentials",
            json={
                "user_id": "api_user",
                "credential": "phd",
                "institution": "Test U",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "api_user"
        assert "drug_discovery" in data["modes_unlocked"]

    def test_post_check_mode_access_allowed(self, client: TestClient) -> None:
        attest_credentials("api_user2", ProfessionalCredential.phd, "MIT")
        resp = client.post(
            "/compliance/check-mode-access",
            json={
                "user_id": "api_user2",
                "mode": "drug_discovery",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True

    def test_post_check_mode_access_blocked(self, client: TestClient) -> None:
        resp = client.post(
            "/compliance/check-mode-access",
            json={
                "user_id": "unattest_user",
                "mode": "gene_therapy",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is False


class TestResidencyEndpoint:
    def test_get_residency_local_only(self, client: TestClient) -> None:
        resp = client.get("/compliance/residency/local_only")
        assert resp.status_code == 200
        data = resp.json()
        assert data["residency"] == "local_only"
        assert "alphafold_server" in data["blocked_backends"]

    def test_get_residency_unrestricted(self, client: TestClient) -> None:
        resp = client.get("/compliance/residency/unrestricted")
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked_backends"] == []

    def test_get_residency_eu_only(self, client: TestClient) -> None:
        resp = client.get("/compliance/residency/eu_only")
        assert resp.status_code == 200
        data = resp.json()
        assert data["residency"] == "eu_only"

    def test_get_residency_invalid_returns_422(self, client: TestClient) -> None:
        resp = client.get("/compliance/residency/invalid_level")
        assert resp.status_code == 422
