# AlphaFold and report examples

This file documents the upgraded AlphaFold, report, diagnostics, gating, dry-run parity, and dashboard-preview surfaces in the current NeoVax repo.

## Running API docs

When the FastAPI app is running:
- Swagger UI: `/api/docs`
- ReDoc: `/api/redoc`
- OpenAPI JSON: `/api/openapi.json`

Local exported schema snapshot:
- `docs/reference/api/openapi.json`

## AlphaFold backend diagnostics

### 1. Inspect backend diagnostics

GET `/alphafold/backends`

Current backend payloads can expose:
- `available`
- `validation_ok`
- `validation_reason`
- `version_string`
- `version_probe_ok`
- `diagnostics.version_probe`
- `diagnostics.gpu_runtime_available`
- `diagnostics.configured_paths`

Example troubleshooting signals:
- executable found but probe failed
- probe timed out
- GPU runtime missing for GPU-required backends
- configured AlphaFold env path has `exists=false` when the env var is set

### 2. ColabFold dry run with custom MSA server

POST `/alphafold/backends/colabfold/dry-run`

```json
{
  "case_id": "demo-case",
  "job_name": "colabfold-demo",
  "sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV",
  "host_url": "https://msa.example.org",
  "num_recycle": 6,
  "num_seeds": 3,
  "use_templates": true
}
```

Dry-run responses now include:
- `validation_reason`
- `diagnostics`
- the same command/availability/validation bundle used to explain whether the backend can run now

### 3. AlphaFold 3 local run from JSON input

POST `/alphafold/backends/alphafold3_local/run`

```json
{
  "case_id": "demo-case",
  "candidate_id": "candidate-123",
  "job_name": "af3-rich",
  "input_kind": "json",
  "json_path": "/tmp/af3.json"
}
```

Current API-side behavior:
- if backend environment validation is not OK, NeoVax returns HTTP `409`
- the error body now includes:
  - `detail`
  - `backend_name`
  - `validation_ok`
  - `validation_reason`

Example 409 body:

```json
{
  "detail": "AlphaFold backend 'colabfold' failed environment validation: Command 'colabfold_batch' not found on PATH.",
  "backend_name": "colabfold",
  "validation_ok": false,
  "validation_reason": "Command 'colabfold_batch' not found on PATH."
}
```

Possible parsed outputs now supported:
- direct `stdout` payload with `structure`
- `stdout` payload with `output_dir`, where NeoVax inspects:
  - `*_model.cif`
  - `*_summary_confidences.json`

### 4. AlphaFold Server run

POST `/alphafold/backends/alphafold_server/run`

```json
{
  "case_id": "demo-case",
  "job_name": "remote-job",
  "input_kind": "json",
  "json_path": "/tmp/afserver.json",
  "acknowledge_external_upload": true
}
```

Important behavior:
- without `acknowledge_external_upload: true`, server-mode runs are blocked by safety gating
- even with acknowledgement, backend environment validation still has to pass for the run endpoint to execute

### 5. AlphaFold DB lookup

POST `/alphafold/backends/alphafold_db/run`

```json
{
  "case_id": "demo-case",
  "candidate_id": "candidate-123",
  "accession": "P04637",
  "job_name": "tp53-ref"
}
```

This populates structure evidence such as:
- `source_url`
- `model_cif`
- `summary_confidences_json`
- `output_format`
- `accession`

## Candidate review report fields

Current candidate review `content_json` can include:
- `candidate_table`
- `missing_data_checklist`
- `tool_versions`
- `safety_labels`
- `review_status`
- `structure_backend`
- `structure_status`
- `model_cif`
- `source_url`
- `output_format`
- `ranking_score`
- `ptm`
- `iptm`
- `chain_pair_iptm`

## Ethics package report fields

Current ethics package `content_json` can include:
- `consent_templates`
- `privacy_notices`
- `risk_benefit_summary`
- `professional_oversight_checklist`
- `jurisdiction_warning`

## Dashboard/operator surfaces tied to this API

The dashboard now exposes:
- top-level diagnostics metrics
- recommended backend banner
- validation troubleshooting expander
- capability table expander
- backend picker with ready/warning/unavailable labels
- capability chip row in the run form
- blocked reason messaging before submit
- payload preview before submit

Key helper module:
- `frontend/app/report_preview.py`

Key dashboard file:
- `frontend/app/dashboard.py`

## Artifact harvesting behavior

AlphaFold output-dir parsing can harvest and register binary artifacts for an execution:
- `alphafold_model_cif`
- `alphafold_summary_confidences`

Harvested files are copied under artifact root before registration so they are downloadable through:
- GET `/artifacts/file?path=...`

## Shared client methods relevant to these flows

See `skills/shared/neovax_client.py` for:
- `alphafold_backend_dry_run()`
- `alphafold_backend_run()`
- `list_structure_jobs()`
- `get_structure_job()`
- `export_report()`
- `get_case_bundle()`
- `export_case_bundle()`
