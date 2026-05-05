# Threat Model — FoldAgent Agent

**Classification:** Internal — Research Use Only  
**Phase:** 19 (Security Hardening)  
**Last Updated:** 2026-04-27  
**Owner:** Platform Security

---

## Scope

This document covers the threat surface of the FoldAgent Agent platform: a local-first, safety-gated research coordination tool for personalized cancer-vaccine exploration under licensed professional supervision. It does not cover threats to downstream wet-lab or clinical processes.

---

## 1. Prompt Injection Threats

### 1.1 Attack Surface

Agent skills accept free-text user input (mutation descriptions, protein sequences, research queries) that is forwarded to LLM inference endpoints. An adversary controlling input content can attempt to override system instructions, exfiltrate context, or trigger unsafe skill invocations.

### 1.2 Threat Scenarios

| ID   | Scenario                                                                       | Likelihood | Impact   |
| ---- | ------------------------------------------------------------------------------ | ---------- | -------- |
| PI-1 | Crafted mutation description embeds instructions to bypass safety preflight    | Medium     | High     |
| PI-2 | Uploaded FASTA/VCF file contains prompt-injection payload in sequence headers  | Low        | High     |
| PI-3 | Indirect injection via external tool output (AlphaFold annotation, NCBI fetch) | Low        | Medium   |
| PI-4 | Operator overrides system prompt via config to suppress safety gating          | Low        | Critical |

### 1.3 Mitigations

- **Safety preflight gate** (`backend/safety/`) runs before every agent skill execution; rejects requests that fail policy checks regardless of LLM output.
- Sequence data (FASTA, VCF) is parsed structurally before any LLM involvement; headers are stripped of non-standard characters.
- LLM system prompt is hardcoded and not configurable at runtime without redeployment.
- Audit logging records every skill invocation with full input hashes for post-hoc review.

### 1.4 Residual Risks

- Indirect injection via fetched external content (PI-3) is not fully mitigated; a content-sanitization pass before LLM injection is planned for Phase 20.

---

## 2. Genomic Privacy Threats

### 2.1 Attack Surface

The platform processes patient-adjacent genomic data: somatic mutation calls (VCF), expressed neoantigen candidates, HLA typing, and protein structure predictions. This data is among the most sensitive personal information possible — it is permanent, familially linked, and re-identifiable.

### 2.2 Threat Scenarios

| ID   | Scenario                                                                    | Likelihood | Impact   |
| ---- | --------------------------------------------------------------------------- | ---------- | -------- |
| GP-1 | Raw VCF/FASTA files exfiltrated from local data directory                   | Medium     | Critical |
| GP-2 | Genomic data included in LLM API requests to cloud providers                | Medium     | Critical |
| GP-3 | Audit logs inadvertently capture sequence snippets or mutation coordinates  | Low        | High     |
| GP-4 | SQLite database (`foldagent.db`) copied or accessed without authorization      | Medium     | High     |
| GP-5 | Browser/frontend session leaks sequence data to browser history or devtools | Low        | Medium   |

### 2.3 Mitigations

- **Local-first default**: no genomic data leaves the machine unless the operator explicitly enables a cloud upload step.
- LLM API calls receive only derivative artifacts (epitope scores, binding predictions) — not raw sequences — by policy enforced in skill wrappers.
- `data/` directory is `.gitignore`d and excluded from all CI artifact uploads.
- Audit log fields are schema-controlled; sequence fields are hashed before logging.
- `foldagent.db` is SQLite with file-system permissions; Docker compose mounts it as a named volume with restricted container access.

### 2.4 Residual Risks

- GP-4 requires OS-level encryption (FileVault/LUKS) on the host; the platform does not enforce this itself.
- GP-2 risk exists if a future skill directly passes raw genomic context to a cloud LLM; the LLM API call abstraction layer should add a genomic-data classifier before Phase 20 cloud features.

---

## 3. Supply-Chain Risks

### 3.1 Attack Surface

The platform installs ~80+ transitive Python dependencies from PyPI. A compromised package, typosquat, or malicious update can execute arbitrary code at install time or runtime.

### 3.2 Threat Scenarios

| ID   | Scenario                                                                     | Likelihood | Impact   |
| ---- | ---------------------------------------------------------------------------- | ---------- | -------- |
| SC-1 | Typosquat package name installed by developer error                          | Low        | High     |
| SC-2 | Legitimate package compromised post-pinning (supply-chain attack)            | Very Low   | Critical |
| SC-3 | Dependabot auto-merge introduces breaking or malicious update                | Low        | High     |
| SC-4 | CI runner environment poisoned via compromised GitHub Action                 | Very Low   | Critical |
| SC-5 | `pip install` at build time fetches unpinned transitive dep with new version | Medium     | Medium   |

### 3.3 Mitigations

- **`requirements.lock`** pins all transitive dependencies at exact versions; CI installs from this file.
- **`pip-audit`** in `security.yml` scans against OSV/PyPI advisory databases on every push and PR.
- **Dependabot** (`dependabot.yml`) files automated PRs for dependency updates; major-version bumps require manual review.
- GitHub Actions use pinned SHA references for third-party actions (enforce via Dependabot `github-actions` ecosystem).
- **CodeQL** scans for known vulnerable code patterns introduced by deps.
- SBOM (`foldagent-sbom.spdx.json`) generated on every main-branch push and uploaded to GitHub dependency graph for continuous monitoring.

### 3.4 Residual Risks

- SC-2 (post-install compromise of a pinned version) is mitigated only by pip-audit detecting a new CVE filing; zero-day window exists.
- Enforcing hash-pinning (`pip install --require-hashes`) would close SC-5 fully but requires all deps to publish hashes; planned for Phase 20.

---

## 4. Cloud Upload Risks

### 4.1 Attack Surface

AlphaFold Server and future cloud APIs (ESMFold, OpenFold) accept protein sequences for structure prediction. Uploading neoantigen sequences to external servers creates a privacy and data-sovereignty risk.

### 4.2 Threat Scenarios

| ID   | Scenario                                                                  | Likelihood | Impact   |
| ---- | ------------------------------------------------------------------------- | ---------- | -------- |
| CU-1 | Neoantigen sequences uploaded to AlphaFold Server without patient consent | Medium     | Critical |
| CU-2 | Cloud API TLS interception / MITM exposes sequence data in transit        | Very Low   | High     |
| CU-3 | Cloud provider retains and mines submitted sequences                      | Low        | High     |
| CU-4 | API key/token for cloud service committed to repository                   | Low        | High     |
| CU-5 | Rate-limit abuse or accidental bulk-upload of full exome sequences        | Low        | Medium   |

### 4.3 Mitigations

- **Local-first default**: AlphaFold/cloud upload skills are disabled unless explicitly enabled in `config.yaml` with `cloud_upload: true`.
- Safety preflight requires operator acknowledgement before any cloud upload skill executes.
- API keys are stored in environment variables / `.env` (excluded from git via `.gitignore`); **TruffleHog** scan in `security.yml` catches accidental commits.
- Cloud upload skills enforce a sequence-length cap and do not accept raw VCF or full-exome data.
- All cloud API calls use TLS with certificate verification; `httpx` client has `verify=True` enforced.

### 4.4 Residual Risks

- CU-3 (cloud provider data retention) is a contractual/legal risk; operators must review AlphaFold Server ToS before enabling cloud upload.
- CU-1 requires operator-level consent workflow to be enforced; a consent-acknowledgement prompt is planned for the cloud-upload skill in Phase 20.

---

## 5. Mitigations Already in Place

| Control                                       | Location                              | Covers            |
| --------------------------------------------- | ------------------------------------- | ----------------- |
| Safety preflight gate                         | `backend/safety/`                     | PI-1, PI-2, CU-1  |
| Audit logging (structured, append-only)       | `audit_logs/`, `structlog`            | PI-\*, GP-3, CU-5 |
| Local-first default (no network by default)   | `config.example.yaml`                 | GP-2, CU-1..3     |
| `.gitignore` for `data/`, `.env`, `foldagent.db` | `.gitignore`                          | GP-4, CU-4        |
| `requirements.lock` pinned deps               | `requirements.lock`                   | SC-5              |
| `pip-audit` in CI                             | `.github/workflows/security.yml`      | SC-1..2           |
| Dependabot automated updates                  | `.github/dependabot.yml`              | SC-3              |
| CodeQL static analysis                        | `.github/workflows/security.yml`      | SC-4, PI-\*       |
| TruffleHog secrets scan                       | `.github/workflows/security.yml`      | CU-4              |
| SBOM generation + upload                      | `.github/workflows/security.yml`      | SC-2..4           |
| License audit in CI                           | `.github/workflows/license-check.yml` | SC-1              |
| Sequence data never in LLM raw payload        | Skill wrappers                        | GP-2              |
| TLS verify=True on all outbound HTTP          | `httpx` client config                 | CU-2              |

---

## 6. Out of Scope

- Physical security of the host machine.
- Security of the clinical or laboratory systems that consume FoldAgent outputs.
- Threats to downstream manufacturing or treatment processes.
- Compliance with specific jurisdictional regulations (HIPAA, GDPR) — see `DATA_PRIVACY.md`.

---

## 7. Review Cadence

This threat model must be reviewed and updated:

- At the start of each new project phase that introduces external integrations.
- Within 30 days of any security incident or near-miss.
- Annually at minimum.

Next scheduled review: **Phase 20 kickoff** or **2026-07-27**, whichever comes first.
