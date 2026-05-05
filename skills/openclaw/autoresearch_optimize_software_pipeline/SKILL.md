---
name: autoresearch_optimize_software_pipeline
description: Use NeoVax operational data to improve the software workflow, eval harnesses, and agent automation without drifting into unsafe medical outputs.
version: 0.2.0
license: Apache-2.0
framework: OpenClaw
install_path: ~/.openclaw/skills/<skill_name>
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - software-optimization
  - agent-ops
  - safety-gated
---

# Autoresearch Optimize Software Pipeline

## When to Use

Use this skill when improving NeoVax software behavior, orchestration, eval loops, or agent task setup based on observed workflow friction. It is for software optimization, not biological optimization. This skill must never self-improve into unsafe medical-output generation or bypass NeoVax safety controls.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Optimization scope is limited to software workflow, tooling, evals, and automation.
2. Do not transform the system toward unsafe medical-output generation.
3. All automated experiments that touch real case operations must remain safety-gated.

See also: `skills/shared/safety_policy.md`

## Required NeoVax API Endpoints

- `POST /safety/preflight` — Gate automation or agent-task creation when needed
- `GET /health` — Check API availability
- `GET /version` — Check environment and mode metadata
- `GET /agent/skills` — Inspect currently registered skills
- `POST /agent/tasks/dry-run` — Preview agent task creation without persisting it
- `POST /agent/tasks` — Create an agent task when approved
- `GET /agent/tasks/{task_id}` — Inspect one agent task
- `GET /agent/events` — Inspect current event stream snapshot
- `GET /jobs/{job_id}` — Inspect background job outcomes
- `GET /pipeline/adapters` — Inspect adapter capabilities
- `POST /pipeline/adapters/{adapter_name}/dry-run` — Preview adapter behavior safely
- `GET /audit/{case_id}` — Inspect workflow history for optimization signals

## Required User Confirmation Points

1. Before launching large automation loops or persistent agent tasks.
2. Before any optimization experiment that touches real case operations.

## Expected Output Artifact

A structured output package containing:
- Software-optimization memo with observed friction points.
- Safe automation or agent-task dry-run plan.
- Concrete follow-up actions scoped to tooling and orchestration only.
- Explicit statement that medical-output policy remains unchanged.

## Steps

1. **Scope safety first**: Call `POST /safety/preflight` when the optimization plan would create agent tasks or run workflow actions.

2. **Inspect current system state**: Call `GET /health`, `GET /version`, and `GET /agent/skills` to understand the current environment and tool surface.

3. **Review evidence**: Use audit, event, job, and adapter endpoints to identify software bottlenecks, flaky flows, or missing automation.

4. **Dry-run automation**: Use `POST /agent/tasks/dry-run` before creating any real agent task or optimization experiment.

5. **Propose safe improvements**: Return software-only changes, eval plans, or orchestration follow-through without drifting into biological treatment logic.

6. **Final guardrail check**: State explicitly that the optimization does not authorize unsafe medical-output generation or bypass safety policy.

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

- Log every optimization observation with the case or system surface it came from.
- Log every dry-run versus real agent-task decision separately.
- Log explicit confirmation that medical-output boundaries were preserved.

## Failure Handling

- If the system is unhealthy, stop and report environment issues before proposing optimization work.
- If safety preflight blocks an automation step, stop and preserve the current boundary.
- If audit or event data is incomplete, note that the optimization recommendation is partial rather than inferred.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires licensed professional review before any real-world action.
