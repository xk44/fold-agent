# NeoVax Day-1 Minimum Governance/Safety Documentation Set

Extracted from "NeoVax-Agent — Full Project Plan" (Section 5, Section 13 Phase 0,
Section 17 build order items 1-3, plus cross-cutting wording constraints).

---

## FILE 1: README.md

### Must-Have Sections
1. **Project title and one-sentence summary** — Use exact phrasing:
   > NeoVax-Agent is a local-first, safety-gated research coordination platform
   > that turns the Paul Conyngham / Rosie story into an auditable,
   > expert-supervised software workflow with AlphaFold support, bioinformatics
   > adapters, ethics documentation, and plug-and-play Claude Code / OpenClaw /
   > Hermes skills — without providing DIY vaccine manufacturing or treatment
   > instructions.

2. **"Not medical/veterinary/treatment advice" banner** — Prominent, at top.
   Critical wording (from Phase 0 todo):
   > NOT MEDICAL ADVICE · NOT VETERINARY ADVICE · NOT TREATMENT INSTRUCTIONS

3. **What NeoVax-Agent IS** (Section 3):
   - Privacy-first research case manager
   - Computational biology workflow orchestrator
   - For personalized cancer-vaccine exploration under licensed professional
     supervision

4. **What NeoVax-Agent IS NOT** (Section 3):
   - NOT a cure generator
   - NOT a direct-to-consumer treatment app
   - NOT a vaccine manufacturing guide
   - NOT a replacement for veterinarians, oncologists, immunologists,
     regulatory review, IRB review, or licensed RNA manufacturing facilities

5. **Three system modes** (Section 4): dog/vet-research, human clinical-research,
   demo/education — with brief restrictions per mode.

6. **License choice** — Apache-2.0 or AGPL-3.0 (must be stated; pick one).

7. **Link to all other governance docs** — ETHICS.md, SAFETY_POLICY.md,
   DATA_PRIVACY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, docs/source_registry.md

8. **Quickstart** — How to run in demo mode with synthetic data.

### Critical Wording Constraints
- Banner MUST use the exact triple-phrase: "not medical advice / not veterinary
  advice / not treatment instructions" (Phase 0 line 833).
- Every generated output MUST carry the label:
  > Research candidate only — not administerable.
  (Section 5, Phase 8 line 979)
- NEVER frame as "vaccine design" or "clinical-use tool."

---

## FILE 2: ETHICS.md

### Must-Have Sections
1. **Project ethical stance** — Software produces research candidate information
   requiring professional review; not medical advice or an administerable
   treatment plan (Section 1, line 30).

2. **Veterinary ethics** (Section 4.1):
   - Explicit vet-oncologist oversight required
   - Owner consent package required
   - No self-administration workflow
   - No dosing instructions
   - No compounding or manufacturing instructions

3. **Human clinical-research ethics** (Section 4.2):
   - Human mode more restrictive than dog mode
   - Physician/oncologist ownership of case required
   - IRB/ethics path before any downstream manufacturing discussion
   - "Not for treatment use" warning on every generated output

4. **Professional oversight rule** — Software cannot bypass ethics approval
   (Phase 9 line 998).

5. **Jurisdiction warning** — User must consult local regulations (Phase 9
   line 997).

6. **Source attribution ethics** — Paul's GitHub repo is related direct
   material, NOT verified as the exact Rosie mRNA pipeline; must NOT copy
   operational manufacturing, formulation, dosing, or administration details
   from it (Section 2.1 line 51).

7. **AI hallucination acknowledgment** — Source registry, citations,
   model/version appendix, uncertainty flags, and expert-review workflow exist
   to counter AI-generated false confidence (Section 16).

8. **Autoresearch scope restriction** — Only software-metric optimization;
   prohibited from treatment-efficacy, dose-optimization, or manufacturing-
   optimization metrics (Phase 16 lines 1121-1125).

### Critical Wording Constraints
- Human mode: "not for treatment use" on EVERY generated output (line 205).
- Ethics/IRB/veterinary review is a first-class workflow, NOT a stretch goal
  (Section 12 Problem 3, line 770).

---

## FILE 3: SAFETY_POLICY.md

### Must-Have Sections
1. **Allowed outputs** (Section 5 lines 224-240):
   - Case organization summaries
   - Sequencing inventory
   - Variant tables
   - Candidate-antigen review reports
   - AlphaFold structure job manifests
   - Protein structure visualization links
   - Confidence and uncertainty reports
   - Missing-data checklists
   - Ethics/IRB/veterinary-review drafts
   - Lab outreach email drafts
   - Cost/timeline estimates
   - Audit logs
   - Agent task plans
   - Expert-review packets

2. **Prohibited outputs** (Section 5 lines 242-253) — verbatim:
   - DIY vaccine manufacturing protocols
   - Injection instructions
   - Dosing schedules
   - LNP formulation instructions
   - Tumor-lysate preparation instructions
   - Adjuvant mixing instructions
   - Sterility/QC release instructions for real administration
   - "Ready to inject" sequence packages
   - Medical recommendations to proceed with treatment
   - Claims that AI cured cancer
   - Claims that an output is clinically valid without professional validation

3. **mRNA/sequence-design safety gate** (Section 5 lines 255-262):
   - Expert mode required
   - Local-only processing
   - Case owner verification
   - Required warning banner
   - Export label: "Research candidate only — not administerable."
   - Audit log entry
   - Approval checkpoint before export

4. **Mode-specific restrictions**:
   - **Dog/vet mode** (Section 4.1): vet-oncologist oversight, no self-
     administration, no dosing, no manufacturing instructions.
   - **Human mode** (Section 4.2): more restrictive than dog mode, physician
     ownership, IRB required, "not for treatment use" on every output, no
     direct patient self-use workflow, no generated administerable construct.
   - **Demo mode** (Section 4.3): synthetic variants only, no real patient
     data, no treatment claims, safe demo report only.

5. **Unsafe-output scanner** — Automated scan to block unsafe operational text
  in generated reports (Phase 8 line 982, Phase 17 line 1150).

6. **Agent safety guardrails** — Dry-run defaults, approval gates, unsafe-
   output scanner, audit logs, limited permissions (Section 16 line 1309);
   SKILL.md files must include: safety boundaries, no-medical-advice warning,
   required user confirmation points (Section 11 lines 715-723).

7. **Autoresearch prohibited actions** (Phase 16):
   - No autonomous wet-lab optimization
   - No autonomous treatment design
   - No autonomous sequence optimization for administration

8. **AlphaFold use restrictions**:
   - Structure prediction only — NOT clinical validation (Phase 6 line 950)
   - AlphaFold Server: must warn about privacy and external data upload
     (Section 10 lines 607-608)
   - Must not silently upload private genomic/protein data (line 608)

### Critical Wording Constraints
- Exactly these 11 prohibited output types must be listed verbatim.
- Export watermark MUST read: "Research candidate only — not administerable."
- "Ready to inject" is a banned phrase in any output.
- "AI cured cancer" as a claim is explicitly prohibited.
- AlphaFold outputs MUST be labeled "structure prediction only — not clinical
  validation."

---

## FILE 4: DATA_PRIVACY.md

### Must-Have Sections
1. **Local-first default** — No cloud upload unless explicitly enabled
   (Section 7 lines 383-384).

2. **Encryption at rest** option (line 384).

3. **Per-case audit logs** (line 386).

4. **Redaction pipeline for reports** (line 387).

5. **Consent and data-ownership screens** (line 388).

6. **Role-based permissions** (line 389).

7. **External-upload confirmation gate** — Cloud upload requires explicit user
   consent; must warn before AlphaFold Server or other cloud use (Phase 3
   lines 884-890).

8. **Cloud-disabled default config** (line 886).

9. **File-retention policy** (line 887).

10. **Data deletion workflow** (line 888).

11. **Audit export** (line 889).

12. **No-training-on-user-data policy** (line 890).

13. **"Do not send sensitive genomic data by email" warning** (Phase 10
    line 1014).

14. **Paul's GitHub repo — do not copy operational protocol steps** (Section
    2.1 line 51, Section 16 line 1321).

### Critical Wording Constraints
- Default is local-first with cloud DISABLED.
- User MUST explicitly confirm before any external data upload.
- No user data may be used for AI training.

---

## FILE 5: CONTRIBUTING.md

### Must-Have Sections
1. **How to contribute** — PR process, dev environment setup (from Phase 1).
2. **Safety contribution gate** — Any contribution that adds or touches
   safety-relevant code (pipeline outputs, report generation, AlphaFold
   adapters, agent skills) must pass unsafe-output blocking tests (Phase 18
   line 1170).
3. **Prohibited contribution types** — Do not submit PRs that add: dosing
   calculators, manufacturing instructions, injection guides, LNP formulation
   recipes, "ready to inject" features, or any self-treatment workflow.
4. **Code of Conduct link** — Points to CODE_OF_CONDUCT.md.
5. **License notice** — Apache-2.0 or AGPL-3.0; do not copy incompatible
   protocol text from Paul's GPL repo (Section 6 line 273).

### Critical Wording Constraints
- Contributions MUST NOT add any of the 11 prohibited output types.
- GPL-incompatible code from Paul's repo must not be mixed unless license
  implications are accepted.

---

## FILE 6: CODE_OF_CONDUCT.md

### Must-Have Sections
1. **Standard open-source CoC** — Adopt Contributor Covenant or equivalent
   (no specific text prescribed by plan).
2. **Medical-safety clause** — Add a project-specific clause:
   contributors and community members must not use the project's issue
   tracker, discussions, or channels to share DIY treatment, dosing, or
   manufacturing instructions.
3. **Enforcement contact** — Must be defined.

### Critical Wording Constraints
- Must include a medical-safety clause prohibiting treatment/manufacturing
  instruction sharing in project spaces (derived from Section 5 and Phase 0
  prohibitions).

---

## FILE 7: docs/source_registry.md

### Must-Have Sections
1. **Paul Conyngham / Rosie source links** (Section 2.1):
   - Paul X profile
   - Paul X thread
   - Paul GitHub profile
   - Paul GitHub repo

2. **Critical warning** (MUST be prominent) — must use wording:
   > Paul's GitHub repo is related direct material, NOT verified as the exact
   > Rosie mRNA pipeline. NeoVax-Agent must NOT copy operational manufacturing,
   > formulation, dosing, or administration details from it.

3. **Reporting and context links** (Section 2.2):
   - UNSW article
   - The Scientist article
   - CNA/AFP article
   - Fortune article
   - Sam Altman X post

4. **AlphaFold / protein structure links** (Section 2.3):
   - AlphaFold 2 GitHub
   - AlphaFold 3 GitHub
   - AlphaFold 3 weight terms of use
   - AlphaFold Server
   - AlphaFold Server guides
   - AlphaFold Protein Structure Database
   - ColabFold GitHub
   - LocalColabFold GitHub

5. **Bioinformatics tool links** (Section 2.4):
   - BWA / BWA-MEM2
   - GATK Mutect2
   - Ensembl VEP
   - pVACtools
   - NetMHCpan 4.1
   - NetMHCIIpan 4.1

6. **Agent/skills links** (Section 2.5):
   - Claude Code skills docs
   - OpenClaw
   - Hermes Agent

7. **Autoresearch link with restriction** (Section 2.6):
   - Karpathy autoresearch — software/research-pipeline optimization ONLY;
     NOT for autonomous wet-lab or treatment design.

8. **Status notes per link** — Whether each link is active, archived, or
   needs verification (per Phase 0 todo lines 829-832).

### Critical Wording Constraints
- The Paul GitHub repo warning MUST use that exact framing (from line 51 and
  line 832).
- Autoresearch MUST be annotated "software/research-pipeline optimization
  ONLY, not autonomous wet-lab or treatment design" (line 159).

---

## SUMMARY TABLE

| # | File                           | Phase-0 Priority | Must Exist Day-1? |
|---|--------------------------------|------------------|--------------------|
| 1 | README.md                      | Yes              | YES                |
| 2 | ETHICS.md                      | Yes              | YES                |
| 3 | SAFETY_POLICY.md               | Yes              | YES                |
| 4 | DATA_PRIVACY.md                | Yes              | YES                |
| 5 | CONTRIBUTING.md                | Yes              | YES                |
| 6 | CODE_OF_CONDUCT.md             | Yes              | YES                |
| 7 | docs/source_registry.md        | Yes              | YES                |

All 7 files are Phase 0 line items in the plan. Section 17 build order places
"Safety policy" and "Source registry" as items 2 and 3 (after repo scaffold),
confirming they are day-1 blockers for a safe public launch.

---

## CROSS-CUTTING CRITICAL WORDING CONSTRAINTS (apply to ALL files)

1. **Never** use these phrases in any doc or output:
   - "vaccine design" (use "candidate-antigen research")
   - "treatment plan" (use "research candidate information")
   - "clinical validation" (say "theoretical modeling" or "computational prediction")
   - "ready to inject" / "administerable"
   - "AI cured cancer"

2. **Always** include these labels where outputs/reports are discussed:
   - "Research candidate only — not administerable."
   - "Not for treatment use" (mandatory in human mode outputs)
   - "Not medical advice · Not veterinary advice · Not treatment instructions"

3. **Paul Conyngham's repo** must always be described as "related direct
   material" — never as "the Rosie pipeline" or "verified protocol."

4. **AlphaFold outputs** must be labeled "structure prediction only — not
   clinical validation."

5. **Agent skills** must each include: "safety boundaries", "no-medical-advice
   warning", "required user confirmation points", "logging requirements",
   "failure handling" (Section 11 lines 715-723).

6. **License**: Pick one — Apache-2.0 or AGPL-3.0. Do NOT mix GPL code from
   Paul's repo without accepting license implications (Section 6 line 273).