# Safety Guide

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

Every write action, export, and agent task passes through the safety preflight system before execution. The system is implemented in `backend/app/safety/` and has three layers:

1. Unsafe text scanner — pattern-matching on output content
2. mRNA/sequence gate — extra restrictions on sequence-level data
3. Mode-based restrictions — demo, dog, and human modes each carry different constraints

The preflight result is always one of: `pass`, `block`, or `requires_approval`. Blocked actions are logged and never proceed.

---

## Preflight Checks (`preflight.py`)

Call `POST /safety/preflight` before any write, export, or agent task. The function `preflight_action()` runs five sequential checks:

### Check 1 — Unsafe Text Scanner

If `content` is provided, the scanner tests it against `UNSAFE_OUTPUT_PATTERNS`. A match results in an immediate `BLOCK`.

Blocked patterns include:

- Injection/injectable language
- Dosing schedules or regimens
- LNP/lipid nanoparticle formulation or preparation
- Adjuvant mixing or preparation
- Sterility/QC release for administration
- "Ready to inject/administer/use"
- Manufacturing or preparing vaccine/mRNA/RNA
- Treatment protocols or self-administration
- Clinical validity claims or "AI cures cancer"

### Check 2 — mRNA Gate

The dedicated mRNA/sequence gate (`mrna_gate.py`) runs after the text scanner. It activates when any of the following are true:

- `involves_sequence_data=True`
- The content contains a nucleotide sequence (12+ contiguous ACGUTN characters)
- The action string contains "sequence", "mrna", "rna", or "construct"

Gate outcomes:

- **Human mode + export + not expert mode** → `BLOCK` with IRB/physician message
- **Not expert mode (any mode)** → `REQUIRES_APPROVAL` with professional attestation message
- **Expert mode active** → `PASS`

### Check 3 — External Upload Gate

If `involves_external_upload=True`, result is always `REQUIRES_APPROVAL`. The AlphaFold Server backend sets this flag automatically.

### Check 4 — Demo Mode Content Guard

In `species_mode=demo`, content containing "clinically validated", "treatment plan", or "administer" returns `BLOCK`.

### Check 5 — Export Logging

Export actions (`is_export=True`) are always logged even when passing. No additional block logic at this step.

---

## Unsafe Text Scanner

`check_text_for_unsafe_patterns(text)` returns `(is_safe: bool, matched: list[str])`. Call this directly if you need to pre-screen content before invoking the full preflight.

Example patterns that will block:

```
"Here is a dosing schedule and injection instruction."   → BLOCK
"LNP formulation mix for mRNA vaccine"                   → BLOCK
"Candidate review summary for expert research."          → PASS
```

---

## mRNA Gate (`mrna_gate.py`)

`looks_like_sequence_content(content)` uses a regex `[ACGUTNacgutn]{12,}` to detect raw nucleotide strings. Any sequence-looking content triggers the gate regardless of action name.

`evaluate_mrna_gate(...)` is called internally by `preflight_action()`. Do not call it independently; use `preflight_action()` to ensure all five checks run.

---

## Expert Mode

Expert mode (`is_expert_mode=True`) relaxes the mRNA gate but does **not** bypass the unsafe text scanner. It is intended for use by licensed oncologists or researchers who have acknowledged professional oversight requirements.

Expert mode must be set per-request. There is no global session flag. Set it only after professional attestation is recorded.

---

## Species-Based Restrictions

The `species_mode` setting (configured via `FOLDAGENT_SPECIES_MODE`) controls baseline safety posture:

| Mode    | Restriction level | Notes                                                              |
| ------- | ----------------- | ------------------------------------------------------------------ |
| `demo`  | Moderate          | Synthetic data only; blocks clinical claims                        |
| `dog`   | High              | Requires veterinary oncologist oversight                           |
| `human` | Highest           | Sequence exports blocked without physician + IRB; most restrictive |

Mode is set at startup via environment variable. Changing it requires restarting the service (it is not a runtime toggle).

---

## Prohibited Outputs

The system will never produce or export:

- Vaccine manufacturing instructions
- Injection or dosing schedules
- LNP encapsulation or adjuvant formulation protocols
- Self-treatment workflows
- Claims that an AI output is clinically validated
- Sequence-level exports in human mode without expert + IRB attestation

Any API endpoint that would produce these outputs will return a `403` or `422` with the exact block reason from preflight.

---

## Audit Trail

Every preflight call — pass, block, or requires_approval — is logged to the audit trail via `backend/app/safety/audit.py`. Log entries include:

- `log_id` (UUID)
- `case_id`
- `actor` (user or agent name)
- `action` string
- `inputs_hash` and `outputs_hash` (SHA-256, for tamper detection)
- `safety_gate_result`

Audit logs are append-only. Use `GET /audit` or the export utilities in `privacy.py` to retrieve them.

---

## Safety Configuration

Set via environment variables (prefix `FOLDAGENT_`):

| Variable                                | Default | Description                                 |
| --------------------------------------- | ------- | ------------------------------------------- |
| `FOLDAGENT_SAFETY_PREFLIGHT_ENABLED`       | `true`  | Master switch for preflight                 |
| `FOLDAGENT_UNSAFE_TEXT_SCANNER_ENABLED`    | `true`  | Enable text pattern scanner                 |
| `FOLDAGENT_REQUIRE_PROFESSIONAL_OVERSIGHT` | `true`  | Attach oversight requirement to all outputs |
| `FOLDAGENT_SPECIES_MODE`                   | `demo`  | Operating mode                              |

Do not disable preflight in production.

---

## Testing Safety

```bash
# Run all safety-tagged tests
make test-safety

# Run the preflight unit tests specifically
pytest backend/tests/test_preflight.py -v
pytest backend/tests/test_mrna_safety_gate_api.py -v
pytest backend/tests/test_safety_enforcement_api.py -v
```
