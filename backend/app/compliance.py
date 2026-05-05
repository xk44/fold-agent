"""Compliance & Safety Infrastructure — Phase 24 Tier 1

Mandatory IRB gates, HIPAA safeguards, hash-chained audit logs,
clinical-use watermarks, credential attestation, and GDPR data residency.

RESEARCH USE ONLY. This module enforces programmatic safety controls
beyond simple disclaimers.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class IRBGateError(Exception):
    """Raised when IRB readiness check fails and human-sequence job cannot proceed."""


class DataResidencyError(Exception):
    """Raised when a requested backend violates the configured data residency policy."""


# ---------------------------------------------------------------------------
# Feature 1: IRB readiness gate
# ---------------------------------------------------------------------------


@dataclass
class IRBSubmission:
    institution: str
    irb_protocol_number: str
    pi_name: str
    data_use_agreement_signed: bool
    human_subjects_approval: bool
    veterinary_authorization: Optional[bool] = None


@dataclass
class IRBReadinessCheck:
    passed: bool
    institution: Optional[str]
    irb_protocol: Optional[str]
    data_use_agreement: bool
    human_subjects: bool
    veterinary_authorization: bool
    missing_requirements: list[str]
    timestamp: str


def check_irb_readiness(submission: IRBSubmission) -> IRBReadinessCheck:
    """Validate all required IRB fields and return a pass/fail readiness check."""
    missing: list[str] = []

    if not submission.institution or not submission.institution.strip():
        missing.append("institution name is required")
    if not submission.irb_protocol_number or not submission.irb_protocol_number.strip():
        missing.append("IRB protocol number is required")
    if not submission.pi_name or not submission.pi_name.strip():
        missing.append("principal investigator name is required")
    if not submission.data_use_agreement_signed:
        missing.append("data use agreement must be signed")
    if not submission.human_subjects_approval:
        missing.append("human subjects approval is required for human-sequence jobs")

    passed = len(missing) == 0
    return IRBReadinessCheck(
        passed=passed,
        institution=submission.institution if submission.institution.strip() else None,
        irb_protocol=submission.irb_protocol_number if submission.irb_protocol_number.strip() else None,
        data_use_agreement=submission.data_use_agreement_signed,
        human_subjects=submission.human_subjects_approval,
        veterinary_authorization=submission.veterinary_authorization or False,
        missing_requirements=missing,
        timestamp=datetime.now(UTC).isoformat(),
    )


def enforce_irb_gate(submission: Optional[IRBSubmission]) -> None:
    """Raise IRBGateError if the IRB readiness check fails.

    This is a hard gate — not a disclaimer. No submission proceeds without passing.
    """
    if submission is None:
        raise IRBGateError(
            "IRB submission is required before human-sequence job submission. "
            "Provide institution, IRB protocol number, PI name, signed DUA, and human subjects approval."
        )
    result = check_irb_readiness(submission)
    if not result.passed:
        raise IRBGateError(
            f"IRB readiness check failed. Missing requirements: {result.missing_requirements}"
        )


# ---------------------------------------------------------------------------
# Feature 2: HIPAA safeguards
# ---------------------------------------------------------------------------


class PHIFieldType(str, Enum):
    name = "name"
    mrn = "mrn"
    dob = "dob"
    ssn = "ssn"
    address = "address"
    phone = "phone"
    email = "email"
    genomic_sequence = "genomic_sequence"
    diagnosis = "diagnosis"
    provider = "provider"


@dataclass
class HIPAASafeguard:
    field_type: PHIFieldType
    access_level: str  # "restricted" | "need_to_know" | "public"
    encrypted: bool
    audit_logged: bool
    retention_days: int


HIPAA_SAFEGUARDS_MATRIX: dict[PHIFieldType, HIPAASafeguard] = {
    PHIFieldType.name: HIPAASafeguard(
        field_type=PHIFieldType.name,
        access_level="need_to_know",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,  # 7 years
    ),
    PHIFieldType.mrn: HIPAASafeguard(
        field_type=PHIFieldType.mrn,
        access_level="restricted",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.dob: HIPAASafeguard(
        field_type=PHIFieldType.dob,
        access_level="restricted",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.ssn: HIPAASafeguard(
        field_type=PHIFieldType.ssn,
        access_level="restricted",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.address: HIPAASafeguard(
        field_type=PHIFieldType.address,
        access_level="need_to_know",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.phone: HIPAASafeguard(
        field_type=PHIFieldType.phone,
        access_level="need_to_know",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.email: HIPAASafeguard(
        field_type=PHIFieldType.email,
        access_level="need_to_know",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.genomic_sequence: HIPAASafeguard(
        field_type=PHIFieldType.genomic_sequence,
        access_level="restricted",
        encrypted=True,
        audit_logged=True,
        retention_days=3650,  # 10 years for genomic data
    ),
    PHIFieldType.diagnosis: HIPAASafeguard(
        field_type=PHIFieldType.diagnosis,
        access_level="restricted",
        encrypted=True,
        audit_logged=True,
        retention_days=2555,
    ),
    PHIFieldType.provider: HIPAASafeguard(
        field_type=PHIFieldType.provider,
        access_level="need_to_know",
        encrypted=False,
        audit_logged=True,
        retention_days=2555,
    ),
}

# Canonical field name aliases that map to PHIFieldType values
_PHI_FIELD_ALIASES: dict[str, PHIFieldType] = {
    "name": PHIFieldType.name,
    "patient_name": PHIFieldType.name,
    "full_name": PHIFieldType.name,
    "first_name": PHIFieldType.name,
    "last_name": PHIFieldType.name,
    "mrn": PHIFieldType.mrn,
    "medical_record_number": PHIFieldType.mrn,
    "dob": PHIFieldType.dob,
    "date_of_birth": PHIFieldType.dob,
    "birthdate": PHIFieldType.dob,
    "ssn": PHIFieldType.ssn,
    "social_security_number": PHIFieldType.ssn,
    "address": PHIFieldType.address,
    "street_address": PHIFieldType.address,
    "zip_code": PHIFieldType.address,
    "postal_code": PHIFieldType.address,
    "phone": PHIFieldType.phone,
    "phone_number": PHIFieldType.phone,
    "telephone": PHIFieldType.phone,
    "email": PHIFieldType.email,
    "email_address": PHIFieldType.email,
    "genomic_sequence": PHIFieldType.genomic_sequence,
    "sequence": PHIFieldType.genomic_sequence,
    "dna_sequence": PHIFieldType.genomic_sequence,
    "rna_sequence": PHIFieldType.genomic_sequence,
    "diagnosis": PHIFieldType.diagnosis,
    "icd_code": PHIFieldType.diagnosis,
    "condition": PHIFieldType.diagnosis,
    "provider": PHIFieldType.provider,
    "physician": PHIFieldType.provider,
    "doctor": PHIFieldType.provider,
}


@dataclass
class HIPAAComplianceReport:
    compliant: bool
    safeguards: list[HIPAASafeguard]
    violations: list[str]
    recommendations: list[str]


def assess_hipaa_compliance(data_fields: list[str]) -> HIPAAComplianceReport:
    """Check which fields are PHI, verify safeguards are defined, report violations."""
    safeguards_applied: list[HIPAASafeguard] = []
    violations: list[str] = []
    recommendations: list[str] = []

    for field_name in data_fields:
        normalized = field_name.lower().strip()
        phi_type = _PHI_FIELD_ALIASES.get(normalized)
        if phi_type is not None:
            safeguard = HIPAA_SAFEGUARDS_MATRIX[phi_type]
            safeguards_applied.append(safeguard)

            if not safeguard.encrypted:
                violations.append(
                    f"PHI field '{field_name}' ({phi_type.value}) is not encrypted"
                )
            if not safeguard.audit_logged:
                violations.append(
                    f"PHI field '{field_name}' ({phi_type.value}) is not audit-logged"
                )
            if safeguard.access_level == "public":
                violations.append(
                    f"PHI field '{field_name}' ({phi_type.value}) has public access level"
                )

    if not safeguards_applied and data_fields:
        recommendations.append(
            "No recognized PHI fields detected; verify field names match HIPAA_SAFEGUARDS_MATRIX keys."
        )

    if violations:
        recommendations.append(
            "Encrypt all PHI fields at rest and in transit before processing."
        )
        recommendations.append(
            "Enable audit logging for all PHI field access."
        )

    return HIPAAComplianceReport(
        compliant=len(violations) == 0,
        safeguards=safeguards_applied,
        violations=violations,
        recommendations=recommendations,
    )


def separate_phi_fields(record: dict) -> tuple[dict, dict]:
    """Split a record dict into (phi_fields, non_phi_fields)."""
    phi: dict = {}
    non_phi: dict = {}
    for key, value in record.items():
        normalized = key.lower().strip()
        if normalized in _PHI_FIELD_ALIASES:
            phi[key] = value
        else:
            non_phi[key] = value
    return phi, non_phi


# ---------------------------------------------------------------------------
# Feature 3: Hash-chained audit log
# ---------------------------------------------------------------------------

_GENESIS_HASH = "0" * 64  # SHA-256 of genesis block


@dataclass
class AuditEntry:
    entry_id: str
    timestamp: str
    action: str
    user: str
    details: dict
    previous_hash: str
    entry_hash: str


def _compute_entry_hash(
    previous_hash: str,
    action: str,
    user: str,
    timestamp: str,
    details: dict,
) -> str:
    payload = previous_hash + action + user + timestamp + json.dumps(details, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class HashChainedAuditLog:
    """Singleton tamper-evident audit log using SHA-256 hash chaining."""

    _instance: Optional[HashChainedAuditLog] = None

    def __new__(cls) -> HashChainedAuditLog:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._chain = []
        return cls._instance

    def append(self, action: str, user: str, details: dict) -> AuditEntry:
        timestamp = datetime.now(UTC).isoformat()
        previous_hash = self._chain[-1].entry_hash if self._chain else _GENESIS_HASH
        entry_hash = _compute_entry_hash(previous_hash, action, user, timestamp, details)
        entry = AuditEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=timestamp,
            action=action,
            user=user,
            details=details,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )
        self._chain.append(entry)
        return entry

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify all hashes in the chain. Returns (valid, errors)."""
        errors: list[str] = []
        for i, entry in enumerate(self._chain):
            expected_previous = self._chain[i - 1].entry_hash if i > 0 else _GENESIS_HASH
            if entry.previous_hash != expected_previous:
                errors.append(
                    f"Entry {entry.entry_id} (index {i}): previous_hash mismatch. "
                    f"Expected {expected_previous[:16]}..., got {entry.previous_hash[:16]}..."
                )
            recomputed = _compute_entry_hash(
                entry.previous_hash, entry.action, entry.user,
                entry.timestamp, entry.details,
            )
            if entry.entry_hash != recomputed:
                errors.append(
                    f"Entry {entry.entry_id} (index {i}): entry_hash mismatch — chain tampered"
                )
        return len(errors) == 0, errors

    def get_entries(self, since: Optional[str] = None) -> list[AuditEntry]:
        if since is None:
            return list(self._chain)
        return [e for e in self._chain if e.timestamp >= since]

    def export_chain(self) -> list[dict]:
        return [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp,
                "action": e.action,
                "user": e.user,
                "details": e.details,
                "previous_hash": e.previous_hash,
                "entry_hash": e.entry_hash,
            }
            for e in self._chain
        ]

    def clear(self) -> None:
        """Reset the chain. For testing only."""
        self._chain = []


# Module-level singleton
audit_log = HashChainedAuditLog()


# ---------------------------------------------------------------------------
# Feature 4: Clinical use watermark
# ---------------------------------------------------------------------------

WATERMARK_TEXT = "NOT FOR CLINICAL USE — RESEARCH ARTIFACT ONLY"
_TOOL_VERSION = "foldagent-phase24"


def _watermark_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class WatermarkedOutput:
    data: str
    format: str
    watermark: str
    watermark_hash: str
    machine_readable_metadata: dict


def watermark_pdb(pdb_data: str) -> WatermarkedOutput:
    """Inject REMARK lines into PDB with watermark, timestamp, and tool version."""
    timestamp = datetime.now(UTC).isoformat()
    remark_lines = (
        f"REMARK   0 {WATERMARK_TEXT}\n"
        f"REMARK   0 TOOL: {_TOOL_VERSION}\n"
        f"REMARK   0 GENERATED: {timestamp}\n"
        f"REMARK   0 WATERMARK_HASH: {_watermark_hash(WATERMARK_TEXT)}\n"
    )
    watermarked = remark_lines + pdb_data

    meta = {
        "watermark_text": WATERMARK_TEXT,
        "tool_version": _TOOL_VERSION,
        "generated_at": timestamp,
        "format": "pdb",
        "clinical_use_prohibited": True,
    }
    return WatermarkedOutput(
        data=watermarked,
        format="pdb",
        watermark=WATERMARK_TEXT,
        watermark_hash=_watermark_hash(WATERMARK_TEXT),
        machine_readable_metadata=meta,
    )


def watermark_report(report_text: str, format: str = "html") -> WatermarkedOutput:
    """Inject watermark header/footer and hidden machine-readable metadata."""
    timestamp = datetime.now(UTC).isoformat()
    w_hash = _watermark_hash(WATERMARK_TEXT)

    meta = {
        "watermark_text": WATERMARK_TEXT,
        "tool_version": _TOOL_VERSION,
        "generated_at": timestamp,
        "format": format,
        "clinical_use_prohibited": True,
        "watermark_hash": w_hash,
    }

    if format == "html":
        meta_comment = (
            f"<!-- FOLDAGENT_WATERMARK: {json.dumps(meta, separators=(',', ':'))} -->"
        )
        header = (
            f'<div class="foldagent-watermark" style="background:#ffd700;color:#000;'
            f'font-weight:bold;padding:8px;text-align:center;">'
            f"{WATERMARK_TEXT}</div>\n"
        )
        footer = (
            f'\n<div class="foldagent-watermark-footer" style="background:#ffd700;color:#000;'
            f'font-weight:bold;padding:8px;text-align:center;">'
            f"{WATERMARK_TEXT}</div>\n"
            f"{meta_comment}\n"
        )
        watermarked = header + report_text + footer
    else:
        header = f"{'=' * 60}\n{WATERMARK_TEXT}\n{'=' * 60}\n"
        footer = f"\n{'=' * 60}\n{WATERMARK_TEXT}\n{'=' * 60}\n"
        meta_line = f"# FOLDAGENT_METADATA: {json.dumps(meta, separators=(',', ':'))}\n"
        watermarked = header + report_text + footer + meta_line

    return WatermarkedOutput(
        data=watermarked,
        format=format,
        watermark=WATERMARK_TEXT,
        watermark_hash=w_hash,
        machine_readable_metadata=meta,
    )


def verify_watermark(data: str) -> bool:
    """Check if watermark text is present in the data."""
    return WATERMARK_TEXT in data


# ---------------------------------------------------------------------------
# Feature 5: Credential attestation
# ---------------------------------------------------------------------------


class ProfessionalCredential(str, Enum):
    md = "md"
    dvm = "dvm"
    phd = "phd"
    pharmd = "pharmd"
    nurse_practitioner = "nurse_practitioner"
    research_scientist = "research_scientist"
    student = "student"


THERAPEUTIC_MODES: list[str] = [
    "drug_discovery",
    "vaccine_design",
    "antibody_design",
    "gene_therapy",
    "enzyme_engineering",
]

# Which credentials unlock which therapeutic modes
CREDENTIAL_MODE_REQUIREMENTS: dict[str, list[ProfessionalCredential]] = {
    "drug_discovery": [
        ProfessionalCredential.md,
        ProfessionalCredential.phd,
        ProfessionalCredential.pharmd,
        ProfessionalCredential.research_scientist,
    ],
    "vaccine_design": [
        ProfessionalCredential.md,
        ProfessionalCredential.phd,
        ProfessionalCredential.research_scientist,
    ],
    "antibody_design": [
        ProfessionalCredential.md,
        ProfessionalCredential.phd,
        ProfessionalCredential.research_scientist,
    ],
    "gene_therapy": [
        ProfessionalCredential.md,
        ProfessionalCredential.phd,
    ],
    "enzyme_engineering": [
        ProfessionalCredential.phd,
        ProfessionalCredential.research_scientist,
    ],
}

_ATTESTATION_VALIDITY_DAYS = 365


@dataclass
class CredentialAttestation:
    user_id: str
    credential: ProfessionalCredential
    institution: str
    license_number: Optional[str]
    attested_at: str
    expires_at: str
    modes_unlocked: list[str]


# In-memory store: user_id -> CredentialAttestation
_attestation_store: dict[str, CredentialAttestation] = {}


def attest_credentials(
    user_id: str,
    credential: ProfessionalCredential,
    institution: str,
    license_number: Optional[str] = None,
) -> CredentialAttestation:
    """Record a credential attestation and return which modes are unlocked."""
    now = datetime.now(UTC)
    expires = now + timedelta(days=_ATTESTATION_VALIDITY_DAYS)

    modes_unlocked = [
        mode
        for mode, required_creds in CREDENTIAL_MODE_REQUIREMENTS.items()
        if credential in required_creds
    ]

    attestation = CredentialAttestation(
        user_id=user_id,
        credential=credential,
        institution=institution,
        license_number=license_number,
        attested_at=now.isoformat(),
        expires_at=expires.isoformat(),
        modes_unlocked=modes_unlocked,
    )
    _attestation_store[user_id] = attestation
    return attestation


def check_mode_access(user_id: str, mode: str) -> tuple[bool, str]:
    """Check if user has attested credentials for the requested mode.

    Returns (allowed: bool, reason: str).
    """
    if mode not in THERAPEUTIC_MODES:
        return True, f"Mode '{mode}' does not require credential attestation."

    attestation = _attestation_store.get(user_id)
    if attestation is None:
        return False, (
            f"No credential attestation found for user '{user_id}'. "
            "Professional credentials must be attested before accessing therapeutic modes."
        )

    # Check expiry
    now = datetime.now(UTC)
    expires = datetime.fromisoformat(attestation.expires_at)
    if now > expires:
        return False, (
            f"Credential attestation for user '{user_id}' expired at {attestation.expires_at}. "
            "Please re-attest credentials."
        )

    if mode not in attestation.modes_unlocked:
        required = [c.value for c in CREDENTIAL_MODE_REQUIREMENTS.get(mode, [])]
        return False, (
            f"Credential '{attestation.credential.value}' does not unlock mode '{mode}'. "
            f"Required credentials: {required}."
        )

    return True, f"Access granted: credential '{attestation.credential.value}' unlocks mode '{mode}'."


# ---------------------------------------------------------------------------
# Feature 6: GDPR data residency
# ---------------------------------------------------------------------------


class DataResidency(str, Enum):
    local_only = "local_only"
    eu_only = "eu_only"
    unrestricted = "unrestricted"


CLOUD_BACKENDS: list[str] = ["alphafold_server", "alphafold_db"]

LOCAL_BACKENDS: list[str] = [
    "mock",
    "colabfold",
    "local_colabfold",
    "alphafold2_local",
    "alphafold3_local",
    "boltz1",
    "boltz2",
    "esmfold",
    "openfold",
    "rfdiffusion",
    "rfdiffusion2",
    "proteinmpnn",
    "chai1",
]

# EU-hosted or EU-compliant backends (subset of cloud)
_EU_BACKENDS: list[str] = []  # No current backends are EU-verified cloud


@dataclass
class ResidencyConfig:
    residency: DataResidency
    allowed_backends: list[str]
    blocked_backends: list[str]
    reason: str


def get_residency_config(residency: DataResidency) -> ResidencyConfig:
    """Return which backends are allowed/blocked for the given residency policy."""
    if residency == DataResidency.local_only:
        return ResidencyConfig(
            residency=residency,
            allowed_backends=list(LOCAL_BACKENDS),
            blocked_backends=list(CLOUD_BACKENDS),
            reason=(
                "local_only: all data must remain on local infrastructure. "
                "External API calls are prohibited."
            ),
        )
    elif residency == DataResidency.eu_only:
        return ResidencyConfig(
            residency=residency,
            allowed_backends=list(LOCAL_BACKENDS) + _EU_BACKENDS,
            blocked_backends=[b for b in CLOUD_BACKENDS if b not in _EU_BACKENDS],
            reason=(
                "eu_only: data may only be processed within the EU. "
                "Non-EU cloud backends are blocked."
            ),
        )
    else:  # unrestricted
        return ResidencyConfig(
            residency=residency,
            allowed_backends=list(LOCAL_BACKENDS) + list(CLOUD_BACKENDS),
            blocked_backends=[],
            reason="unrestricted: all backends are permitted.",
        )


def enforce_residency(backend_name: str, residency: DataResidency) -> None:
    """Raise DataResidencyError if the backend violates the residency policy."""
    config = get_residency_config(residency)
    if backend_name in config.blocked_backends:
        raise DataResidencyError(
            f"Backend '{backend_name}' is blocked under data residency policy '{residency.value}'. "
            f"Reason: {config.reason}"
        )
