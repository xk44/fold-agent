# NeoVax Operator Verification Walkthrough

Step-by-step runbook to verify a local NeoVax stack is healthy and functional.

## Port defaults

| Service    | Variable         | Default            |
|------------|------------------|--------------------|
| API        | `API_PORT`       | `8010`             |
| Dashboard  | `DASHBOARD_PORT`  | `8502`             |

Override either at invocation:

```bash
make dev API_PORT=18010
make dashboard API_PORT=18010 DASHBOARD_PORT=18501
```

The dashboard reads `NEOVAX_API_URL` (defaults to `http://127.0.0.1:$(API_PORT)`)
to find the API.

## Prerequisites

```bash
cd ~/projects/neovax
cp .env.example .env          # first time only
make install                   # pip install -e ".[dev,frontend]"
```

## 1. Start the API

```bash
make dev
# Binds to http://127.0.0.1:8010 by default
```

## 2. Verify API health

Do not use `curl -f` here: NeoVax now returns a structured JSON body even when
`/health` is degraded (`HTTP 503`). Capture both the HTTP status and the JSON
payload.

```bash
curl -sS -o /tmp/neovax-health.json -w '%{http_code}\n' http://127.0.0.1:8010/health
python3 -m json.tool /tmp/neovax-health.json
```

Healthy example (`HTTP 200`):

```json
{
    "status": "ok",
    "version": "0.1.0-alpha",
    "mode": "demo",
    "db_status": "ok",
    "database_url": "sqlite:///./neovax.db",
    "db_init_mode": "create_all",
    "tables_present": 14,
    "tables_expected": 14,
    "missing_tables": [],
    "extra_tables": [],
    "error": null
}
```

Degraded example (`HTTP 503`):

```json
{
    "status": "degraded",
    "version": "0.1.0-alpha",
    "mode": "demo",
    "db_status": "degraded",
    "database_url": "sqlite:///./neovax.db",
    "db_init_mode": "create_all",
    "tables_present": 0,
    "tables_expected": 14,
    "missing_tables": ["background_jobs", "cases"],
    "extra_tables": [],
    "error": "no such table: cases"
}
```

If `mode` shows `demo`, the default safe pipeline is active (mock pipeline,
mock AlphaFold, safety preflight enabled). This is the expected local-dev
state. If `status` is `degraded`, the API process is alive but the backing DB
schema or connectivity needs repair before normal operator work.

## 3. Verify API configuration

```bash
curl -sf http://127.0.0.1:8010/version | python3 -m json.tool
```

Expected keys and default values:

| Field                | Default |
|----------------------|---------|
| `version`            | `0.1.0-alpha` |
| `mode`               | `demo` |
| `pipeline_mode`      | `mock` |
| `alphafold_backend`  | `mock` |
| `safety_preflight`   | `true` |

If any value is not the default, check your `.env` file for overrides.

## 4. Seed demo data

```bash
make seed-demo
```

This creates sample cases, samples, variants, and candidates so the dashboard
has content to display.

## 5. Verify key API endpoints

Run each curl and confirm the response shape. All of these should return HTTP
200 with non-empty data when demo data has been seeded.

```bash
# List cases
curl -sf http://127.0.0.1:8010/cases | python3 -m json.tool | head -20

# AlphaFold backend diagnostics
curl -sf http://127.0.0.1:8010/alphafold/backends | python3 -m json.tool | head -30

# Pipeline adapters
curl -sf http://127.0.0.1:8010/pipeline/adapters | python3 -m json.tool | head -20
```

## 6. Start the dashboard

In a second terminal:

```bash
make dashboard
# Binds to http://127.0.0.1:8502 by default
```

## 7. Verify dashboard health

```bash
curl -sf http://127.0.0.1:8502/_stcore/health
```

Expected: HTTP 200, body `ok`.

Open the dashboard in a browser:

```
http://127.0.0.1:8502
```

You should see the NeoVax dashboard with demo case data, AlphaFold diagnostics,
report previews, and structure-job/artifact panels.

## 8. Verify structure viewer flow

After seeding demo data and running at least one mock or dry-run AlphaFold path that registers structure artifacts:

1. Open a case in the dashboard.
2. In the structure-job explorer, select a structure job.
3. Pick a `.cif`, `.mmcif`, or `.pdb` artifact.
4. Confirm the confidence summary shows ranking score/pTM/ipTM or explicitly reports incomplete metrics.
5. Click `Load 3D structure`; the 3Dmol viewer should render the selected artifact.
6. Enable compare mode, select a second artifact when available, and reload to verify the side-by-side compare viewer.

If the browser cannot load 3Dmol.js, the viewer shows a CDN failure message while the underlying artifact remains downloadable.

## 9. Verify API docs

```
http://127.0.0.1:8010/api/docs     # Swagger UI
http://127.0.0.1:8010/api/redoc     # ReDoc
```

Both should load and list all available endpoints.

## 10. Run the unit smoke test suite

From the repo root (no running server required):

```bash
make smoke
```

This runs the fast unit/integration tests that confirm internal logic without
requiring live services.

## 11. Run the live verification target

With API and dashboard both running:

```bash
make smoke-verify
```

This checks:
- API `/health` responds with `status: ok` when healthy, or `status: degraded` with a structured DB snapshot when schema/connectivity has drifted
- API `/version` returns expected fields
- API `/cases` responds (seed data present)
- Dashboard `/_stcore/health` responds

All port overrides are respected via `API_HOST`, `API_PORT`,
`DASHBOARD_HOST`, `DASHBOARD_PORT`.

Example with non-default ports:

```bash
make smoke-verify API_PORT=18010 DASHBOARD_PORT=18501
```

## 12. (Optional) Verify worker stack

If the Celery + Redis worker stack is enabled:

```bash
# Start Redis + worker
docker compose --profile worker up redis worker -d

# Confirm dispatch routing at /health is not threadpool
curl -sf http://127.0.0.1:8010/version | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('pipeline_mode:', d.get('pipeline_mode','unknown'))"
```

To shut down the worker stack:

```bash
docker compose --profile worker down
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` Connection refused | API not running | `make dev` |
| `/health` returns `503` with `status: degraded` | Database schema drift or wrong DB path | Read `missing_tables`, `db_init_mode`, and `database_url` from the JSON body, then migrate/fix the DB and restart the API |
| Dashboard shows connection error | `NEOVAX_API_URL` wrong | Check `API_PORT` or set `NEOVAX_API_URL` explicitly |
| `make seed-demo` fails | Database not initialised | Delete `neovax.db`, restart API, re-run `seed-demo` |
| `/alphafold/backends` shows all unavailable | Expected in demo mode with no local AF2/AF3/ColabFold | `mock` backend is used by default; only `alphafold_server` and `alphafold_db` may show available |
| Worker won't start | Redis not reachable | Start Redis first: `docker compose --profile worker up redis -d` |
| Port already in use | Another process on 8010 or 8502 | Override: `make dev API_PORT=18010` |

## Quick reference

```bash
# Start everything (two terminals)
make dev                                          # terminal 1
make dashboard                                    # terminal 2

# Seed data
make seed-demo

# Verify
make smoke-verify

# Run unit tests (no server needed)
make smoke

# Run full test suite
make test

# Docker Compose (without worker)
docker compose up

# Docker Compose (with worker)
docker compose --profile worker up
```