# NeoVax-Agent: Week 1 Execution Plan

## Prioritized Phase Breakdown

This plan collapses the 22-phase master plan into a 7-day sprint that maximizes
progress toward a runnable local-first safety-gated research coordination
platform. The ordering principle: **mock everything, gate everything, then fill
in real implementations behind the mocks and gates.**

---

## IMMEDIATE (Day 1-2) -- Foundation + Safety + Source Registry

These are unblockable prerequisites. Everything else sits on top of them.
Created first because they define the legal and safety boundaries for the
entire project.

### D1.1 -- Repo scaffold

Create monorepo structure:

```
/backend
  /app
    /api
    /models
    /pipeline
    /alphafold
    /skills
    /safety
    /reports
  /migrations
  /tests
/frontend
  /app
/skills
  /shared
  /claude-code
  /openclaw
  /hermes
/docs
/examples
/research_modes
  /autoresearch
```

Create: pyproject.toml (Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic,
structlog), .gitignore, .env.example, config.example.yaml, Makefile, docker-
compose.yml (app + SQLite + Redis), ruff/mypy config.

### D1.2 -- Safety policy + governance documents

Create these files with substantive content (not stubs):

- `ETHICS.md` -- project ethics, prohibited outputs, mode restrictions
- `SAFETY_POLICY.md` -- hard "must not generate" list, export checkpoints,
  expert-only gates, audit requirements
- `DATA_PRIVACY.md` -- local-first default, encryption, retention, deletion
- `CONTRIBUTING.md` -- contributor covenant, safety review requirement
- `CODE_OF_CONDUCT.md`
- `README.md` -- project summary, safety banner, quickstart, mode descriptions,
  FAQ seed (Is this medical advice? No. Can this make a vaccine? No.)

### D1.3 -- Source registry

Create `docs/source_registry.md` with:
- Paul Conyngham links (X, GitHub, Rosie repo) with disclaimer that his repo
  is an autologous tumor-lysate protocol, not the exact mRNA neoantigen pipeline
- AlphaFold links (2, 3, Server, ColabFold, LocalColabFold)
- Bioinformatics tool links (BWA, GATK, VEP, pVACtools, NetMHCpan)
- Agent/skills links (Claude Code, OpenClaw, Hermes)
- Reporting links (UNSW, The Scientist, CNA, Fortune)
- Status tags: verified / related / third-party

### D1.4 -- Core Pydantic config model

Create `backend/app/config.py` with:
- Species mode enum (dog / human / demo)
- AlphaFold backend selector config
- Cloud-disabled-by-default settings
- Safety gate configuration

---

## PARALLEL BUILD (Day 2-3) -- Backend Core + Audit Logging + Safety Gates

With the scaffold and safety docs in place, build the backbone that every
feature will depend on: data models, audit logging, and the safety preflight
system.

### D2.1 -- SQLAlchemy models + Alembic

Implement all entities from the plan's Core Data Model (section 8):
- Case, Subject, Sample, Variant, CandidateAntigen, StructureJob, Report,
  AgentTask, AuditLog
- Use SQLite for dev (local-first default), PostgreSQL-ready
- Create initial Alembic migration

### D2.2 -- Audit logging system

Implement `backend/app/safety/audit.py`:
- `log_action(case_id, actor, action, inputs_hash, outputs_hash, safety_gate_result)`
- Append-only, tamper-evident design (hash chaining or signed entries)
- Every API write, every agent action, every export must log here
- Query endpoint: `GET /audit/{case_id}`

### D2.3 -- Safety preflight endpoint

Implement `backend/app/safety/preflight.py` and `POST /safety/preflight`:
- Checks proposed action against prohibited-outputs policy
- Returns pass / block / requires_expert_approval
- Integrates with audit log
- Policy loaded from SAFETY_POLICY.md or config

### D2.4 -- FastAPI app skeleton

Implement `backend/app/api/`:
- Health endpoints: `GET /health`, `GET /version`
- Case CRUD: `POST /cases`, `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}`
- Sample registration: `POST /cases/{id}/samples`, `GET /cases/{id}/samples`
- Wire up audit logging middleware

---

## MOCK-FIRST (Day 3-4) -- Mock Pipeline + Mock AlphaFold + Demo Mode

Now we can demonstrate the system end-to-end with no real bioinformatics tools
installed. Every subsequent real implementation replaces a mock behind the same
interface.

### D3.1 -- PipelineStep base class + MockPipeline

Create `backend/app/pipeline/`:
- `base.py` -- PipelineStep abstract base (name, version, run, validate,
  collect_outputs, requires_professional_review flag)
- `mock_steps.py` -- MockAlignment, MockVariantCalling, MockAnnotation,
  MockCandidatePrioritization
- Each mock step returns realistic-looking synthetic data with appropriate
  "not clinically validated" warnings baked in
- Pipeline orchestrator: run steps sequentially, log progress, capture
  reproducibility manifest

### D3.2 -- AlphaFoldBackend abstract class + MockAlphaFoldBackend

Create `backend/app/alphafold/`:
- `base.py` -- AlphaFoldBackend abstract class (name, version, mode, run_structure_prediction,
  validate_environment, estimate_cost, estimate_runtime, collect_outputs,
  supports_protein_only, supports_complexes, supports_rna_dna_ligands,
  requires_gpu, requires_external_upload, license_notes)
- `mock.py` -- MockAlphaFoldBackend returning fixture PDB/mmCIF with synthetic
  confidence scores
- Registry pattern: `get_backend(name)` returns the correct class
- API endpoints: `GET /alphafold/backends`, `POST /alphafold/jobs`,
  `GET /alphafold/jobs/{id}`, `GET /alphafold/jobs/{id}/files`
- Privacy gate: any backend with `requires_external_upload=True` triggers a
  confirmation prompt

### D3.3 -- Demo mode seed data + synthetic case

Create `examples/` with:
- `synthetic_demo_case.json` -- a demo dog case with fake but realistic data
- `synthetic_variants.vcf` -- toy VCF with a handful of variants
- `mock_alphafold_output/` -- fixture PDB files
- `mock_expert_review_report.md` -- sample output
- Seed script that creates a demo case via API

### D3.4 -- Variant + Candidate endpoints (mock-backed)

- `GET /cases/{id}/variants` -- returns mock variant table
- `GET /variants/{id}`, `PATCH /variants/{id}/review`
- `GET /cases/{id}/candidates` -- returns mock candidate antigens
- `GET /candidates/{id}`, `PATCH /candidates/{id}/review`
- Every response includes: "Research candidate only -- not administerable"
  and uncertainty flags

---

## REPORTING + GATES (Day 4-5) -- Reports + Ethics Package + Candidate Review

### D4.1 -- Candidate-antigen review report generator

Create `backend/app/reports/candidate_review.py`:
- Assembles variant table, prediction scores, expression evidence, MHC context,
  AlphaFold evidence, uncertainty flags, expert notes
- Every report has: source citations, model/tool version appendix,
  "not administerable" watermark
- Unsafe-output scanner: block any text matching dosing/injection/formulation
  patterns before export
- Endpoints: `POST /cases/{id}/reports/candidate-review`,
  `GET /reports/{id}`
- Export formats: JSON, Markdown (PDF later)

### D4.2 -- Ethics / veterinary review package generator

Create `backend/app/reports/ethics_package.py`:
- Veterinary owner consent template
- Human research consent template
- Data-ownership notice
- Genomic privacy notice
- Risk/benefit summary
- Professional oversight checklist
- Jurisdiction warning: "User must consult local regulations"
- Endpoints: `POST /cases/{id}/reports/ethics-package`

### D4.3 -- mRNA safety gate (placeholder)

Create `backend/app/safety/mrna_gate.py`:
- No direct mRNA design feature in MVP
- Placeholder for future expert-only sequence-level export
- Automatically block any export containing mRNA/text that matches
  manufacturing/dosing patterns
- Log every attempt

---

## AGENT LAYER (Day 5-6) -- Shared Client + Skill Packs

### D5.1 -- Shared NeoVax API client

Create `skills/shared/neovax_client.py`:
- Python client wrapping all API endpoints
- Safety policy built in: client-side preflight before dangerous actions
- Retry logic, error handling, idempotency keys
- OpenAPI spec at `skills/shared/openapi.json`

Create `skills/shared/safety_policy.md`:
- Canonical safety rules that all agent skills must follow
- "Not medical advice" declaration
- Prohibited output categories

Create `skills/shared/report_templates/`:
- Markdown templates for all report types

### D5.2 -- Claude Code skill packs

Create all 9 skills under `skills/claude-code/`:
- run_full_neovax_case_review/SKILL.md
- organize_case_data/SKILL.md
- run_bioinformatics_pipeline/SKILL.md
- get_alphafold_structures/SKILL.md
- generate_candidate_review_report/SKILL.md
- create_ethics_review_package/SKILL.md
- coordinate_licensed_lab_outreach/SKILL.md
- monitor_case_progress/SKILL.md
- autoresearch_optimize_software_pipeline/SKILL.md

Each SKILL.md includes: name, description, when to use, when NOT to use,
safety boundaries, required API endpoint, required user confirmation points,
expected output artifact, logging requirements, failure handling,
no-medical-advice warning.

### D5.3 -- OpenClaw skill packs

Port same 9 skills to `skills/openclaw/` with OpenClaw-specific frontmatter
and install path docs.

### D5.4 -- Hermes skill packs

Port same 9 skills to `skills/hermes/` with Hermes-specific format, plus:
- Memory seed template
- "Do not self-improve into unsafe medical outputs" policy
- Audit-log integration notes

### D5.5 -- Agent integration API layer

- WebSocket events: case.created, sample.uploaded, pipeline.started,
  pipeline.step.completed, pipeline.failed, alphafold.job.started/completed,
  report.generated, safety.blocked, expert.review.required
- `GET /agent/skills`, `POST /agent/tasks`, `GET /agent/tasks/{id}`
- Agent-safe error messages (no internal stack traces)
- Dry-run mode for all agent actions
- Audit trail for all agent actions

---

## DASHBOARD + DEMO (Day 6-7) -- Streamlit MVP + End-to-End Demo

### D6.1 -- Streamlit dashboard

Create `frontend/app/` with Streamlit pages:
- Case overview
- Upload wizard (file registration + metadata)
- Data inventory
- Pipeline status (shows mock pipeline running)
- Variant explorer (shows mock variants)
- Candidate-antigen review table (shows mock candidates)
- AlphaFold backend selector + structure gallery (shows mock PDB)
- Report builder (generates mock reports)
- Ethics package builder
- Safety policy page
- Audit log viewer
- Persistent warning banners on every page

### D6.2 -- End-to-end synthetic demo

- Run seed script to create a demo case
- Run mock pipeline end-to-end
- Run mock AlphaFold predictions
- Generate candidate-review report
- Generate ethics package
- Verify unsafe-output scanner blocks bad content
- Verify audit logging captures every action
- Verify agent API endpoints respond correctly

### D6.3 -- Tests

Create `backend/tests/`:
- Unit tests for models, config, safety gates, audit logging
- Mock pipeline tests
- Mock AlphaFold backend tests
- Candidate report tests
- Ethics package tests
- Unsafe-output blocking tests
- End-to-end synthetic demo test

---

## WHAT CAN WAIT (Post Week 1)

These items from the master plan are deferred because they depend on the week-1
foundation or are lower priority for getting a working demo:

| Item | Why it can wait |
|------|----------------|
| Real BWA/BWA-MEM2 wrapper | Mock pipeline is sufficient for demo |
| Real GATK Mutect2 wrapper | Same |
| Real Ensembl VEP wrapper | Same |
| Real pVACtools wrapper | Same |
| Real NetMHCpan/IIpan wrappers | Same |
| RNA expression validation adapter | Mock-only for now |
| MHC/HLA/DLA typing adapter | Mock-only for now |
| ColabFold backend | Mock backend first; real backend second |
| LocalColabFold backend | After ColabFold |
| AlphaFold2 local backend | Heavy setup; later |
| AlphaFold3 local backend | License/weight terms; later |
| AlphaFold Server backend | Privacy concerns need more review; later |
| Encryption at rest | Post-MVP hardening |
| External-upload confirmation gate | Basic gate exists; full UI later |
| File retention policy | Post-MVP |
| Data deletion workflow | Post-MVP hardening |
| Redaction pipeline | Post-MVP |
| Consent status tracker UI | Basic in model; full UI later |
| Next.js production frontend | Streamlit MVP first |
| NGL/py3Dmol structure viewer | Mock PDB display first |
| Clinical trial matching | Stretch goal |
| Veterinary trial matching | Stretch goal |
| Sequencing vendor API integration | Stretch goal |
| Federated learning | Far future |
| Expert-only mRNA sequence design | Locked behind policy gate; far future |
| Autoresearch integration | After software is stable enough to benchmark |

---

## WHAT TO MOCK FIRST (Priority Order)

Mocks are the fastest path to a demonstrable system. Build these interfaces
first, then swap implementations:

1. **MockPipeline** -- returns synthetic alignment + variant + annotation data
   so the entire case flow can run without any bioinformatics tools installed.
   This is the single highest-value mock.

2. **MockAlphaFoldBackend** -- returns fixture PDB/mmCIF files with synthetic
   confidence scores. Second-highest-value mock because structure prediction
   is the most distinctive feature and the hardest to set up for real.

3. **MockReport generator** -- assembles plausible candidate-antigen reports and
   ethics packages from mock data. Proves the safety labeling and export gate
   system works end-to-end.

4. **Demo mode seed data** -- a complete synthetic dog case (diagnosis, samples,
   variants, candidates) that can be loaded with one command. Without this,
   there is nothing to show.

5. **Mock safety preflight** -- blocks known-dangerous patterns. Can be
   rule-based initially; ML-based scanning later.

---

## DAILY CHECKPOINT SUMMARY

| Day | Deliverable |
|-----|-------------|
| D1  | Repo scaffold, all governance docs, source registry, config model |
| D2  | SQLAlchemy models, Alembic migration, audit logging, safety preflight, FastAPI CRUD |
| D3  | PipelineStep base + MockPipeline, AlphaFoldBackend base + MockAlphaFoldBackend, demo seed data |
| D4  | Variant/candidate endpoints, report generators, mRNA safety gate placeholder |
| D5  | Shared API client, all 27 skill packs (9 x 3 frameworks), agent integration endpoints + WS events |
| D6  | Streamlit dashboard MVP, end-to-end demo run |
| D7  | Test suite, bug fixes, v0.1.0-alpha tag |

---

## SWARM PARALLELIZATION HINTS

If running multiple agents in parallel, assign by dependency layer:

**Layer 0 (no dependencies):** Governance docs, source registry, README, config model
**Layer 1 (depends on Layer 0):** SQLAlchemy models, Alembic, audit system, safety preflight
**Layer 2 (depends on Layer 1):** FastAPI endpoints, PipelineStep/AlphaFoldBackend bases
**Layer 3 (depends on Layer 2):** Mock implementations, demo seed data
**Layer 4 (depends on Layer 3):** Reports, ethics packages, safety gates
**Layer 5 (depends on Layer 3):** Skill packs (can start once API shape is known)
**Layer 6 (depends on Layers 3-5):** Dashboard, end-to-end test, demo

Each layer can be parallelized across multiple agents, but layers must be
completed in order. Within a layer, assignments can be split by subsystem
(e.g., one agent does pipeline mocks while another does AlphaFold mocks).