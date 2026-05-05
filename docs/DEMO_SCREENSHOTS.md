# NeoVax-Agent Demo Screenshots

Placeholder documentation for UI screenshots. Screenshots to be added after UI stabilization.

---

## Case Creation

**Endpoint:** `POST /demo/create-case`

Screenshot: case creation confirmation showing case ID, subject display name, sample/variant/candidate counts, and structure job ID.

---

## Pipeline Status

**Endpoint:** `GET /cases/{case_id}/pipeline/status`

Screenshot: pipeline run status view showing step progression, current status, and completion indicators.

---

## Candidate Explorer

**Endpoint:** `GET /cases/{case_id}/candidates`

Screenshot: candidate antigen table with MHC context, peptide metadata, binding predictions, and review status controls.

---

## Structure Gallery

**Endpoint:** `GET /cases/{case_id}/structure-jobs`

Screenshot: AlphaFold structure job list with backend, status, and output path for each candidate structure.

---

## Report Generation

**Endpoints:** `GET /cases/{case_id}/report/html`, `GET /cases/{case_id}/report/markdown`

Screenshot: rendered HTML report with candidate tables, evidence summary, citations, and safety labels. Markdown export view shown alongside.

---

## Safety Dashboard

**Endpoints:** `GET /cases/{case_id}/false-positive-risk`, `GET /cases/{case_id}/evidence`, `GET /cases/{case_id}/report/citations`

Screenshot: safety panel showing FP risk level, evidence flags, and verified citation list from the hallucination guard.

---

> **Note:** Screenshots to be added after UI stabilization.
> All demo data is synthetic. NOT FOR CLINICAL USE.
