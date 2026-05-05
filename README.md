# FoldAgent

**Local-first, safety-gated AI agent platform for protein science and structural biology research.**

---

> **SAFETY DISCLAIMER**
>
> FoldAgent is **research software only**. It is not medical advice, not veterinary advice, not a vaccine manufacturing tool, and not a treatment application. Every output is a research candidate that requires review by a licensed physician, veterinary oncologist, or qualified researcher before any real-world action. No output constitutes dosing, injection, formulation, manufacturing, or administration guidance.

---

## Features

**Research pipeline**

- Full bioinformatics pipeline: BWA alignment → Mutect2 somatic variant calling → VEP annotation → NetMHCpan binding prediction
- 9 specialized research modes covering the full spectrum of structural biology use cases
- 14 structure prediction backends (mock through production AlphaFold3)
- Event-driven job dispatch with SSE streaming and WebSocket support

**Safety and compliance**

- Preflight safety gates block prohibited outputs before any write or export
- mRNA safety gates with automatic redaction of unsafe output patterns
- Audit logging on every action, exportable for professional review
- Ethics package generation: consent templates, privacy notices, IRB/oversight checklists
- RBAC, encryption-at-rest support, artifact integrity hashing

**Infrastructure**

- Local-first by default — no data leaves the machine unless cloud backends are explicitly enabled
- SQLite (dev) or PostgreSQL (production) via SQLAlchemy + Alembic migrations
- Optional Celery + Redis worker stack for distributed background execution; falls back to thread pool automatically
- Docker Compose with worker profile
- Streamlit dashboard with 3D structure viewer (py3Dmol)
- TypeScript client SDK (`clients/typescript/`)
- Multi-agent skill system with Claude Code, Hermes, and OpenClaw integrations

---

## Research Modes

| #   | Mode                      | Description                                                 |
| --- | ------------------------- | ----------------------------------------------------------- |
| 1   | **Vaccine Design**        | Neoantigen candidate pipeline, mRNA construct optimization  |
| 2   | **Antibody Design**       | Therapeutic antibody engineering, paratope/epitope modeling |
| 3   | **Drug Discovery**        | Small molecule / protein target interaction modeling        |
| 4   | **Gene Therapy**          | Vector design with structural validation                    |
| 5   | **Enzyme Engineering**    | Enzyme-substrate modeling, activity prediction              |
| 6   | **TCR-pMHC**              | T-cell receptor / peptide-MHC ternary complex modeling      |
| 7   | **PPI Mapping**           | Protein-protein interaction analysis                        |
| 8   | **Protein Misfolding**    | Aggregation and amyloid pathology research                  |
| 9   | **Variant Pathogenicity** | Structural impact prediction for genetic variants           |

Each mode enforces its own safety restrictions and report templates. The `species_mode` setting (`demo` / `dog` / `human`) applies an additional layer of restrictions on top of mode-specific rules.

---

## Structure Prediction Backends

| Backend            | Status                   | Notes                                                                |
| ------------------ | ------------------------ | -------------------------------------------------------------------- |
| `mock`             | Working                  | Synthetic outputs for testing; no external tools required            |
| `boltz1`           | Working                  | Local Boltz-1 execution                                              |
| `boltz2`           | Working                  | Local Boltz-2 execution                                              |
| `esmfold`          | Working                  | Local ESMFold execution                                              |
| `rfdiffusion`      | Working                  | RFdiffusion backbone design                                          |
| `proteinmpnn`      | Working                  | ProteinMPNN sequence design                                          |
| `colabfold`        | Available when installed | Remote ColabFold API                                                 |
| `local_colabfold`  | Available when installed | Local ColabFold CLI                                                  |
| `alphafold2_local` | Available when installed | Local AlphaFold 2                                                    |
| `alphafold3_local` | Available when installed | Local AlphaFold 3 (JSON/input-dir style)                             |
| `alphafold_server` | Available when installed | AlphaFold Server HTTP API (requires explicit upload acknowledgement) |
| `alphafold_db`     | Available when installed | EBI AlphaFold DB REST lookup by accession                            |
| `openfold`         | Available when installed | OpenFold local execution                                             |
| `chai1`            | Available when installed | Chai-1 structure prediction                                          |

Harvested artifact types: `alphafold_model_cif`, `alphafold_summary_confidences`. Confidence metrics (ranking score, pTM, ipTM, chain-pair ipTM) are stored per job when `FOLDAGENT_ALPHAFOLD_STORE_CONFIDENCE_METRICS=true`.

---

## Quick Start

```bash
git clone <repo-url> fold-agent
cd fold-agent

python -m venv .venv
source .venv/bin/activate

cp .env.example .env
make install

# Start API (SQLite, mock pipeline, mock AlphaFold backend)
make dev                  # http://127.0.0.1:8010

# Seed demo data
make seed-demo

# Start dashboard
make dashboard            # http://127.0.0.1:8502
```

Port overrides without editing files:

```bash
make dev API_PORT=18010
make dashboard API_PORT=18010 DASHBOARD_PORT=18501
```

API endpoints once running:

- Swagger UI: `http://127.0.0.1:8010/api/docs`
- ReDoc: `http://127.0.0.1:8010/api/redoc`
- OpenAPI JSON: `http://127.0.0.1:8010/api/openapi.json`
- Dashboard: `http://127.0.0.1:8502`

---

## Architecture

```
Browser / CLI
     │
     ▼
Streamlit Dashboard      frontend/
     │
     ▼  REST / SSE / WebSocket
FastAPI Backend          backend/app/
  ├─ Safety Preflight
  ├─ Audit Logger
  ├─ RBAC / Encryption
  ├─ Case / Sample / Variant / Candidate APIs
  ├─ Report & Ethics Package Generation
     │
     ▼
Research Modes           backend/app/modes/
  vaccine_design | antibody_design | drug_discovery | gene_therapy
  enzyme_engineering | tcr_pmhc | ppi_mapping | protein_misfolding
  variant_pathogenicity
     │
     ▼
Pipeline Framework       backend/app/pipeline/
  BWA ──► Mutect2 ──► VEP ──► NetMHCpan
     │
     ▼
Structure Prediction     backend/app/alphafold/
  mock / boltz1 / boltz2 / esmfold / rfdiffusion / proteinmpnn
  colabfold / local_colabfold / alphafold2_local / alphafold3_local
  alphafold_server / alphafold_db / openfold / chai1
     │
     ▼
Background Jobs          backend/app/worker/
  Thread pool (default) or Celery + Redis (opt-in)
```

Directory layout:

```
/backend       FastAPI + SQLAlchemy + safety/audit/report logic
/frontend      Streamlit dashboard + py3Dmol structure viewer
/clients       TypeScript SDK (clients/typescript/)
/skills        Agent skill packs (claude-code / hermes / openclaw / shared)
/research_modes  Autoresearch workflow support
/docs          Operator guides, API references, safety docs
/examples      Synthetic demo data, mock expert-review examples
/scripts       Utility and seeding scripts
```

---

## Configuration

All settings use the `FOLDAGENT_` environment variable prefix. Copy `config.example.yaml` and `.env.example` as starting points.

Key environment variables:

| Variable                                       | Default                    | Description                                       |
| ---------------------------------------------- | -------------------------- | ------------------------------------------------- |
| `FOLDAGENT_SPECIES_MODE`                       | `demo`                     | Operating mode: `demo` / `dog` / `human`          |
| `FOLDAGENT_DATABASE_URL`                       | `sqlite:///./foldagent.db` | SQLAlchemy database URL                           |
| `FOLDAGENT_DB_INIT_MODE`                       | `create_all`               | `create_all` / `validate` / `alembic`             |
| `FOLDAGENT_API_PORT`                           | `8010`                     | API listen port                                   |
| `FOLDAGENT_DASHBOARD_PORT`                     | `8502`                     | Streamlit listen port                             |
| `FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND`          | `mock`                     | Default structure prediction backend              |
| `FOLDAGENT_ALPHAFOLD_ALLOWED_BACKENDS`         | _(all)_                    | Comma-separated list of enabled backends          |
| `FOLDAGENT_ALPHAFOLD_STORE_CONFIDENCE_METRICS` | `true`                     | Store pTM / ipTM per job                          |
| `FOLDAGENT_SAFETY_PREFLIGHT_ENABLED`           | `true`                     | Enable preflight safety checks                    |
| `FOLDAGENT_UNSAFE_TEXT_SCANNER_ENABLED`        | `true`                     | Scan outputs for prohibited patterns              |
| `FOLDAGENT_REQUIRE_PROFESSIONAL_OVERSIGHT`     | `true`                     | Block outputs without oversight flag              |
| `FOLDAGENT_CLOUD_UPLOAD_ENABLED`               | `false`                    | Allow external cloud backend calls                |
| `FOLDAGENT_CLOUD_UPLOAD_CONFIRMATION_REQUIRED` | `true`                     | Require explicit ACK before upload                |
| `FOLDAGENT_ENCRYPTION_AT_REST_ENABLED`         | `false`                    | Encrypt stored artifacts                          |
| `FOLDAGENT_ENCRYPTION_KEY`                     | _(none)_                   | Encryption key (set via env, not config file)     |
| `FOLDAGENT_PIPELINE_MODE`                      | `mock`                     | `mock` or `real`                                  |
| `FOLDAGENT_PIPELINE_BWA_REFERENCE`             | `/data/reference/hg38.fa`  | BWA reference genome path                         |
| `FOLDAGENT_PIPELINE_GATK_REFERENCE`            | `/data/reference/hg38.fa`  | GATK reference genome path                        |
| `FOLDAGENT_PIPELINE_VEP_CACHE_DIR`             | `/data/vep_cache`          | VEP cache directory                               |
| `FOLDAGENT_PIPELINE_VEP_ASSEMBLY`              | `GRCh38`                   | Reference assembly                                |
| `FOLDAGENT_REDIS_URL`                          | _(none)_                   | Redis URL for worker stack                        |
| `FOLDAGENT_CELERY_BROKER_URL`                  | _(none)_                   | Celery broker URL                                 |
| `FOLDAGENT_CELERY_RESULT_BACKEND`              | _(none)_                   | Celery result backend URL                         |
| `FOLDAGENT_BACKGROUND_JOB_BACKEND`             | `auto`                     | `auto` / `threadpool` / `celery`                  |
| `FOLDAGENT_AUDIT_LOG_PATH`                     | `./audit_logs`             | Audit log output directory                        |
| `FOLDAGENT_LOG_LEVEL`                          | `INFO`                     | Log level                                         |
| `FOLDAGENT_SECRET_KEY`                         | _(changeme)_               | Application secret key — **change in production** |

---

## Testing

```bash
# Run full test suite
make test

# Run with coverage
make test-cov

# Run a specific test file
pytest backend/tests/test_vaccine_design.py -v
```

The test suite covers 1,455 test files spanning all research modes, pipeline adapters, AlphaFold backends, safety enforcement, audit logging, report generation, agent events, worker dispatch, and Streamlit smoke tests. Tests run against mock backends by default; no external tools or credentials are required.

---

## Docker Deployment

```bash
# API only (thread pool, no Redis)
docker compose up app

# API + Redis + Celery worker
docker compose --profile worker up

# Worker services only
docker compose --profile worker up redis worker
```

The `auto` job backend detects Redis availability at dispatch time. If Redis is unreachable, jobs fall back to the thread pool without a restart.

For production, set `FOLDAGENT_DB_INIT_MODE=alembic` and supply a PostgreSQL `DATABASE_URL`. Run `alembic upgrade head` before starting the container, or set `db_init_mode: alembic` to auto-migrate on startup.

---

## Agent Skills

FoldAgent ships three agent skill packs for AI-assisted research workflows.

| Pack          | Location                            | Description                                                                |
| ------------- | ----------------------------------- | -------------------------------------------------------------------------- |
| Claude Code   | `skills/claude-code/`               | Claude Code skill pack for structure prediction and pipeline orchestration |
| Hermes        | `skills/hermes/`                    | Hermes skill pack for report generation and ethics workflows               |
| OpenClaw      | `skills/openclaw/`                  | OpenClaw integration for candidate review and data extraction              |
| Shared client | `skills/shared/foldagent_client.py` | Python client shared across all skill packs                                |

Skills communicate with the FoldAgent API over REST/SSE using the shared client. See the skill-specific install guides in `docs/`.

Installation guides:

- `docs/AGENT_SKILLS_GUIDE.md` — overview and architecture
- `docs/CLAUDE_CODE_INSTALL_GUIDE.md`
- `docs/HERMES_INSTALL_GUIDE.md`
- `docs/OPENCLAW_INSTALL_GUIDE.md`
- `docs/AUTORESEARCH_SAFE_USE_GUIDE.md`

---

## Safety and Ethics

FoldAgent is designed around the principle that AI-assisted structural biology research requires explicit safety boundaries at every layer.

**Enforcement layers:**

1. **Preflight checks** — every write and export operation passes through a preflight gate that evaluates the output against a prohibited-pattern list
2. **mRNA safety gate** — mRNA-specific outputs are scanned for unsafe construction patterns before export
3. **Audit trail** — every action (create, update, export, structure job, pipeline run) is logged with timestamp, user context, and payload hash
4. **Professional oversight requirement** — outputs are labeled `Research candidate only — not administerable` and the oversight flag must be set before export
5. **External upload acknowledgement** — any backend that submits data to an external service (AlphaFold Server) requires an explicit ACK field in the request

**What FoldAgent will not produce:**

- DIY vaccine manufacturing instructions
- Injection, dosing, or formulation instructions
- LNP formulation protocols
- Clinical validity claims without professional review

**Governance documents:**

- `SAFETY_POLICY.md`
- `ETHICS.md`
- `DATA_PRIVACY.md`
- `docs/SAFETY_GUIDE.md`
- `docs/PRIVACY_GUIDE.md`
- `docs/THREAT_MODEL.md`
- `docs/ETHICS_PACKAGE_GUIDE.md`

---

## Documentation

| Guide                                                                        | Description                                  |
| ---------------------------------------------------------------------------- | -------------------------------------------- |
| [docs/OPERATOR_GUIDE.md](docs/OPERATOR_GUIDE.md)                             | Full operator reference                      |
| [docs/VERIFICATION_WALKTHROUGH.md](docs/VERIFICATION_WALKTHROUGH.md)         | Step-by-step stack verification runbook      |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)                           | Development setup, extending the pipeline    |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)                         | Production deployment                        |
| [docs/ALPHAFOLD_BACKEND_GUIDE.md](docs/ALPHAFOLD_BACKEND_GUIDE.md)           | Backend configuration                        |
| [docs/BIOINFORMATICS_ADAPTER_GUIDE.md](docs/BIOINFORMATICS_ADAPTER_GUIDE.md) | BWA/GATK/VEP/pVACtools adapter setup         |
| [docs/SAFETY_GUIDE.md](docs/SAFETY_GUIDE.md)                                 | Safety system, preflight, prohibited outputs |
| [docs/PRIVACY_GUIDE.md](docs/PRIVACY_GUIDE.md)                               | Data privacy, local-first, deletion workflow |
| [docs/ETHICS_PACKAGE_GUIDE.md](docs/ETHICS_PACKAGE_GUIDE.md)                 | Ethics/IRB package generation                |
| [docs/AGENT_SKILLS_GUIDE.md](docs/AGENT_SKILLS_GUIDE.md)                     | Agent skill framework                        |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)                           | Common issues                                |
| [docs/FAQ.md](docs/FAQ.md)                                                   | Frequently asked questions                   |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)                                 | Threat model                                 |
| [docs/source_registry.md](docs/source_registry.md)                           | Sources and references                       |

---

## License

Apache-2.0 — see [LICENSE](LICENSE).

> External tools wrapped or invoked by FoldAgent (AlphaFold 3 weights, NetMHCpan, pVACtools, ESMFold, RFdiffusion, ProteinMPNN) carry their own licenses. Review each license before commercial or clinical research use.
