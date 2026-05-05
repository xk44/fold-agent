---
name: review_candidates
description: Review and annotate neoantigen candidates after pipeline execution.
action_type: read-write
primary_endpoint: GET /cases/{case_id}/candidates
framework: Claude Code
safety_gate: required
---

# Action: Review Candidates

## Purpose

Retrieve, rank, and annotate neoantigen candidates produced by the NeoVax
pipeline. Supports reviewing binding affinity scores, variant annotations,
false-positive risk, clinical evidence, and per-candidate expert review flags.

## Safety Disclaimer

Candidate rankings are computational predictions only. Do NOT interpret
binding affinity scores as immunogenicity guarantees or treatment readiness
indicators. All candidates require licensed professional review.

## API Endpoints

- `GET /cases/{case_id}/candidates` — Retrieve ranked candidate list
- `GET /cases/{case_id}/variants` — Get underlying variant annotations
- `PATCH /candidates/{candidate_id}/review` — Set expert review flags
- `PATCH /variants/{variant_id}/review` — Set variant-level review flags
- `GET /cases/{case_id}/evidence` — Retrieve supporting evidence per candidate
- `GET /cases/{case_id}/false-positive-risk` — Get false-positive risk scores
- `GET /cases/{case_id}/report/citations` — Retrieve literature citations
- `POST /safety/preflight` — Gate before writing review flags on non-demo data
- `GET /cases/{case_id}/pipeline/status` — Confirm pipeline completed before review

## Steps

1. **Confirm pipeline complete**: Call `GET /cases/{case_id}/pipeline/status`.
   Stop and prompt user to run pipeline if status is not `completed`.

2. **Retrieve candidates**: Call `GET /cases/{case_id}/candidates`. Sort by
   predicted binding affinity (lowest IC50 = highest priority).

3. **Retrieve variants**: Call `GET /cases/{case_id}/variants` to correlate
   each candidate with its source variant and VEP annotation.

4. **Check false-positive risk**: Call `GET /cases/{case_id}/false-positive-risk`
   to flag candidates with elevated false-positive scores.

5. **Retrieve evidence**: Call `GET /cases/{case_id}/evidence` and
   `GET /cases/{case_id}/report/citations` to attach supporting literature.

6. **Safety preflight** (before writing review flags): Call
   `POST /safety/preflight` with `action: "candidate.review"`.

7. **Set review flags**: For candidates the user approves or rejects, call
   `PATCH /candidates/{candidate_id}/review` with the expert decision and notes.

8. **Surface review summary**: Return a table of candidates with scores, risk
   flags, evidence status, and review decisions. Include research-only label.

## Expected Output

- Ranked candidate table: peptide sequence, MHC allele, IC50 (nM), rank %
- Source variant and VEP consequence per candidate
- False-positive risk score per candidate
- Evidence and citation counts
- Per-candidate review status (pending / approved / rejected)

## Failure Handling

- Pipeline not complete: stop, direct user to `run_pipeline` action.
- No candidates found: confirm pipeline actually ran; check for variant-calling failures.
- Safety blocked on review write: report reason, do not write flags.
- Candidate not found on PATCH: surface 404, verify ID from candidate list.

## Audit

Candidate review decisions are logged. Verify via `GET /audit/{case_id}`.
