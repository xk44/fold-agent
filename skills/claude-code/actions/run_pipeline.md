---
name: run_pipeline
description: Execute the NeoVax bioinformatics pipeline (BWA, Mutect2, VEP, NetMHCpan) for a case.
action_type: write
primary_endpoint: POST /cases/{case_id}/pipeline/run
framework: Claude Code
safety_gate: required
---

# Action: Run Pipeline

## Purpose

Launch the NeoVax bioinformatics pipeline for a case. The pipeline runs
BWA alignment, Mutect2 somatic variant calling, VEP annotation, and
NetMHCpan MHC-binding prediction to produce a ranked neoantigen candidate list.

## Safety Disclaimer

Pipeline execution on sequence-bearing data requires a named supervising
professional and a passed safety preflight. Do NOT present pipeline outputs
as clinically validated results. Mock/demo mode outputs are synthetic only.

## API Endpoints

- `POST /safety/preflight` — Mandatory gate before pipeline start
- `GET /cases/{case_id}` — Verify case exists and confirm species/mode
- `GET /cases/{case_id}/data/missing` — Confirm no required files are absent
- `POST /cases/{case_id}/pipeline/run` — Synchronous pipeline execution
- `POST /cases/{case_id}/pipeline/run-async` — Async background execution
- `GET /cases/{case_id}/pipeline/status` — Poll pipeline status
- `GET /cases/{case_id}/pipeline/history` — Review prior runs
- `GET /cases/{case_id}/executions` — Inspect per-step execution artifacts
- `GET /pipeline/adapters` — List available pipeline adapters
- `POST /pipeline/adapters/{adapter_name}/dry-run` — Preview adapter run
- `POST /pipeline/adapters/{adapter_name}/run` — Run a single adapter
- `GET /jobs/{job_id}` — Monitor async background job
- `POST /jobs/{job_id}/retry` — Retry a failed async job
- `POST /jobs/{job_id}/cancel` — Cancel a running async job

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` with
   `action: "pipeline.run"` and `case_id`. Stop on block; require confirmation
   if approval is needed.

2. **Verify case**: Call `GET /cases/{case_id}`. Confirm species mode and that
   `supervising_professional` is set.

3. **Check data completeness**: Call `GET /cases/{case_id}/data/missing`. If
   required files are missing, stop and report gaps before proceeding.

4. **Choose execution mode**:
   - Short / demo runs: `POST /cases/{case_id}/pipeline/run` (synchronous)
   - Long-running / production: `POST /cases/{case_id}/pipeline/run-async`
     (returns `job_id`)

5. **Monitor progress**:
   - Sync: inspect the returned `PipelineRunRead` for step statuses.
   - Async: poll `GET /jobs/{job_id}` until `status` is `completed` or
     `failed`. Stream events via `GET /agent/events` or WebSocket
     `ws://…/agent/events/ws?prefix=pipeline` for live updates.

6. **Inspect artifacts**: On completion, call
   `GET /cases/{case_id}/executions` to retrieve per-step logs and artifacts.

7. **Surface result**: Return a run summary with per-step status table, any
   warnings or failures, and the research-only framing.

## Expected Output

- Pipeline run ID and overall status
- Per-step status table (BWA, Mutect2, VEP, NetMHCpan)
- Any warnings or failure messages
- Execution artifact references
- Research-only label on all output

## Failure Handling

- Safety blocked: report exact policy violation, stop.
- Case not found: stop, request correct case ID.
- Missing data: list gaps from `/data/missing`, stop until resolved.
- Pipeline reports failure: surface step-level failure detail, suggest retry.
- Async job failed: call `POST /jobs/{job_id}/retry` only after user confirms.
- Adapter validation error: return structured validation payload unchanged.

## Audit

Pipeline starts, retries, and cancellations are logged with `log_action`.
Verify via `GET /audit/{case_id}`.
