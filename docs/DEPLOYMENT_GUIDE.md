# Deployment Guide

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

FoldAgent ships with a multi-stage `Dockerfile` and a `docker-compose.yml` covering four services:

| Service     | Default        | Profile  | Port |
| ----------- | -------------- | -------- | ---- |
| `app`       | Always started | —        | 8010 |
| `dashboard` | Always started | —        | 8502 |
| `redis`     | Opt-in         | `worker` | 6379 |
| `worker`    | Opt-in         | `worker` | —    |

Ports are bound to `127.0.0.1` by default. Do not expose them on `0.0.0.0` in production without a reverse proxy and authentication layer.

---

## Docker Build

```bash
# Build images (uses layer cache)
make docker-build

# Build without cache (clean rebuild)
make docker-build-clean
```

The Dockerfile uses a two-stage build:

1. **Builder** — installs all dependencies into `/install` using `pip install --prefix`
2. **Runtime** — copies from builder, creates a non-root `foldagent` user (uid/gid 1000), exposes ports 8010 and 8502

---

## Prepare Volume Directories

```bash
make docker-prepare-volumes
```

Creates `data/`, `audit_logs/`, and `artifacts/` on the host and ensures they are owned by uid/gid 1000 (the container user). Run this once before the first `docker compose up`.

---

## Starting Services

```bash
# Start API + dashboard only (no worker)
make docker-up-core
# Equivalent: docker compose up -d app dashboard

# Start all services including worker
docker compose --profile worker up -d

# Start Redis + worker only (assumes app is already running)
docker compose --profile worker up -d redis worker
```

---

## Stopping Services

```bash
make docker-down
# Equivalent: docker compose down
```

---

## Logs

```bash
# Tail all services
make docker-logs

# Tail a specific service
make docker-logs-svc SVC=app
make docker-logs-svc SVC=dashboard
make docker-logs-svc SVC=worker
```

---

## Health Checks

```bash
# Check service status and health endpoints
make docker-health
```

The `app` service health check polls `GET /health` every 30 seconds. The `dashboard` health check polls `/_stcore/health`. The `worker` profile's `redis` service uses `redis-cli ping`.

Manual verification:

```bash
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/version
curl http://127.0.0.1:8502/_stcore/health
```

---

## Environment Variables

Set via a `.env` file in the project root (loaded by `docker compose` via `env_file`). The `.env` file is optional — defaults are safe for demo use.

### Core

```bash
FOLDAGENT_API_PORT=8010
FOLDAGENT_DASHBOARD_PORT=8502
FOLDAGENT_DATABASE_URL=sqlite:///./data/foldagent.db
FOLDAGENT_DB_INIT_MODE=validate          # use validate or alembic in production
FOLDAGENT_SPECIES_MODE=demo              # demo | dog | human
FOLDAGENT_SECRET_KEY=changeme            # CHANGE THIS in production
FOLDAGENT_LOG_LEVEL=INFO
FOLDAGENT_STRUCTURED_LOGS=true
FOLDAGENT_AUDIT_LOG_PATH=/app/audit_logs
FOLDAGENT_ARTIFACT_ROOT=/app/artifacts
```

### Safety

```bash
FOLDAGENT_SAFETY_PREFLIGHT_ENABLED=true
FOLDAGENT_UNSAFE_TEXT_SCANNER_ENABLED=true
FOLDAGENT_REQUIRE_PROFESSIONAL_OVERSIGHT=true
```

### AlphaFold

```bash
FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=mock
FOLDAGENT_ALPHAFOLD_ALLOWED_BACKENDS=mock,colabfold,local_colabfold,alphafold2_local,alphafold3_local,alphafold_server,alphafold_db
FOLDAGENT_ALPHAFOLD_CACHE_OUTPUTS=true
```

### Pipeline

```bash
FOLDAGENT_PIPELINE_MODE=mock             # mock | real
FOLDAGENT_PIPELINE_DEFAULT_THREADS=4
FOLDAGENT_PIPELINE_DEFAULT_MEMORY_GB=8
FOLDAGENT_PIPELINE_BWA_REFERENCE=/data/reference/hg38.fa
FOLDAGENT_PIPELINE_GATK_REFERENCE=/data/reference/hg38.fa
FOLDAGENT_PIPELINE_VEP_CACHE_DIR=/data/vep_cache
FOLDAGENT_PIPELINE_VEP_ASSEMBLY=GRCh38
```

### Worker (Celery)

```bash
FOLDAGENT_REDIS_URL=redis://redis:6379/0
FOLDAGENT_CELERY_BROKER_URL=redis://redis:6379/0
FOLDAGENT_CELERY_RESULT_BACKEND=redis://redis:6379/1
FOLDAGENT_BACKGROUND_JOB_BACKEND=auto   # auto | threadpool | celery
```

When `FOLDAGENT_CELERY_BROKER_URL` is set, background jobs are dispatched through Celery. Without it, the app falls back to a threadpool executor.

### Privacy

```bash
FOLDAGENT_CLOUD_UPLOAD_ENABLED=false
FOLDAGENT_CLOUD_UPLOAD_CONFIRMATION_REQUIRED=true
FOLDAGENT_ENCRYPTION_AT_REST_ENABLED=false
FOLDAGENT_ENCRYPTION_KEY=               # required if encryption enabled
```

---

## Production Configuration Checklist

- [ ] Set `FOLDAGENT_SECRET_KEY` to a strong random value
- [ ] Set `FOLDAGENT_DB_INIT_MODE=validate` (or `alembic`) — never use `create_all` in production
- [ ] Run `make migrate` before first start to apply all Alembic migrations
- [ ] Set `FOLDAGENT_SPECIES_MODE` to the appropriate value for your research context
- [ ] Keep `FOLDAGENT_CLOUD_UPLOAD_ENABLED=false` unless you have reviewed the privacy implications
- [ ] Keep `FOLDAGENT_SAFETY_PREFLIGHT_ENABLED=true` — never disable in production
- [ ] Bind ports to `127.0.0.1` (already default in docker-compose.yml)
- [ ] Place a reverse proxy (nginx, Caddy) in front if external access is needed
- [ ] Set up log rotation for `audit_logs/` — these grow indefinitely
- [ ] Back up `data/foldagent.db` and `artifacts/` regularly

---

## Database Migration on Deploy

```bash
# Inside container or from host with virtualenv active
make migrate
# Equivalent: alembic upgrade head
```

Or set `FOLDAGENT_DB_INIT_MODE=alembic` to run migrations automatically at startup.

---

## Volume Mounts

The compose file mounts three host directories into the container:

| Host path      | Container path    | Purpose                               |
| -------------- | ----------------- | ------------------------------------- |
| `./data`       | `/app/data`       | SQLite database                       |
| `./audit_logs` | `/app/audit_logs` | Append-only audit logs                |
| `./artifacts`  | `/app/artifacts`  | Pipeline outputs, reports, structures |

These directories persist across container restarts. Back them up before upgrades.

---

## Worker Stack (Celery + Redis)

The worker profile adds Redis and a Celery worker. Start it with:

```bash
docker compose --profile worker up -d
```

Or from the Makefile for local dev (without Docker):

```bash
# Terminal 1: Redis (or use Docker)
docker compose --profile worker up -d redis

# Terminal 2: API
make dev

# Terminal 3: Celery worker
make worker
```

Worker concurrency defaults to 2 (`--concurrency=2`). Adjust via the `worker` service command in `docker-compose.yml`.
