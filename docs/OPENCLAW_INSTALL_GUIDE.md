# OpenClaw Skills Install Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical
> advice, treatment instructions, or administerable outputs.**

---

## Overview

The `neovax-openclaw` skill pack exposes the NeoVax pipeline to OpenClaw agents
as structured YAML task definitions. Tasks support synchronous REST calls and
real-time event streaming via WebSocket (`ws://…/agent/events/ws`).

---

## Prerequisites

- OpenClaw runtime installed and configured
- NeoVax API running (`make dev`, default: `http://127.0.0.1:8010`)
- Python 3.11+ with `httpx` and `pydantic` (`pip install httpx pydantic`)
- TLS reverse proxy if deploying beyond localhost (see OPSEC checklist)

---

## Installation

### Option A — Copy to OpenClaw skills directory

```bash
cp -r /path/to/neovax/skills/openclaw ~/.openclaw/skills/neovax-openclaw
mkdir -p ~/.openclaw/skills/neovax-openclaw/shared
cp /path/to/neovax/skills/shared/neovax_client.py \
   /path/to/neovax/skills/shared/event_stream_client.py \
   /path/to/neovax/skills/shared/safety_policy.md \
   ~/.openclaw/skills/neovax-openclaw/shared/
```

### Option B — Symlink for active development

```bash
ln -s "$(pwd)/skills/openclaw" ~/.openclaw/skills/neovax-openclaw
ln -s "$(pwd)/skills/shared" ~/.openclaw/skills/neovax-openclaw/shared
```

### Load the skill pack

```bash
openclaw skills load ~/.openclaw/skills/neovax-openclaw
openclaw skills list | grep neovax
```

---

## Configure WebSocket Endpoint

In your OpenClaw agent config, set:

```yaml
neovax_api_url: "http://127.0.0.1:8010"
neovax_ws_url: "ws://127.0.0.1:8010/agent/events/ws"
# For auth-protected deployments:
# neovax_api_token: "${NEOVAX_API_TOKEN}"
```

Never hardcode tokens in YAML files. Inject via environment variable or
secrets manager.

---

## Available Tasks

| Task               | File                          | Purpose                                   |
| ------------------ | ----------------------------- | ----------------------------------------- |
| `pipeline_run`     | `tasks/pipeline_run.yaml`     | Execute the full bioinformatics pipeline  |
| `candidate_review` | `tasks/candidate_review.yaml` | Review and annotate neoantigen candidates |
| `safety_check`     | `tasks/safety_check.yaml`     | Run safety preflight and risk assessment  |

Full workflow skills (9 total) are defined in `skills/openclaw/*/SKILL.md`.
See [docs/AGENT_SKILLS_GUIDE.md](AGENT_SKILLS_GUIDE.md) for the complete list.

---

## Key API Endpoints

| Endpoint                              | Purpose                               |
| ------------------------------------- | ------------------------------------- |
| `POST /safety/preflight`              | Mandatory gate before all write tasks |
| `POST /cases`                         | Create a case                         |
| `POST /cases/{id}/pipeline/run`       | Synchronous pipeline run              |
| `POST /cases/{id}/pipeline/run-async` | Async pipeline with job tracking      |
| `GET /cases/{id}/candidates`          | Candidate list with scores            |
| `GET /agent/events`                   | SSE event stream snapshot             |
| `ws://…/agent/events/ws`              | Real-time WebSocket event stream      |

---

## OPSEC Checklist

Before deploying beyond a local dev machine, complete
`skills/openclaw/OPSEC_CHECKLIST.md`. Key items:

- No API keys or tokens hardcoded in task YAML files
- `NEOVAX_API_URL` and auth injected via environment variables
- NeoVax API not exposed to untrusted networks without auth
- WebSocket endpoint behind reverse proxy with token auth in production
- TLS enforced for all production API connections
- `POST /safety/preflight` confirmed present in all deployed task files
- Audit trail accessible to supervising professional

Before publishing to ClawHub, complete `skills/openclaw/CLAWHUB_CHECKLIST.md`.

---

## Safety Notes

- Safety is enforced **server-side**. Task YAML instructions cannot bypass the
  preflight system.
- Every task must call `POST /safety/preflight` before pipeline runs, report
  generation, or data exports.
- All executions emit audit events readable at `GET /audit/{case_id}`.
- Do not install on an agent with unrestricted internet access or auto-execution
  without human confirmation.

See [docs/SAFETY_GUIDE.md](SAFETY_GUIDE.md) and
`skills/shared/safety_policy.md` for the full safety policy.
