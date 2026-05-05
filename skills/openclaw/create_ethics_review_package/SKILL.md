---
name: create_ethics_review_package
description: Generate and export NeoVax ethics-package materials for licensed professional review under safety gating.
version: 0.2.0
license: Apache-2.0
framework: OpenClaw
install_path: ~/.openclaw/skills/<skill_name>
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - ethics-review
  - reporting
  - safety-gated
---

# Create Ethics Review Package

## When to Use

Use this skill when a case needs an ethics-review package covering consent, privacy, risk framing, and professional oversight. It prepares the operator-facing ethics report and safe export workflow. This skill does NOT decide legal sufficiency or replace licensed professional judgment.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Ethics reports remain research coordination materials only.
2. Exports must pass safety preflight before leaving the system.
3. Do not rewrite jurisdictional warnings into legal or medical advice.

See also: `skills/shared/safety_policy.md`

## Required NeoVax API Endpoints

- `POST /safety/preflight` — Gate ethics-package generation and export
- `GET /cases/{case_id}` — Verify case context
- `POST /cases/{case_id}/reports/ethics-package` — Generate the ethics package
- `GET /reports/{report_id}` — Inspect generated ethics-package content
- `GET /cases/{case_id}/reports` — List reports available for the case
- `GET /reports/{report_id}/export?format=markdown|json` — Preview the export payload
- `POST /reports/{report_id}/save?format=markdown|json` — Persist the package to artifacts

## Required User Confirmation Points

1. Before generating a new ethics package.
2. Before exporting or saving the ethics package.

## Expected Output Artifact

A structured output package containing:
- Ethics-package report id and content summary.
- Consent/privacy/risk sections suitable for expert review.
- Export preview or saved artifact metadata.
- Research-only safety labels and jurisdiction warnings.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` before generating or exporting the ethics package.

2. **Verify case**: Call `GET /cases/{case_id}` to confirm the package target exists.

3. **Generate package**: Call `POST /cases/{case_id}/reports/ethics-package` and capture the report id.

4. **Inspect content**: Call `GET /reports/{report_id}` to confirm the package contains consent, privacy, and oversight framing.

5. **Preview export**: Use `GET /reports/{report_id}/export?format=...` to preview markdown or JSON output safely.

6. **Persist if approved**: Only after confirmation, call `POST /reports/{report_id}/save?format=...` and return the saved artifact path.

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

- Log ethics-package generation and all export operations.
- Log safety preflight results for both generation and export stages.
- Log saved artifact ids and paths when persistence occurs.

## Failure Handling

- If package generation fails, surface the structured API error and stop.
- If export is blocked by safety policy, stop and report the exact reason.
- If the case lacks prerequisite data, report the missing prerequisites rather than inventing content.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
