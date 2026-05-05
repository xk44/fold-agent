---
name: monitor_case_progress
description: Summarize FoldAgent operational progress, blockers, and next steps for a case without changing scientific conclusions.
version: 0.2.0
license: Apache-2.0
framework: Claude Code
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - ops-monitoring
  - case-progress
  - safety-gated
---

# Monitor Case Progress

## When to Use

Use this skill when an operator needs a current-status snapshot of one FoldAgent case across tasks, jobs, reports, and audit activity. It is the operational monitoring skill for identifying blockers and next actions. This skill does NOT alter scientific results or make treatment recommendations.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass FoldAgent safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Monitoring summaries must stay descriptive, not prescriptive.
2. Escalation or retry actions on real data still require safety gating and confirmation.
3. Do not reinterpret blocked or failed states as success.

See also: `skills/shared/safety_policy.md`

## Required FoldAgent API Endpoints

- `GET /cases/{case_id}` — Retrieve high-level case metadata
- `GET /cases/{case_id}/tasks` — Inspect coordination tasks
- `GET /cases/{case_id}/agent-tasks` — Inspect agent work state
- `GET /cases/{case_id}/samples` — Inspect data inventory progress
- `GET /cases/{case_id}/variants` — Inspect variant analysis progress
- `GET /cases/{case_id}/candidates` — Inspect candidate review progress
- `GET /cases/{case_id}/reports` — Inspect report generation progress
- `GET /cases/{case_id}/structure-jobs` — Inspect structure evidence progress
- `GET /cases/{case_id}/pipeline/status` — Inspect current pipeline state
- `GET /cases/{case_id}/pipeline/history` — Inspect prior pipeline runs
- `GET /jobs?case_id={case_id}` — Inspect background jobs
- `GET /audit/{case_id}` — Inspect audit trail and blockers

## Required User Confirmation Points

1. Before retrying failed work or escalating blocked tasks on real data.

## Expected Output Artifact

A structured output package containing:
- Case progress summary with completed, running, failed, and blocked work.
- Blocker list tied to tasks, jobs, reports, or safety gates.
- Recommended next operational actions requiring human approval when needed.

## Steps

1. **Load case context**: Call `GET /cases/{case_id}` to anchor the monitoring summary.

2. **Inspect workflow state**: Call tasks, agent-task, pipeline, report, structure-job, and job endpoints to collect operational status.

3. **Inspect audit trail**: Call `GET /audit/{case_id}` to identify blocked, failed, or recently completed actions.

4. **Identify blockers**: Separate missing-data, failed-job, safety-blocked, and pending-review blockers in the summary.

5. **Recommend next ops steps**: Provide concrete operational next actions while clearly marking any step that still needs approval or safety gating.

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

- Treat the FoldAgent audit trail as the source of truth for actions taken.
- Prefer endpoints that already emit audit events over ad hoc side channels.
- When blocked, preserve the exact structured reason instead of paraphrasing it into something weaker.

## Logging Requirements

- Log every monitoring sweep with timestamps and case context.
- Log the blockers surfaced so the audit trail shows what was reviewed.
- If a retry or escalation is proposed, log that as a recommendation rather than an executed action.

## Failure Handling

- If the case does not exist, stop and report the missing case id.
- If one status endpoint fails, report that surface as unavailable but keep other monitoring data separate.
- If audit data is unavailable, say so explicitly rather than inferring progress from partial state.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
