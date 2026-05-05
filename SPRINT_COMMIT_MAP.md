# NeoVax-Agent: First Sprint Commit Map

This file lists all files created in the initial sprint scaffold, organized
by the week-1 execution plan phases.

## Phase 0 — Governance, Safety, Source Registry

- README.md
- ETHICS.md
- SAFETY_POLICY.md
- DATA_PRIVACY.md
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- docs/source_registry.md
- .gitignore

## Phase 1 — Repo Scaffold + Developer Experience

- pyproject.toml
- Makefile
- docker-compose.yml
- config.example.yaml
- .env.example

## Phase 2 — Backend Core + Audit + Safety Gates

- backend/app/__init__.py
- backend/app/config.py
- backend/app/models.py
- backend/app/main.py
- backend/app/safety/__init__.py
- backend/app/safety/audit.py
- backend/app/safety/preflight.py

## Phase 3 — Mock Pipeline + Mock AlphaFold + Demo Data

- backend/app/pipeline/__init__.py
- backend/app/pipeline/base.py
- backend/app/alphafold/__init__.py
- backend/app/alphafold/base.py
- examples/synthetic_demo_case.json
- examples/synthetic_variants.vcf
- examples/mock_expert_review_report.md

## Phase 5 — Agent Skills (shared client + skill packs)

- skills/shared/neovax_client.py
- skills/shared/safety_policy.md
- skills/claude-code/run_full_neovax_case_review/SKILL.md

## Execution Plan

- WEEK1_EXECUTION_PLAN.md (this file's companion)
- SPRINT_COMMIT_MAP.md (this file)