---
name: run_full_foldagent_case_review
description: Runs the safe FoldAgent case-review workflow and produces an expert-review packet. Use only for research coordination under professional oversight. Never provide treatment, dosing, manufacturing, or administration instructions.
version: 0.2.0
license: Apache-2.0
framework: Hermes
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - case-review
  - research-coordination
  - safety-gated
---

# Run Full FoldAgent Case Review

## When to Use

Use this skill when you need the full end-to-end FoldAgent research workflow for one case: safety gating, data inventory, pipeline state review, candidate review, and expert-facing report generation. It is the Hermes-first orchestrator for turning a case record into a reviewable research packet. This skill does NOT authorize treatment decisions, clinical claims, dosing, formulation, or manufacturing guidance.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass FoldAgent safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Every output must include the label: "Research candidate only — not administerable".
2. Every export must pass FoldAgent safety preflight before leaving the system.
3. No dosing, injection, formulation, or manufacturing instructions may be generated.
4. Professional review is required before any downstream action.
5. Demo mode must remain synthetic-only.

See also: `skills/shared/safety_policy.md`

## Required FoldAgent API Endpoints

- `POST /safety/preflight` — Safety gate before execution and export steps
- `GET /cases/{case_id}` — Retrieve case metadata and species mode
- `GET /cases/{case_id}/samples` — Inspect data inventory completeness
- `GET /cases/{case_id}/pipeline/status` — Check current pipeline state
- `GET /cases/{case_id}/variants` — Review variant evidence
- `GET /cases/{case_id}/candidates` — Review candidate antigens and flags
- `POST /cases/{case_id}/reports/candidate-review` — Generate the expert-review packet
- `GET /reports/{report_id}/export?format=markdown|json` — Preview exportable report payloads

## Required User Confirmation Points

1. Before running or re-running the pipeline on non-demo data.
2. Before generating the expert-review report.
3. Before exporting any report or bundle.
4. Before any external upload pathway (for example AlphaFold Server).

## Expected Output Artifact

A structured output package containing:
- Case summary with species mode and supervision context.
- Data inventory and missing-data checklist.
- Pipeline state snapshot and reproducibility context.
- Variant table with research-only framing.
- Candidate antigen table with uncertainty flags.
- Structure evidence summary if available.
- Safety labels on every major section.
- Explicit professional-review reminder.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` for the intended workflow action. If blocked, stop immediately. If approval is required, surface that requirement before continuing.

2. **Load case context**: Call `GET /cases/{case_id}` and verify species mode, diagnosis summary, and case existence.

3. **Inspect inventory**: Call `GET /cases/{case_id}/samples` and summarize what source data exists versus what is missing.

4. **Check pipeline status**: Call `GET /cases/{case_id}/pipeline/status`. If no run exists, report that gap instead of pretending analysis is complete.

5. **Review evidence**: Call `GET /cases/{case_id}/variants` and `GET /cases/{case_id}/candidates` to assemble research evidence and uncertainty flags.

6. **Generate report**: Call `POST /cases/{case_id}/reports/candidate-review` and capture the generated report id for follow-through export or review.

7. **Final review**: Present the report as research coordination output only, include the safety label, and remind the operator that licensed professional review is required.

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

- Log every API call with timestamps and case context.
- Log every safety preflight result and whether the workflow stopped or continued.
- Log generated report identifiers and any exported artifact ids.
- Preserve the FoldAgent audit trail as the system of record for this workflow.

## Failure Handling

- If the case does not exist, stop and report the missing case id.
- If safety preflight blocks the workflow, surface the exact blocking reason and do not proceed.
- If pipeline status is missing or failed, report that clearly and avoid pretending downstream evidence exists.
- If report generation fails, capture the structured API error and return it unchanged.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
