# Hermes Skills Install Guide

> **FoldAgent is a research coordination tool only. It does not provide medical
> advice, treatment instructions, or administerable outputs.**

---

## Overview

The `foldagent-hermes` skill pack exposes the FoldAgent pipeline to Hermes agents as
memory-seeded, audit-integrated skills. Hermes maintains a case memory seed
between skill invocations so context (case ID, species mode, safety posture)
is preserved across steps without re-prompting.

---

## Prerequisites

- Hermes agent runtime installed and configured
- FoldAgent API running (`make dev`, default: `http://127.0.0.1:8010`)
- Python 3.11+ with `httpx` and `pydantic` (`pip install httpx pydantic`)

---

## Installation

### Option A — Copy from project source

```bash
cp -r /path/to/foldagent/skills/hermes ~/.hermes/skills/foldagent-hermes
mkdir -p ~/.hermes/skills/foldagent-hermes/shared
cp /path/to/foldagent/skills/shared/foldagent_client.py \
   /path/to/foldagent/skills/shared/event_stream_client.py \
   /path/to/foldagent/skills/shared/safety_policy.md \
   ~/.hermes/skills/foldagent-hermes/shared/
```

### Option B — Symlink for active development

```bash
ln -s "$(pwd)/skills/hermes" ~/.hermes/skills/foldagent-hermes
ln -s "$(pwd)/skills/shared" ~/.hermes/skills/foldagent-hermes/shared
```

### Verify discovery

```bash
hermes skills list | grep foldagent
```

Expected: all 9 skill names listed (e.g. `run_bioinformatics_pipeline`,
`run_full_foldagent_case_review`, etc.).

---

## Environment

```bash
export FOLDAGENT_API_URL="http://127.0.0.1:8010"
# For auth-protected deployments:
# export FOLDAGENT_API_TOKEN="<token>"
```

---

## Available Skills

| Skill directory                            | Purpose                                    |
| ------------------------------------------ | ------------------------------------------ |
| `run_full_foldagent_case_review/`             | End-to-end case review orchestrator        |
| `run_bioinformatics_pipeline/`             | Execute BWA, Mutect2, VEP, NetMHCpan       |
| `organize_case_data/`                      | Case, subject, and sample setup            |
| `generate_candidate_review_report/`        | Candidate report generation                |
| `get_alphafold_structures/`                | AlphaFold structure prediction             |
| `create_ethics_review_package/`            | Ethics/IRB package generation              |
| `coordinate_licensed_lab_outreach/`        | Lab contact and outreach coordination      |
| `monitor_case_progress/`                   | Case and job status monitoring             |
| `autoresearch_optimize_software_pipeline/` | Pipeline adapter and workflow optimization |

See [docs/AGENT_SKILLS_GUIDE.md](AGENT_SKILLS_GUIDE.md) for full descriptions.

---

## Memory Seed

Each skill reads and writes these fields in Hermes memory between invocations:

```yaml
case_id: null # Active case UUID
species_mode: null # e.g. canis_lupus_familiaris
safety_posture: null # demo | approval-required | blocked
supervising_professional: null
last_pipeline_run_id: null
last_job_id: null
last_report_id: null
open_blockers: []
```

Set `case_id` and `species_mode` before invoking any skill on real case data.

---

## Audit Integration

All skills emit structured audit events via `log_action`. The audit trail is
the authoritative record — no side-channel logging replaces it.

- Read audit trail: `GET /audit/{case_id}`
- Export audit trail: `GET /audit/export`

See `skills/hermes/audit_integration.md` for full details on event schema and
retention requirements.

---

## Self-Improvement Guardrails

Skills must never self-improve into generating treatment, dosing, formulation,
or manufacturing output. Allowed and prohibited improvement patterns are
documented in `skills/hermes/emergent_improvements.md`. Review before making
any modifications to skill files.

---

## Updating / Uninstalling

```bash
# Update (Option A installs)
rm -rf ~/.hermes/skills/foldagent-hermes
# Then repeat Option A steps

# Uninstall
rm -rf ~/.hermes/skills/foldagent-hermes
```

Uninstalling does not affect the FoldAgent database, audit logs, or case data.

---

## Safety Notes

- Safety is enforced **server-side**. Hermes skill instructions cannot bypass
  the preflight system.
- Every write operation requires `POST /safety/preflight` first.
- Do not install on a Hermes agent configured for auto-execution without human
  confirmation at write steps.

See [docs/SAFETY_GUIDE.md](SAFETY_GUIDE.md) and
`skills/shared/safety_policy.md` for the full safety policy.
