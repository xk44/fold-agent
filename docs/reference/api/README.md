# FoldAgent API reference snapshot

Generated local reference for current API surface.

Current snapshot stats:
- `41` API paths
- `37` component schemas

Files:
- `openapi.json` — current FastAPI OpenAPI schema snapshot
- `ALPHAFOLD_AND_REPORT_EXAMPLES.md` — curated examples for upgraded AlphaFold/report workflows

Primary docs endpoints when server is running:
- `/api/docs`
- `/api/redoc`
- `/api/openapi.json`

Notable current AlphaFold API behavior captured in this snapshot:
- richer backend diagnostics on `GET /alphafold/backends`
- backend-specific dry-run and run payload validation
- dry-run parity now includes `validation_reason` plus backend `diagnostics`
- deeper local validation metadata including `validation_reason`, `version_probe`, `gpu_runtime_available`, and configured-path checks
- API-side HTTP `409` gating on `/alphafold/backends/{backend_name}/run` when backend environment validation is not OK
- structured `409` error payloads now expose `backend_name`, `validation_ok`, and `validation_reason`
- AlphaFold Server safety acknowledgement remains required for external upload flows

Current run endpoint OpenAPI summary:
- `Run AlphaFold backend`
