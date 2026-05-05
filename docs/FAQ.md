# Frequently Asked Questions

> **NeoVax-Agent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Purpose and Scope

### Is this medical advice?

No. NeoVax-Agent is a research coordination platform. It does not diagnose, treat, prescribe, or advise on any medical condition. All outputs are research coordination materials only and require review by a licensed physician, oncologist, or veterinary oncologist before any real-world action.

### Can this make a vaccine?

No. NeoVax-Agent coordinates research workflows and produces candidate rankings and analysis summaries. It does not produce administerable vaccines, formulation instructions, dosing schedules, or manufacturing protocols. Any output labeled "research candidate" means exactly that — a candidate for further research, not a finished product.

### Can I use this clinically?

No. NeoVax-Agent outputs are not approved, cleared, or validated for clinical use. They have not undergone regulatory review. Do not use any output as the basis for administering, prescribing, or recommending a treatment to a patient or animal. Clinical use requires licensed professional oversight, institutional approval, and (in most jurisdictions) regulatory clearance that NeoVax-Agent cannot provide.

### What is it actually for?

NeoVax-Agent helps researchers:

- Organize genomic sequencing data and sample metadata for a case
- Run or simulate bioinformatics pipelines (alignment, variant calling, annotation, neoantigen prioritization)
- Retrieve AlphaFold structure predictions for protein candidates
- Generate structured reports suitable for expert review
- Coordinate lab outreach, cost tracking, and professional collaboration
- Produce ethics package materials for IRB or veterinary ethics review
- Maintain an auditable, reproducible research record

---

## Species Support

### What species does this support?

NeoVax-Agent supports three operating modes:

- **Demo** — Synthetic data only. No real patient or animal data. Used for development, testing, and exploration.
- **Dog (veterinary)** — Research coordination for canine cancer cases. Requires licensed veterinary oncologist oversight.
- **Human** — Research coordination for human cancer cases. Most restrictive mode. Requires physician and IRB oversight. Sequence-level exports are blocked without expert mode and IRB attestation.

Other species are not currently supported. Dog mode exists because canine comparative oncology is an established research domain with institutional infrastructure.

### Can I use human mode for my patient?

NeoVax-Agent is not a clinical tool and must not be used as one. If you are a licensed researcher or physician using it as part of an IRB-approved study, you may use human mode for research coordination — but the platform itself does not constitute medical care and its outputs are not treatment plans.

---

## Data and Privacy

### Is my data safe?

NeoVax-Agent is local-first by design. By default:

- All data stays on your machine
- No sequence data is sent to external services unless you explicitly enable a cloud AlphaFold backend
- The database is a local SQLite file
- Audit logs and artifacts are written to local directories

Cloud uploads are disabled by default (`NEOVAX_CLOUD_UPLOAD_ENABLED=false`). The only backends that send data externally are `alphafold_server` (sends sequences to Google DeepMind) and `alphafold_db` (sends UniProt accessions to EBI). Both require explicit opt-in and user confirmation.

See `docs/PRIVACY_GUIDE.md` for full details.

### Does NeoVax-Agent store patient identifiers?

NeoVax-Agent stores what you give it. The default redaction level for all cases is `full`. The system does not require or validate real patient identifiers — use pseudonymized or de-identified identifiers for all cases unless your institution's data governance policy explicitly permits otherwise.

### Can I delete a case and its data?

Yes. Use `DELETE /cases/{case_id}` to remove database records and `remove_case_data_dir(case_id)` (or the equivalent API call) to remove the case's file artifacts. See `docs/PRIVACY_GUIDE.md` for the full deletion workflow.

---

## AlphaFold and Structure Prediction

### Do I need a GPU?

Only for local AlphaFold backends (ColabFold, LocalColabFold, AF2, AF3). The default `mock` backend requires no GPU and no installation. The `alphafold_server` cloud backend requires no local GPU but sends data externally.

For development and testing, the mock backend is sufficient. For real structure predictions in a privacy-sensitive context, LocalColabFold or AF2/AF3 local require a GPU.

### Are structure predictions clinically valid?

No. All structure predictions — from any backend — carry the label: **"Structure prediction only — not clinical validation."** AlphaFold produces theoretical structural models. They are useful for research prioritization but have not been validated as diagnostic or therapeutic tools.

---

## Safety System

### Can the safety checks be disabled?

`NEOVAX_SAFETY_PREFLIGHT_ENABLED` can be set to `false`, but this should never be done in production or in any context where real patient or animal data is present. The safety system exists to prevent the platform from producing prohibited outputs (dosing schedules, injection instructions, manufacturing protocols). Disabling it removes that protection.

The unsafe text scanner has a separate flag (`NEOVAX_UNSAFE_TEXT_SCANNER_ENABLED`) but the same reasoning applies — leave it enabled.

### What happens when preflight blocks an action?

The API returns a structured error with the exact block reason. The block is logged to the audit trail. The action does not proceed. Agent skills are required to surface the exact block reason to the user rather than paraphrasing it.

---

## Agent Skills

### What agent frameworks are supported?

NeoVax-Agent ships skill packs for three agent frameworks:

- **Claude Code** — skills in `skills/claude-code/`, invoked as slash commands or CLAUDE.md task prompts. See [docs/CLAUDE_CODE_INSTALL_GUIDE.md](CLAUDE_CODE_INSTALL_GUIDE.md).
- **OpenClaw** — structured YAML task definitions in `skills/openclaw/`, with WebSocket event streaming. See [docs/OPENCLAW_INSTALL_GUIDE.md](OPENCLAW_INSTALL_GUIDE.md).
- **Hermes** — memory-seeded, audit-integrated skills in `skills/hermes/`. See [docs/HERMES_INSTALL_GUIDE.md](HERMES_INSTALL_GUIDE.md).

All three frameworks share the same 9 workflow skills, the same shared API client, and the same safety policy. Framework differences are in invocation syntax only.

### What are the agent skills?

Skills are structured workflow definitions for AI agents (Claude Code, OpenClaw, Hermes). They guide the agent through NeoVax API operations with built-in safety gates and confirmation points. See `docs/AGENT_SKILLS_GUIDE.md`.

### Can an agent bypass the safety system?

No. Safety is enforced server-side by the FastAPI application. Agent instructions cannot override the preflight system — a blocked action returns an error regardless of what the agent's skill instructions say. Skills are additionally prohibited by their own self-improvement guardrails from modifying themselves to widen medical-output scope.

---

## Pipeline and Bioinformatics

### Do I need BWA, GATK, VEP, and pVACtools installed?

Only for real pipeline mode (`NEOVAX_PIPELINE_MODE=real`). The default mock mode simulates all pipeline steps without any external tools. Use mock mode for development and testing. Install real tools only when you have actual sequencing data and a validated research setup.

### What reference genome is used?

The default configuration references `hg38` (GRCh38) for human mode. For dog mode, you would need a canine reference (CanFam3.1 or CanFam4). Reference paths are configured via environment variables — see `docs/BIOINFORMATICS_ADAPTER_GUIDE.md`.

---

## Licensing and Use

### Can I use this for commercial research?

NeoVax-Agent itself is Apache-2.0 licensed. However, the external tools it wraps (AlphaFold3 weights, NetMHCpan, pVACtools dependencies) have their own licenses. Review each tool's license before commercial or clinical use. The AlphaFold3 model weights have a non-commercial research license from Google DeepMind.

### Who should oversee use of this platform?

Any use beyond synthetic demo data should involve:

- A licensed physician or veterinary oncologist (depending on species mode)
- An institutional review board (IRB) or veterinary ethics committee
- A data governance officer if institutional patient/animal data is involved

NeoVax-Agent is a tool to assist qualified researchers. It is not a substitute for professional expertise or institutional oversight.

---

## Additional Questions

### Can I use this for my pet's treatment?

No. NeoVax-Agent is for research and education only. Always consult a qualified veterinarian or veterinary oncologist. This software does not provide medical or veterinary advice.

### Is the AlphaFold Server safe to use?

The AlphaFold Server sends sequence data to Google DeepMind's servers. Use local backends (ColabFold, AlphaFold2 Local) if data privacy is a concern. Review the cloud upload gate at `/privacy/cloud-upload-check`.

### How do I add a new pipeline step?

Subclass `PipelineStep` from `backend/app/pipeline/framework.py`, implement the `name` property and `execute()` method, then add it to `FRAMEWORK_STEPS`. See the Developer Guide for details.

### Can autoresearch optimize treatment outcomes?

No. Treatment outcomes, survival rates, dosage parameters, and safety gate pass rates are prohibited metrics. Autoresearch can only optimize software pipeline performance metrics. See `docs/AUTORESEARCH_SAFE_USE_GUIDE.md`.
