---
title: Emergent Skill Improvement Patterns — neovax-hermes
framework: Hermes
skill: neovax-hermes
version: 1.0.0
---

# Emergent Skill Improvement Patterns

This document defines allowed and prohibited self-improvement patterns for
Hermes agents operating NeoVax skills. Hermes agents may propose workflow
improvements based on observed execution patterns, but all changes are
subject to the guardrails below.

## What "Emergent Improvement" Means Here

Hermes agents can observe repeated patterns across skill invocations —
e.g., a step that consistently fails, an endpoint that returns empty results
before a prerequisite step completes, or a confirmation prompt that fires
for low-risk read-only operations. Agents may propose improvements to skill
step ordering, fallback logic, or output formatting based on these patterns.

This is distinct from agents autonomously modifying their own SKILL.md files,
which is **not permitted** without human review.

## Allowed Improvement Patterns

### 1. Step Ordering Optimisation

If an agent observes that `GET /cases/{case_id}/data/missing` consistently
returns missing files that block `POST /cases/{case_id}/pipeline/run`, it
may propose moving the data completeness check earlier in the workflow.

**Allowed**: Propose the reordering; surface the evidence; wait for human approval.

### 2. Polling Interval Tuning

If pipeline async jobs consistently complete in under 30 seconds, an agent
may propose reducing the poll interval for `GET /jobs/{job_id}` from 10s
to 5s for that case's species mode.

**Allowed**: Propose the tuning with supporting timing data; apply only after
human approval.

### 3. Output Format Enrichment

If users repeatedly ask for a specific field (e.g., `binding_affinity_rank_pct`)
not included in the default candidate summary, the agent may propose adding
that field to the output template.

**Allowed**: Propose the addition; do not change the output schema without
human approval.

### 4. Fallback Route Discovery

If a primary endpoint returns 503 and a documented fallback exists (e.g.,
`GET /cases/{case_id}/runs` as an alternative to `GET /cases/{case_id}/executions`),
the agent may note the fallback in its memory seed for future invocations.

**Allowed**: Record fallback in memory seed; surface to human for confirmation
before making it permanent.

### 5. Confirmation Prompt Reduction

If a read-only step (e.g., `GET /cases/{case_id}/candidates`) is generating
confirmation prompts due to a misconfigured Hermes policy, the agent may
flag the misconfiguration.

**Allowed**: Flag and propose the policy fix; never unilaterally suppress
safety confirmation prompts on write or preflight steps.

## Prohibited Improvement Patterns

The following self-improvement directions are **hard stops** regardless of
observed execution patterns. Agents must escalate to a human instead of
adapting around these guardrails.

### PROHIBITED: Widening Medical Output Scope

Any proposed change that would cause a skill to output treatment recommendations,
dosing instructions, formulation guidance, administration routes, or
manufacturing procedures is prohibited.

**If observed**: Stop. Do not implement. Escalate to the supervising
professional and the NeoVax project maintainer.

### PROHIBITED: Bypassing Safety Preflight

Any proposed change that removes, skips, or conditions-out `POST /safety/preflight`
calls on write or pipeline operations is prohibited.

**If observed**: Stop. Do not implement. Log the proposed change to the audit
trail with reason "prohibited_self_improvement".

### PROHIBITED: Reinterpreting Research Summaries as Clinical Validation

Any proposed change to output formatting that removes safety labels, removes
the "research only" framing, or presents computational predictions as clinical
findings is prohibited.

**If observed**: Stop. Do not implement. Surface the proposed change to a
human for review.

### PROHIBITED: Autonomous SKILL.md Modification

Agents must not autonomously edit, overwrite, or replace any `SKILL.md` file
in `~/.hermes/skills/neovax-hermes/`. All SKILL.md changes require human
review and version control.

### PROHIBITED: Expanding Audit-Bypass Paths

Any proposed change that routes actions through paths that do not emit
`log_action` audit events is prohibited.

## Escalation Path

When an agent encounters a potential improvement that is ambiguous — it might
fall into a prohibited category but the agent is uncertain — the correct
action is:

1. Stop the improvement proposal.
2. Log the observation to the NeoVax audit trail via `GET /audit/{case_id}`
   context note.
3. Surface the ambiguity to the supervising professional and a human reviewer.
4. Do not proceed until a human explicitly approves or rejects the change.

## Review Cycle

Proposed improvements that pass the guardrails above should be batched and
reviewed by a human maintainer on a regular cycle (recommended: per sprint
or per major case completion). Approved improvements are applied to the
canonical SKILL.md files in version control, not just to the local Hermes
install.
