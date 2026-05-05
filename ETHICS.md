# NeoVax-Agent Ethics Policy

## Purpose

NeoVax-Agent is a research coordination platform, not a medical device or
treatment recommendation system. This document defines the ethical boundaries
that every feature, module, agent skill, and output must respect.

## Core Principles

1. **Research Only** -- All outputs are research candidate information requiring
   professional review. Nothing produced by this system is administerable.

2. **Professional Supervision Required** -- Every case must have a licensed
   professional (veterinarian, oncologist, or IRB-approved researcher) as
   case owner. No self-treatment workflow exists.

3. **No DIY Manufacturing** -- The system must never generate vaccine
   manufacturing protocols, injection instructions, dosing schedules,
   LNP formulation instructions, or sterility/QC release instructions.

4. **Transparency and Honesty** -- All outputs include model limitations,
   uncertainty flags, source citations, and version information. AI
   hallucination risk is surfaced explicitly.

5. **Local-First Privacy** -- Data stays local by default. Cloud uploads
   require explicit, informed consent. No training on user data.

6. **Mode-Specific Restrictions**

   - **Demo mode**: Synthetic data only. No treatment claims.
   - **Dog/Veterinary mode**: Vet-oncologist oversight required. DLA/MHC
     limitations surfaced. No self-administration.
   - **Human/Clinical mode**: Most restrictive. Physician/oncologist
     ownership. IRB/ethics path required before any downstream discussion.
     "Not for treatment use" on every output.

## Prohibited Outputs

The system MUST NOT generate:

- DIY vaccine manufacturing protocols
- Injection instructions
- Dosing schedules
- LNP formulation instructions
- Tumor-lysate preparation instructions
- Adjuvant mixing instructions
- Sterility/QC release instructions for real administration
- "Ready to inject" sequence packages
- Medical recommendations to proceed with treatment
- Claims that AI cured or can cure cancer
- Claims that any output is clinically valid without professional validation

## Expert-Only Exports

Any module that touches mRNA sequence design or construct-level information
must be locked behind:

- Expert mode activation
- Local-only processing (no cloud export)
- Case owner verification
- Required warning banner on every page
- Export label: "Research candidate only -- not administerable"
- Audit log entry for every access
- Approval checkpoint before export
- Automated scan for unsafe operational text

## Source Material Policy

Paul Conyngham's public GitHub repository contains a related autologous
tumor-lysate protocol. NeoVax-Agent links to it as source/context only and
does NOT copy operational lab protocol steps, manufacturing details, or
administration instructions.

## Violation Handling

If any module, skill, or agent action produces output that violates these
ethics:

1. The safety preflight system must block the action.
2. The attempt must be recorded in the audit log.
3. The user must be notified of the policy violation.
4. The module must be corrected before it can be used again.

## Attribution

This project is inspired by Paul Conyngham's public story about his dog Rosie.
It does not represent his endorsement, clinical validation, or medical
recommendation.