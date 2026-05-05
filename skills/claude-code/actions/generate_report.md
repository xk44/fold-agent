---
name: generate_report
description: Generate and export candidate review reports and ethics packages for expert review.
action_type: write
primary_endpoint: POST /cases/{case_id}/reports/candidate-review
framework: Claude Code
safety_gate: required
---

# Action: Generate Report

## Purpose

Generate the NeoVax candidate review report and optionally an ethics package
for a case. Reports are safety-gated, structured for expert review, and
exportable as artifacts.

## Safety Disclaimer

Reports contain research-grade computational predictions only. Do NOT share
reports outside the research team without proper de-identification and IRB/IACUC
approval. Every report must include the research-only safety label.

## API Endpoints

- `POST /safety/preflight` — Mandatory gate before report generation
- `GET /cases/{case_id}/candidates` — Confirm candidates are present
- `GET /cases/{case_id}/pipeline/status` — Confirm pipeline completed
- `POST /cases/{case_id}/reports/candidate-review` — Generate candidate review report
- `POST /cases/{case_id}/reports/ethics-package` — Generate ethics review package
- `GET /cases/{case_id}/reports` — List all reports for a case
- `GET /reports/{report_id}` — Retrieve a specific report
- `POST /reports/{report_id}/save` — Save report as a file artifact
- `GET /cases/{case_id}/bundle` — Get full case bundle
- `POST /cases/{case_id}/bundle/save` — Export full case bundle
- `GET /cases/{case_id}/report/enhanced` — Get enhanced report with citations
- `GET /cases/{case_id}/attestation` — Check professional attestation status
- `POST /cases/{case_id}/attestation` — Submit professional attestation

## Steps

1. **Safety preflight**: Call `POST /safety/preflight` with
   `action: "report.generate"` and `case_id`. Stop on block.

2. **Confirm pipeline complete**: Call `GET /cases/{case_id}/pipeline/status`.
   Abort if pipeline has not run or failed.

3. **Confirm candidates present**: Call `GET /cases/{case_id}/candidates`.
   Warn if zero candidates (report will be empty).

4. **Check attestation**: Call `GET /cases/{case_id}/attestation` to verify
   the supervising professional has attested. If missing, prompt for
   `POST /cases/{case_id}/attestation` before proceeding.

5. **Generate report** (require user confirmation):
   - Candidate review: `POST /cases/{case_id}/reports/candidate-review`
   - Ethics package (if requested): `POST /cases/{case_id}/reports/ethics-package`

6. **Save artifact** (if requested): Call `POST /reports/{report_id}/save`
   to persist the report. For full bundle: `POST /cases/{case_id}/bundle/save`.

7. **Return report**: Present the report ID, summary, and artifact path.
   Include research-only safety label on all output.

## Expected Output

- Report ID and generation timestamp
- Candidate summary table (count, top candidates by IC50)
- Report artifact path (if saved)
- Bundle artifact path (if full export requested)
- Safety label and professional review reminder

## Failure Handling

- Safety blocked: report exact reason, stop, do not generate.
- Pipeline not complete: direct user to `run_pipeline` action.
- No candidates: warn user, offer to proceed with empty report or abort.
- Attestation missing: require submission before report generation.
- Report generation API error: surface structured error payload, do not retry silently.

## Audit

Report generation and artifact saves are logged. Verify via `GET /audit/{case_id}`.
