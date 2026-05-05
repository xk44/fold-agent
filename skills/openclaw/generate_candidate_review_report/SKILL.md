---
name: generate_candidate_review_report
description: Generate, inspect, and export a NeoVax candidate-review report under safety gating and professional-review framing.
version: 0.2.0
license: Apache-2.0
framework: OpenClaw
install_path: ~/.openclaw/skills/<skill_name>
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - reporting
  - candidate-review
  - safety-gated
---

# Generate Candidate Review Report

## When to Use

Use this skill when a case is ready for a candidate-review report summarizing variants, candidates, and structure evidence for expert review. It focuses on report generation, inspection, and safe export handling. This skill does NOT escalate research findings into medical advice or clinical instructions.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Every report must retain the NeoVax research-only safety label.
2. All export paths must pass safety preflight before proceeding.
3. Blocked or approval-required exports must stop immediately.

See also: `skills/shared/safety_policy.md`

## Required NeoVax API Endpoints

- `POST /safety/preflight` — Gate report generation and export actions
- `GET /cases/{case_id}` — Verify target case
- `POST /cases/{case_id}/reports/candidate-review` — Generate the candidate-review report
- `GET /reports/{report_id}` — Inspect generated report content
- `GET /cases/{case_id}/reports` — List prior case reports
- `GET /reports/{report_id}/export?format=markdown|json` — Preview export payloads
- `POST /reports/{report_id}/save?format=markdown|json` — Persist exports to artifact storage

## Required User Confirmation Points

1. Before generating a new candidate-review report.
2. Before exporting or saving report artifacts.

## Expected Output Artifact

A structured output package containing:
- Candidate-review report id and rendered content summary.
- Export preview in markdown or JSON form.
- Saved artifact id/path when persisted.
- Safety labels and export gate result.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` before generating or exporting report content.

2. **Verify case**: Call `GET /cases/{case_id}` to confirm the report target exists.

3. **Generate report**: Call `POST /cases/{case_id}/reports/candidate-review` and capture the returned report id.

4. **Inspect output**: Call `GET /reports/{report_id}` and review the content for completeness and safety labels.

5. **Preview export**: Call `GET /reports/{report_id}/export?format=...` if the operator wants an export preview.

6. **Persist if approved**: Only after user confirmation, call `POST /reports/{report_id}/save?format=...` and report the saved artifact path.

## OpenClaw Memory Seed Template

- Case id and species mode currently in scope.
- Current safety posture (demo, approval-required, or blocked).
- Open blockers or missing-data items relevant to this skill.
- Most recent report, pipeline, job, or artifact ids touched by this skill.

## OpenClaw Self-Improvement Guardrails

- Do not self-improve the workflow into treatment, dosing, formulation, administration, or manufacturing output generation.
- Do not reinterpret research summaries as clinical validation or patient-specific advice.
- If a proposed automation change would widen medical-output scope, stop and escalate instead of adapting around the guardrail.

## Audit Log Integration Notes

- Treat the NeoVax audit trail as the source of truth for actions taken.
- Prefer endpoints that already emit audit events over ad hoc side channels.
- When blocked, preserve the exact structured reason instead of paraphrasing it into something weaker.

## Logging Requirements

- Log report generation, export preview, and saved artifact ids.
- Log every preflight outcome associated with report generation and export.
- Log whether the artifact was only previewed or actually persisted.

## Failure Handling

- If generation fails, surface the structured backend error and stop.
- If export is blocked by safety preflight, report the exact blocked reason and do not continue.
- If the report id is missing or invalid, stop and request regeneration or the correct id.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
