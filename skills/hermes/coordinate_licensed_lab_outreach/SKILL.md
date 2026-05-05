---
name: coordinate_licensed_lab_outreach
description: Prepare case bundles and supporting research artifacts for licensed professional outreach without performing external communication automatically.
version: 0.2.0
license: Apache-2.0
framework: Hermes
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - handoff
  - bundle-export
  - safety-gated
---

# Coordinate Licensed Lab Outreach

## When to Use

Use this skill when a FoldAgent case needs a structured handoff package for licensed professional or lab review. It prepares bundles, saved exports, and artifact references so outreach can happen through approved human-controlled channels. This skill does NOT send email, upload data externally, or contact third parties on its own.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass FoldAgent safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. No external sharing happens automatically from this skill.
2. Bundle export must pass safety preflight before persistence or handoff.
3. All materials remain research-only and require professional review.

See also: `skills/shared/safety_policy.md`

## Required FoldAgent API Endpoints

- `POST /safety/preflight` — Gate case-bundle export or save actions
- `GET /cases/{case_id}` — Verify case context
- `GET /cases/{case_id}/bundle` — Assemble full bundle payload for review
- `GET /cases/{case_id}/bundle/export?format=markdown|json` — Preview bundle export content
- `POST /cases/{case_id}/bundle/save?format=markdown|json` — Persist the bundle artifact
- `GET /cases/{case_id}/artifacts` — List saved artifacts available for handoff
- `GET /artifacts/file?path=...` — Download a specific saved artifact

## Required User Confirmation Points

1. Before exporting a bundle for professional handoff.
2. Before saving or downloading artifacts intended for external sharing.

## Expected Output Artifact

A structured output package containing:
- Case bundle summary with inventory, reports, audit, and pipeline context.
- Markdown or JSON export preview.
- Saved artifact path and content hash when persisted.
- Research-only safety labels ready for handoff packaging.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` before bundle export or save actions.

2. **Verify case**: Call `GET /cases/{case_id}` and confirm the handoff target exists.

3. **Assemble bundle**: Call `GET /cases/{case_id}/bundle` and inspect whether required reports or artifacts are missing.

4. **Preview export**: Call `GET /cases/{case_id}/bundle/export?format=...` to show the outbound package content without persisting it yet.

5. **Persist approved bundle**: After explicit confirmation, call `POST /cases/{case_id}/bundle/save?format=...` and capture the saved artifact path.

6. **Prepare handoff summary**: List relevant artifacts with hashes and remind the user that any external outreach must remain human-controlled.

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

- Log every bundle preview and bundle save action.
- Log artifact ids, paths, and content hashes used in the handoff summary.
- Log safety-preflight outcomes before any export step.

## Failure Handling

- If bundle export is blocked by safety policy, stop and report the exact reason.
- If prerequisite reports or artifacts are missing, report those gaps instead of building a misleading handoff package.
- If artifact download fails, provide the failing path and stop rather than substituting another file silently.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
