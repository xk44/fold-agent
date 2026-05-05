# Troubleshooting

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Database Issues

### "database is locked" / SQLite lock errors

**Symptom:** API returns 500 with `sqlite3.OperationalError: database is locked` or similar.

**Cause:** SQLite WAL mode handles concurrent reads well but a long-running write transaction can block others. Common causes:

- A previous API process crashed while holding a write lock
- Multiple processes writing to the same SQLite file simultaneously
- A Celery worker and the API server sharing one SQLite file without coordination

**Fix:**

1. Stop all services: `make docker-down` or kill all uvicorn/celery processes
2. Check for stale lock files: `ls foldagent.db*` — if `foldagent.db-shm` or `foldagent.db-wal` are present and the database is not in use, they can be safely removed
3. Restart: `make dev` or `make docker-up`

For production workloads with concurrent workers, migrate to PostgreSQL:

```bash
FOLDAGENT_DATABASE_URL=postgresql://user:pass@localhost/foldagent
```

---

### "no such table: cases" / Missing Tables

**Symptom:** API returns 500 with `sqlalchemy.exc.OperationalError: no such table: cases` (or any other table).

**Cause:** The database schema has not been initialized or a migration has not been applied.

**Fix (development):**

```bash
# Option 1: auto-create all tables (bypasses Alembic)
FOLDAGENT_DB_INIT_MODE=create_all make dev

# Option 2: apply Alembic migrations
make migrate && make dev
```

**Fix (production / validate mode):**

```bash
make migrate
# Then restart the service
```

If the database file is new (e.g. after `make reset`), run `make migrate` or start with `DB_INIT_MODE=create_all` once to bootstrap the schema, then switch to `validate`.

---

### Schema drift detected at startup

**Symptom:** App fails to start with `RuntimeError: Schema validation failed: missing tables [...]`.

**Cause:** `FOLDAGENT_DB_INIT_MODE=validate` found ORM models with no corresponding database table. A migration was added but not applied.

**Fix:**

```bash
make migrate
```

---

## AlphaFold Issues

### `validate_environment()` returns False / Backend unavailable

**Symptom:** `GET /alphafold/backends` shows `validation_ok: false` for a non-mock backend.

**Cause:** The backend binary is not on `PATH`.

**Fix:** Install the required tool and ensure the binary is accessible:

| Backend                         | Binary to install                               |
| ------------------------------- | ----------------------------------------------- |
| `colabfold` / `local_colabfold` | `colabfold_batch` (ColabFold or LocalColabFold) |
| `alphafold2_local`              | `run_alphafold` (AlphaFold2 CLI)                |
| `alphafold3_local`              | `alphafold` (AlphaFold3 CLI)                    |
| `alphafold_server`              | `alphafold_server_submit` (placeholder binary)  |
| `alphafold_db`                  | `alphafold_db_lookup` (placeholder binary)      |

After installing, restart the API. The `PIPELINE_ADAPTERS` dict and backend registry are populated at startup.

If you only need mock functionality, set `FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=mock` — the mock backend always passes `validate_environment()`.

---

### AlphaFold job blocked by safety preflight

**Symptom:** `POST /alphafold/backends/{name}/run` returns 403 with `BLOCK` or `REQUIRES_APPROVAL`.

**Cause (BLOCK):** Content contains prohibited output patterns, or human-mode sequence export attempted without expert mode.

**Cause (REQUIRES_APPROVAL):** The backend requires external upload (`alphafold_server`) or the request involves sequence data without expert mode active.

**Fix:**

- For external upload: set `acknowledge_external_upload: true` in the request and confirm via the API
- For sequence data without expert mode: set `is_expert_mode: true` only after professional attestation is in place
- For human mode: sequence exports require both expert mode and IRB attestation

See `docs/SAFETY_GUIDE.md` for the full preflight decision tree.

---

## Pipeline Adapter Issues

### "adapter not found" / KeyError on adapter name

**Symptom:** `POST /pipeline/adapters/{name}/dry-run` or `/run` returns 404 or raises `KeyError`.

**Cause:** The adapter name in the request does not match a registered key.

**Valid adapter keys:** `bwa`, `bwa_mem2`, `gatk_mutect2`, `vep`, `pvactools`

**Fix:** Check spelling. Keys are lowercase with underscores. Use `GET /pipeline/adapters` to list all registered adapters and their exact names.

---

### Adapter returns `status: "unavailable"`

**Symptom:** Execution returns `available: false` and `stderr: "Command 'gatk' not found on PATH."`.

**Fix:** Install the tool and add it to `PATH`. Then restart the API (the registry checks `shutil.which()` at startup).

For running without real tools, switch to mock mode: `FOLDAGENT_PIPELINE_MODE=mock`.

---

### Pipeline command built with wrong reference path

**Symptom:** Dry-run shows `/data/reference/hg38.fa` but your reference is elsewhere.

**Fix:** Override via environment variable:

```bash
FOLDAGENT_PIPELINE_BWA_REFERENCE=/path/to/your/reference.fa
FOLDAGENT_PIPELINE_GATK_REFERENCE=/path/to/your/reference.fa
```

Or pass `reference` directly in the request payload — payload values always override config defaults.

---

## Test Failures

### Tests fail with "no such table"

**Cause:** Test fixtures in `conftest.py` use an in-memory SQLite database, but a test is importing from a module that references the main database at import time.

**Fix:** Ensure all DB access inside tests goes through the injected `db` fixture. Do not call `settings`-derived database paths directly in test bodies.

---

### `test_alembic_scaffold.py` fails

**Symptom:** Alembic scaffold test fails with "no migration scripts found" or version mismatch.

**Cause:** A model change was made without generating a migration.

**Fix:**

```bash
make makemigration MSG="describe the change"
git add alembic/versions/
```

---

### Safety tests fail after adding new output patterns

**Symptom:** `test_preflight.py` or `test_mrna_safety_gate_api.py` fail after editing `preflight.py`.

**Fix:** Review `UNSAFE_OUTPUT_PATTERNS` for unintended regex changes. Run the specific test file in isolation to see which assertion fails:

```bash
pytest backend/tests/test_preflight.py -v
```

---

## Streamlit Dashboard Issues

### Dashboard shows "Cannot connect to API"

**Cause:** API server is not running, or `FOLDAGENT_API_URL` is wrong.

**Fix:**

```bash
# Ensure the API is running
make dev   # in a separate terminal

# Ensure the dashboard uses the correct URL
FOLDAGENT_API_URL=http://127.0.0.1:8010 make dashboard
```

In Docker, the dashboard service uses `FOLDAGENT_API_URL=http://app:8010` (internal Docker network). If running outside Docker, change this to `http://127.0.0.1:8010`.

---

## General

### Port already in use

**Symptom:** `uvicorn` fails with `[Errno 98] Address already in use` on port 8010 or 8502.

**Fix:**

```bash
make ports-check   # shows what is listening on 8010 and 8502
# Kill the conflicting process, then retry
```

### Logs show no structured JSON

**Symptom:** Log output is plain text instead of JSON.

**Fix:** Ensure `FOLDAGENT_STRUCTURED_LOGS=true` (default). If running in a terminal and JSON is hard to read, set `FOLDAGENT_STRUCTURED_LOGS=false` for local development.

### `make reset` cleared the database but tables are missing

After `make reset`, the SQLite file is deleted. Recreate the schema:

```bash
FOLDAGENT_DB_INIT_MODE=create_all make dev
# or
make migrate
```
