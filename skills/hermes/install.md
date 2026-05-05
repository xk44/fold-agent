---
title: Installation — foldagent-hermes
framework: Hermes
skill: foldagent-hermes
version: 1.0.0
---

# Installing the foldagent-hermes Skill Pack

## Install Path

Hermes skills are installed under `~/.hermes/skills/`. Each skill in this
pack occupies its own subdirectory:

```
~/.hermes/skills/foldagent-hermes/
├── SKILL.md
├── install.md
├── emergent_improvements.md
├── audit_integration.md
├── run_bioinformatics_pipeline/
│   └── SKILL.md
├── run_full_foldagent_case_review/
│   └── SKILL.md
├── organize_case_data/
│   └── SKILL.md
├── generate_candidate_review_report/
│   └── SKILL.md
├── get_alphafold_structures/
│   └── SKILL.md
├── create_ethics_review_package/
│   └── SKILL.md
├── coordinate_licensed_lab_outreach/
│   └── SKILL.md
├── monitor_case_progress/
│   └── SKILL.md
└── autoresearch_optimize_software_pipeline/
    └── SKILL.md
```

## Prerequisites

- Hermes agent runtime installed and configured
- FoldAgent API accessible at `FOLDAGENT_API_URL` (default: `http://localhost:8000`)
- Python 3.11+ with `skills/shared/` dependencies installed:
  ```
  pip install httpx pydantic
  ```
- `skills/shared/foldagent_client.py` and `skills/shared/event_stream_client.py`
  symlinked or copied into `~/.hermes/skills/foldagent-hermes/shared/`

## Installation Steps

### Option A: Copy from project source

```bash
cp -r /path/to/foldagent/skills/hermes ~/.hermes/skills/foldagent-hermes
mkdir -p ~/.hermes/skills/foldagent-hermes/shared
cp /path/to/foldagent/skills/shared/foldagent_client.py \
   /path/to/foldagent/skills/shared/event_stream_client.py \
   /path/to/foldagent/skills/shared/safety_policy.md \
   ~/.hermes/skills/foldagent-hermes/shared/
```

### Option B: Symlink for active development

```bash
ln -s /path/to/foldagent/skills/hermes ~/.hermes/skills/foldagent-hermes
ln -s /path/to/foldagent/skills/shared ~/.hermes/skills/foldagent-hermes/shared
```

## Environment Configuration

Set the following environment variables before running Hermes with this pack:

```bash
export FOLDAGENT_API_URL="http://localhost:8000"
# For production deployments, set auth credentials:
# export FOLDAGENT_API_TOKEN="<token>"
```

## Verify Installation

After installing, confirm Hermes can discover the skills:

```bash
hermes skills list | grep foldagent
```

Expected output includes all 9 skill names (e.g., `run_bioinformatics_pipeline`,
`run_full_foldagent_case_review`, etc.).

## Updating

To update the skill pack, re-copy or re-symlink from the source. If using
Option A, remove the old install first:

```bash
rm -rf ~/.hermes/skills/foldagent-hermes
# Then repeat Option A steps above
```

## Uninstalling

```bash
rm -rf ~/.hermes/skills/foldagent-hermes
```

This does not affect the FoldAgent database, audit logs, or case data.

## Safety Note

Do not install this skill pack on a Hermes agent that has unrestricted
internet access or that is configured to auto-execute skills without human
confirmation. The skill pack requires human confirmation at all write
operations and safety-gated steps.
