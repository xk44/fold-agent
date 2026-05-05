---
name: run_bioinformatics_pipeline
description: Run or inspect the NeoVax mock bioinformatics pipeline and summarize reproducible outputs under safety gating.
version: 0.2.0
license: Apache-2.0
framework: Claude Code
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - pipeline
  - bioinformatics
  - safety-gated
---

# Run Bioinformatics Pipeline

## When to Use

Use this skill when you need to launch, inspect, or summarize NeoVax pipeline execution for a case. It is the operational wrapper around synchronous runs, async background runs, adapter checks, and pipeline status/history review. This skill does NOT claim scientific validity beyond the currently available pipeline implementation and mode.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Pipeline execution on non-demo sequence-bearing data must pass safety preflight first.
2. Do not present mock or partial pipeline outputs as validated wet-lab conclusions.
3. Professional review is required before acting on pipeline findings.

See also: `skills/shared/safety_policy.md`

## Required NeoVax API Endpoints

- `POST /safety/preflight` — Gate pipeline execution or retry decisions
- `GET /cases/{case_id}` — Verify case and species mode
- `POST /cases/{case_id}/pipeline/run` — Run the pipeline synchronously
- `POST /cases/{case_id}/pipeline/run-async` — Dispatch a background pipeline job
- `GET /cases/{case_id}/pipeline/status` — Inspect current pipeline status
- `GET /cases/{case_id}/pipeline/history` — Review prior pipeline runs
- `GET /cases/{case_id}/executions` — Inspect execution artifacts and shell history
- `GET /pipeline/adapters` — Inspect available adapters and diagnostics
- `POST /pipeline/adapters/{adapter_name}/dry-run` — Preview adapter execution
- `POST /pipeline/adapters/{adapter_name}/run` — Run a specific adapter
- `GET /jobs/{job_id}` — Inspect async job state
- `POST /jobs/{job_id}/retry` — Retry a failed async job
- `POST /jobs/{job_id}/cancel` — Cancel a running async job when appropriate

## Required User Confirmation Points

1. Before starting or re-running the pipeline on non-demo data.
2. Before retrying a failed background job when real data is involved.

## Expected Output Artifact

A structured output package containing:
- Pipeline status summary with run mode and current state.
- Per-step status table including warnings and failures.
- Execution artifact inventory when available.
- Background-job identifiers for async runs.
- Research-only framing and professional-review reminder.

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` for the intended pipeline action. Stop on block; require approval if needed.

2. **Verify case**: Call `GET /cases/{case_id}` to confirm the target case and species mode.

3. **Choose execution mode**: Use `POST /cases/{case_id}/pipeline/run` for direct execution or `POST /cases/{case_id}/pipeline/run-async` for long-running work.

4. **Track status**: Call `GET /cases/{case_id}/pipeline/status`, `GET /jobs/{job_id}`, and `GET /cases/{case_id}/pipeline/history` to monitor progress and prior outcomes.

5. **Inspect artifacts**: Call `GET /cases/{case_id}/executions` and adapter dry-run/run endpoints when you need reproducibility or tool-specific detail.

6. **Summarize outcome**: Return a run summary that clearly distinguishes completed, failed, and blocked states without overstating biological meaning.

## Claude Code Context Seed Template

- Case id and species mode currently in scope.
- Current safety posture (demo, approval-required, or blocked).
- Open blockers or missing-data items relevant to this skill.
- Most recent report, pipeline, job, or artifact ids touched by this skill.

## Claude Code Self-Improvement Guardrails

- Do not self-improve the workflow into treatment, dosing, formulation, administration, or manufacturing output generation.
- Do not reinterpret research summaries as clinical validation or patient-specific advice.
- If a proposed automation change would widen medical-output scope, stop and escalate instead of adapting around the guardrail.

## Audit Log Integration Notes

- Treat the NeoVax audit trail as the source of truth for actions taken.
- Prefer endpoints that already emit audit events over ad hoc side channels.
- When blocked, preserve the exact structured reason instead of paraphrasing it into something weaker.

## Logging Requirements

- Log every pipeline start, async dispatch, retry, or cancellation decision.
- Log per-step failures and surfaced warnings when they exist in API results.
- Log job ids, execution ids, and artifact references used in the summary.
- Preserve all workflow changes through the NeoVax audit trail.

## Failure Handling

- If safety preflight blocks pipeline execution, report the exact safety reason and stop.
- If the case does not exist, stop and request the correct case id.
- If the pipeline status or async job reports failure, surface that failure instead of collapsing it into a generic success summary.
- If adapter validation fails, return the structured validation payload unchanged.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
