# Claude Code Skills Install Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical
> advice, treatment instructions, or administerable outputs.**

---

## Overview

The `neovax-pipeline` Claude Code skill gives Claude Code agents structured,
safety-gated access to the NeoVax API. It wraps the full pipeline
(BWA → Mutect2 → VEP → NetMHCpan) and AlphaFold backends behind audited API
calls with mandatory confirmation points.

---

## Prerequisites

- Claude Code installed and authenticated
- NeoVax API running (`make dev`, default: `http://127.0.0.1:8010`)
- Python 3.11+ with `httpx` and `pydantic` (`pip install httpx pydantic`)

---

## Installation

### Option A — Copy to user skills directory

```bash
cp -r /path/to/neovax/skills/claude-code ~/.claude/skills/neovax-pipeline
mkdir -p ~/.claude/skills/neovax-pipeline/shared
cp /path/to/neovax/skills/shared/neovax_client.py \
   /path/to/neovax/skills/shared/event_stream_client.py \
   /path/to/neovax/skills/shared/safety_policy.md \
   ~/.claude/skills/neovax-pipeline/shared/
```

### Option B — Copy to project `.claude/skills/`

```bash
mkdir -p .claude/skills
cp -r skills/claude-code .claude/skills/neovax-pipeline
mkdir -p .claude/skills/neovax-pipeline/shared
cp skills/shared/neovax_client.py \
   skills/shared/event_stream_client.py \
   skills/shared/safety_policy.md \
   .claude/skills/neovax-pipeline/shared/
```

### Option C — Symlink for active development

```bash
ln -s "$(pwd)/skills/claude-code" ~/.claude/skills/neovax-pipeline
ln -s "$(pwd)/skills/shared" ~/.claude/skills/neovax-pipeline/shared
```

---

## Environment

```bash
export NEOVAX_API_URL="http://127.0.0.1:8010"
# For auth-protected deployments:
# export NEOVAX_API_TOKEN="<token>"
```

---

## Available Actions

| Action              | File                           | Endpoint                                    |
| ------------------- | ------------------------------ | ------------------------------------------- |
| `create_case`       | `actions/create_case.md`       | `POST /cases`                               |
| `run_pipeline`      | `actions/run_pipeline.md`      | `POST /cases/{id}/pipeline/run`             |
| `review_candidates` | `actions/review_candidates.md` | `GET /cases/{id}/candidates`                |
| `generate_report`   | `actions/generate_report.md`   | `POST /cases/{id}/reports/candidate-review` |
| `check_safety`      | `actions/check_safety.md`      | `POST /safety/preflight`                    |

Full skill descriptions for all 9 workflow skills are in `skills/claude-code/*/SKILL.md`.
See [docs/AGENT_SKILLS_GUIDE.md](AGENT_SKILLS_GUIDE.md) for the complete list.

---

## Example Prompts

```
# Create a canine osteosarcoma case
"Create a new NeoVax case for a canine patient with osteosarcoma.
Supervising vet is Dr. Smith."

# Run the pipeline
"Run the neoantigen pipeline for case abc-123."

# Review top candidates
"Show the top-ranked neoantigen candidates for case abc-123
with binding affinities."

# Generate a report for expert review
"Generate a candidate review report for case abc-123
ready for Dr. Smith."

# Safety preflight before export
"Run a safety preflight check before exporting case abc-123 results."

# Full end-to-end review
"Run a full NeoVax case review for case abc-123 in dog mode."
```

---

## Safety Notes

- Safety is enforced **server-side**. Claude Code skill instructions cannot
  override the preflight system — a blocked action returns an error regardless.
- The skill requires **explicit user confirmation** before pipeline runs,
  report generation, and exports.
- Every action is logged to the NeoVax audit trail (`GET /audit/{case_id}`).
- Skills must **not** be modified to widen medical-output scope. The
  self-improvement guardrails in each `SKILL.md` are mandatory.
- Do not install on an agent configured for auto-execution without human
  confirmation.

See [docs/SAFETY_GUIDE.md](SAFETY_GUIDE.md) and
`skills/shared/safety_policy.md` for the full safety policy.
