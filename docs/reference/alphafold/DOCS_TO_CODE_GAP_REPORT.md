# AlphaFold docs-to-code gap report

Generated after comparing the local NeoVax AlphaFold implementation against the dumped reference corpus in `docs/reference/alphafold/`.

## Scope compared

Docs / references:
- `alphafold3/docs/input.md`
- `alphafold3/docs/output.md`
- `colabfold/MsaServer/README.md`
- `localcolabfold/README.md`
- `alphafold_server` browser dump and archived pages
- `alphafold_db` browser dump

NeoVax code:
- `backend/app/alphafold/base.py`
- `backend/app/alphafold/shells.py`
- `backend/app/main.py`
- `backend/app/config.py`
- AlphaFold tests under `backend/tests/`

## What NeoVax already has

1. Backend names are aligned at a high level.
   - Config exposes `mock`, `colabfold`, `local_colabfold`, `alphafold2_local`, `alphafold3_local`, `alphafold_server`.
   - Evidence: `backend/app/config.py:20-28`, `config.example.yaml:20-30`

2. There is a useful common backend metadata shape.
   - `AlphaFoldBackend` already models mode, GPU requirement, external upload flag, capability flags, cost/runtime estimation, output collection.
   - Evidence: `backend/app/alphafold/base.py:50-151`

3. Shell-backend discovery exists.
   - NeoVax can already report whether `colabfold_batch`, `run_alphafold`, or `alphafold` are on PATH and build a dry-run command.
   - Evidence: `backend/app/alphafold/shells.py:66-105`

4. API surface exists for backend listing, dry-run, and run.
   - Evidence: `backend/app/main.py:335-404`

5. Parsed structure outputs can already update candidate structure evidence.
   - Evidence: `backend/app/main.py:170-216`, `backend/tests/test_alphafold_output_parsing_api.py:8-105`

## Root gap: NeoVax does not yet model real AlphaFold input/output dialects

Current implementation is still a shell stub / generic command wrapper, not a real AlphaFold integration layer.

Evidence:
- `build_alphafold_command()` only builds `[command, fasta_path, output_dir]` regardless of backend. `backend/app/alphafold/shells.py:81-89`
- `alphafold_backend_run()` accepts an untyped `payload: dict`. `backend/app/main.py:348-404`
- Tests only assert graceful execution shell behavior or monkeypatched JSON parsing. `backend/tests/test_alphafold_execution_api.py:4-32`, `backend/tests/test_alphafold_output_parsing_api.py:8-105`

## Docs-vs-code mismatches

### A. AlphaFold 3 input dialect not represented

Docs say AF3 supports JSON input with:
- `name`
- `modelSeeds`
- `sequences` with protein/RNA/DNA/ligand entities
- optional `bondedAtomPairs`
- optional `userCCD` / `userCCDPath`
- required `dialect`
- required `version`
- optional custom MSA/template paths
- automatic conversion from AlphaFold Server JSON dialect
- Evidence: `docs/reference/alphafold/alphafold3/docs/input.md:5-45`, `:102-170`, `:178-233`

Current NeoVax code:
- only has `StructureInputManifest(sequence, sequence_type, job_name, case_id, candidate_id)`
- no typed JSON payload model for AF3
- no support for RNA, DNA, ligand, PTM, CCD, bonded atoms, multiple seeds, custom MSA, templates, or dialect/version fields
- no AlphaFold Server JSON converter abstraction
- Evidence: `backend/app/alphafold/base.py:25-33`, `backend/app/alphafold/shells.py:81-89`

Impact:
- `alphafold3_local` cannot correctly interface with actual AF3 inputs yet.

### B. AlphaFold 3 output model not represented

Docs say AF3 output directory includes:
- top-level `*_model.cif`
- `*_confidences.json`
- `*_summary_confidences.json`
- `*_data.json`
- `*_ranking_scores.csv`
- per-seed/per-sample subdirs
- optional embeddings/distograms
- confidence metrics including `ptm`, `iptm`, `ranking_score`, `chain_pair_iptm`, `chain_ptm`, `chain_iptm`, `pae`, `atom_plddts`
- Evidence: `docs/reference/alphafold/alphafold3/docs/output.md:3-42`, `:81-219`

Current NeoVax code:
- only expects a parsed JSON blob in stdout with a `structure` object containing things like `pdb_file`, `pLDDT_mean`, `pAE_mean`
- creates a `StructureJob` with only `output_path`, `pLDDT_mean`, `pAE_mean`
- does not model mmCIF vs PDB distinction, sample/seed hierarchy, rankings, summary confidence files, embeddings, or distograms
- Evidence: `backend/app/main.py:370-394`, `backend/tests/test_alphafold_output_parsing_api.py:19-43`

Impact:
- AF3 output provenance and ranking semantics are missing.
- current parsing contract is too thin for real AF3/AF2 runs.

### C. ColabFold / LocalColabFold command contract is underspecified

Docs say LocalColabFold / ColabFold support:
- input as directory, fasta, csv/tsv, or a3m
- multimer syntax with `:` separators in FASTA
- flags like `--amber`, `--templates`, `--use-gpu-relax`, `--num-recycle`, `--custom-template-path`, `--random-seed`, `--num-seeds`, `--max-msa`, `--use-dropout`, `--overwrite-existing-results`
- custom MSA files
- `colabfold_batch --help`
- Evidence: `docs/reference/alphafold/localcolabfold/README.md:149-217`, `:241-258`

Current NeoVax code:
- always builds `colabfold_batch <tmp fasta> <tmp output_dir>`
- no support for any documented flags
- no typed request model for seeds, recycles, templates, a3m, csv/tsv, multimer mode, or host-url
- Evidence: `backend/app/alphafold/shells.py:81-89`

Impact:
- `colabfold` and `local_colabfold` are only superficial command launchers right now.

### D. ColabFold MSA server endpoint support is missing

Docs say ColabFold can use:
- a local/custom API server
- `--host-url` to point `colabfold_batch` at that server
- MSA server config concepts like address/port/workers/rate limit/GPU mode
- Evidence: `docs/reference/alphafold/colabfold/MsaServer/README.md:27-34`, `:62-65`

Current NeoVax code:
- no config field for ColabFold MSA host URL
- no endpoint-specific backend metadata
- no distinction between online MMseqs-backed mode and fully local DB mode
- no environment validation for MSA server reachability
- Evidence: `backend/app/config.py:53-64`, `backend/app/alphafold/shells.py:66-71`

Impact:
- NeoVax cannot cleanly target a custom ColabFold endpoint yet.

### E. AlphaFold Server-specific capabilities and restrictions are not encoded

Server docs/browser state show:
- powered by AlphaFold 3
- supports proteins, DNA, RNA, ligands, ions, PTMs, glycans
- token limit 5000
- quota 30 jobs/day
- explicit non-commercial terms and output-use restrictions
- external upload/privacy implications
- Evidence: browser snapshot of `https://alphafoldserver.com/welcome`; archived pages under site archive and local dump

Current NeoVax code:
- has backend name `alphafold_server` in config but no actual shell/backend implementation in `SHELL_BACKENDS`
- no request model for server dialect JSON
- no explicit token-limit validation
- no quota/account-state representation
- no distinct license/terms metadata beyond generic fields
- Evidence: `backend/app/config.py:20-28`, `backend/app/alphafold/shells.py:66-71`

Impact:
- `alphafold_server` exists only as a configured name, not an actionable backend.

### F. AlphaFold Database endpoint integration is missing

Docs/browser state show AlphaFold DB/API docs exist and are relevant as a compatible reference source for precomputed structures.

Current NeoVax code:
- no backend or helper for lookup-first workflow against AlphaFold DB
- no retrieval of precomputed structures by UniProt/accession/name
- no strategy that prefers DB hits before running expensive structure jobs

Impact:
- misses an obvious optimization / reference path for known proteins.

## Most important architectural conclusion

NeoVax currently mixes three very different things under one thin shell abstraction:
1. local command-line predictors
2. external/server predictors
3. structure database lookup/reference services

That abstraction is too small.

Real integration needs at least:
- typed input dialects per backend family
- typed output parsers per backend family
- richer backend capability metadata
- config for endpoint/host/database locations
- request validation before launch

## Recommended implementation plan

### Phase 1 — Introduce typed backend contracts

Add typed request/response models, not raw `dict` payloads.

Suggested models:
- `AlphaFoldJobRequestBase`
- `ColabFoldJobRequest`
- `AlphaFold2LocalJobRequest`
- `AlphaFold3JobRequest`
- `AlphaFoldServerJobRequest`
- `AlphaFoldDbLookupRequest`

Must cover:
- input kind: `fasta | a3m | csv | tsv | json | input_dir | accession_lookup`
- `job_name`
- `case_id`, `candidate_id`
- `sequence_type`
- seed/recycle/template/MSA controls
- host URL for ColabFold API server
- AF3 dialect/version fields
- external upload acknowledgement for server-mode jobs

### Phase 2 — Split backend families

Create concrete modules:
- `backend/app/alphafold/colabfold.py`
- `backend/app/alphafold/alphafold2_local.py`
- `backend/app/alphafold/alphafold3_local.py`
- `backend/app/alphafold/alphafold_server.py`
- `backend/app/alphafold/alphafold_db.py`

Reason:
- each has different input/output semantics
- current single `shells.py` cannot accurately encode them

### Phase 3 — Add real output parsers

Need parser support for at least:
- AF3 output dir and summary confidence files
- ColabFold output files and confidence images/jsons
- mmCIF-first handling for AF3
- ranking score extraction
- seed/sample provenance

Store more structure evidence fields, e.g.:
- `output_format`
- `model_cif`
- `summary_confidences_json`
- `ranking_score`
- `ptm`
- `iptm`
- `chain_pair_iptm`
- `seed`
- `sample`
- `output_terms`

### Phase 4 — Add endpoint / service config

Config additions likely needed:
- `alphafold_colabfold_host_url`
- `alphafold_colabfold_use_templates`
- `alphafold_colabfold_default_num_recycle`
- `alphafold_colabfold_default_num_seeds`
- `alphafold_af3_model_dir`
- `alphafold_af3_db_dir`
- `alphafold_af3_jackhmmer_binary`
- `alphafold_server_enabled`
- `alphafold_server_terms_ack_required`
- `alphafold_db_base_url`

### Phase 5 — Add lookup-first workflow

Before launching a new job for a canonical protein target, support:
- AlphaFold DB lookup
- storing returned reference links/files as structure evidence
- fallback to local/server prediction only if needed

### Phase 6 — Expand tests

Add tests for:
- AF3 JSON validation and dialect conversion paths
- ColabFold command generation with flags
- `--host-url` injection for custom MSA server
- AF3 output directory parsing
- AlphaFold Server gating and consent checks
- AlphaFold DB lookup path

## Best next coding slice

Best next slice is not "wire everything".
Best next slice is:

1. typed job schemas
2. backend-specific command builders
3. one real parser path for ColabFold output and one for AF3 output metadata

That creates the base needed for the later safety/report work.

## Concrete immediate tasks

1. Add `backend/app/alphafold/schemas.py` with typed request/response payloads.
2. Refactor `shells.py` into backend-specific builders.
3. Implement config for ColabFold custom `--host-url`.
4. Implement `alphafold_server` as a gated remote backend descriptor even if execution is still stubbed.
5. Add `alphafold_db` lookup helper / pseudo-backend.
6. Update API endpoints from generic `payload: dict` to typed models.
7. Extend parsing/storage beyond `pdb_file`, `pLDDT_mean`, `pAE_mean`.

## Priority ranking

P0:
- typed payloads
- backend-specific builders
- alphafold_server real representation
- colabfold host-url / flags

P1:
- AF3 output parsing
- AlphaFold DB lookup path
- richer structure evidence storage

P2:
- embeddings/distograms support
- deeper AF3 advanced fields (`userCCD`, bonded glycans, complex covalent bonds)

## Bottom line

The repo is already pointed in the correct direction, but the current AlphaFold layer is still a mock-era shell facade. The docs corpus confirms NeoVax can interface with AlphaFold-family tools, but only after the backend layer is upgraded from:
- one generic `dict` request
- one generic shell command shape
- one thin parsed JSON expectation

to:
- typed backend-specific requests
- backend-family adapters
- real parser/storage models for AF2/AF3/ColabFold/server/database workflows.
