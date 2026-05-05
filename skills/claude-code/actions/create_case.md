---
name: create_case
description: Create a new FoldAgent case with subject and sample registration.
action_type: write
primary_endpoint: POST /cases
framework: Claude Code
safety_gate: required
---

# Action: Create Case

## Purpose

Create a new FoldAgent case record, register subjects, and upload initial sample
metadata before any pipeline execution. This is the required first step for all
FoldAgent workflows.

## Safety Disclaimer

Do NOT create cases with real patient identifiers unless operating under an
approved institutional protocol with a named supervising professional. In demo
mode, use synthetic identifiers only.

## API Endpoints

- `POST /cases` — Create the case record
- `POST /cases/{case_id}/subjects` — Register subjects (patients/animals)
- `POST /cases/{case_id}/samples` — Register sample metadata
- `GET /cases/{case_id}` — Verify case was created correctly
- `GET /cases/{case_id}/data/checklist` — Confirm required data is present
- `GET /cases/{case_id}/data/missing` — Identify missing files before pipeline
- `POST /safety/preflight` — Safety gate before any write on non-demo data

## Request Schema: POST /cases

```json
{
  "species": "canis_lupus_familiaris",
  "diagnosis_summary": "Osteosarcoma, appendicular",
  "supervising_professional": "Dr. Jane Smith, DVM"
}
```

Supported `species` values: `homo_sapiens`, `canis_lupus_familiaris`,
`mus_musculus`, `felis_catus`.

## Steps

1. **Safety preflight** (non-demo data): Call `POST /safety/preflight` with
   `action: "case.create"`. Stop if blocked; request approval if required.

2. **Create case**: Call `POST /cases` with species, diagnosis summary, and
   supervising professional. Capture the returned `case_id`.

3. **Register subject**: Call `POST /cases/{case_id}/subjects` with subject
   demographics (age, sex, breed for veterinary cases).

4. **Register samples**: Call `POST /cases/{case_id}/samples` for each sample
   (tumor, matched normal, RNA-seq where available).

5. **Verify completeness**: Call `GET /cases/{case_id}/data/checklist` and
   `GET /cases/{case_id}/data/missing` to confirm required files are present
   before downstream steps.

## Expected Output

- Case ID (UUID) for use in all subsequent actions
- Subject ID(s)
- Sample inventory with completeness status
- Missing data checklist (if any gaps)

## Failure Handling

- If safety preflight blocks: report exact reason and stop.
- If species is unsupported: list supported values and stop.
- If supervising professional is missing: require it before proceeding.
- If sample registration fails validation: surface the structured error payload.

## Audit

Every case creation is logged via `log_action` with `action: "case.created"`.
Verify via `GET /audit/{case_id}` after creation.
