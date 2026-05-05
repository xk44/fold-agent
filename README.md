# FoldAgent

**AI-assisted protein science and structural biology research coordination platform.**

> **SAFETY DISCLAIMER — READ BEFORE USE**
>
> FoldAgent is **not medical advice**, not veterinary advice, not a vaccine manufacturing tool, and not a treatment app.
> Every output is research-only and requires review by a licensed physician or veterinary oncologist.
> No output should be used as dosing, injection, formulation, manufacturing, or administration guidance.

## Inspiration

FoldAgent was inspired by Paul Conyngham's public story of using AI and AlphaFold to help coordinate a research approach for his dog Rosie's cancer treatment.

- Paul on X: <https://x.com/paul_conyngham>
- UNSW article: <https://news.unsw.edu.au/en/meet-the-man-who-designed-a-cancer-vaccine-for-his-dog>
- Source registry: [docs/source_registry.md](docs/source_registry.md)

> Note: Paul's public GitHub repo is an autologous tumor-lysate protocol, not the exact mRNA neoantigen pipeline. FoldAgent does not reproduce manufacturing, dosing, formulation, or administration details from any source.

## Features

- Case management — organize subjects, samples, variants, and candidates per case
- Pipeline — BWA alignment → Mutect2 somatic variant calling → VEP annotation → NetMHCpan binding prediction
- AlphaFold structure prediction — ColabFold, LocalColabFold, AF2/AF3 local, AlphaFold Server (gated), AlphaFold DB
- Safety gates — preflight checks block prohibited outputs before any write or export
- Audit logging — every action recorded; exportable for professional review
- Ethics package — consent templates, privacy notices, IRB/veterinary-oversight checklists
- Agent skills — Claude Code, OpenClaw, and Hermes skill packs for AI-assisted workflows
- Local-first by default — no data leaves your machine unless you explicitly enable a cloud backend

## Architecture

```
  Browser / CLI
       │
       ▼
  Streamlit Dashboard  (frontend/)
       │
       ▼  REST / SSE / WebSocket
  FastAPI Backend      (backend/)
   ├─ Safety Preflight
   ├─ Audit Logger
   ├─ Case / Report APIs
       │
       ▼
  Pipeline Framework   (backend/pipeline/)
   ├─ BWA  ──► Mutect2  ──► VEP  ──► NetMHCpan
       │
       ▼
  AlphaFold Backends   (backend/alphafold/)
   ├─ mock / colabfold / local_colabfold
   └─ alphafold2_local / alphafold3_local / alphafold_server / alphafold_db
```

## Current status

Current implemented stack includes:

- FastAPI backend with audit logging, safety preflight, case/sample/variant/candidate APIs
- Streamlit dashboard with readable previews for reports, bundles, and structure jobs
- AlphaFold-family backend routing for:
  - `colabfold`
  - `local_colabfold`
  - `alphafold2_local`
  - `alphafold3_local`
  - `alphafold_server` (gated remote submission surface)
  - `alphafold_db` (reference lookup backend)
- Rich candidate-review and ethics-package report generation + markdown/json export
- AlphaFold artifact harvesting for model CIF and summary-confidence outputs
- Shared Python client in `skills/shared/foldagent_client.py`

## What it does

- Organizes research cases and sequencing metadata for demo, dog, and human workflows
- Coordinates mock-first bioinformatics execution and provenance tracking
- Connects to AlphaFold-family backends and records structure evidence
- Stores enriched structure metadata such as ranking score, pTM, ipTM, model/source references
- Produces candidate-review reports with candidate tables, missing-data checklist, tool versions, and safety labels
- Produces ethics-package reports with consent/privacy/risk/oversight/jurisdiction sections
- Exports reports and bundles as markdown/json and stores artifacts with integrity metadata
- Surfaces readable previews in the local dashboard for reports, bundles, and structure jobs

## What it does not do

- DIY vaccine manufacturing instructions
- Injection or dosing instructions
- LNP formulation instructions
- Medical recommendations
- Claims of clinical validity without professional review

## Modes

| Mode  | Purpose                                   | Restrictions                                             |
| ----- | ----------------------------------------- | -------------------------------------------------------- |
| Demo  | Synthetic-data testing                    | No real-patient treatment claims                         |
| Dog   | Veterinary oncology research coordination | Requires veterinary oversight                            |
| Human | Human clinical research coordination      | Most restrictive; requires physician/IRB style oversight |

## Quickstart

```bash
# enter repo
cd foldagent

# setup
cp .env.example .env
make install

# run API (SQLite, mock pipeline, mock/default AlphaFold flows)
make dev                 # defaults to http://127.0.0.1:8010

# seed demo data
make seed-demo

# open dashboard
make dashboard           # points at $(FOLDAGENT_API_URL) / defaults to http://127.0.0.1:8010
```

You can override ports/URL without editing files:

```bash
make dev API_PORT=18010
make dashboard API_PORT=18010 DASHBOARD_PORT=18501
# or explicitly
make dashboard FOLDAGENT_API_URL=http://127.0.0.1:18010 DASHBOARD_PORT=18501
```

Once running:

- API docs: `http://127.0.0.1:8010/api/docs` (or your `API_PORT`)
- ReDoc: `http://127.0.0.1:8010/api/redoc` (or your `API_PORT`)
- OpenAPI JSON: `http://127.0.0.1:8010/api/openapi.json` (or your `API_PORT`)
- Dashboard: usually `http://127.0.0.1:8502` (or your `DASHBOARD_PORT`)

## AlphaFold support

Current backend surfaces:

- `colabfold` / `local_colabfold`
  - typed request validation
  - dry-run and run routes
  - support for host-url and common CLI flags in command generation
- `alphafold2_local`
  - local command builder
- `alphafold3_local`
  - JSON/input-dir style request validation
  - output-dir parsing for `*_model.cif` and `*_summary_confidences.json`
- `alphafold_server`
  - explicit external-upload acknowledgement gate
- `alphafold_db`
  - lookup/reference backend using accession-based structure evidence

Harvested execution artifact types:

- `alphafold_model_cif`
- `alphafold_summary_confidences`

## Reports and previews

Candidate-review report payloads can include:

- candidate table
- missing-data checklist
- tool versions
- safety labels
- review status
- structure backend/status
- model/source/output-format references
- ranking score / pTM / ipTM / chain-pair ipTM

Ethics-package report payloads can include:

- consent templates
- privacy notices
- risk/benefit summary
- professional oversight checklist
- jurisdiction warning

Dashboard readable preview helpers:

- `frontend/app/report_preview.py`

## Architecture

```text
/backend   FastAPI + SQLAlchemy + audit/safety/report logic
/frontend  Streamlit dashboard
/skills    shared client + agent-oriented integration surfaces
/docs      source registry + API/reference snapshots + operator guide
/examples  synthetic demo data and mock expert-review example
```

## Worker stack (opt-in)

FoldAgent supports an optional Celery + Redis worker stack for distributed
background-job processing. By default, background jobs (pipeline runs,
AlphaFold structure predictions) run in an in-process thread-pool — no
additional infrastructure required.

When the worker stack is enabled, these jobs are dispatched to Celery workers
instead, giving you horizontal scalability and asynchronous execution with
result persistence in Redis.

### Quick start (local dev — threadpool, no Redis needed)

```bash
cp .env.example .env
make install
make dev        # background jobs use the built-in threadpool
```

### Enabling the worker stack

1. **Uncomment the broker variables** in `.env`:

```bash
FOLDAGENT_REDIS_URL=redis://localhost:6379/0
FOLDAGENT_CELERY_BROKER_URL=redis://localhost:6379/0
FOLDAGENT_CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

2. **Install the worker extras**:

```bash
pip install -e ".[worker]"   # or: make install-worker
```

3. **Start Redis + the worker** — either locally or via Docker Compose:

```bash
# Docker Compose (recommended)
docker compose --profile worker up

# Or start just the worker services:
docker compose --profile worker up redis worker
```

The app container detects the broker URL at dispatch time. If it can reach
Redis and `FOLDAGENT_BACKGROUND_JOB_BACKEND` is `auto` (the default), jobs are
routed to Celery automatically. If Redis is unavailable, jobs fall back to the
threadpool — no restart required.

### Disabling the worker stack

Comment out (or remove) the broker variables in `.env`, or set:

```bash
FOLDAGENT_BACKGROUND_JOB_BACKEND=threadpool
```

The app will always use the threadpool executor regardless of whether broker
URLs are present.

## Safety

- Every export is labeled `Research candidate only — not administerable`
- Every write/export action is audit-logged
- Expert review is required before real-world action
- AlphaFold Server style external uploads require explicit acknowledgement
- Unsafe output patterns are automatically blocked
- Artifact integrity is tracked with hashes

See:

- `SAFETY_POLICY.md`
- `ETHICS.md`
- `DATA_PRIVACY.md`
- `docs/reference/api/ALPHAFOLD_AND_REPORT_EXAMPLES.md`
- `docs/reference/api/openapi.json`

## Operator docs

Start with:

- `docs/VERIFICATION_WALKTHROUGH.md` — step-by-step runbook to verify a local stack
- `docs/OPERATOR_GUIDE.md` — full operator reference
- `docs/reference/api/README.md`
- `docs/reference/api/ALPHAFOLD_AND_REPORT_EXAMPLES.md`

## FAQ

Is this medical advice? No.

Can this make a vaccine? No.

Can I treat my dog/human with this? No. Professional review is required.

Does AlphaFold validate efficacy? No. Structure predictions are theoretical modeling only.

Can I keep data local? Yes, that is the default.

Can I use AlphaFold Server? Yes, but only with explicit external-upload acknowledgement.

## Documentation

| Guide                                                                        | Description                                  |
| ---------------------------------------------------------------------------- | -------------------------------------------- |
| [docs/SAFETY_GUIDE.md](docs/SAFETY_GUIDE.md)                                 | Safety system, preflight, prohibited outputs |
| [docs/PRIVACY_GUIDE.md](docs/PRIVACY_GUIDE.md)                               | Data privacy, local-first, deletion workflow |
| [docs/ALPHAFOLD_BACKEND_GUIDE.md](docs/ALPHAFOLD_BACKEND_GUIDE.md)           | AlphaFold backend configuration              |
| [docs/BIOINFORMATICS_ADAPTER_GUIDE.md](docs/BIOINFORMATICS_ADAPTER_GUIDE.md) | BWA/GATK/VEP/pVACtools adapter setup         |
| [docs/ETHICS_PACKAGE_GUIDE.md](docs/ETHICS_PACKAGE_GUIDE.md)                 | Ethics/IRB package generation                |
| [docs/AGENT_SKILLS_GUIDE.md](docs/AGENT_SKILLS_GUIDE.md)                     | Agent skill framework overview               |
| [docs/CLAUDE_CODE_INSTALL_GUIDE.md](docs/CLAUDE_CODE_INSTALL_GUIDE.md)       | Installing Claude Code skills                |
| [docs/OPENCLAW_INSTALL_GUIDE.md](docs/OPENCLAW_INSTALL_GUIDE.md)             | Installing OpenClaw skills                   |
| [docs/HERMES_INSTALL_GUIDE.md](docs/HERMES_INSTALL_GUIDE.md)                 | Installing Hermes skills                     |
| [docs/AUTORESEARCH_SAFE_USE_GUIDE.md](docs/AUTORESEARCH_SAFE_USE_GUIDE.md)   | Safe autoresearch usage                      |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)                           | Development setup, extending the pipeline    |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)                         | Production deployment                        |
| [docs/OPERATOR_GUIDE.md](docs/OPERATOR_GUIDE.md)                             | Operator reference                           |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)                                 | Threat model                                 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)                           | Common issues                                |
| [docs/FAQ.md](docs/FAQ.md)                                                   | Frequently asked questions                   |
| [docs/source_registry.md](docs/source_registry.md)                           | Sources, references, inspirations            |

## License

Apache-2.0 — see LICENSE file.

> External tools wrapped by FoldAgent (AlphaFold3 weights, NetMHCpan, pVACtools) have their own licenses. Review each before commercial or clinical use.
