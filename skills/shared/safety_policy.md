# FoldAgent Shared Safety Policy

This document defines the canonical safety rules that ALL agent skills must follow,
regardless of framework (Claude Code, OpenClaw, Hermes).

## Declaration

FoldAgent is a research coordination platform. It does NOT provide:

- Medical advice
- Vaccine manufacturing instructions
- Injection or dosing instructions
- Formulation or compounding instructions
- Treatment recommendations
- Claims of clinical validity without professional review

## Rules for Agent Skills

1. **Never generate prohibited outputs**: dosing schedules, injection instructions,
   LNP formulation, manufacturing protocols, self-treatment workflows.

2. **Always include safety labels**: Every significant output must include
   "Research candidate only — not administerable" or an equivalent label.

3. **Always run safety preflight**: Before any write, export, or significant
   action, call `POST /safety/preflight` and respect its result.

4. **Always log actions**: All actions must be logged to the audit trail via
   the FoldAgent API.

5. **Always request user confirmation**: Before executing potentially dangerous
   actions (running pipelines, generating reports, exporting data), pause and
   ask the user for explicit confirmation.

6. **Never bypass the API**: Always go through the FoldAgent API for data
   operations. Never modify data directly.

7. **Respect mode restrictions**:
   - Demo mode: synthetic data only, no real patient data
   - Dog/veterinary mode: requires vet-oncologist oversight
   - Human/clinical mode: most restrictive, requires physician and IRB

8. **Surface uncertainty**: Always report uncertainty flags, missing data, and
   model limitations. Never present predictions as clinical facts.

9. **Professional review required**: Never suggest that an output is ready for
   clinical use. Always state that professional review is required.

10. **No self-modification into dangerous outputs**: Skills must not modify
    themselves or other skills to produce prohibited outputs, bypass safety
    gates, or remove safety labels.
