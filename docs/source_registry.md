# Source Registry

All primary sources, references, and tool links for the NeoVax-Agent project.

## Status Tags

- `verified` -- Direct source, confirmed accurate
- `related` -- Related material, not the exact pipeline
- `third-party` -- Independent tool or resource

---

## 1. Paul Conyngham / Rosie Direct Sources

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| Paul X profile | https://x.com/paul_conyngham | verified | Primary source |
| Paul X thread | https://x.com/paul_conyngham/status/2036940410363535823 | verified | Original thread |
| Paul GitHub profile | https://github.com/PaulConyngham | verified | |
| Paul GitHub repo | https://github.com/PaulConyngham/AutologousCancerVaccineWithQuantumParticles | **related** | **This is an autologous tumor-lysate protocol, NOT the exact Rosie mRNA neoantigen pipeline. Links as source/context only. Do NOT copy operational manufacturing, formulation, dosing, or administration details into NeoVax-Agent.** |

---

## 2. Reporting and Context

| Resource | URL | Status |
|----------|-----|--------|
| UNSW article | https://news.unsw.edu.au/en/meet-the-man-who-designed-a-cancer-vaccine-for-his-dog | verified |
| The Scientist article | https://www.the-scientist.com/chatgpt-and-alphafold-help-design-personalized-vaccine-for-dog-with-cancer-74227 | verified |
| CNA/AFP article | https://www.channelnewsasia.com/world/chatgpt-ai-dog-cancer-treatment-6025186 | verified |
| Fortune article | https://fortune.com/2026/03/15/australian-tech-entrepreneur-ai-cancer-vaccine-dog-rosie-unsw-mrna/ | verified |
| Sam Altman X post | https://x.com/sama/status/2037396826060673188 | verified |

---

## 3. AlphaFold / Protein Structure

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| AlphaFold 2 GitHub | https://github.com/google-deepmind/alphafold | third-party | Requires large sequence DBs |
| AlphaFold 3 GitHub | https://github.com/google-deepmind/alphafold3 | third-party | Check WEIGHTS_TERMS_OF_USE.md |
| AlphaFold 3 model terms | https://github.com/google-deepmind/alphafold3/blob/main/WEIGHTS_TERMS_OF_USE.md | third-party | License restrictions apply |
| AlphaFold Server | https://alphafoldserver.com/ | third-party | **Privacy concern: uploads protein data to cloud** |
| AlphaFold Server guides | https://alphafoldserver.com/guides | third-party | |
| AlphaFold DB | https://alphafold.ebi.ac.uk/ | third-party | Precomputed structures |
| ColabFold | https://github.com/sokrypton/ColabFold | third-party | Default MVP backend |
| LocalColabFold | https://github.com/YoshitakaMo/localcolabfold | third-party | Local GPU pathway |

---

## 4. Bioinformatics Tools

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| BWA | https://github.com/lh3/bwa | third-party | Short-read alignment |
| BWA-MEM2 | https://github.com/bwa-mem2/bwa-mem2 | third-party | Faster BWA |
| GATK Mutect2 | https://gatk.broadinstitute.org/hc/en-us/articles/360037593851-Mutect2 | third-party | Somatic variant calling |
| Ensembl VEP | https://www.ensembl.org/vep | third-party | Variant annotation |
| VEP GitHub | https://github.com/Ensembl/ensembl-vep | third-party | |
| pVACtools | https://github.com/griffithlab/pVACtools | third-party | Neoantigen prediction |
| pVACtools docs | https://pvactools.readthedocs.io/ | third-party | |
| NetMHCpan 4.1 | https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/ | third-party | MHC-I binding prediction |
| NetMHCIIpan 4.1 | https://services.healthtech.dtu.dk/services/NetMHCIIpan-4.1/ | third-party | MHC-II binding prediction |

---

## 5. Agent / Skills Frameworks

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| Claude Code skills docs | https://code.claude.com/docs/en/skills | third-party | |
| Claude custom skills | https://support.claude.com/en/articles/12512198 | third-party | |
| OpenClaw | https://github.com/openclaw/openclaw | third-party | |
| Awesome OpenClaw skills | https://github.com/VoltAgent/awesome-openclaw-skills | third-party | |
| OpenClaw SKILL.md example | https://github.com/openclaw/openclaw/blob/main/skills/github/SKILL.md | third-party | |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | third-party | |
| Hermes skills docs | https://hermes-agent.nousresearch.com/docs/user-guide/features/skills | third-party | |
| Hermes SKILL.md example | https://github.com/NousResearch/hermes-agent/blob/main/skills/software-development/requesting-code-review/SKILL.md | third-party | |
| Skill MD standard | https://www.mintlify.com/blog/skill-md | third-party | |

---

## 6. Autonomous Research (Software Only)

| Resource | URL | Status | Notes |
|----------|-----|--------|-------|
| Karpathy autoresearch | https://github.com/karpathy/autoresearch | third-party | **Software/pipeline optimization ONLY. NOT for autonomous wet-lab or treatment design.** |

---

## Disclaimer

Source links are provided for reference and context. Inclusion does not imply
endorsement, clinical validation, or that the tools produce administerable
outputs. All outputs from NeoVax-Agent require professional review.