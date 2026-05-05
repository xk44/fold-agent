# Autoresearch Safe Use Guide

> **CRITICAL SAFETY NOTICE**
>
> The autoresearch skill optimizes **software and pipeline tooling only**.
> It cannot and must not be used to optimize clinical outcomes, treatment
> selection, dosing, formulation, or any biological decision affecting a
> patient or animal. All outputs remain research-only and require licensed
> professional review.

---

## What Autoresearch Is

The `autoresearch_optimize_software_pipeline` skill uses FoldAgent operational
data (audit logs, job outcomes, adapter diagnostics) to improve the **software
workflow**: eval harnesses, agent task configuration, pipeline adapter
performance, and orchestration efficiency.

Concretely, it can:

- Identify slow or flaky pipeline adapter steps from job history
- Propose dry-run agent task configurations for review
- Review adapter capabilities and flag missing configuration
- Suggest eval loop improvements for mock/demo workflows
- Surface orchestration friction from audit trail patterns

---

## What Autoresearch Is Not

Autoresearch **cannot**:

- Optimize treatment selection or candidate ranking for clinical benefit
- Improve biological outcomes (binding affinity, immunogenicity, efficacy)
- Modify safety gates, preflight rules, or prohibited-output policies
- Replace or substitute for licensed professional judgment
- Produce dosing schedules, formulation parameters, or administration guidance

Any proposed change that would move the system toward biological optimization
or treatment output must be stopped and escalated — not worked around.

---

## Allowed vs Prohibited Metrics

| Allowed (software only)              | Prohibited                                    |
| ------------------------------------ | --------------------------------------------- |
| Pipeline step wall-clock time        | Predicted clinical response                   |
| Adapter dry-run success rate         | Candidate immunogenicity score optimization   |
| Job failure / retry rate             | Treatment outcome probability                 |
| API latency and error rates          | Dosing or formulation parameters              |
| Eval harness coverage                | Patient survival or remission metrics         |
| Agent task configuration correctness | Any metric derived from real patient outcomes |

If a proposed optimization references a prohibited metric, stop the experiment
and report it rather than proceeding.

---

## Running Experiments Safely

### 1. Scope check first

Before starting any autoresearch session, confirm:

- The optimization target is software/tooling only (not biological)
- No real patient or animal case data will be used as a training signal
- The experiment does not require modifying safety preflight rules

### 2. Use dry-run mode

Always use `POST /agent/tasks/dry-run` before creating real agent tasks.
Dry-run previews the task without persisting it or triggering side effects.

```bash
# Example: preview an agent task via the API
curl -X POST http://127.0.0.1:8010/agent/tasks/dry-run \
  -H "Content-Type: application/json" \
  -d '{"task_type": "pipeline_optimization", "case_id": null, "dry_run": true}'
```

### 3. Use a git sandbox

For experiments that modify pipeline adapter code or skill files:

```bash
git checkout -b autoresearch/experiment-$(date +%Y%m%d)
# make changes
# run evals
# review diff before merging
git diff main
```

Never commit autoresearch changes directly to `main` without review.
Changes that affect safety gate logic require explicit human sign-off.

### 4. Require user confirmation

The skill requires explicit user confirmation before:

- Launching large automation loops or persistent agent tasks
- Any experiment that touches real case operations (non-demo data)

Do not configure the agent to auto-confirm these steps.

### 5. Inspect results

After any autoresearch run, review:

- `GET /audit/{case_id}` — what actions were taken
- `GET /jobs/{job_id}` — job outcomes
- `GET /agent/tasks/{task_id}` — task results

Confirm the experiment stayed within software scope before applying any
changes to the main branch or production configuration.

---

## Git Sandbox Usage

Autoresearch experiments that touch code should always run in a branch:

```bash
# Create a sandbox branch
git checkout -b autoresearch/pipeline-timing-$(date +%Y%m%d)

# Run the experiment (mock mode, demo data only)
FOLDAGENT_PIPELINE_MODE=mock FOLDAGENT_SPECIES_MODE=demo make dev

# Review what changed
git diff

# Only merge if: software-only scope confirmed, safety gates intact,
# no prohibited metrics referenced
git checkout main
git merge --no-ff autoresearch/pipeline-timing-$(date +%Y%m%d)
```

---

## Self-Improvement Guardrails

The autoresearch skill's own `SKILL.md` contains explicit self-improvement
guardrails. Key rules:

1. Do not self-improve the workflow into treatment, dosing, formulation,
   administration, or manufacturing output generation.
2. Do not reinterpret research summaries as clinical validation or
   patient-specific advice.
3. If a proposed automation change would widen medical-output scope, stop
   and escalate instead of adapting around the guardrail.

These are not suggestions. A skill that violates them must be reverted.

---

## Safety Enforcement Chain

Autoresearch cannot bypass the FoldAgent safety system:

1. **Server-side preflight** (`POST /safety/preflight`) — blocks prohibited
   outputs regardless of skill instructions
2. **Unsafe text scanner** — catches prohibited patterns in generated content
3. **Audit trail** — every action logged; deviations are traceable
4. **Skill guardrails** — explicit prohibitions in `SKILL.md`

All four layers remain active during autoresearch sessions. Disabling any
layer (`FOLDAGENT_SAFETY_PREFLIGHT_ENABLED=false`) is prohibited during
autoresearch experiments.

---

## Summary

Autoresearch is a software engineering tool. It improves pipelines the way a
performance profiler or CI system does — by measuring and tuning code, not by
optimizing biological or clinical outcomes. Treat any drift toward clinical
optimization as a safety incident.

See also:

- `skills/claude-code/autoresearch_optimize_software_pipeline/SKILL.md`
- `skills/shared/safety_policy.md`
- [docs/SAFETY_GUIDE.md](SAFETY_GUIDE.md)
- [docs/DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
