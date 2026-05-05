---
name: organize_case_data
description: Organize FoldAgent case data inventory, metadata, and sample registration before downstream analysis.
version: 0.2.0
license: Apache-2.0
framework: Hermes
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - case-management
  - data-inventory
  - safety-gated
---

# Organize Case Data

## When to Use

Use this skill when setting up a new FoldAgent case, normalizing existing metadata, or auditing sample completeness before downstream analysis. It focuses on case, subject, and sample organization so later pipeline and reporting skills can operate on clean inventory state. This skill does NOT run scientific analysis or generate treatment-facing conclusions.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass FoldAgent safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. No treatment, dosing, or administration decisions.
2. Professional oversight is required for real data registration and review.
3. Demo mode must use synthetic data only.
4. Stop immediately if safety preflight requires approval for real sequence-bearing data.

See also: `skills/shared/safety_policy.md`

## Required FoldAgent API Endpoints

- `POST /safety/preflight` — Gate new sample registration or real-data handling
- `GET /cases/{case_id}` — Verify the case exists and inspect summary metadata
- `GET /cases/{case_id}/subjects` — Review subject metadata linked to the case
- `GET /cases/{case_id}/samples` — Inspect current sample inventory
- `GET /cases/{case_id}/variants` — Check whether upstream data already exists
- `GET /cases/{case_id}/candidates` — Check downstream candidate inventory status
- `POST /cases` — Create a case if starting from scratch
- `POST /cases/{case_id}/subjects` — Register subject metadata
- `POST /cases/{case_id}/samples` — Register sample metadata
- `GET /samples/{sample_id}/checksum` — Verify stored checksum for integrity review

## Required User Confirmation Points

1. Before registering new sample metadata.
2. Before handling real sequence-bearing or subject-identifying data.

## Expected Output Artifact

A structured output package containing:
- Case summary with species mode and diagnosis metadata.
- Subject and sample inventory tables.
- Missing-data checklist for downstream analysis readiness.
- Integrity notes such as checksum presence or gaps.
- Research-only safety labels on the inventory summary.

## Steps

1. **Safety preflight**: Run `POST /safety/preflight` before any write action involving real data or new registrations.

2. **Verify case**: Call `GET /cases/{case_id}` if a case already exists; otherwise create one with `POST /cases`.

3. **Inspect inventory**: Call `GET /cases/{case_id}/subjects`, `GET /cases/{case_id}/samples`, `GET /cases/{case_id}/variants`, and `GET /cases/{case_id}/candidates` to understand current completeness.

4. **Register metadata**: If new metadata is approved, call `POST /cases/{case_id}/subjects` and/or `POST /cases/{case_id}/samples` with normalized fields only.

5. **Verify integrity**: For new or questionable samples, call `GET /samples/{sample_id}/checksum` and note missing checksum coverage.

6. **Summarize gaps**: Return a concise missing-data checklist describing what is ready and what blocks downstream pipeline or reporting work.

## Hermes Memory Seed Template

- Case id and species mode currently in scope.
- Current safety posture (demo, approval-required, or blocked).
- Open blockers or missing-data items relevant to this skill.
- Most recent report, pipeline, job, or artifact ids touched by this skill.

## Hermes Self-Improvement Guardrails

- Do not self-improve the workflow into treatment, dosing, formulation, administration, or manufacturing output generation.
- Do not reinterpret research summaries as clinical validation or patient-specific advice.
- If a proposed automation change would widen medical-output scope, stop and escalate instead of adapting around the guardrail.

## Audit Log Integration Notes

- Treat the FoldAgent audit trail as the source of truth for actions taken.
- Prefer endpoints that already emit audit events over ad hoc side channels.
- When blocked, preserve the exact structured reason instead of paraphrasing it into something weaker.

## Logging Requirements

- Log every case, subject, and sample lookup with case context.
- Log all safety preflight outcomes before registration steps.
- Log each created subject or sample id after successful writes.
- Keep the FoldAgent audit trail as the authoritative registration record.

## Failure Handling

- If the case is missing, stop and create or request the correct case id before proceeding.
- If subject or sample registration is blocked by safety policy, surface the exact reason and stop.
- If required metadata fields are missing, report the missing fields instead of writing partial records.
- If checksum information is unavailable, label the inventory as incomplete rather than assuming integrity.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
