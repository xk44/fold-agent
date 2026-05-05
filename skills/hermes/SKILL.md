---
name: neovax-hermes
description: Hermes agent skill pack for the NeoVax neoantigen vaccine pipeline. Provides memory-seeded, audit-integrated skills for pipeline execution, candidate review, report generation, and safety assessment under mandatory expert oversight.
version: 1.0.0
license: Apache-2.0
framework: Hermes
install_path: ~/.hermes/skills/neovax-hermes/
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - oncology-research
  - pipeline
  - neoantigen
  - safety-gated
---

# NeoVax Hermes Skill Pack

> **Safety Disclaimer**: This skill pack coordinates research workflow only.
> It does NOT provide medical advice, treatment recommendations, dosing
> instructions, formulation guidance, or manufacturing instructions. All
> outputs require review by a licensed professional (veterinarian or
> physician) before any real-world action is taken. Never use pipeline
> outputs to make treatment decisions without expert supervision.

## Overview

The `neovax-hermes` skill pack exposes the NeoVax neoantigen pipeline to
Hermes agents as memory-seeded, audit-integrated skills. Hermes agents
maintain a case memory seed between skill invocations so context (case ID,
species mode, safety posture) is preserved across steps.

## Available Skills

| Skill directory                            | Purpose                              |
| ------------------------------------------ | ------------------------------------ |
| `run_bioinformatics_pipeline/`             | Execute BWA, Mutect2, VEP, NetMHCpan |
| `run_full_neovax_case_review/`             | End-to-end case review orchestrator  |
| `organize_case_data/`                      | Case, subject, and sample setup      |
| `generate_candidate_review_report/`        | Candidate report generation          |
| `get_alphafold_structures/`                | AlphaFold structure prediction       |
| `create_ethics_review_package/`            | Ethics/IRB package generation        |
| `coordinate_licensed_lab_outreach/`        | Lab contact and outreach             |
| `monitor_case_progress/`                   | Case and job status monitoring       |
| `autoresearch_optimize_software_pipeline/` | Pipeline adapter optimization        |

## Key API Endpoints Used Across Skills

- `POST /safety/preflight` — Mandatory gate before all write operations
- `POST /cases` — Case creation
- `POST /cases/{case_id}/pipeline/run` — Synchronous pipeline
- `POST /cases/{case_id}/pipeline/run-async` — Async pipeline
- `GET /cases/{case_id}/candidates` — Candidate retrieval
- `GET /cases/{case_id}/evidence` — Evidence retrieval
- `POST /cases/{case_id}/reports/candidate-review` — Report generation
- `GET /audit/{case_id}` — Audit trail review
- `ws://…/agent/events/ws` — Real-time event streaming

## Hermes Memory Seed (Default Template)

Each skill reads and updates these memory fields at invocation:

```yaml
case_id: null # Active case UUID
species_mode: null # e.g., canis_lupus_familiaris
safety_posture: null # demo | approval-required | blocked
supervising_professional: null
last_pipeline_run_id: null
last_job_id: null
last_report_id: null
open_blockers: []
```

## Audit Integration

All skills emit structured audit events via `log_action`. The audit trail
is readable at `GET /audit/{case_id}` and exportable via `GET /audit/export`.
Skills treat the NeoVax audit trail as the authoritative record — no
side-channel logging replaces it.

## Installation

See `install.md` for installation instructions.

## Self-Improvement Guardrails

See `emergent_improvements.md` for allowed and prohibited self-improvement
patterns. Skills must never self-improve into generating treatment,
dosing, formulation, or manufacturing output.

## No Medical Advice Warning

This skill pack coordinates research workflow only. It does NOT provide
medical advice, veterinary advice, treatment recommendations, dosing
instructions, or manufacturing guidance. Every output requires review by
a licensed professional. No output from this skill pack should be used
to make treatment decisions.
