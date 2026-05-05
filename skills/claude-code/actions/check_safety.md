---
name: check_safety
description: Run safety preflight checks and evidence-based risk assessment for a FoldAgent case.
action_type: read
primary_endpoint: POST /safety/preflight
framework: Claude Code
safety_gate: self
---

# Action: Check Safety

## Purpose

Run safety preflight checks, mRNA safety gate validation, false-positive risk
assessment, and evidence review for a FoldAgent case before any pipeline,
report, or data export action. This action is self-gating — it never requires
a prior preflight call, but all other actions require it.

## Safety Disclaimer

Safety checks are computational screens only. A passed preflight does NOT
constitute clinical clearance. All findings require review by the named
supervising professional before any real-world action.

## API Endpoints

- `POST /safety/preflight` — General pre-action safety gate
- `POST /safety/mrna-gate` — mRNA vaccine–specific safety gate
- `GET /cases/{case_id}/false-positive-risk` — Computational false-positive scores
- `GET /cases/{case_id}/evidence` — Supporting evidence for candidates
- `GET /cases/{case_id}/report/citations` — Literature citations
- `GET /cases/{case_id}/privacy` — Data privacy assessment
- `GET /privacy/cloud-upload-check` — Cloud upload safety check
- `GET /audit/{case_id}` — Review audit trail for prior safety events
- `GET /audit/export` — Export full audit log

## Steps

1. **General preflight**: Call `POST /safety/preflight` with the intended
   `action` and `case_id`. Capture the result:
   - `status: "ok"` → proceed
   - `status: "requires_approval"` → surface reason, request confirmation
   - `status: "blocked"` → surface exact reason, stop all downstream actions

2. **mRNA gate** (when vaccine formulation context is present): Call
   `POST /safety/mrna-gate` to run sequence-level safety screens specific
   to mRNA vaccine design. Stop on block.

3. **False-positive risk**: Call `GET /cases/{case_id}/false-positive-risk`
   to surface candidate-level false-positive risk scores. Flag any candidates
   above threshold to the user.

4. **Evidence review**: Call `GET /cases/{case_id}/evidence` and
   `GET /cases/{case_id}/report/citations` to verify supporting evidence
   is available and credible.

5. **Privacy check** (before any data sharing): Call
   `GET /cases/{case_id}/privacy` and `GET /privacy/cloud-upload-check`
   to confirm no PII/PHI is exposed in export targets.

6. **Audit review**: Call `GET /audit/{case_id}` to surface any prior safety
   events or blocking decisions relevant to the current action.

7. **Surface result**: Return a structured safety summary with pass/warn/block
   status for each check, false-positive flags, and privacy clearance status.

## Expected Output

- Preflight result: ok / requires_approval / blocked
- mRNA gate result (if applicable): ok / blocked
- False-positive risk summary per candidate
- Evidence and citation availability
- Privacy clearance status
- Audit trail summary of prior safety events

## Failure Handling

- Preflight blocked: surface the exact structured reason; do NOT proceed with
  the downstream action that triggered this check.
- mRNA gate blocked: treat as hard stop; escalate to supervising professional.
- Privacy check fails: do not export or upload data; report exact privacy issue.
- Evidence endpoint unavailable: warn user; do not suppress the warning.

## Audit

All preflight calls are logged. Verify results via `GET /audit/{case_id}`.
