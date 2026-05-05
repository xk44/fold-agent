---
title: Audit Log Integration — neovax-hermes
framework: Hermes
skill: neovax-hermes
version: 1.0.0
---

# Audit Log Integration

This document describes how Hermes skills integrate with the NeoVax audit
trail and what `log_action` patterns each skill emits.

## Overview

Every write operation, safety check, and pipeline action performed by a
Hermes skill emits a structured audit event via the NeoVax `log_action`
function (`backend/app/safety/audit.py`). These events are stored in the
`audit_logs` table and are accessible via:

- `GET /audit/{case_id}` — Events for a specific case
- `GET /audit/export` — Full audit log export (access-controlled)

Hermes agents treat the NeoVax audit trail as the authoritative record of
all actions taken. No side-channel logging (e.g., local files, agent memory
only) replaces the audit trail.

## log_action Patterns by Skill

Each skill produces audit events with a specific `action` string. The table
below maps skill names to their primary audit action patterns.

| Skill                                     | Primary log_action patterns                                                                                             |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `organize_case_data`                      | `case.created`, `subject.created`, `sample.registered`                                                                  |
| `run_bioinformatics_pipeline`             | `pipeline.run.started`, `pipeline.run.completed`, `pipeline.run.failed`, `job.dispatched`, `job.retry`, `job.cancelled` |
| `run_full_neovax_case_review`             | `review.started`, `review.completed`, `report.generated`                                                                |
| `generate_candidate_review_report`        | `report.generated`, `report.saved`, `bundle.exported`, `attestation.submitted`                                          |
| `get_alphafold_structures`                | `structure_job.created`, `structure_job.completed`                                                                      |
| `create_ethics_review_package`            | `ethics_package.generated`, `ethics_package.saved`                                                                      |
| `coordinate_licensed_lab_outreach`        | `lab.contact.added`, `lab.outreach.email.generated`                                                                     |
| `monitor_case_progress`                   | `case.status.checked`, `job.status.checked`                                                                             |
| `autoresearch_optimize_software_pipeline` | `adapter.dry_run`, `adapter.run`, `pipeline.step.optimized`                                                             |

Safety preflight calls (`POST /safety/preflight`, `POST /safety/mrna-gate`)
emit their own audit events independently of skill-level logging.

## Reading the Audit Trail

To retrieve all audit events for a case:

```
GET /audit/{case_id}
```

Response is a list of `AuditLogRead` objects with fields:

```json
{
  "id": "uuid",
  "case_id": "uuid",
  "actor": "hermes-agent | api | human",
  "action": "pipeline.run.started",
  "inputs": { "…": "…" },
  "outputs": { "…": "…" },
  "created_at": "2026-04-27T10:00:00Z"
}
```

## Hermes Agent Responsibilities

Hermes agents using this skill pack must:

1. **Never suppress audit events.** If a `log_action` call fails, the skill
   must surface the failure rather than continuing silently.

2. **Prefer audit-emitting endpoints.** When two endpoints can accomplish the
   same goal, prefer the one that emits `log_action` events (documented in
   the individual SKILL.md files).

3. **Preserve exact structured reasons.** When safety preflight or mRNA gate
   blocks an action, the agent must log the exact structured reason returned
   by the API — not a paraphrase.

4. **Log job and artifact IDs.** Pipeline run IDs, job IDs, report IDs, and
   artifact paths must be recorded in the agent memory seed and in the audit
   trail so they can be traced later.

5. **Reference the audit trail for conflict resolution.** If the agent's
   memory seed conflicts with the audit trail, the audit trail takes
   precedence.

## Verifying Audit Coverage

After any skill execution, the agent should call `GET /audit/{case_id}` and
confirm that expected audit events were emitted. If an expected event is
missing, surface the gap to the human operator before proceeding.

## Audit Export for Compliance

For institutional compliance or case closure, export the full audit log:

```
GET /audit/export
```

This returns all audit events across all cases. Access to this endpoint
should be restricted to authorized users only (see `OPSEC_CHECKLIST.md` in
the OpenClaw skill pack, or institutional access control policy).

## Prohibited Audit Patterns

- Do not write directly to the `audit_logs` table bypassing `log_action`.
- Do not delete or modify audit log entries.
- Do not use agent memory as the sole record of safety-gated actions.
