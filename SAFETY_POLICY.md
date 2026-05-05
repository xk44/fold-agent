# NeoVax-Agent Safety Policy

## Scope

This policy governs all outputs, API responses, agent skill actions, reports,
exports, and user-facing text produced by NeoVax-Agent.

## Hard Boundaries

### MUST NOT Generate

1. DIY vaccine manufacturing protocols
2. Injection instructions of any kind
3. Dosing schedules for any substance
4. LNP formulation instructions
5. Tumor-lysate preparation instructions
6. Adjuvant mixing instructions
7. Sterility or QC release instructions for real administration
8. "Ready to inject" sequence packages
9. Medical recommendations to proceed with treatment
10. Claims that AI or any model output is clinically valid without
    professional validation
11. Claims that the system cures or treats cancer

### MUST Include On Every Export

- "Research candidate only -- not administerable" label
- Model/tool version information
- Uncertainty flags for any prediction
- Source citations
- "Professional review required" notice

## Safety Preflight System

Every write action, export, and agent task passes through the safety preflight
system before execution.

The preflight system checks:
- Whether the action is in the prohibited outputs list
- Whether the action requires expert mode
- Whether the action requires professional attestation
- Whether the action involves external data upload
- Whether the output matches unsafe text patterns

If the preflight system blocks an action:
- The action is NOT executed
- The attempt is logged in the audit trail
- The user is informed of the policy violation and which rule applied

## Mode Restrictions

### Demo Mode
- Synthetic data only
- No real patient/pet data
- No treatment claims
- "Demo -- for pipeline demonstration only" on all outputs

### Dog / Veterinary Mode
- Requires assigned vet-oncologist
- DLA/MHC limitations surfaced on every relevant output
- Owner consent documentation required
- No self-administration workflow
- No dosing or formulation instructions

### Human / Clinical Mode
- Most restrictive mode
- Requires assigned physician/oncologist
- Requires IRB/ethics approval path before any downstream discussion
- "Not for treatment use" on every output
- No direct patient self-use workflow
- No generated administerable construct

## Audit Requirements

Every action must log:
- case_id
- actor (user, agent, system)
- action type
- timestamp
- inputs hash
- outputs hash
- safety gate result (pass / block / requires_approval)

Audit logs are append-only.

## mRNA / Construct Handling

There is NO direct mRNA sequence design feature in the MVP.

Future expert-only sequence-level exports require:
- Explicit expert mode activation
- Case owner attestation
- Local-only processing
- Safety preflight pass
- Manual approval checkpoint
- Audit log entry
- Export watermark: "Research candidate only -- not administerable"

## AlphaFold Output Policy

AlphaFold structure predictions are theoretical computational models only.
They do NOT validate clinical efficacy. Every structure output must display:
- "Structure prediction only -- not clinical validation"
- Confidence metrics (pLDDT, pAE)
- Model version
- Date of prediction
- Uncertainty notice

## Agent Skill Safety

All agent skills (Claude Code, OpenClaw, Hermes) must:
- Include a safety boundaries section in their SKILL.md
- Never produce prohibited outputs
- Include a "when NOT to use" section
- Require user confirmation before dangerous actions
- Include a no-medical-advice warning
- Log all actions to the audit trail
- Support dry-run mode

## Unsafe Text Scanner

An automated pattern scanner checks all generated text before export for:
- Dosing language patterns
- Injection/administration instructions
- Formulation recipes
- Manufacturing steps
- Claims of clinical validity or cure

Matches are blocked and logged.