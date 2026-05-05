# Hermes Skill-Pack Enrichment Template

> **Status**: Gap audit + enrichment template  
> **Scope**: All 9 Hermes skills under `skills/hermes/*/SKILL.md`  
> **Canonical reference**: `skills/claude-code/run_full_neovax_case_review/SKILL.md` (110 lines, 4476 bytes)  
> **Date**: 2026-04-21

---

## 1. Gap Audit Summary

### 1.1 Quantitative Comparison

| Metric                        | Canonical (cc/run_full) | Hermes avg (9 skills) |
|-------------------------------|------------------------|-----------------------|
| Total lines                   | 110                    | 58 (range 57–67)      |
| File size (bytes)             | 4476                   | ~1850 (range 1788–2515) |
| Body sections                 | 9                      | 8                     |
| Procedural steps (`## Steps`) | 7 steps with details   | **MISSING entirely**   |
| API endpoint descriptions     | 7 with purposes        | URLs only, no purpose  |
| Output artifact detail        | 9 bullet items         | 1 sentence each        |
| Failure scenarios             | 4 specific scenarios   | 3 generic lines        |
| Logging specificity           | 4 specific requirements | 3 generic lines        |

### 1.2 Section-by-Section Gap Analysis

Sections are ordered by enrichment impact (highest first).

#### CRITICAL: `## Steps` — COMPLETELY MISSING

Every Hermes skill lacks a `## Steps` section. This is the core procedural content — the actual workflow the agent must follow. The canonical version has 7 numbered steps with sub-details (e.g., "Call `POST /safety/preflight` with the intended action. If blocked: inform user and STOP. If requires approval: request confirmation before proceeding."). Without this, the agent has no ordered execution plan.

#### HIGH: `## Expected Output Artifact` — One-liner vs. Detailed Spec

Hermes versions use a single sentence like "Structured case-data inventory summary with missing-data checklist." The canonical version lists 9 specific bullet items (case summary with species mode, data inventory and completeness checklist, pipeline reproducibility manifest, variant table, etc.). Without detail, the agent cannot validate or structure its own output.

#### HIGH: `## When to Use` — Single Sentence vs. Multi-line Context

Hermes versions use one sentence (e.g., "Create or normalize case, subject, and sample metadata; inspect data inventory completeness; do not perform treatment analysis.") The canonical version provides a 3-line paragraph with specific triggers and scope boundaries.

#### HIGH: `## Required NeoVax API Endpoints` — Bare URLs vs. Annotated

Hermes versions list endpoints as bare paths. The canonical version adds purpose annotations (e.g., "`GET /cases/{case_id}/samples` — Get data inventory"). Agents need endpoint purposes to select the right call.

#### MEDIUM: `## Failure Handling` — Generic Boilerplate vs. Skill-Specific

All 9 Hermes skills share identical 3-line failure handling:
```
- If the case or resource is missing: stop and report the missing dependency.
- If safety preflight blocks the action: stop and report the blocking policy.
- If backend validation fails: surface the structured validation payload.
```
The canonical version provides 4 skill-specific scenarios (API unreachable → check status, case doesn't exist → create first, safety blocks → specific policy, pipeline failed → check logs).

#### MEDIUM: `## Logging Requirements` — Generic vs. Skill-Specific

All 9 Hermes skills share identical 3-line logging. The canonical version specifies: log timestamps and case_id, log all safety preflight checks and results, log report generation with output hash, all logs must be sent to NeoVax audit trail.

#### LOW: `## No Medical Advice Warning` — Abbreviated vs. Full Paragraph

All Hermes skills use one sentence: "This skill coordinates research workflow only. It does NOT provide medical advice, veterinary advice, treatment recommendations, dosing instructions, or manufacturing guidance." The canonical version is a 3-sentence paragraph specifying who must review (licensed professional, veterinarian or physician) and that outputs must not be used for treatment decisions.

#### LOW: `tags` in frontmatter — Missing

The canonical version includes tags (`neovax-agent`, `oncology-research`, `case-review`, `safety-gated`). No Hermes skill has tags. This affects discoverability and filtering.

### 1.3 Boilerplate Sections (Acceptable as-is)

The following sections are nearly identical across all 9 Hermes skills AND all 9 claude-code skills, because they express universal safety constraints:

- `## When NOT to Use` — 3 bullet items, identical across all. Appropriate as-is since these are project-wide safety rules.
- `## Safety Boundaries` — Each skill has skill-specific items here (2-6 boundaries). This is already differentiated. No change needed.
- `## No Medical Advice Warning` — Consistent across all frameworks. The abbreviated form is acceptable, but enrichment is recommended for the keystone skill only.

---

## 2. Enrichment Template

Below is the REQUIRED enriched template structure for every Hermes `SKILL.md`. Sections marked **[MANDATORY]** must be present and skill-specific. Sections marked **[BOILERPLATE]** use the shared template text. Sections marked **[ENRICHED]** use the shared template as a base plus skill-specific additions.

### 2.1 Frontmatter

```yaml
---
name: <skill_name>
description: <one-line description, kept from current version>
version: 0.2.0                          # bump minor on enrichment
license: Apache-2.0
framework: Hermes                       # [BOILERPLATE] Hermes-specific
memory_seed_template: default           # [BOILERPLATE] Hermes-specific
audit_log_integration: required         # [BOILERPLATE] Hermes-specific
tags:                                   # [MANDATORY] NEW — add skill-specific tags
  - neovax-agent
  - <domain-tag>
  - <operation-tag>
  - safety-gated
---
```

**Tag guidance**: Always include `neovax-agent` and `safety-gated`. Add 1-3 domain/operation tags specific to the skill (e.g., `bioinformatics`, `alphafold`, `ethics-review`, `case-management`).

### 2.2 Title [MANDATORY]

```markdown
# <Skill Title>

(Exact title matching the skill's domain; currently present and fine)
```

### 2.3 When to Use [MANDATORY — ENRICH]

Replace the current single sentence with a 2-4 sentence paragraph that includes:
- What trigger or situation calls for this skill
- What the skill accomplishes at a high level
- What it explicitly does NOT do (scope boundary)

**Template pattern**:
```
Use this skill when <trigger/situation>. It <what it does> to <outcome>. 
This skill <scope boundary — what it does NOT cover>.
```

**Current (abbreviated) example** (`organize_case_data`):
> Create or normalize case, subject, and sample metadata; inspect data inventory completeness; do not perform treatment analysis.

**Enriched example** (`organize_case_data`):
> Use this skill when setting up a new case, registering samples, or checking data completeness before downstream analysis. It creates and normalizes case/subject/sample metadata and reports missing-data gaps so downstream pipeline and report skills can proceed safely. This skill does NOT run pipelines, generate reports, or perform any treatment analysis.

### 2.4 When NOT to Use [BOILERPLATE]

Keep as-is. These 3 lines are universal and correct:

```markdown
## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.
```

### 2.5 Safety Boundaries [MANDATORY — already skill-specific, refine if needed]

Each skill already has 2-6 skill-specific boundaries. Keep these. Optionally add a cross-reference:

```markdown
## Safety Boundaries

1. <skill-specific boundary 1>
2. <skill-specific boundary 2>
3. <... additional as needed>

See also: [shared safety policy](../shared/safety_policy.md)
```

### 2.6 Required NeoVax API Endpoints [MANDATORY — ENRICH]

Add a brief purpose annotation (em-dash + short description) after each endpoint.

**Current (abbreviated) example**:
```
- `GET /cases/{case_id}/samples`
- `POST /safety/preflight`
```

**Enriched pattern**:
```
- `GET /cases/{case_id}/samples` — Retrieve data inventory and completeness
- `POST /safety/preflight` — Safety gate before write actions
```

### 2.7 Required User Confirmation Points [MANDATORY — already present, refine]

Already skill-specific. Keep as-is. No change needed.

### 2.8 Expected Output Artifact [MANDATORY — ENRICH]

Replace the current single sentence with a structured bullet list of the artifact's components.

**Current (abbreviated) example** (`organize_case_data`):
> Structured case-data inventory summary with missing-data checklist.

**Enriched example** (`organize_case_data`):
> A structured case data inventory containing:
> - Case summary with species mode and supervision status
> - Sample registration table with metadata completeness flags
> - Missing-data checklist identifying gaps before pipeline execution
> - Safety labels on every section

### 2.9 Steps [MANDATORY — NEW SECTION]

**This is the most critical addition.** Every skill must include a numbered step-by-step execution plan. Each step should reference the API endpoint it calls and include decision branches.

**Template pattern**:
```markdown
## Steps

1. **Safety Preflight** (if this skill includes write/mutation actions): 
   Call `POST /safety/preflight` with the intended action.
   - If blocked: inform user and STOP.
   - If requires approval: inform user and request confirmation before proceeding.

2. **<Step Name>**: Call `<HTTP METHOD> <endpoint>` to <purpose>.
   - <Decision branch or validation>

3. **<Step Name>**: Call `<HTTP METHOD> <endpoint>` to <purpose>.
   - <Decision branch or validation>

4. **<Repeat until workflow complete>**

N. **Final Review**: Present results to the user with all safety labels and remind them that professional review is required.
```

### 2.10 Logging Requirements [MANDATORY — ENRICH]

Replace generic 3-line boilerplate with skill-specific logging requirements.

**Current (abbreviated — identical across all 9 skills)**:
```
- Log all API calls with case context where available.
- Preserve NeoVax safety/audit trail for any action taken.
- Stop and report the exact safety reason if blocked.
```

**Enriched pattern** (example for `run_full_neovax_case_review`):
```markdown
## Logging Requirements

- Log all API calls with timestamps and case_id.
- Log all safety preflight checks and their results.
- Log report generation with output content hash.
- All logs must be sent to the NeoVax audit trail via the API.
```

For simpler skills, add 1-2 skill-specific lines to the base 3-line template:

```markdown
## Logging Requirements

- Log all API calls with timestamps and case_id where available.
- Log safety preflight results and any blocking decisions.
- All actions must be recorded in the NeoVax audit trail via `POST /audit/{case_id}`.
```

### 2.11 Failure Handling [MANDATORY — ENRICH]

Replace generic 3-line boilerplate with skill-specific failure scenarios.

**Current (abbreviated — identical across all 9 skills)**:
```
- If the case or resource is missing: stop and report the missing dependency.
- If safety preflight blocks the action: stop and report the blocking policy.
- If backend validation fails: surface the structured validation payload.
```

**Enriched pattern** (example for `run_bioinformatics_pipeline`):
```markdown
## Failure Handling

- If safety preflight blocks the action: inform user of the specific policy violation and do NOT proceed.
- If the case does not exist: inform user and suggest verifying the case ID or creating a case first.
- If the pipeline has already failed: suggest checking pipeline history/logs and retry options.
- If the API is unreachable: inform user and suggest checking NeoVax-Agent service status.
- If backend validation fails: surface the structured validation payload to the user.
```

### 2.12 No Medical Advice Warning [BOILERPLATE — optional enrichment for keystone skill]

Keep the current one-liner as the default. For the keystone/orchestrator skill (`run_full_neovax_case_review`) only, expand to the canonical multi-sentence form:

```markdown
## No Medical Advice Warning

This skill coordinates research workflow. It does NOT provide medical advice,
treatment recommendations, dosing instructions, or manufacturing guidance.
Every output requires review by a licensed professional (veterinarian or
physician). No output from this skill should be used to make treatment decisions.
```

All other skills keep the current abbreviated form.

---

## 3. Per-Skill Enrichment Priority Matrix

Priority reflects impact of enrichment on agent correctness and safety.

| Skill | Steps | Output Artifact | When to Use | Endpoints | Failure | Logging | Priority |
|-------|-------|----------------|-------------|-----------|---------|---------|----------|
| run_full_neovax_case_review | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P0** |
| run_bioinformatics_pipeline | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P0** |
| get_alphafold_structures | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P1** |
| organize_case_data | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P1** |
| generate_candidate_review_report | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P1** |
| create_ethics_review_package | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P1** |
| coordinate_licensed_lab_outreach | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P2** |
| monitor_case_progress | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P2** |
| autoresearch_optimize_software_pipeline | MISSING | 1-line→bullets | 1-line→para | bare→annotated | generic→specific | generic→specific | **P2** |

---

## 4. Recommended Best Enrichment Slice

**Start with `run_full_neovax_case_review`** (P0, keystone orchestrator skill).

This is the right first slice because:
1. It is the most complex skill — the orchestrator that calls all other skills.
2. It is the only skill where the canonical reference (`skills/claude-code/run_full_neovax_case_review/SKILL.md`) already has full `## Steps`, detailed output, and specific failure handling, providing a proven template.
3. Enriching it first establishes the enriched pattern that all other skills can follow.
4. It has the most API endpoints (7), the most user confirmation points (4), and the most complex failure surface — making detailed steps the most safety-critical gap.

After completing `run_full_neovax_case_review`, the next most impactful candidate is `run_bioinformatics_pipeline` (also P0, high-risk pipeline execution).

---

## 5. Enriched Example: run_full_neovax_case_review

Below is the fully enriched version of the keystone skill, ready for review. This demonstrates all mandatory enrichment sections in practice.

```markdown
---
name: run_full_neovax_case_review
description: Runs the safe NeoVax-Agent case-review workflow and produces an expert-review packet. Use only for research coordination under professional oversight. Never provide treatment, dosing, manufacturing, or administration instructions.
version: 0.2.0
license: Apache-2.0
framework: Hermes
memory_seed_template: default
audit_log_integration: required
tags:
  - neovax-agent
  - oncology-research
  - case-review
  - safety-gated
---

# Run Full Neovax Case Review

## When to Use

Use this skill when you need to run the complete end-to-end case review workflow for a NeoVax-Agent research case. It coordinates preflight safety checks, data inventory, pipeline status review, candidate review, and export of an expert-review packet. This skill does NOT run pipeline executions, make structure predictions, or provide clinical decisions.

## When NOT to Use

- Do NOT provide treatment, dosing, administration, or manufacturing instructions.
- Do NOT bypass NeoVax safety preflight or expert approval requirements.
- Do NOT treat research outputs as clinical validation.

## Safety Boundaries

1. Every output must include the label: "Research candidate only — not administerable"
2. Every report must pass the safety preflight system before export.
3. No dosing, injection, formulation, or manufacturing instructions.
4. Professional review is required before any action is taken.
5. This skill will not proceed if the safety preflight check blocks the action.
6. In demo mode, synthetic data only — no real patient data.

See also: [shared safety policy](../shared/safety_policy.md)

## Required NeoVax API Endpoints

- `POST /safety/preflight` — Safety gate; must pass before proceeding
- `GET /cases/{case_id}` — Retrieve case details and mode
- `GET /cases/{case_id}/samples` — Get data inventory and completeness
- `GET /cases/{case_id}/pipeline/status` — Get current pipeline status
- `GET /cases/{case_id}/candidates` — Get candidate antigens with scores
- `GET /cases/{case_id}/variants` — Get variant annotations
- `POST /cases/{case_id}/reports/candidate-review` — Generate expert-review report

## Required User Confirmation Points

1. Before running the pipeline (if run mode)
2. Before generating the expert-review report
3. Before exporting any data
4. Before any external upload (AlphaFold Server, etc.)

## Expected Output Artifact

A structured expert-review packet containing:
- Case summary with species mode and supervision status
- Data inventory and completeness checklist
- Pipeline reproducibility manifest
- Variant table with annotations
- Candidate antigen table with scores and uncertainty flags
- Structure prediction summary (if available)
- Safety labels on every section
- Missing data checklist
- Professional review status tracking

## Steps

1. **Safety Preflight**: Call `POST /safety/preflight` with the intended action.
   - If blocked: inform user and STOP.
   - If requires approval: inform user and request confirmation before proceeding.

2. **Data Inventory**: Call `GET /cases/{case_id}/samples` to check what data is available. Flag any missing data (e.g., no matched normal sample).

3. **Pipeline Status**: Call `GET /cases/{case_id}/pipeline/status` to check whether the pipeline has been run and what the current status is. Inform the user of any blockers.

4. **Candidate Review**: Call `GET /cases/{case_id}/candidates` to get the candidate antigen list with scores, uncertainty flags, and review status.

5. **Safety Check Before Report**: Call `POST /safety/preflight` again with the report content to verify it passes safety checks.

6. **Generate Report**: Call `POST /cases/{case_id}/reports/candidate-review` to generate the expert-review packet. Requires user confirmation (see Confirmation Point 2).

7. **Final Review**: Present the report to the user with all safety labels and remind them that professional review is required.

## Logging Requirements

- Log all API calls with timestamps and case_id.
- Log all safety preflight checks and their results.
- Log report generation with output content hash.
- All logs must be sent to the NeoVax audit trail via `POST /audit/{case_id}`.

## Failure Handling

- If the API is unreachable: inform user and suggest checking NeoVax-Agent status.
- If the case does not exist: inform user and suggest verifying the case ID or creating a case first.
- If safety preflight blocks an action: inform user of the specific policy violation and do NOT proceed.
- If the pipeline has failed: suggest checking pipeline history/logs and retry options.
- If backend validation fails: surface the structured validation payload to the user.

## No Medical Advice Warning

This skill coordinates research workflow. It does NOT provide medical advice, treatment recommendations, dosing instructions, or manufacturing guidance. Every output requires review by a licensed professional (veterinarian or physician). No output from this skill should be used to make treatment decisions.
```

---

## 6. Enrichment Checklist (for applying to each skill)

For each Hermes `SKILL.md`, verify:

- [ ] `tags` added to frontmatter (include `neovax-agent`, `safety-gated`, plus 1-3 domain tags)
- [ ] `version` bumped to `0.2.0`
- [ ] `## When to Use` expanded to 2-4 sentences with trigger, scope, and boundary
- [ ] `## When NOT to Use` — confirmed unchanged (boilerplate)
- [ ] `## Safety Boundaries` — skill-specific items confirmed; added `See also` link
- [ ] `## Required NeoVax API Endpoints` — every endpoint annotated with purpose
- [ ] `## Required User Confirmation Points` — confirmed unchanged (already skill-specific)
- [ ] `## Expected Output Artifact` — expanded to structured bullet list
- [ ] `## Steps` — NEW section added with numbered procedural workflow
- [ ] `## Logging Requirements` — enriched with skill-specific details (timestamps, case_id, audit endpoint)
- [ ] `## Failure Handling` — enriched with skill-specific failure scenarios and recovery hints
- [ ] `## No Medical Advice Warning` — expanded for keystone skill; kept abbreviated for others