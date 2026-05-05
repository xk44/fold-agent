# Genomic Privacy Threat Model — NeoVax-Agent

**Classification:** Internal — Research Use Only
**Phase:** 19 (Security Hardening)
**Last Updated:** 2026-04-27
**Owner:** Platform Security

> **Disclaimer:** This document is not legal compliance guidance. It does not constitute HIPAA,
> GDPR, or any other regulatory compliance. Operators must obtain qualified legal and privacy
> counsel before deploying this platform with real patient data.

---

## Scope

Genomic data processed by NeoVax-Agent — somatic VCF calls, expressed neoantigen candidates,
HLA typing, protein sequences — is among the most sensitive personal information possible. It is
permanent, familially linked, and re-identifiable even after apparent anonymization. This document
catalogs threats to that data across the full platform lifecycle.

---

## 1. Threat Scenarios

### 1.1 Sequence Data Leakage via Cloud Backends

**Threat:** AlphaFold Server, ESMFold, or other cloud structure-prediction APIs receive protein
sequences. Those sequences may contain or be derived from patient somatic mutations.

**Attack paths:**

- Operator enables cloud upload without reviewing backend data-use policy.
- A future skill directly passes raw FASTA or peptide sequences to a cloud LLM API.
- API key for a cloud backend is stored in environment and rotated insecurely.

**Severity:** Critical — genomic sequences submitted to external servers may be retained,
mined, or disclosed by the provider.

---

### 1.2 Log Files Containing Sequences

**Threat:** `structlog`-formatted application logs or audit logs inadvertently capture:

- Genomic coordinates from `Variant.genomic_coordinates`.
- Peptide sequences from `CandidateAntigen.peptide_metadata`.
- Full VCF records logged in error tracebacks or debug output.

Log files may be copied to centralized logging systems, cloud observability platforms, or
CI artifact stores.

**Severity:** High — logs are often treated as low-sensitivity and stored broadly.

---

### 1.3 Export Data Containing Raw Sequences

**Threat:** Case bundle exports (`/cases/{id}/export/bundle`) and report exports include
candidate and variant data. Exported files may:

- Be transmitted via email without encryption.
- Be stored in cloud file shares (Google Drive, S3) accessible to unauthorized parties.
- Contain more information than the recipient is authorized to receive.

**Severity:** High — exports are designed for sharing, making control of recipients critical.

---

### 1.4 Browser Cache and DevTools Exposure

**Threat:** The Streamlit frontend or any future web UI renders genomic data in the browser.
Browser engines may cache:

- API responses containing sequences in browser storage or disk cache.
- Form field values including diagnostic summaries in autocomplete history.
- DevTools network inspector logs retained on a shared workstation.

**Severity:** Medium — local-only deployment limits blast radius, but shared workstations
are common in research settings.

---

### 1.5 SQLite Database Exfiltration

**Threat:** `neovax.db` is a single file on the local filesystem. Anyone with read access to
the file can copy the entire database, including all case records, candidates, and variants.

**Severity:** High — no application-layer controls protect against file-level copy.

---

### 1.6 Audit Log Re-identification

**Threat:** Audit log entries contain `case_id`, `actor`, `action`, and timing metadata.
Correlation of audit entries across cases may re-identify de-identified subjects, particularly
in small cohorts.

**Severity:** Medium — audit logs are required for integrity; residual re-identification
risk must be accepted and managed by policy.

---

## 2. Mitigations

### 2.1 Local-First Architecture

- **Default:** All genomic data stays on the local machine. No network egress unless the
  operator explicitly sets `NEOVAX_CLOUD_UPLOAD_ENABLED=true`.
- Cloud upload skills (`alphafold_server`, `alphafold_db`) are disabled by default in
  `config.example.yaml`.
- `check_cloud_upload_allowed()` in `privacy.py` enforces the gate programmatically before
  any upload.

### 2.2 Cloud Upload Gate

- Any cloud upload requires `requires_confirmation=true` in the upload confirmation payload.
- `build_upload_confirmation()` in `security.py` generates a confirmation record with explicit
  `warnings` and `requires_explicit_consent` flag that the caller must acknowledge.
- Operators must review backend-specific data-use and privacy policies before enabling.

### 2.3 Data Retention Policy

- Default retention: 365 days (`DEFAULT_RETENTION_DAYS` in `privacy.py`).
- `find_expired_artifacts()` surfaces stale artifacts for operator review.
- `remove_case_data_dir()` deletes all filesystem artifacts for a case on deletion.
- `verify_data_deletion()` in `security.py` confirms no DB records remain after deletion.

### 2.4 Audit Trail Integrity

- All audit log entries include SHA-256 hashes of inputs and outputs.
- `verify_audit_chain()` in `security.py` validates hash-chain integrity to detect tampering.
- Audit logs are append-only by application policy; no `DELETE` or `UPDATE` paths exist.

### 2.5 Log Hygiene

- Sequence data is never logged directly; only SHA-256 hashes are recorded in audit fields.
- `structlog` configuration should be reviewed to confirm no debug formatters log raw
  SQLAlchemy query parameters (which may include sequence strings).
- CI and deployment pipelines must not upload log artifacts to external stores.

### 2.6 Export Controls

- Case bundle exports are labeled with `RESEARCH_LABEL` and include privacy disclaimers.
- Redaction levels (`full`, `deidentify`, `anonymous`, `deleted`) control what fields appear
  in exports.
- Operators are responsible for secure transmission of exported files.

---

## 3. HIPAA Considerations (Non-Compliance Disclaimer)

> This section is informational only. NeoVax-Agent is **not** a HIPAA-covered entity or
> Business Associate by itself. Operators using this platform with Protected Health Information
> (PHI) must independently assess and establish HIPAA compliance, including BAAs with any
> cloud providers.

Relevant HIPAA-adjacent controls present in the platform:

| HIPAA Safeguard Category            | Platform Control                        |
| ----------------------------------- | --------------------------------------- |
| Access Control (§164.312(a))        | Role-based permission model (`rbac.py`) |
| Audit Controls (§164.312(b))        | Append-only audit log with hash chain   |
| Integrity (§164.312(c))             | SHA-256 hashes on all audit entries     |
| Transmission Security (§164.312(e)) | TLS enforced on all outbound HTTP       |
| Minimum Necessary (§164.502(b))     | Redaction levels on case export         |

---

## 4. GDPR Considerations (Non-Compliance Disclaimer)

> This section is informational only. Operators in EU/EEA jurisdictions must independently
> assess GDPR Article 9 obligations (special-category data) for genomic data.

Relevant GDPR-adjacent controls:

- **Right to erasure (Art. 17):** `remove_case_data_dir()` + `verify_data_deletion()` support
  physical deletion workflows.
- **Data minimization (Art. 5(1)(c)):** Redaction levels and export controls.
- **Retention limits (Art. 5(1)(e)):** Configurable retention policy via `DEFAULT_RETENTION_DAYS`.
- **Pseudonymization:** `anonymized_display_name` on `Subject`; de-identification redaction level.

---

## 5. Residual Risk Summary

| ID   | Threat                   | Residual Risk                   | Owner                       |
| ---- | ------------------------ | ------------------------------- | --------------------------- |
| GP-1 | Cloud sequence leakage   | Low (gate active)               | Operator policy             |
| GP-2 | Log sequence capture     | Medium (no log classifier)      | Phase 20                    |
| GP-3 | Export re-identification | Medium                          | Operator policy             |
| GP-4 | Browser cache            | Low (local deployment)          | Operator workstation policy |
| GP-5 | SQLite exfiltration      | Medium (OS encryption required) | Operator OS config          |
| GP-6 | Audit re-identification  | Accepted                        | Policy                      |

---

## 6. Review Cadence

Review at Phase 20 kickoff, before any cloud integration is enabled, or after any data incident.
Next scheduled review: **Phase 20 kickoff** or **2026-07-27**.
