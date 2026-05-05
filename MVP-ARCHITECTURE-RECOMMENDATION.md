# FoldAgent MVP Architecture & Stack Recommendation

**Goal:** Fastest path to a useful, safe, local-first product.

---

## RECOMMENDED STACK

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.11+ (entire project) | Bioinformatics ecosystem, all pipeline tools are Python-native, one language reduces cognitive load |
| API | FastAPI + Pydantic v2 | Async, auto-OpenAPI docs (agents need this), validation built-in, team knows it |
| Database | SQLite (local-first default) + PostgreSQL (optional production) | SQLite gives zero-config local-first; Alembic migrations make Postgres upgrade trivial |
| ORM | SQLAlchemy 2.0 + Alembic | Plan already specifies this; async support in 2.0 is solid |
| Task Queue | NOT Celery+Redis for MVP. Use Python `asyncio` + `subprocess` for pipeline wrappers, with a simple DB-backed job table | Celery+Redis is operational overhead that kills local-first UX. Add later for multi-user production |
| Frontend | Streamlit (MVP only) | Ships in hours, not weeks. Python-native. Only pivot to Next.js when Streamlit genuinely blocks you |
| Structure Viewer | py3Dmol (embedded in Streamlit via streamlit-py3Dmol) | Pure Python, no NGL build step |
| Testing | pytest + pytest-asyncio | Standard, fast |
| Logging | structlog | Structured JSON logs, essential for audit trail |
| Config | YAML + pydantic-settings | Typed config, .env overlay for secrets |
| Containerization | Docker Compose (3 services: app, db, worker) — but app runs standalone with SQLite by default | Local-first means `pip install + run` with zero Docker required for basic use |

### NOT in MVP (defer)

- Celery + Redis (replace with async subprocess + DB job queue)
- Next.js frontend (Streamlit first)
- Multiple AlphaFold backends (Mock + ColabFold only)
- OpenClaw and Hermes skill packs (Claude Code first, then port)
- Autoresearch mode
- Encryption at rest (add in v0.2)
- TypeScript API client
- RNA-seq / MHC typing adapters

---

## RECOMMENDED ARCHITECTURE

```
foldagent/
  backend/
    app/
      main.py              # FastAPI app + lifespan
      config.py            # pydantic-settings
      db.py                # SQLAlchemy session + SQLite/Postgres
      models/              # SQLAlchemy models
        case.py
        sample.py
        variant.py
        candidate.py
        structure_job.py
        report.py
        agent_task.py
        audit_log.py
      api/
        cases.py
        samples.py
        pipeline.py
        variants.py
        candidates.py
        alphafold.py
        reports.py
        agents.py
        safety.py
      services/
        pipeline_runner.py     # async subprocess orchestration
        alphafold/
          base.py              # abstract backend
          mock.py              # returns fixture PDB files
          colabfold.py         # ColabFold runner
        bioinformatics/
          base.py              # PipelineStep abstract class
          mock.py              # mock callers for demo
        safety.py              # output scanner, preflight checks
        audit.py               # structured audit logging
        reports/
          candidate_review.py
          ethics_package.py
      schemas/                 # Pydantic request/response models
    alembic/
    tests/
    pyproject.toml
  frontend/
    app.py                     # Streamlit app entry
    pages/
      1_Create_Case.py
      2_Upload_Data.py
      3_Pipeline_Status.py
      4_Variants.py
      5_Candidates.py
      6_AlphaFold.py
      7_Reports.py
      8_Audit_Log.py
    components/
      warning_banner.py        # persistent safety banners
      structure_viewer.py      # py3Dmol wrapper
  skills/
    shared/
      foldagent_client.py         # Python API client
      openapi.json
      safety_policy.md
      report_templates/
    claude-code/               # MVP: Claude Code only
      run_full_foldagent_case_review/
      organize_case_data/
      run_bioinformatics_pipeline/
      get_alphafold_structures/
      generate_candidate_review_report/
        SKILL.md
  docs/
    source_registry.md
    safety_policy.md
    ethics_templates/
  examples/
    synthetic_demo_case/
  docker-compose.yml
  Makefile
  README.md
```

### Key Architectural Decisions

**1. SQLite-first, not Postgres-first**
- Local-first means `git clone && pip install && foldagent serve` works with zero config
- SQLite handles single-user and small team use cases fine
- Alembic migrations make Postgres a config swap for production
- WAL mode + busy_timeout handles concurrent reads

**2. No Celery/Redis for MVP**
- The pipeline runner uses `asyncio.create_subprocess_exec` to spawn bioinformatics tools
- Job state lives in a `PipelineRun` table with status + progress
- Polling via API endpoints + optional SSE (not WebSocket initially)
- Celery+Redis is added only when you have >5 concurrent users or need horizontal scaling

**3. Streamlit, not Next.js**
- Streamlit ships pages in hours. Next.js ships in weeks.
- Streamlit's multipage app model covers all dashboard needs
- Python-only means no context switching, no API client generation, no JS build step
- Pivot to Next.js only when: (a) you need real-time collaboration, (b) Streamlit widgets block custom UX, or (c) you have a frontend dev who wants it
- Safety banners, tables, file upload, py3Dmol — all work in Streamlit today

**4. Mock-first pipeline design**
- MockAlphaFoldBackend and mock bioinformatics callers are the default
- Real ColabFold is opt-in (requires GPU setup)
- Demo mode uses synthetic VCF + mock everything
- This means the full demo loop works immediately without any bioinformatics tools installed

**5. Safety as a cross-cutting service, not a phase**
- SafetyService.scanned_output() wraps every report/exports endpoint
- SafetyPreflight check before any pipeline run
- Hardcoded blocklist of dangerous output patterns
- Audit log entry for every action
- This is cheap to build early and expensive to bolt on late

---

## KEY TRADEOFFS

| Decision | Pro | Con |
|----------|-----|-----|
| SQLite over Postgres | Zero config, local-first, single-file database | Not ideal for concurrent writes > ~20/sec; no advanced Postgres features |
| Streamlit over Next.js | Days to ship, Python-only, streamlit-py3Dmol exists | Limited UI customization, slower for complex interactions, harder to do real-time collab |
| No Celery/Redis | Simpler deploy, fewer deps, local-first friendly | No horizontal scaling, no priority queues, no scheduled tasks without custom code |
| Claude Code skills first | Largest user base of the three agent frameworks, fastest to test locally | Must port to OpenClaw/Hermes later; each has slightly different SKILL.md conventions |
| Mock backends only in v0.1 | Full demo loop works immediately | Users must set up real tools separately; no real pipeline in first release |
| FastAPI sync endpoints + async subprocess | Simple mental model, no Celery dependency | Long-running pipeline steps block the async event loop slightly; mitigated by subprocess delegation |

---

## FIRST 5 IMPLEMENTATION PRIORITIES

### Priority 1: Repo scaffold + safety policy + docs skeleton
- Create monorepo structure above
- `pyproject.toml` with FastAPI, SQLAlchemy, Pydantic, structlog, Streamlit
- `SAFETY_POLICY.md` with hardcoded prohibited outputs (no dosing, no manufacturing, no injection instructions)
- `docs/source_registry.md` with Paul/Rosie links and proper attribution caveats
- `README.md` with "not medical advice" banner and local-first pitch
- `Makefile` with `make setup`, `make dev`, `make test`
- Docker Compose with app service (dev mode uses SQLite directly, no container needed)
- **Why first:** Legal/ethical guardrails are non-negotiable. Repo structure is cheap and saves weeks of refactoring.

### Priority 2: Backend core — Case model, audit log, safety service
- SQLAlchemy models: Case, Subject, Sample, AuditLog
- FastAPI endpoints: POST/GET/PATCH cases, GET audit/{case_id}
- `SafetyService.preflight()` — checks mode, consent, professional attestation
- `SafetyService.scan_output()` — regex + keyword blocklist for dangerous content
- `AuditService.log()` — structured append-only log per case
- Alembic initial migration
- Tests for safety gates and audit logging
- **Why second:** Safety gates and audit logs must exist before any data flows. Case model is the root entity everything else attaches to.

### Priority 3: Mock pipeline + mock AlphaFold + demo data
- `PipelineStep` base class with `run()`, `validate_env()`, `collect_outputs()`
- Mock callers for alignment, variant calling, annotation, MHC prediction
- `MockAlphaFoldBackend` returning fixture PDB/mmCIF files
- `ColabFoldBackend` skeleton (validate_env check, real run stubbed for later)
- Synthetic demo VCF + FASTA files in `/examples/synthetic_demo_case/`
- Pipeline runner that chains mock steps and records progress in DB
- API: POST /cases/{id}/pipeline/run, GET /cases/{id}/pipeline/status
- **Why third:** This unlocks the full demo loop: create case → register files → run mock pipeline → see results. No real bioinformatics tools needed.

### Priority 4: Streamlit dashboard MVP
- `streamlit run frontend/app.py` entry point
- Pages: Create Case, Upload Data, Pipeline Status, Variant Explorer, Candidate Review, Reports
- Persistent safety warning banner on every page
- Tables for cases, variants, candidates using `st.dataframe`
- py3Dmol structure viewer for AlphaFold results
- Report generation buttons (candidate review PDF, ethics package draft)
- Links to source registry and safety policy
- **Why fourth:** Dashboard makes the system usable and testable by humans. Without it, the API is invisible. Streamlit gets you here in days, not weeks.

### Priority 5: Claude Code skill packs + API client + shared safety policy
- `skills/shared/foldagent_client.py` — Python client wrapping the OpenAPI spec
- `skills/shared/safety_policy.md` — agent-readable safety policy
- `skills/shared/openapi.json` — auto-generated from FastAPI
- 5 priority SKILL.md packs: `run_full_foldagent_case_review`, `organize_case_data`, `run_bioinformatics_pipeline`, `get_alphafold_structures`, `generate_candidate_review_report`
- Each SKILL.md includes: name, description, safety boundaries, required endpoints, no-medical-advice warning
- Install instructions for Claude Code
- **Why fifth:** Agent integration is a key differentiator but depends on a stable API. Build the API surface first, then expose it to agents. Claude Code first because it has the largest developer audience and simplest skill format.

---

## WHAT v0.1.0 LOOKS LIKE

A user can:
1. `git clone` + `pip install` + `foldagent serve` (zero Docker required)
2. Open Streamlit dashboard
3. Create a demo case (dog/human/demo mode)
4. Register synthetic sequencing files
5. Run mock pipeline (alignment → variant calling → annotation → MHC prediction)
6. View variants and candidate antigens in dashboard
7. View mock AlphaFold structure predictions
8. Generate a candidate-antigen review report (PDF, safety-labeled)
9. Generate an ethics/veterinary review packet draft
10. Use Claude Code skills to do all of the above via agent
11. Trust that no report contains dosing, manufacturing, injection, or treatment instructions
12. See a full audit log of every action

Then v0.2.0 adds: real ColabFold, real bioinformatics wrappers, Celery+Redis for production, Postgres config, OpenClaw/Hermes skills, encryption at rest.