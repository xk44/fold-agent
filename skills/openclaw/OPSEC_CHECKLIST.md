---
title: OPSEC Checklist — OpenClaw NeoVax Deployment
framework: OpenClaw
skill: neovax-openclaw
version: 1.0.0
---

# OPSEC Checklist: OpenClaw NeoVax Deployment

Complete this checklist before deploying the `neovax-openclaw` skill pack to
any environment other than a local development machine.

## 1. Secrets and Credentials

- [ ] No API keys, passwords, or tokens are hardcoded in any YAML task file
- [ ] No secrets are committed to version control (`.env`, `secrets.yaml`, etc.)
- [ ] `NEOVAX_API_URL` and auth tokens are injected via environment variables
      or a secrets manager, not stored in skill files
- [ ] OpenClaw agent config files are excluded from any public repository
- [ ] Service account credentials for AlphaFold or external APIs are rotated
      regularly and scoped to minimum required permissions

## 2. Network Exposure

- [ ] The NeoVax API (`/agent/events/ws`, `/cases/*`, `/safety/*`) is NOT
      exposed to untrusted networks without authentication
- [ ] WebSocket endpoint `/agent/events/ws` is behind a reverse proxy with
      token-based auth enforced in production
- [ ] TLS is enforced for all API connections (no plaintext `http://` in
      production `NEOVAX_API_URL`)
- [ ] SSE endpoint `GET /agent/events` has rate limiting configured

## 3. Data Privacy

- [ ] No real patient PII/PHI is present in any skill file, task file, or
      example file
- [ ] `GET /cases/{case_id}/privacy` passes before any case data is shared
- [ ] `GET /privacy/cloud-upload-check` passes before any cloud upload
- [ ] Case data is stored in a HIPAA/GDPR-compliant location if real patient
      data is involved
- [ ] Data retention policy is configured per `GET /privacy/retention/expired`

## 4. Safety Gate Integrity

- [ ] `POST /safety/preflight` is called before every pipeline run, report
      generation, and data export — confirmed in all deployed task files
- [ ] `POST /safety/mrna-gate` is called for any mRNA vaccine design context
- [ ] Safety gate bypass is not implemented or reachable in the deployed config
- [ ] Blocked safety results are logged and not silently swallowed

## 5. Audit Trail

- [ ] The NeoVax audit trail (`GET /audit/{case_id}`, `GET /audit/export`) is
      accessible to the supervising professional
- [ ] Audit logs are retained for the minimum required period per institutional
      policy
- [ ] Audit log export is access-controlled (not publicly readable)

## 6. Access Control

- [ ] Only authorized personnel have access to the OpenClaw agent config
- [ ] The `supervising_professional` field is set on every case before pipeline
      execution
- [ ] Case deletion (`DELETE /cases/{case_id}`) is restricted to authorized
      users only
- [ ] Redaction endpoints (`POST /cases/{case_id}/redact`) are tested and
      functional before handling real patient data

## 7. Dependency Security

- [ ] All Python dependencies in `skills/shared/` are pinned to specific
      versions
- [ ] No unreviewed third-party packages are imported in skill helper files
- [ ] `skills/shared/neovax_client.py` and `event_stream_client.py` have been
      reviewed for insecure deserialization or SSRF risk

## 8. Incident Response

- [ ] A contact is designated for security incidents involving this deployment
- [ ] Procedure exists to revoke API credentials if a breach is suspected
- [ ] The NeoVax audit log is preserved and backed up before any credential
      rotation

---

Reviewer: ********\_\_\_******** Date: ****\_\_\_**** Environment: ****\_\_\_****
