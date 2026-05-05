# Ethics Package Guide

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

The ethics package generator creates structured review materials for licensed professionals considering a FoldAgent research case. It does **not** determine legal sufficiency, replace IRB review, or constitute professional advice. Every package output requires review by a qualified physician, veterinary oncologist, or institutional ethics board before any real-world action is taken.

Ethics packages are generated via `POST /cases/{case_id}/reports/ethics-package` and stored as `Report` records with type `ethics_package`.

---

## When to Generate an Ethics Package

Generate an ethics package when:

- A case is moving from exploratory to active research coordination
- A collaborating institution or licensed lab requires oversight documentation
- An IRB or veterinary ethics committee requests a structured summary
- The species mode is `dog` or `human` and external parties are involved

Do not generate an ethics package as a substitute for actual IRB approval or professional consent.

---

## What the Package Contains

A generated ethics package report includes these sections:

### 1. Case Summary

- Case ID, species mode, diagnosis summary
- Sample count, variant count, candidate count
- Current consent status and redaction level
- Data directory and privacy posture

### 2. Consent Documentation Section

- Current `consent_status` value for the case
- Reminder that FoldAgent records consent status but does not validate legal sufficiency
- Placeholder checklist for IRB or ethics committee documentation

### 3. Privacy and Data Handling

- Whether cloud uploads are enabled
- Encryption-at-rest status
- Retention policy (default 365 days)
- Data handling warnings for genomic/sequence data

### 4. Risk Framing

- Explicit statement that all outputs are research coordination only
- Uncertainty flags from candidate predictions
- Missing data checklist (real sequencing, HLA/DLA typing, RNA-seq validation, professional review)
- Species-appropriate risk context

### 5. Professional Oversight Checklist

Species-dependent checklist generated from the case mode:

**Demo mode:**

- Confirm this is synthetic data only
- No real patient or animal data present

**Dog/Veterinary mode:**

- Licensed veterinary oncologist review required
- Institutional veterinary ethics approval
- Client/owner informed consent obtained
- Sequencing provider data-use agreement in place
- Chain-of-custody documentation for samples

**Human mode:**

- Licensed oncologist and immunologist review required
- IRB approval or waiver in place
- Patient informed consent obtained (see consent templates below)
- HIPAA or equivalent data protection compliance confirmed
- Data-use agreement with all collaborating institutions
- Sequencing provider privacy and data-use policies reviewed
- No self-administration or home-use of any output

### 6. Jurisdiction Warnings

- FoldAgent does not provide jurisdiction-specific legal or regulatory advice
- Human personalized vaccine research is regulated in most jurisdictions; consult a regulatory expert
- Veterinary research regulations vary by country and institution
- Outputs labeled "research candidate only" are not cleared, approved, or validated for clinical use

### 7. Research-Only Safety Labels

Every section of the package carries: **"Research candidate only — not administerable"**

---

## Consent Templates

FoldAgent includes plain-language consent template stubs accessible via the lab coordination module. These are **starting points only** — they must be reviewed and adapted by a legal or IRB professional before use.

Templates are in `backend/app/lab_coordination.py` and cover:

- Sequencing provider checklist (`SEQUENCING_PROVIDER_CHECKLIST`)
- RNA manufacturing inquiry checklist (`RNA_MANUFACTURING_CHECKLIST`) — note: this checklist explicitly prohibits requesting dosing, formulation, or administration instructions
- University outreach template (`UNIVERSITY_OUTREACH_TEMPLATE`)
- Secure handoff checklist (`SECURE_HANDOFF_CHECKLIST`)
- Lab outreach email template (`LAB_OUTREACH_EMAIL_TEMPLATE`)

Access via:

```bash
GET /lab/templates
```

---

## Generating a Package

```bash
# Safety preflight first (called automatically by the endpoint)
POST /safety/preflight
{
  "action": "generate_ethics_package",
  "species_mode": "human",
  "is_export": false
}

# Generate the package
POST /cases/{case_id}/reports/ethics-package

# Inspect the result
GET /reports/{report_id}

# Preview export
GET /reports/{report_id}/export?format=markdown

# Save to artifacts (requires confirmation)
POST /reports/{report_id}/save?format=markdown
```

The `create_ethics_review_package` agent skill in `skills/claude-code/`, `skills/openclaw/`, and `skills/hermes/` wraps this workflow with preflight gating and required confirmation steps.

---

## Exporting the Package

Ethics packages can be exported as `markdown` or `json`. All exports pass through safety preflight. Human-mode exports involving sequence data require expert mode.

Saved artifacts are written to:

```
artifacts/cases/{case_id}/reports/{report_id}.{format}
```

---

## Professional Oversight Checklist (Summary)

Before any real-world action based on FoldAgent outputs:

- [ ] Licensed professional (physician or veterinary oncologist) has reviewed all outputs
- [ ] Ethics package has been reviewed by the professional, not just generated
- [ ] IRB approval or institutional ethics waiver is in place (human or animal research)
- [ ] Consent is documented and legally sufficient for your jurisdiction
- [ ] All outputs are labeled "research coordination only" in any shared materials
- [ ] No output will be used as a basis for administering, manufacturing, or prescribing anything
- [ ] Data transfers follow your institution's data governance policies

---

## Limitations

- FoldAgent does not know your jurisdiction's regulations. Consult a regulatory expert.
- Generated consent language is a template only. A legal professional must review before use.
- The checklist is a research coordination aid, not a compliance certification.
- Ethics package generation does not replace IRB review or professional sign-off.
- The system records that a package was generated; it cannot verify that the professional review occurred.
