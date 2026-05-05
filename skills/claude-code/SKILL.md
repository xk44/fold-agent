---
name: foldagent-pipeline
description: Claude Code skill for running the FoldAgent neoantigen vaccine pipeline. Coordinates case setup, data upload, pipeline execution, candidate review, report generation, and safety checks under mandatory expert oversight.
version: 1.0.0
license: Apache-2.0
framework: Claude Code
install_path: ~/.claude/skills/foldagent-pipeline/
tags:
  - foldagent
  - oncology-research
  - pipeline
  - neoantigen
  - safety-gated
---

# FoldAgent Pipeline Skill

> **Safety Disclaimer**: This skill coordinates research workflow only. It does NOT provide
> medical advice, treatment recommendations, dosing instructions, formulation guidance, or
> manufacturing instructions. All outputs require review by a licensed professional
> (veterinarian or physician) before any real-world action is taken. Never use pipeline
> outputs to make treatment decisions without expert supervision.

## Overview

The `foldagent-pipeline` skill gives Claude Code agents structured access to the FoldAgent
neoantigen vaccine pipeline API. It wraps BWA alignment, Mutect2 variant calling, VEP
annotation, NetMHCpan binding prediction, and AlphaFold structure prediction behind
safety-gated, audited API calls.

## Available Actions

| Action              | File                           | Primary Endpoint                                 |
| ------------------- | ------------------------------ | ------------------------------------------------ |
| `create_case`       | `actions/create_case.md`       | `POST /cases`                                    |
| `run_pipeline`      | `actions/run_pipeline.md`      | `POST /cases/{case_id}/pipeline/run`             |
| `review_candidates` | `actions/review_candidates.md` | `GET /cases/{case_id}/candidates`                |
| `generate_report`   | `actions/generate_report.md`   | `POST /cases/{case_id}/reports/candidate-review` |
| `check_safety`      | `actions/check_safety.md`      | `POST /safety/preflight`                         |

## Example Prompts

```
# Create a new canine osteosarcoma case
"Create a new FoldAgent case for a canine patient with osteosarcoma. Supervising
vet is Dr. Smith."

# Run the full pipeline
"Run the neoantigen pipeline for case abc-123."

# Review top candidates
"Show me the top-ranked neoantigen candidates for case abc-123 with their
binding affinities."

# Generate expert review report
"Generate a candidate review report for case abc-123 ready for Dr. Smith."

# Safety check before sharing
"Run a safety preflight check before exporting case abc-123 results."
```

## Prerequisites

- FoldAgent API running at `http://localhost:8010` (or configured `FOLDAGENT_API_URL`)
- Case must be created before running pipeline
- Safety preflight must pass before pipeline execution on non-demo data
- Licensed professional must be named as `supervising_professional` on each case

## Research Modes

FoldAgent supports 9 research modes, selectable via `GET /modes` and `POST /modes/{mode}/check`:

| Mode                    | Description                                 |
| ----------------------- | ------------------------------------------- |
| `neoantigen`            | Neoantigen vaccine pipeline (default)       |
| `variant_pathogenicity` | Variant pathogenicity assessment            |
| `drug_discovery`        | Small molecule and drug target discovery    |
| `vaccine_design`        | Broader vaccine antigen design              |
| `antibody_design`       | Antibody and nanobody design                |
| `gene_therapy`          | Gene therapy target and vector analysis     |
| `ppi_mapping`           | Protein-protein interaction mapping         |
| `enzyme_engineering`    | Enzyme function and engineering analysis    |
| `protein_misfolding`    | Protein misfolding and aggregation research |

## Shared Utilities

- `skills/shared/foldagent_client.py` — FoldAgent API client with auth and retry
- `skills/shared/event_stream_client.py` — SSE/WebSocket event streaming
- `skills/shared/safety_policy.md` — Full safety policy reference

## Audit Trail

Every action taken through this skill is logged to the FoldAgent audit trail via
`GET /audit/{case_id}` and `GET /audit/export`. Do not bypass the audit trail.

## No Medical Advice Warning

This skill coordinates research workflow only. It does NOT provide medical advice,
veterinary advice, treatment recommendations, dosing instructions, or manufacturing
guidance. Every output requires review by a licensed professional. No output from
this skill should be used to make treatment decisions.
