# FoldAgent Operator Guide

This guide is for someone running the local FoldAgent stack and trying to understand the current working surfaces.

## Core endpoints

When the API is running locally:
- Swagger UI: `/api/docs`
- ReDoc: `/api/redoc`
- OpenAPI JSON: `/api/openapi.json`

Local reference snapshot:
- `docs/reference/api/openapi.json`
- `docs/reference/api/ALPHAFOLD_AND_REPORT_EXAMPLES.md`

## Recommended operator flow

1. Create or select a case.
2. Register samples if needed.
3. Check AlphaFold backend diagnostics before attempting structure work.
4. Run mock pipeline and/or AlphaFold backend flows.
5. Review variants and candidates.
6. Generate candidate-review and ethics-package reports.
7. Export/save reports and inspect artifacts.
8. Use bundle exports for compact case handoff.

## AlphaFold operator notes

### Available backend names
- `colabfold`
- `local_colabfold`
- `alphafold2_local`
- `alphafold3_local`
- `alphafold_server`
- `alphafold_db`

### Backend intent
- `colabfold` / `local_colabfold`: local sequence-driven wrappers around `colabfold_batch`
- `alphafold2_local`: local AF2 shell builder using FASTA-style inputs
- `alphafold3_local`: local AF3 shell builder using JSON or input-dir style flows with output-dir parsing
- `alphafold_server`: remote/gated submission surface; requires external-upload acknowledgement
- `alphafold_db`: built-in reference lookup path for known accessions

### Backend metadata surfaced in `/alphafold/backends`
Each backend payload can expose:
- `mode`
- `available`
- `validation_ok`
- `validation_reason`
- `requires_gpu`
- `requires_external_upload`
- `supports_protein_only`
- `supports_complexes`
- `supports_rna_dna_ligands`
- `license_notes`
- `command`
- `path`
- `diagnostics`

### Deeper local validation behavior
`validation_ok` is no longer just “binary on PATH”. For local shell backends it now reflects a deeper local check bundle:
- command lookup on PATH
- short executable probe (`--version` or `--help` depending on backend family)
- GPU runtime presence check when the backend requires GPU
- configured path checks for AlphaFold-specific env vars when those env vars are set

Current env-path checks:
- `FOLDAGENT_ALPHAFOLD2_DATA_DIR`
- `FOLDAGENT_ALPHAFOLD3_MODEL_DIR`
- `FOLDAGENT_ALPHAFOLD3_DB_DIR`

If one of those env vars is set and the path is missing, diagnostics report it and `validation_ok` becomes false.

### Diagnostics keys by backend family
Common diagnostics keys:
- `command_on_path`
- `command_name`
- `version_probe`
- `gpu_runtime_available`
- `configured_paths`

Backend-specific examples:
- ColabFold-family:
  - `host_url_supported`
  - `supports_a3m_input`
  - `supports_multimer_fasta_colon_syntax`
  - `supports_templates_flag`
  - `supports_num_recycle`
- AlphaFold 2 local:
  - `supports_fasta_input`
  - `supports_data_dir`
  - `supports_max_template_date`
- AlphaFold 3 local:
  - `requires_json_input`
  - `supports_input_dir`
  - `parses_output_directory`
  - `harvests_model_cif_artifacts`
  - `harvests_summary_confidences`
- AlphaFold Server:
  - `requires_external_upload_acknowledgement`
  - `supports_remote_json_submission`
- AlphaFold DB:
  - `supports_accession_lookup`
  - `returns_reference_structure_metadata`

### Input mode routing in the dashboard
The dashboard AlphaFold form auto-routes inputs by backend diagnostics.

Input modes:
- `sequence`
  - active field: sequence
  - typical backends: `colabfold`, `local_colabfold`, `alphafold2_local`
- `json`
  - active field: json path
  - typical backends: `alphafold3_local`, `alphafold_server`
- `accession`
  - active field: accession
  - backend: `alphafold_db`

Inactive fields are disabled and show an inline reason.

### Recommended backend selection
The dashboard chooses a default recommended backend automatically. Current ranking favors:
- available backends over unavailable ones
- validated backends over non-validated ones
- backends that do not require external upload
- local mode over reference mode over cloud mode
- richer capability surfaces where there is otherwise a tie

The diagnostics panel also shows a “Recommended backend” summary banner with reasons.

### Form severity and blocked reasons
The form uses three operator-facing severity states:
- `info`
  - backend appears ready for the selected input mode
- `warning`
  - backend exists but has extra requirements (for example validation incomplete or acknowledgement required)
- `error`
  - backend is not currently runnable locally

Common blocked reasons:
- `Selected backend is not currently runnable on this system.`
- `Acknowledge the backend requirements before submitting this run.`

Important: the dashboard is not the only guard anymore. The API now also refuses `POST /alphafold/backends/{backend_name}/run` with HTTP 409 when backend environment validation is not OK, using the backend's `validation_reason` in the response.

### Warning acknowledgement flow
When a backend is warning-severity and requires acknowledgement:
- the dashboard shows a checkbox
- the submit button stays blocked until checked
- once acknowledged, the blocked reason clears

### Capability chip row
The AlphaFold form shows a compact chip-style summary for the selected backend:
- `mode: ...`
- `gpu: yes/no`
- `complexes: yes/no`
- `rna/dna/ligands: yes/no`

Use this as the quick glance summary before reading the full diagnostics block.

### Payload preview
Before submission, the dashboard shows the exact request payload it plans to send.

Typical shapes:
- Sequence backend:
  - `case_id`
  - `job_name`
  - `backend_name`
  - `sequence`
- JSON backend:
  - `case_id`
  - `job_name`
  - `backend_name`
  - `input_kind: json`
  - `json_path`
- Accession backend:
  - `case_id`
  - `job_name`
  - `backend_name`
  - `accession`

### Important safety behavior
- `alphafold_server` runs are blocked unless upload acknowledgement is present
- AlphaFold outputs remain research-only and not clinical validation
- dashboard/operator messaging is only a UX aid; server-side safety checks still matter most

## Report/operator notes

### Candidate review reports
Current report payloads can contain:
- candidate table
- missing-data checklist
- tool versions
- safety labels
- structure metadata (`model_cif`, `source_url`, `ranking_score`, `ptm`, `iptm`)

### Ethics package reports
Current report payloads can contain:
- consent templates
- privacy notices
- risk/benefit summary
- professional oversight checklist
- jurisdiction warning

### Export behavior
Reports can be exported as:
- markdown
- json

Bundle exports can be exported as:
- markdown
- json

## Dashboard notes

### AlphaFold diagnostics section
The top-level diagnostics section is visible even before case selection and currently includes:
- metrics row
- recommended backend banner
- readable diagnostics preview
- backend capability table
- raw payload expander

### AlphaFold form UX
The AlphaFold form currently includes:
- backend picker with ready/needs-validation/unavailable labeling
- default recommended backend selection
- severity banners
- capability chip row
- readable guidance block
- disabled-field reasons
- acknowledgement checkbox when needed
- payload preview
- exact submit blocked reason before the button

### Other dashboard surfaces
The dashboard also provides:
- structure job explorer
- linked execution artifact browsing
- artifact download links
- case bundle loading/export/save flows
- readable previews for reports, bundles, and structure jobs
- structure viewer / compare viewer flows
- pipeline shell adapters
- task management lanes and summary metrics

## Artifact notes

Execution artifacts can include:
- execution log
- execution output json
- AlphaFold model CIF
- AlphaFold summary confidences

Harvested AlphaFold files are copied under artifact root before registration, so they remain downloadable through the artifact endpoint.

## Shared client

Primary integration helper:
- `skills/shared/foldagent_client.py`

Useful current methods:
- `alphafold_backend_dry_run()`
- `alphafold_backend_run()`
- `list_structure_jobs()`
- `get_structure_job()`
- `export_report()`
- `save_report()`
- `get_case_bundle()`
- `export_case_bundle()`
- `save_case_bundle()`

## Practical starting docs

Read these first when resuming work:
- `README.md`
- `docs/reference/api/README.md`
- `docs/reference/api/ALPHAFOLD_AND_REPORT_EXAMPLES.md`
- `docs/reference/alphafold/README.md`
- `docs/reference/alphafold/DOCS_TO_CODE_GAP_REPORT.md`
