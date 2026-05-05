# Bioinformatics Adapter Guide

> **NeoVax-Agent is a research coordination tool only. It does not provide medical advice, treatment instructions, or administerable outputs.**

---

## Overview

Pipeline adapters are shell wrappers in `backend/app/pipeline/shells.py` that build, validate, and optionally execute bioinformatics tool commands. They follow a three-mode pattern: **status check**, **dry-run**, and **execute**.

All adapters are registered at startup in the `PIPELINE_ADAPTERS` dict. A `ShellAdapterStatus` is computed for each adapter using `shutil.which()` — if the binary is not on `PATH`, `available=False` and execution is blocked.

Every `StepResult` carries the safety label: **"Research candidate only — not administerable"**.

---

## Adapter Registry

| Adapter key    | Binary     | Tool                                |
| -------------- | ---------- | ----------------------------------- |
| `bwa`          | `bwa`      | BWA short-read aligner              |
| `bwa_mem2`     | `bwa-mem2` | BWA-MEM2 faster aligner             |
| `gatk_mutect2` | `gatk`     | GATK Mutect2 somatic variant caller |
| `vep`          | `vep`      | Ensembl Variant Effect Predictor    |
| `pvactools`    | `pvacseq`  | pVACtools neoantigen prioritization |

---

## Pipeline Mode

The `NEOVAX_PIPELINE_MODE` setting controls whether real adapters run:

- `mock` (default): Uses `MockAlignmentStep`, `MockVariantCallingStep`, `MockAnnotationStep`, `MockCandidatePrioritizationStep` from `pipeline/base.py`. No real tools required.
- `real`: Routes requests through the shell adapters. Requires all tools installed.

Switch to `real` only after verifying adapter availability via `GET /pipeline/adapters`.

---

## Checking Adapter Status

```bash
GET /pipeline/adapters
```

Returns `ShellAdapterStatus` for each registered adapter:

```json
{
  "bwa": {
    "name": "bwa",
    "command": "bwa",
    "available": true,
    "path": "/usr/bin/bwa",
    "validation_ok": true,
    "notes": "BWA short-read aligner shell stub."
  }
}
```

If `available` is `false`, the adapter cannot execute. Install the tool and ensure it is on `PATH`.

---

## Dry-Run Mode

```bash
POST /pipeline/adapters/{adapter_name}/dry-run
```

Builds and returns the full command list without executing anything. Use this to verify arguments and config defaults before a real run.

```json
{
  "adapter": "bwa",
  "mode": "dry_run",
  "command": [
    "bwa",
    "mem",
    "-t",
    "4",
    "-R",
    "@RG\\tID:sample",
    "/data/reference/hg38.fa",
    "tumor_R1.fastq.gz"
  ],
  "available": true,
  "validation_ok": true
}
```

---

## Execute Mode

```bash
POST /pipeline/adapters/{adapter_name}/run
```

Executes the tool via `subprocess.run()` with `capture_output=True`. Returns `ShellExecution` with `stdout`, `stderr`, `return_code`, `timed_out`, and `output_path`.

If the binary is unavailable, returns `status: "unavailable"` immediately without attempting execution.

Default timeout: 30 seconds. Override with `"timeout_seconds"` in the request payload.

---

## Adapters in Detail

### BWA / BWA-MEM2

**Request schema:** `BwaRequest`

Builds: `bwa mem [-t THREADS] [-R READ_GROUP] REFERENCE FASTQ_1 [FASTQ_2]`

Key fields:

- `reference` — FASTA reference genome path (default: `NEOVAX_PIPELINE_BWA_REFERENCE`)
- `fastq_1` — First read file (required)
- `fastq_2` — Second read file (optional, for paired-end)
- `threads` — Parallelism (default: `NEOVAX_PIPELINE_DEFAULT_THREADS`)
- `read_group` — SAM `@RG` header string
- `output_bam` — Output BAM path

Config defaults are merged from `settings.pipeline_bwa_reference` and `settings.pipeline_default_threads`. Payload values override defaults.

### GATK Mutect2

**Request schema:** `GatkMutect2Request`

Builds: `gatk Mutect2 [-R REFERENCE] -I TUMOR_BAM [-I NORMAL_BAM] [-L INTERVALS] [--panel-of-normals PON] [--germline-resource RESOURCE] [-O OUTPUT_VCF]`

Key fields:

- `input_bam` — Tumor BAM (required)
- `normal_bam` — Matched normal BAM (optional but recommended)
- `reference` — Reference FASTA (default: `NEOVAX_PIPELINE_GATK_REFERENCE`)
- `intervals` — Genomic intervals (BED or interval list)
- `panel_of_normals` — PON VCF path (default: `NEOVAX_PIPELINE_GATK_PANEL_OF_NORMALS`)
- `germline_resource` — Germline AF resource (default: `NEOVAX_PIPELINE_GATK_GERMLINE_RESOURCE`)
- `tumor_sample` — Sample name in the BAM header
- `output_vcf` — Output VCF path

### VEP (Ensembl Variant Effect Predictor)

**Request schema:** `VepRequest`

Builds: `vep --input_file VCF [--dir_cache CACHE_DIR] [--assembly ASSEMBLY] [--fork N] [--everything] [--hgvs] [--symbol] [--canonical] [--output_file OUTPUT]`

Key fields:

- `input_vcf` — Input VCF (required)
- `cache_dir` — VEP cache directory (default: `NEOVAX_PIPELINE_VEP_CACHE_DIR`)
- `assembly` — Reference assembly e.g. `GRCh38` (default: `NEOVAX_PIPELINE_VEP_ASSEMBLY`)
- `fork` — CPU threads for VEP (default: `NEOVAX_PIPELINE_VEP_FORK`)
- `everything` — Enable all annotation plugins (bool)
- `hgvs`, `symbol`, `canonical` — Common annotation flags

VEP requires a local cache. Download with `vep_install` or `INSTALL.pl` per Ensembl documentation.

### pVACtools (pvacseq)

**Request schema:** `PvactoolsRequest`

Builds: `pvacseq INPUT_VCF SAMPLE_NAME ALLELES ALGORITHMS [OUTPUT_DIR] [--peptide-length N] [--netmhc-stab]`

Key fields:

- `input_vcf` — Annotated VCF from VEP (required)
- `sample_name` — Sample identifier in the VCF (required)
- `alleles` — List of HLA/DLA alleles e.g. `["HLA-A*02:01"]` (default: `NEOVAX_PIPELINE_PVACTOOLS_ALLELES`)
- `prediction_algorithms` — List of algorithms e.g. `["NetMHC"]` (default: `NEOVAX_PIPELINE_PVACTOOLS_ALGORITHMS`)
- `output_dir` — Output directory
- `peptide_length` — Peptide length for binding prediction
- `netmhc_stab` — Enable NetMHCstab stability predictions

pVACtools requires NetMHCpan (and optionally other predictors) installed and licensed separately from the DTU Health Tech website.

---

## Tool Version Capture

`StepResult` includes a `tool_versions` dict and `reproducibility_manifest`. For mock steps, versions are reported as `"mock_* v0.1.0-mock"`. For real adapter executions, capture versions by running the tool with `--version` as a pre-flight step and storing the output in the manifest.

The `create_reproducibility_manifest()` method on `PipelineStep` hashes all inputs with SHA-256 and records tool versions for audit traceability.

---

## Configuration Reference

```bash
NEOVAX_PIPELINE_MODE=mock                          # mock or real
NEOVAX_PIPELINE_BWA_REFERENCE=/data/reference/hg38.fa
NEOVAX_PIPELINE_GATK_REFERENCE=/data/reference/hg38.fa
NEOVAX_PIPELINE_GATK_PANEL_OF_NORMALS=/data/pon.vcf.gz
NEOVAX_PIPELINE_GATK_GERMLINE_RESOURCE=/data/af-only-gnomad.hg38.vcf.gz
NEOVAX_PIPELINE_VEP_CACHE_DIR=/data/vep_cache
NEOVAX_PIPELINE_VEP_ASSEMBLY=GRCh38
NEOVAX_PIPELINE_VEP_FORK=4
NEOVAX_PIPELINE_PVACTOOLS_ALLELES=HLA-A*02:01
NEOVAX_PIPELINE_PVACTOOLS_ALGORITHMS=NetMHC
NEOVAX_PIPELINE_DEFAULT_THREADS=4
NEOVAX_PIPELINE_DEFAULT_MEMORY_GB=8
NEOVAX_PIPELINE_CONCURRENT_WORKERS=2
NEOVAX_PIPELINE_RETRY_MAX_ATTEMPTS=3
```

---

## Running the Pipeline

```bash
# Synchronous mock run for a case
POST /cases/{case_id}/pipeline/run

# Async background job
POST /cases/{case_id}/pipeline/run-async

# Check adapter health before running real mode
GET /pipeline/adapters

# Dry-run a specific adapter
POST /pipeline/adapters/gatk_mutect2/dry-run

# Run a specific adapter directly
POST /pipeline/adapters/vep/run
```

All pipeline API calls pass through `POST /safety/preflight` first. Non-demo sequence data requires expert mode.
