# AlphaFold Backend Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

NeoVax-Agent supports seven AlphaFold backends behind a common `AlphaFoldBackend` abstract interface (`backend/app/alphafold/base.py`). All backends share the same `run_structure_prediction()` / `validate_environment()` / `collect_outputs()` contract. Structure predictions carry the safety label: **"Structure prediction only — not clinical validation"**.

Backends are registered at startup in `base.py`. The active default is controlled by `NEOVAX_ALPHAFOLD_DEFAULT_BACKEND` (default: `mock`).

---

## Backend Summary

| Name               | Mode  | GPU | External Upload   | Complexes | RNA/DNA/Ligands |
| ------------------ | ----- | --- | ----------------- | --------- | --------------- |
| `mock`             | mock  | No  | No                | No        | No              |
| `colabfold`        | local | Yes | Optional (MMseqs) | Yes       | No              |
| `local_colabfold`  | local | Yes | No                | Yes       | No              |
| `alphafold2_local` | local | Yes | No                | Yes       | No              |
| `alphafold3_local` | local | Yes | No                | Yes       | Yes             |
| `alphafold_server` | cloud | No  | **Yes**           | Yes       | Yes             |
| `alphafold_db`     | cloud | No  | No                | No        | No              |

---

## Backends in Detail

### `mock`

**Class:** `MockAlphaFoldBackend` (fully implemented, not metadata-only)

Returns deterministic fake results without any computation. pLDDT and pAE values in the output are hard-coded placeholders.

- **Setup:** None. Always available.
- **GPU:** Not required.
- **Privacy:** No data leaves the machine.
- **When to use:** Development, CI, demos, and any workflow where structure data is not needed for a real research decision.
- **Warning:** Mock output explicitly states "No real AlphaFold computation was performed." Do not use mock outputs for research conclusions.

### `colabfold`

**Command:** `colabfold_batch` (wraps ColabFold CLI)

Built via `build_colabfold_command()` in `backend/app/alphafold/colabfold.py`. Accepts `ColabFoldJobRequest` with options for recycles, seeds, templates, dropout, max MSA, and custom template path.

- **Setup:** Install ColabFold locally. The `colabfold_batch` binary must be on `PATH`.
- **GPU:** Required for practical use.
- **Privacy:** By default, ColabFold queries remote MMseqs2 servers for MSA generation. To keep all data local, configure `--host-url` to point to a local MMseqs2 server instance.
- **When to use:** Fast local structure prediction; best when you have a GPU and can tolerate the default remote MSA lookup, or have a local MMseqs2 server.

### `local_colabfold`

**Command:** `colabfold_batch` (LocalColabFold variant)

Wraps the LocalColabFold installation, which bundles a local MMseqs2 database to avoid remote queries.

- **Setup:** Install LocalColabFold per the upstream instructions. Requires significant local storage for the MMseqs2 database.
- **GPU:** Required.
- **Privacy:** Fully local; no external network calls when database is local.
- **When to use:** Preferred over `colabfold` when data privacy requires no external MSA calls. Suitable for human-mode research.

### `alphafold2_local`

**Command:** `run_alphafold` (DeepMind/Google AlphaFold2 CLI)

Built via `build_alphafold2_local_command()` in `backend/app/alphafold/alphafold2_local.py`. Accepts `AlphaFold2LocalJobRequest` with `fasta_path`, `data_dir`, `max_template_date`, `model_preset`, and `db_preset`.

- **Setup:** Install AlphaFold2 per DeepMind's instructions. Requires genetic databases (UniRef90, BFD, etc.) — several hundred GB of storage.
- **GPU:** Required (A100 or equivalent recommended).
- **Privacy:** Fully local if databases are local.
- **When to use:** Standard protein structure prediction with full AF2 database access. More accurate than ColabFold for some targets; slower.

### `alphafold3_local`

**Command:** `alphafold` (AlphaFold3 CLI via `run_alphafold.py`)

Built via `build_alphafold3_local_command()` in `backend/app/alphafold/alphafold3_local.py`. Accepts `AlphaFold3LocalJobRequest` supporting two input modes:

- `json` — pass `--json_path` with a structured AF3 JSON input file
- `input_dir` — pass `--input_dir`

The helper `build_af3_json_input_file()` writes an `AF3InputJSON` model to disk for `--json_path` use.

- **Setup:** Requires AlphaFold3 model weights (separate license from Google DeepMind), a compatible GPU, and the `alphafold3` Python package.
- **GPU:** Required. AF3 is significantly more memory-intensive than AF2.
- **Privacy:** Fully local.
- **When to use:** When you need RNA, DNA, or ligand complex prediction in addition to protein folding. AF3 is the only local backend with this capability.
- **License note:** AlphaFold3 model weights have a non-commercial research license. Review terms before use.

### `alphafold_server`

**Command:** `alphafold_server_submit` (dry-run placeholder)

Built via `build_alphafold_server_command()` in `backend/app/alphafold/alphafold_server.py`.

- **Setup:** Account with the AlphaFold Server (alphafoldserver.com). The `acknowledge_external_upload` flag must be explicitly set to `true` in the request.
- **GPU:** Not required locally (computation runs remotely).
- **Privacy:** **Sequence data is uploaded to Google DeepMind's servers.** This triggers the external upload gate in preflight — requires explicit user confirmation and is blocked in human mode without expert approval. Review the server's data-use policy before submitting any real patient or animal data.
- **When to use:** When you have no local GPU and need AF3-quality prediction including RNA/DNA/ligands. Never use for sensitive human genomic data without institutional clearance.

### `alphafold_db`

**Command:** `alphafold_db_lookup` (accession lookup)

Built via `build_alphafold_db_command()` in `backend/app/alphafold/alphafold_db.py`. Fetches pre-computed structures from the AlphaFold EBI database by UniProt accession.

- **Setup:** Internet access to `alphafold.ebi.ac.uk`. No local GPU needed.
- **Privacy:** Sends only a UniProt accession (not patient sequence data) to the EBI API. Lower privacy risk than `alphafold_server` but still an external call.
- **When to use:** When your protein of interest has a pre-computed entry in the AF database and you do not need to fold a custom/mutant sequence.
- **Output format:** Returns CIF file URL and PAE JSON URL. Not suitable for neoantigen-specific mutant sequences — those require a real prediction backend.

---

## Checking Backend Availability

```bash
GET /alphafold/backends
```

Returns the registered status of all backends including `requires_gpu`, `requires_external_upload`, and `license_notes`. Use `validate_environment()` (called server-side) to check if the local binary is actually present.

---

## Dry-Run vs. Execute

```bash
# Preview command without running
POST /alphafold/backends/{backend_name}/dry-run

# Run synchronously
POST /alphafold/backends/{backend_name}/run

# Dispatch async background job
POST /alphafold/backends/{backend_name}/run-async
```

Always run a dry-run first when testing a new backend configuration. The dry-run mode builds and returns the command manifest without executing anything.

---

## Environment Variable

```bash
NEOVAX_ALPHAFOLD_DEFAULT_BACKEND=mock        # safe default
NEOVAX_ALPHAFOLD_DEFAULT_BACKEND=local_colabfold  # local GPU setup
NEOVAX_ALPHAFOLD_ALLOWED_BACKENDS=mock,local_colabfold,alphafold3_local
NEOVAX_ALPHAFOLD_CACHE_OUTPUTS=true
NEOVAX_ALPHAFOLD_STORE_CONFIDENCE_METRICS=true
```

---

## Output Safety Labels

Every `StructureResult` carries:

```
safety_label: "Structure prediction only — not clinical validation"
```

This label is preserved in all downstream reports and artifact exports. It cannot be removed by agent skills or API callers.
