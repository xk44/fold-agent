# AlphaFold Backend Guide

> **FoldAgent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

FoldAgent supports 15 AlphaFold-family backends behind a common `AlphaFoldBackend` abstract interface (`backend/app/alphafold_backends.py`). All backends share the same `predict(sequence, options)` / `validate()` contract and return a `PredictionResult`. Structure predictions carry the safety label: **"Structure prediction only — not clinical validation"**.

Backends are registered in `_ALL_BACKENDS` at module level. The active default is controlled by `FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND` (default: `mock`).

---

## Backend Summary

| Name               | Mode  | GPU | External Upload   | Complexes | RNA/DNA/Ligands | Status                            |
| ------------------ | ----- | --- | ----------------- | --------- | --------------- | --------------------------------- |
| `mock`             | mock  | No  | No                | No        | No              | Always available                  |
| `colabfold`        | local | Yes | Optional (MMseqs) | Yes       | No              | Needs `colabfold_batch` on PATH   |
| `local_colabfold`  | local | Yes | No                | Yes       | No              | Needs LocalColabFold install      |
| `alphafold2_local` | local | Yes | No                | Yes       | No              | Needs AF2 install + databases     |
| `alphafold3_local` | local | Yes | No                | Yes       | Yes             | Needs AF3 weights + GPU           |
| `alphafold_server` | cloud | No  | **Yes**           | Yes       | Yes             | Needs account + auth cookie/key   |
| `alphafold_db`     | cloud | No  | No                | No        | No              | Network access only               |
| `boltz1`           | local | Yes | No                | Yes       | Yes             | Needs `boltz` binary on PATH      |
| `boltz2`           | local | Yes | No                | Yes       | Yes             | Needs `boltz` binary on PATH      |
| `esmfold`          | local | Yes | No                | No        | No              | Needs `esm` module or binary      |
| `openfold`         | local | Yes | No                | Yes       | No              | Needs OpenFold install            |
| `rfdiffusion`      | local | Yes | No                | Yes       | No              | Needs RFdiffusion install         |
| `proteinmpnn`      | local | Yes | No                | Yes       | No              | Needs ProteinMPNN install         |
| `chai1`            | local | Yes | No                | Yes       | Yes             | Needs `chai_lab` module or binary |
| `rfdiffusion2`     | local | Yes | No                | Yes       | No              | Needs RFdiffusion2 install        |

---

## Backends in Detail

### `mock`

**Class:** `MockBackend` (always available, no setup required)

Returns synthetic PDB data and random pLDDT/pAE scores without computation. Explicitly warns in output that no real prediction was performed.

- **Setup:** None.
- **GPU:** Not required.
- **Privacy:** No data leaves the machine.
- **When to use:** Development, CI, demos, and any workflow where real structure data is not needed.

### `colabfold`

**Binary:** `colabfold_batch`

Wraps ColabFold CLI. Accepts options for `num_recycle`, `num_seeds`, `use_templates`, `host_url`, `max_msa`. Override binary path via `FOLDAGENT_COLABFOLD_PATH`.

- **Setup:** `pip install colabfold` or install via conda. The `colabfold_batch` binary must be on `PATH`.
- **GPU:** Required for practical use.
- **Privacy:** By default queries remote MMseqs2 servers for MSA. Set `host_url` to a local MMseqs2 instance to keep data local.
- **When to use:** Fast local structure prediction with remote MSA fallback.

### `local_colabfold`

**Binary:** `colabfold_batch` (LocalColabFold variant)

Checks `~/localcolabfold/colabfold-conda/bin/colabfold_batch` or `~/.local/bin/colabfold_batch` before PATH. Override via `FOLDAGENT_LOCALCOLABFOLD_PATH`.

- **Setup:** Install LocalColabFold per https://github.com/YoshitakaMo/localcolabfold. Requires significant local storage for the MMseqs2 database.
- **GPU:** Required.
- **Privacy:** Fully local; no external network calls when local database is configured.
- **When to use:** Preferred over `colabfold` when data privacy requires no external MSA calls.

### `alphafold2_local`

**Binary:** `run_alphafold` or `run_alphafold.py`

Checks `~/alphafold/`, `/opt/alphafold/`, `/usr/local/alphafold/`. Override via `FOLDAGENT_ALPHAFOLD2_BINARY`. Accepts `data_dir` (`FOLDAGENT_ALPHAFOLD2_DATA_DIR`), `max_template_date`, `model_preset`, `db_preset`.

- **Setup:** Install AlphaFold2 per DeepMind's instructions. Requires genetic databases (UniRef90, BFD, etc.) — several hundred GB of storage.
- **GPU:** Required (A100 or equivalent recommended).
- **Privacy:** Fully local if databases are local.
- **When to use:** Standard protein structure prediction with full AF2 database access.

### `alphafold3_local`

**Binary:** `alphafold` or `run_alphafold.py`

Checks `~/alphafold3/`, `/opt/alphafold3/`, `/usr/local/alphafold3/`. Override via `FOLDAGENT_ALPHAFOLD3_BINARY`. Accepts `model_dir` (`FOLDAGENT_ALPHAFOLD3_MODEL_DIR`), `db_dir` (`FOLDAGENT_ALPHAFOLD3_DB_DIR`), `model_seeds`.

- **Setup:** Requires AlphaFold3 model weights (separate non-commercial license from Google DeepMind), compatible GPU, and the `alphafold3` Python package.
- **GPU:** Required. AF3 is significantly more memory-intensive than AF2.
- **Privacy:** Fully local.
- **When to use:** When you need RNA, DNA, or ligand complex prediction locally.
- **License note:** AlphaFold3 model weights have a non-commercial research license. Review terms before use.

### `alphafold_server`

**Cloud:** alphafoldserver.com

Submits job via HTTP, polls for completion, downloads CIF result. Requires `FOLDAGENT_AFSERVER_API_KEY` or `FOLDAGENT_AFSERVER_COOKIE`. Optional `FOLDAGENT_AFSERVER_BASE_URL`.

- **Setup:** Account at alphafoldserver.com; set auth env var.
- **GPU:** Not required locally (runs remotely).
- **Privacy:** **Sequence data is uploaded to Google DeepMind's servers.** Triggers the external upload gate in preflight — requires explicit user confirmation. Never use for sensitive human genomic data without institutional clearance.
- **When to use:** No local GPU and need AF3-quality predictions including RNA/DNA/ligands.

### `alphafold_db`

**Cloud:** alphafold.ebi.ac.uk

Fetches pre-computed structures from the AlphaFold EBI database by UniProt accession. The `sequence` parameter is treated as a UniProt accession (6–10 alphanumeric characters, e.g. `P00533`). Alternatively pass via `options["accession"]`.

- **Setup:** Internet access to `alphafold.ebi.ac.uk`. No local GPU needed.
- **Privacy:** Sends only a UniProt accession (not patient sequence data) to the EBI API. Low privacy risk.
- **When to use:** Protein has a pre-computed entry in the AF database. Not suitable for neoantigen-specific mutant sequences.

### `boltz1`

**Binary:** `boltz`

Boltz-1 is an MIT-licensed AF3-class model supporting protein, ligand, and nucleic acid structure prediction. Override binary via `FOLDAGENT_CHAI1_BINARY` (note: set `FOLDAGENT_BOLTZ1_BINARY` if separate). Currently stub implementation — returns synthetic output until full CLI integration is complete.

- **Setup:** Install `boltz` via pip or conda. The `boltz` binary must be on `PATH`.
- **GPU:** Required.
- **Privacy:** Fully local.

### `boltz2`

**Binary:** `boltz`

Boltz-2 extends Boltz-1 with binding affinity prediction. MIT license. Stub implementation — returns synthetic output including `binding_affinity_kcal`.

- **Setup:** Same as `boltz1`.
- **GPU:** Required.
- **Privacy:** Fully local.

### `esmfold`

**Module/Binary:** `esm` Python module or `esmfold` binary

Fast single-sequence structure prediction (no MSA, ~60x faster than AF2). Stub implementation returns synthetic output.

- **Setup:** `pip install fair-esm` or equivalent; or install `esmfold` binary.
- **GPU:** Required.
- **Privacy:** Fully local.
- **When to use:** Fast screening of many sequences without MSA.

### `openfold`

**Binary/Module:** `run_pretrained_openfold.py` or `openfold` Python module

Trainable AF2 reimplementation (Apache 2.0). Checks `~/openfold/`, `/opt/openfold/`, `/usr/local/openfold/`. Override via `FOLDAGENT_OPENFOLD_BINARY`. Accepts `data_dir` (`FOLDAGENT_OPENFOLD_DATA_DIR`), `jax_param_path` (`FOLDAGENT_OPENFOLD_PARAM_PATH`), `model_device`.

- **Setup:** Install from https://github.com/aqlaboratory/openfold.
- **GPU:** Required.
- **Privacy:** Fully local.

### `rfdiffusion`

**Binary/Module:** `rfdiffusion` binary or module

Generative protein backbone design. Checks `~/RFdiffusion/`, `/opt/RFdiffusion/`. Override via `FOLDAGENT_RFDIFFUSION_BINARY`. Stub implementation; `design_mode` option accepts `binder`, `scaffold`, `symmetric`, `enzyme`.

- **Setup:** Install from https://github.com/RosettaCommons/RFdiffusion.
- **GPU:** Required.
- **Privacy:** Fully local.

### `proteinmpnn`

**Binary/Module:** `protein_mpnn` binary or module

Inverse folding / sequence design from a given backbone. Checks `~/ProteinMPNN/`, `/opt/ProteinMPNN/`. Stub implementation; `num_sequences` option controls output count. Note: output is designed sequences, not a PDB file.

- **Setup:** Install from https://github.com/dauparas/ProteinMPNN.
- **GPU:** Required.
- **Privacy:** Fully local.

### `chai1`

**Binary/Module:** `chai` binary or `chai_lab` Python module

Chai-1 multi-modal structure prediction (Chai Discovery). Override binary via `FOLDAGENT_CHAI1_BINARY`. Accepts `num_trunk_recycles`, `num_diffusion_samples`, `seed`, `device`, `use_esm_embeddings`.

- **Setup:** `pip install chai_lab` (https://github.com/chaidiscovery/chai-lab).
- **GPU:** Required.
- **Privacy:** Proprietary license; data may be logged if using cloud endpoints. Local inference keeps data local.

### `rfdiffusion2`

**Binary/Module:** `rfdiffusion2` binary or module

De novo enzyme design from reaction description. Checks `~/RFdiffusion2/`, `/opt/RFdiffusion2/`. Stub implementation; accepts `reaction_description` option.

- **Setup:** Install RFdiffusion2 when available.
- **GPU:** Required.
- **Privacy:** Fully local.

---

## Checking Backend Availability

```bash
GET /alphafold/backends
```

Returns the registered status of all 15 backends including `gpu_required`, `cloud`, and `privacy_risk`. Calls `validate()` server-side to check whether the local binary or module is actually present.

---

## Dry-Run vs. Execute

```bash
# Preview backend validation without running
POST /alphafold/backends/{backend_name}/dry-run

# Run synchronously
POST /alphafold/backends/{backend_name}/run

# Dispatch async background job
POST /alphafold/backends/{backend_name}/run-async
```

Always run a dry-run first when testing a new backend configuration. The dry-run validates the backend and returns its `BackendValidation` without executing a prediction.

---

## Environment Variables

```bash
FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=mock             # safe default
FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND=local_colabfold  # local GPU setup
FOLDAGENT_ALPHAFOLD_ALLOWED_BACKENDS=mock,local_colabfold,alphafold3_local
FOLDAGENT_ALPHAFOLD_CACHE_OUTPUTS=true
FOLDAGENT_ALPHAFOLD_STORE_CONFIDENCE_METRICS=true

# Per-backend binary overrides
FOLDAGENT_COLABFOLD_PATH=/path/to/colabfold_batch
FOLDAGENT_LOCALCOLABFOLD_PATH=/path/to/colabfold_batch
FOLDAGENT_ALPHAFOLD2_BINARY=/path/to/run_alphafold.py
FOLDAGENT_ALPHAFOLD2_DATA_DIR=/data/alphafold2
FOLDAGENT_ALPHAFOLD3_BINARY=/path/to/alphafold
FOLDAGENT_ALPHAFOLD3_MODEL_DIR=/data/alphafold3/models
FOLDAGENT_ALPHAFOLD3_DB_DIR=/data/alphafold3/databases
FOLDAGENT_AFSERVER_API_KEY=<key>
FOLDAGENT_AFSERVER_COOKIE=<session-cookie>
FOLDAGENT_OPENFOLD_BINARY=/path/to/run_pretrained_openfold.py
FOLDAGENT_OPENFOLD_DATA_DIR=/data/openfold
FOLDAGENT_OPENFOLD_PARAM_PATH=/path/to/params
FOLDAGENT_CHAI1_BINARY=/path/to/chai
```

---

## Output Safety Labels

Every `PredictionResult` carries a warning in the `confidence` dict when using stub/mock backends. All downstream reports preserve the safety label:

```
"Structure prediction only — not clinical validation"
```

This label cannot be removed by agent skills or API callers.
