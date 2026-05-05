# Agent Skills Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

Agent skills are structured workflow definitions that guide AI agents (Claude Code, OpenClaw, Hermes) through NeoVax-Agent API operations safely. Each skill is a `SKILL.md` file that specifies required API endpoints, confirmation points, safety boundaries, and audit logging requirements.

Skills live under `skills/{framework}/` and share a common client and safety policy:

```
skills/
  claude-code/     — Claude Code skill definitions
  openclaw/        — OpenClaw skill definitions
  hermes/          — Hermes skill definitions (includes ENRICHMENT_TEMPLATE.md)
  shared/
    neovax_client.py       — Shared HTTP client for the NeoVax API
    event_stream_client.py — SSE event stream client
    safety_policy.md       — Canonical safety rules for all agents
    openapi.json           — NeoVax OpenAPI spec for agent tool use
    report_templates/      — Shared report template stubs
    tests/                 — Shared skill integration tests
```

---

## The 9 Skill Packs

Each framework directory contains the same 9 skills:

| Skill                                     | Purpose                                               |
| ----------------------------------------- | ----------------------------------------------------- |
| `run_full_neovax_case_review`             | End-to-end case review orchestration                  |
| `run_bioinformatics_pipeline`             | Launch, inspect, and summarize pipeline runs          |
| `get_alphafold_structures`                | Backend diagnostics, dry-runs, structure jobs         |
| `generate_candidate_review_report`        | Generate and export candidate review reports          |
| `create_ethics_review_package`            | Generate consent/oversight ethics packages            |
| `organize_case_data`                      | Data loading, validation, sample/variant registration |
| `monitor_case_progress`                   | Poll job status, surface blockers, report progress    |
| `coordinate_licensed_lab_outreach`        | Lab contacts, cost tracking, outreach templates       |
| `autoresearch_optimize_software_pipeline` | Pipeline performance and configuration review         |

---

## Skill Structure

Every `SKILL.md` file contains:

- **Metadata header** — name, version, framework, tags, audit log integration flag
- **When to Use / When NOT to Use** — explicit inclusion and exclusion criteria
- **Safety Boundaries** — numbered list of hard limits specific to this skill
- **Required NeoVax API Endpoints** — exact endpoints the skill may call
- **Required User Confirmation Points** — numbered list of actions requiring explicit user approval before proceeding
- **Expected Output Artifact** — what the skill produces
- **Steps** — numbered workflow steps
- **Claude Code Context Seed Template** — what context to carry between steps
- **Self-Improvement Guardrails** — explicit prohibitions on widening medical-output scope
- **Audit Log Integration Notes** — how to treat the audit trail
- **Logging Requirements** — what must be logged
- **Failure Handling** — how to surface errors without inventing content
- **No Medical Advice Warning** — mandatory disclaimer repeated at the end of every skill

---

## Shared Safety Policy

All skills must comply with `skills/shared/safety_policy.md`. The 10 canonical rules:

1. Never generate prohibited outputs (dosing, injection, LNP formulation, manufacturing, self-treatment)
2. Always include safety labels on significant outputs
3. Always run `POST /safety/preflight` before writes, exports, or significant actions
4. Always log actions to the audit trail via the NeoVax API
5. Always request user confirmation before pipeline runs, report generation, and exports
6. Never bypass the API — never modify data directly
7. Respect mode restrictions: demo (synthetic only), dog (vet oversight), human (physician + IRB)
8. Surface uncertainty — always report flags, missing data, and model limitations
9. Professional review required — never suggest output is ready for clinical use
10. No self-modification into dangerous outputs — skills must not modify themselves to bypass safety gates

These rules apply equally across Claude Code, OpenClaw, and Hermes. Framework differences are in invocation syntax only.

---

## Shared Client (`neovax_client.py`)

All skills use the shared client in `skills/shared/neovax_client.py` for HTTP communication with the NeoVax API. The client handles:

- Base URL configuration (default: `http://localhost:8010`)
- Common headers and error handling
- Preflight calls before writes
- Audit log submission

The event stream client (`event_stream_client.py`) provides SSE subscription for monitoring async job progress via `GET /events` or the WebSocket endpoint.

---

## Framework-Specific Notes

### Claude Code

Skills in `skills/claude-code/` are invoked as slash commands or described in `CLAUDE.md` task prompts. Claude Code reads the `SKILL.md`, follows the steps, and uses the NeoVax API via the shared client or direct HTTP tool calls.

The **Context Seed Template** section in each skill tells Claude Code what state to carry in memory between steps (case ID, species mode, safety posture, open blockers, recent artifact IDs).

### OpenClaw

Skills in `skills/openclaw/` follow the same structure. OpenClaw uses its own tool-calling mechanism but the same API endpoints and safety rules.

### Hermes

Skills in `skills/hermes/` include an additional `ENRICHMENT_TEMPLATE.md` at the framework level. This template guides Hermes in structuring enriched outputs (e.g. report summaries with structured metadata). The same safety boundaries apply.

---

## How to Add a New Skill

1. Create the skill directory in all three framework folders:

   ```
   skills/claude-code/my_new_skill/SKILL.md
   skills/openclaw/my_new_skill/SKILL.md
   skills/hermes/my_new_skill/SKILL.md
   ```

2. Use the existing `SKILL.md` files as templates. Required sections:
   - Metadata YAML header
   - When to Use / When NOT to Use
   - Safety Boundaries (reference `skills/shared/safety_policy.md`)
   - Required NeoVax API Endpoints
   - Required User Confirmation Points
   - Steps
   - Self-Improvement Guardrails
   - No Medical Advice Warning

3. Ensure the skill:
   - Calls `POST /safety/preflight` before any write or export action
   - Pauses for explicit user confirmation at each confirmation point
   - Logs all significant actions via the audit trail
   - Never produces prohibited outputs (see safety policy rule 1)
   - Carries the "research only" safety label on every significant output

4. Add integration tests under `skills/shared/tests/`.

5. Do not add skills that widen the medical-output scope beyond research coordination. The self-improvement guardrails section must explicitly prohibit the skill from adapting itself into treatment, dosing, formulation, or manufacturing output generation.

---

## Safety Enforcement in Skills

Skills are not code — they are instructions. Safety is enforced by:

1. The NeoVax API's preflight system (server-side, cannot be bypassed by skill instructions)
2. The skill's own confirmation points (agent must pause and ask the user)
3. The shared safety policy (defines what the agent must refuse regardless of user request)
4. Audit logging (every action is recorded; deviations are traceable)

If a skill step produces a preflight `BLOCK`, the skill must stop and report the exact structured reason. It must not paraphrase the block reason into something weaker or suggest workarounds.
