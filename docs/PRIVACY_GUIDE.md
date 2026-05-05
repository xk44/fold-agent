# Privacy Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Architecture: Local-First

NeoVax-Agent is designed to run entirely on your local machine. By default:

- The database is SQLite at `./data/neovax.db` (or `./neovax.db` in dev)
- All artifacts, reports, and uploaded files are written to `./artifacts/`
- Audit logs are written to `./audit_logs/`
- No data is sent externally unless you explicitly enable a cloud backend

The only exceptions to local-only operation are:

1. `alphafold_server` backend — sends sequence data to Google DeepMind (blocked by default; requires explicit acknowledgement)
2. `colabfold` backend — may query remote MMseqs2 servers for MSA unless configured with a local server
3. `alphafold_db` backend — sends UniProt accessions to the EBI API (not patient sequence data)

---

## Per-Case Data Directories

Each case gets an isolated directory tree under `artifacts/cases/{case_id}/`:

```
artifacts/cases/{case_id}/
  uploads/     — raw uploaded files (FASTQ, BAM, VCF)
  artifacts/   — pipeline and analysis outputs
  reports/     — generated reports and ethics packages
  structures/  — AlphaFold structure outputs
```

`ensure_case_data_dir(case_id)` creates this layout on first use. Functions are in `backend/app/privacy.py`.

---

## Encryption at Rest

Encryption at rest is **not enabled by default**. To enable:

```bash
NEOVAX_ENCRYPTION_AT_REST_ENABLED=true
NEOVAX_ENCRYPTION_KEY=your-32-byte-base64-encoded-key
```

When enabled, artifacts written to disk are encrypted before storage. The encryption key must be provided at startup; there is no key recovery mechanism. Store keys in a secrets manager, not in `.env` files committed to version control.

Check encryption status for a case:

```bash
GET /cases/{case_id}/privacy-summary
```

Returns `"encryption_at_rest": true/false` among other privacy metadata.

---

## Cloud Upload Gates

Cloud uploads are **disabled by default** (`NEOVAX_CLOUD_UPLOAD_ENABLED=false`).

To enable (not recommended for human data):

```bash
NEOVAX_CLOUD_UPLOAD_ENABLED=true
NEOVAX_CLOUD_UPLOAD_CONFIRMATION_REQUIRED=true  # always leave true
```

Before any cloud operation, `check_cloud_upload_allowed()` is called. It returns:

- `allowed: false` if cloud uploads are globally disabled
- A warning list if the backend sends data externally (alphafold_server, alphafold_db)
- `requires_confirmation: true` when the user must explicitly acknowledge

The safety preflight system enforces this as a `REQUIRES_APPROVAL` gate. Human-mode sequence exports to external backends are hard-blocked regardless of cloud upload settings.

---

## Redaction Levels

Cases, subjects, and reports carry a `redaction_level` field. Defined in `RedactionLevelEnum`:

| Level     | Meaning                                              |
| --------- | ---------------------------------------------------- |
| `full`    | Maximum redaction — default for all new cases        |
| `partial` | Some identifiers retained for researcher use         |
| `none`    | No redaction — requires explicit researcher decision |

Set redaction level when creating or updating a case. It is stored per-case and per-report, and is included in the privacy summary.

---

## Consent Tracking

Every `Case` and `Subject` has a `consent_status` field (free-text string, default: `"pending"`).

Expected values (enforced by convention, not enum):

- `pending` — consent not yet obtained
- `obtained` — consent confirmed and documented
- `waived` — IRB or ethics waiver in place
- `not_applicable` — e.g. demo mode synthetic data

The consent status is surfaced in:

- `GET /cases/{case_id}/privacy-summary`
- Ethics package reports
- Audit log exports

NeoVax-Agent does not validate the legal sufficiency of consent. It records what you tell it. Actual consent documentation must be managed outside the system.

---

## Data Deletion

To delete all files for a case:

```python
from backend.app.privacy import remove_case_data_dir
remove_case_data_dir(case_id)
```

Or via the API (if the endpoint is exposed in your deployment). This removes the entire `artifacts/cases/{case_id}/` tree. It does **not** delete the database records — delete those separately via the cases API.

For full case removal including database records, delete via `DELETE /cases/{case_id}` which should cascade to samples, variants, candidates, reports, and audit log entries depending on your cascade configuration.

---

## File Retention Policy

Default retention: **365 days** from artifact creation date.

Find expired artifacts:

```python
from backend.app.privacy import find_expired_artifacts
expired = find_expired_artifacts(db, retention_days=365)
```

Returns a list of artifact records older than the retention window. NeoVax-Agent does not automatically delete expired artifacts — you must implement a retention job or cron task that calls `remove_case_data_dir()` for cases whose artifacts have all expired.

---

## Audit Log Export

Export audit logs for compliance or review:

```python
from backend.app.privacy import export_audit_log

# JSON format (default)
json_export = export_audit_log(db, case_id="abc123", format="json")

# Human-readable text
text_export = export_audit_log(db, since=cutoff_datetime, format="text")
```

Or via the API:

```bash
GET /audit?case_id={case_id}
GET /audit?since=2025-01-01T00:00:00Z
```

Audit entries include actor, action, SHA-256 hashes of inputs and outputs, safety gate result, and timestamp. Hashes allow tamper detection — compare the stored hash against a re-hash of the data.

---

## Privacy Summary Endpoint

```bash
GET /cases/{case_id}/privacy-summary
```

Returns:

```json
{
  "case_id": "...",
  "redaction_level": "full",
  "consent_status": "pending",
  "cloud_upload_enabled": false,
  "encryption_at_rest": false,
  "data_directory": "./artifacts/cases/...",
  "data_directory_exists": true,
  "file_count": 12,
  "sample_count": 2,
  "retention_days": 365
}
```

---

## Configuration Reference

```bash
NEOVAX_DATABASE_URL=sqlite:///./data/neovax.db
NEOVAX_ARTIFACT_ROOT=./artifacts
NEOVAX_AUDIT_LOG_PATH=./audit_logs
NEOVAX_CLOUD_UPLOAD_ENABLED=false
NEOVAX_CLOUD_UPLOAD_CONFIRMATION_REQUIRED=true
NEOVAX_ENCRYPTION_AT_REST_ENABLED=false
NEOVAX_ENCRYPTION_KEY=                          # required if encryption enabled
NEOVAX_SPECIES_MODE=demo                        # demo | dog | human
```

---

## Human Mode Data Handling

When `NEOVAX_SPECIES_MODE=human`:

- Sequence-level exports are hard-blocked without expert mode + IRB attestation
- External AlphaFold backends require explicit acknowledgement and preflight approval
- All pipeline runs on sequence data trigger the mRNA gate
- Redaction level defaults to `full`; do not lower it without deliberate researcher action
- Consent status should be set to `obtained` or `waived` before any data operations
