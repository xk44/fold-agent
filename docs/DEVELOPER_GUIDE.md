# Developer Guide

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Prerequisites

- Python 3.11+
- Git
- (Optional) A CUDA-capable GPU for real AlphaFold backends
- (Optional) Docker + Docker Compose for containerized runs

---

## Local Setup

```bash
# Clone and enter the repo
git clone <repo-url>
cd foldagent

# Install core + dev + frontend dependencies
pip install -e ".[dev,frontend]"

# Install pre-commit hooks
make install-hooks

# (Optional) Install Celery worker stack
pip install -e ".[dev,frontend,worker]"
```

Copy the example config and customize if needed:

```bash
cp config.example.yaml config.yaml
```

Environment variables override all config values. The prefix for all settings is `FOLDAGENT_` (see `backend/app/config.py`).

---

## Running the API Server

```bash
make dev
# Equivalent: uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
```

The API will be available at `http://127.0.0.1:8010`. Interactive docs at `http://127.0.0.1:8010/docs`.

Default settings used on first run:

- `FOLDAGENT_SPECIES_MODE=demo`
- `FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=mock`
- `FOLDAGENT_PIPELINE_MODE=mock`
- `FOLDAGENT_DATABASE_URL=sqlite:///./foldagent.db`

---

## Running the Streamlit Dashboard

```bash
make dashboard
# Equivalent: FOLDAGENT_API_URL=http://127.0.0.1:8010 streamlit run frontend/app/dashboard.py \
#   --server.address 127.0.0.1 --server.port 8502
```

The dashboard will be available at `http://127.0.0.1:8502`. It requires the API server to be running first.

---

## Seed Demo Data

```bash
make seed-demo
# Equivalent: python -m backend.app.seed_demo
```

Creates synthetic cases, samples, variants, candidates, and reports for development and testing. Safe to run multiple times (idempotent for demo records).

---

## Running Tests

```bash
# Full test suite with coverage
make test

# Safety-tagged tests only
make test-safety

# End-to-end workflow tests
make test-e2e

# Fast smoke test (excludes slow/integration/e2e)
make smoke

# Deployment scaffold tests
make test-deployment
```

Tests use an in-memory SQLite database via the `conftest.py` fixtures in `backend/tests/`. No external services are required for the default test suite.

---

## Project Structure

```
foldagent/
  backend/
    app/
      main.py              — FastAPI app, all route definitions
      config.py            — Settings (pydantic-settings, FOLDAGENT_ prefix)
      models.py            — SQLAlchemy ORM models
      schemas.py           — Pydantic request/response schemas
      db.py                — Engine, session factory, init/migration logic
      safety/
        preflight.py       — Core safety gate: preflight_action()
        mrna_gate.py       — Sequence-level safety gate
        audit.py           — Append-only audit logging
      alphafold/
        base.py            — Abstract backend + MockAlphaFoldBackend + registry
        schemas.py         — AlphaFold request/response schemas
        colabfold.py       — ColabFold command builder
        alphafold2_local.py — AF2 command builder
        alphafold3_local.py — AF3 command builder + JSON input writer
        alphafold_server.py — Server submit command builder
        alphafold_db.py    — DB lookup command builder
        shells.py          — Adapter status, dry-run, execute wrappers
        output_parsers.py  — Parse AF output files into structured dicts
      pipeline/
        base.py            — PipelineStep ABC + mock implementations
        shells.py          — Shell adapter registry, dry-run, execute
        schemas.py         — Pipeline request schemas
      privacy.py           — Case dirs, retention, cloud gates, audit export
      lab_coordination.py  — Lab contacts, costs, timeline, templates
      data_loading.py      — File validation, sample role detection
      reports.py           — Report builders (candidate review, ethics package)
      jobs.py              — Background job management
      worker/tasks.py      — Celery task definitions
      event_stream.py      — In-process SSE event bus
      mock_analysis.py     — Demo mode mock data helpers
      seed_demo.py         — Demo seed script
  frontend/
    app/dashboard.py       — Streamlit dashboard
  skills/                  — Agent skill definitions (see AGENT_SKILLS_GUIDE.md)
  docs/                    — This documentation
  alembic/                 — Database migration scripts
  alembic.ini              — Alembic configuration
  pyproject.toml           — Package metadata and dependencies
  docker-compose.yml       — Container orchestration
  Dockerfile               — Multi-stage build
  Makefile                 — Common dev/ops commands
```

---

## Adding a New API Endpoint

1. Add request/response schemas to `backend/app/schemas.py` (or a domain-specific `schemas.py` if the domain module has one).

2. Add the route handler to `backend/app/main.py`. Follow the existing pattern:
   - Inject `db: Session = Depends(get_db)`
   - Call `preflight_action(...)` for any write or export
   - Call `log_action(db, ...)` for the audit trail
   - Return typed Pydantic response models

3. For safety-sensitive endpoints, add the `safety_gate_result` field to the audit log call.

4. Write tests in `backend/tests/test_{domain}_api.py`. Use the `client` fixture from `conftest.py`.

5. Run `make lint` and `make test` before committing.

---

## Adding a New ORM Model

1. Add the model class to `backend/app/models.py`, inheriting from `Base`.

2. Create a migration:

   ```bash
   make makemigration MSG="add my new table"
   ```

3. Apply the migration:

   ```bash
   make migrate
   ```

4. For development without migrations, `FOLDAGENT_DB_INIT_MODE=create_all` will auto-create tables at startup (bypasses Alembic — not for production).

---

## Alembic Migrations

```bash
# Apply all pending migrations
make migrate
# Equivalent: alembic upgrade head

# Create a new auto-generated migration
make makemigration MSG="describe what changed"
# Equivalent: alembic revision --autogenerate -m "describe what changed"
```

`FOLDAGENT_DB_INIT_MODE` controls startup behavior:

- `create_all` — dev default; calls `Base.metadata.create_all()`, bypasses Alembic
- `validate` — asserts all ORM tables exist; raises on schema drift; use in production
- `alembic` — runs `alembic upgrade head` at startup; convenient for single-process deploys

---

## Linting and Formatting

```bash
# Check
make lint
# Equivalent: ruff check backend/ && mypy backend/ && black --check backend/

# Auto-fix
make format
# Equivalent: ruff check --fix backend/ && black backend/

# Local CI parity (pre-commit + smoke + lint + tests)
make ci
```

---

## Environment Variables Quick Reference

```bash
FOLDAGENT_SPECIES_MODE=demo          # demo | dog | human
FOLDAGENT_DATABASE_URL=sqlite:///./foldagent.db
FOLDAGENT_DB_INIT_MODE=create_all    # create_all | validate | alembic
FOLDAGENT_API_PORT=8010
FOLDAGENT_DASHBOARD_PORT=8502
FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=mock
FOLDAGENT_PIPELINE_MODE=mock         # mock | real
FOLDAGENT_SAFETY_PREFLIGHT_ENABLED=true
FOLDAGENT_LOG_LEVEL=INFO
FOLDAGENT_SECRET_KEY=changeme-set-a-real-secret-key
```
