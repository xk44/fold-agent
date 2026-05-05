---
name: foldagent-openclaw
description: OpenClaw skill pack for the FoldAgent neoantigen vaccine pipeline. Provides structured tasks for pipeline execution, candidate review, and safety assessment with real-time WebSocket event streaming.
version: 1.0.0
license: Apache-2.0
framework: OpenClaw
install_path: ~/.openclaw/skills/foldagent-openclaw/
memory_seed_template: default
audit_log_integration: required
tags:
  - foldagent
  - oncology-research
  - pipeline
  - neoantigen
  - safety-gated
---

# FoldAgent OpenClaw Skill Pack

> **Safety Disclaimer**: This skill pack coordinates research workflow only.
> It does NOT provide medical advice, treatment recommendations, dosing
> instructions, or manufacturing guidance. All outputs require review by a
> licensed professional before any real-world action is taken.

## Overview

The `foldagent-openclaw` skill pack exposes the FoldAgent pipeline to OpenClaw
agents as structured YAML task definitions. Tasks support synchronous REST
calls and real-time streaming via WebSocket (`ws://…/agent/events/ws`).

## Available Tasks

| Task               | File                          | Purpose                                   |
| ------------------ | ----------------------------- | ----------------------------------------- |
| `pipeline_run`     | `tasks/pipeline_run.yaml`     | Execute the full bioinformatics pipeline  |
| `candidate_review` | `tasks/candidate_review.yaml` | Review and annotate neoantigen candidates |
| `safety_check`     | `tasks/safety_check.yaml`     | Run safety preflight and risk assessment  |

## Shared Resources

- `skills/shared/foldagent_client.py` — API client with auth and retry
- `skills/shared/event_stream_client.py` — SSE/WebSocket event streaming
- `skills/shared/safety_policy.md` — Full safety policy reference
- `examples/websocket_usage.md` — Real-time streaming usage examples

## Key API Base Endpoints

- `POST /safety/preflight` — Safety gate (required before all write tasks)
- `POST /cases/{case_id}/pipeline/run` — Synchronous pipeline
- `POST /cases/{case_id}/pipeline/run-async` — Async pipeline with job tracking
- `GET /cases/{case_id}/candidates` — Candidate list with scores
- `GET /cases/{case_id}/evidence` — Supporting evidence
- `GET /agent/events` — SSE event stream
- `ws://…/agent/events/ws` — WebSocket event stream

## Security

See `OPSEC_CHECKLIST.md` for deployment security requirements.
See `CLAWHUB_CHECKLIST.md` for publication checklist before sharing to ClawHub.

## Audit Trail

All task executions emit audit events readable via `GET /audit/{case_id}`.
Do not bypass the FoldAgent audit trail.

## No Medical Advice Warning

This skill pack coordinates research workflow only. It does NOT provide
medical advice, veterinary advice, treatment recommendations, dosing
instructions, or manufacturing guidance. Every output requires review by
a licensed professional. No output should be used to make treatment decisions.
