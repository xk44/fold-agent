---
name: get_alphafold_structures
description: Inspect AlphaFold backend diagnostics, run safe dry-runs or executions, and summarize structure evidence for a FoldAgent case.
version: 0.2.0
license: Apache-2.0
framework: OpenClaw
install_path: ~/.openclaw/skills/<skill_name>
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - alphafold
  - structure-evidence
  - safety-gated
---

# Get AlphaFold Structures

## When to Use

Use this skill when a FoldAgent case needs structure evidence or backend diagnostics for AlphaFold-family runs. It handles backend inspection, dry-run preview, synchronous or async execution, and structure-job follow-through. This skill does NOT convert structure output into treatment instructions or bypass upload/privacy controls.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass FoldAgent safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. External-upload backends require explicit acknowledgement before submission.
2. Non-demo sequence-bearing AlphaFold work must pass safety preflight first.
3. Structure evidence is research-only and not clinical validation.
4. Respect backend validation failures and do not fabricate successful runs.

See also: `skills/shared/safety_policy.md`

## Required FoldAgent API Endpoints

- `POST /safety/preflight` — Gate sequence-bearing or external-upload structure actions
- `GET /alphafold/backends` — Inspect backend diagnostics and readiness
- `POST /alphafold/backends/{backend_name}/dry-run` — Preview backend command manifests safely
- `POST /alphafold/backends/{backend_name}/run` — Run a backend synchronously
- `POST /alphafold/backends/{backend_name}/run-async` — Dispatch a background AlphaFold job
- `GET /jobs/{job_id}` — Inspect async job state
- `GET /cases/{case_id}/structure-jobs` — List structure jobs linked to the case
- `GET /structure-jobs/{job_id}` — Inspect one structure job in detail

## Required User Confirmation Points

1. Before any external upload or privacy-sensitive backend use.
2. Before non-demo sequence-bearing structure execution.

## Expected Output Artifact

A structured output package containing:
- Backend diagnostics snapshot with readiness flags.
- Dry-run or execution summary with backend name and status.
- Structure-job linkage for the case and candidate.
- Confidence metrics and artifact references when available.
- Research-only safety labels and privacy caveats.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` with the correct sequence/upload flags before running any real structure action.

2. **Inspect backends**: Call `GET /alphafold/backends` and choose a backend based on validation, privacy requirements, and available capabilities.

3. **Dry-run first**: Call `POST /alphafold/backends/{backend_name}/dry-run` to preview the request and verify the payload shape.

4. **Run backend**: If approved, call the sync or async AlphaFold run endpoint and capture the returned status, validation details, and job ids.

5. **Track structure jobs**: Use `GET /cases/{case_id}/structure-jobs` and `GET /structure-jobs/{job_id}` to summarize structure evidence after execution.

6. **Report carefully**: Return backend status, confidence metrics, and artifact paths as research evidence only, never as treatment guidance.

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

- Treat the FoldAgent audit trail as the source of truth for actions taken.
- Prefer endpoints that already emit audit events over ad hoc side channels.
- When blocked, preserve the exact structured reason instead of paraphrasing it into something weaker.

## Logging Requirements

- Log the chosen backend, safety-preflight result, and whether external upload was involved.
- Log dry-run manifests separately from real execution results.
- Log async job ids and structure-job ids for later tracking.
- Preserve backend validation and failure payloads verbatim in the audit trail.

## Failure Handling

- If backend validation fails, surface the exact structured validation payload and stop.
- If safety preflight blocks the action, stop and report why.
- If async execution fails or times out, return the job id and failure state instead of claiming success.
- If no structure artifact is produced, mark the evidence as unavailable rather than inferred.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
