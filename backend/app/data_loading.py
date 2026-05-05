"""NeoVax-Agent Data Loading and Validation Module (Phase 4)

File type validation, sample role detection, missing-data checklists,
format-specific metadata registration, and data inventory helpers.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from backend.app.models import (
    CandidateAntigen,
    Sample,
    StructureJob,
    Variant,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Supported file formats
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {
    "fastq": {
        "extensions": {".fastq", ".fq", ".fastq.gz", ".fq.gz"},
        "description": "Raw sequencing reads",
        "sample_types": {"tumor", "normal", "rna"},
    },
    "bam": {
        "extensions": {".bam", ".cram"},
        "description": "Aligned sequencing reads",
        "sample_types": {"tumor", "normal", "rna"},
    },
    "vcf": {
        "extensions": {".vcf", ".vcf.gz", ".bcf"},
        "description": "Variant call format",
        "sample_types": {"tumor", "normal"},
    },
    "rnaseq": {
        "extensions": {".fastq", ".fq", ".fastq.gz", ".fq.gz", ".bam"},
        "description": "RNA-seq expression data",
        "sample_types": {"rna"},
    },
    "csv": {
        "extensions": {".csv", ".tsv", ".txt"},
        "description": "Tabular variant/expression data",
        "sample_types": {"tumor", "normal", "rna", "other"},
    },
}


# ---------------------------------------------------------------------------
# File type validation
# ---------------------------------------------------------------------------


def detect_file_format(filename: str) -> str | None:
    name = filename.lower()
    if name.endswith(".gz"):
        stem = name[:-3]
    else:
        stem = name

    suffix = Path(stem).suffix
    for fmt, info in SUPPORTED_FORMATS.items():
        for ext in info["extensions"]:
            clean_ext = ext.lstrip(".")
            if name.endswith(f".{clean_ext}"):
                return fmt
    return None


def validate_file_type(filename: str, expected_format: str | None = None) -> dict:
    detected = detect_file_format(filename)
    if detected is None:
        return {
            "valid": False,
            "detected_format": None,
            "error": f"Unrecognized file format for '{filename}'. Supported: {list(SUPPORTED_FORMATS.keys())}",
        }
    if expected_format and detected != expected_format:
        return {
            "valid": False,
            "detected_format": detected,
            "error": f"Expected '{expected_format}' but detected '{detected}' for '{filename}'.",
        }
    return {"valid": True, "detected_format": detected, "error": None}


def validate_file_paths(file_paths: dict[str, str]) -> list[dict]:
    results = []
    for label, path in file_paths.items():
        result = validate_file_type(path)
        result["label"] = label
        result["path"] = path
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Checksum validation
# ---------------------------------------------------------------------------


def compute_file_checksum(file_path: str, algorithm: str = "sha256") -> str | None:
    p = Path(file_path)
    if not p.is_file():
        return None
    h = hashlib.new(algorithm)
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_checksum(file_path: str, expected_checksum: str, algorithm: str = "sha256") -> dict:
    actual = compute_file_checksum(file_path, algorithm)
    if actual is None:
        return {"valid": False, "error": f"File not found: {file_path}", "actual": None}
    match = actual == expected_checksum
    return {
        "valid": match,
        "actual": actual,
        "expected": expected_checksum,
        "error": None if match else "Checksum mismatch",
    }


# ---------------------------------------------------------------------------
# Sample role detection
# ---------------------------------------------------------------------------

TUMOR_KEYWORDS = {"tumor", "tumour", "cancer", "neoplasm", "malignant", "met", "primary"}
NORMAL_KEYWORDS = {"normal", "germline", "matched_normal", "blood", "buffy", "saliva", "control"}
RNA_KEYWORDS = {"rna", "rnaseq", "rna-seq", "expression", "transcriptome", "mrna"}


def detect_sample_role(
    *,
    filename: str | None = None,
    label: str | None = None,
    metadata: dict | None = None,
) -> str:
    signals = " ".join(filter(None, [filename, label, str(metadata or "")])).lower()

    if any(kw in signals for kw in RNA_KEYWORDS):
        return "rna"
    if any(kw in signals for kw in TUMOR_KEYWORDS):
        return "tumor"
    if any(kw in signals for kw in NORMAL_KEYWORDS):
        return "normal"
    return "other"


# ---------------------------------------------------------------------------
# Missing data detection
# ---------------------------------------------------------------------------


def detect_missing_data(db: Session, case_id: str) -> dict:
    samples = db.query(Sample).filter(Sample.case_id == case_id).all()
    variants = db.query(Variant).filter(Variant.case_id == case_id).all()
    candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
    structure_jobs = db.query(StructureJob).filter(StructureJob.case_id == case_id).all()

    sample_types = {s.sample_type.value for s in samples}

    issues = []
    warnings = []

    if not samples:
        issues.append("No samples registered — upload sequencing metadata to begin.")

    has_tumor = "tumor" in sample_types
    has_normal = "normal" in sample_types
    has_rna = "rna" in sample_types

    if has_tumor and not has_normal:
        issues.append("Missing matched-normal sample — variant calling quality will be reduced.")
    if not has_tumor and not variants:
        issues.append("No tumor sample or variants — cannot identify neoantigen candidates.")
    if not has_rna:
        warnings.append("No RNA-seq data — expression validation of candidates will be unavailable.")

    if not variants and samples:
        warnings.append("Samples registered but no variants called yet — run the bioinformatics pipeline.")
    if variants and not candidates:
        warnings.append("Variants exist but no candidates ranked — run candidate prediction.")
    if candidates and not structure_jobs:
        warnings.append("Candidates exist but no structure predictions — consider running AlphaFold.")

    for s in samples:
        if not s.checksum:
            warnings.append(f"Sample '{s.id[:8]}' ({s.sample_type.value}) has no checksum recorded.")

    return {
        "case_id": case_id,
        "sample_count": len(samples),
        "sample_types": sorted(sample_types),
        "has_tumor": has_tumor,
        "has_normal": has_normal,
        "has_rna": has_rna,
        "variant_count": len(variants),
        "candidate_count": len(candidates),
        "structure_job_count": len(structure_jobs),
        "issues": issues,
        "warnings": warnings,
        "data_completeness": "complete" if not issues else "incomplete",
    }


def build_missing_data_checklist(db: Session, case_id: str) -> list[dict]:
    report = detect_missing_data(db, case_id)
    checklist = []

    checklist.append({
        "item": "Register tumor sample",
        "done": report["has_tumor"],
        "priority": "high",
    })
    checklist.append({
        "item": "Register matched-normal sample",
        "done": report["has_normal"],
        "priority": "high",
    })
    checklist.append({
        "item": "Register RNA-seq sample (optional but recommended)",
        "done": report["has_rna"],
        "priority": "medium",
    })
    checklist.append({
        "item": "Run variant calling pipeline",
        "done": report["variant_count"] > 0,
        "priority": "high",
    })
    checklist.append({
        "item": "Generate candidate antigen predictions",
        "done": report["candidate_count"] > 0,
        "priority": "high",
    })
    checklist.append({
        "item": "Run structure prediction (AlphaFold)",
        "done": report["structure_job_count"] > 0,
        "priority": "medium",
    })

    return checklist


# ---------------------------------------------------------------------------
# Format-specific metadata builders
# ---------------------------------------------------------------------------


def build_fastq_metadata(
    *,
    read1_path: str,
    read2_path: str | None = None,
    instrument: str | None = None,
    run_id: str | None = None,
    lane: str | None = None,
    barcode: str | None = None,
) -> dict:
    meta = {
        "format": "fastq",
        "read1": read1_path,
        "paired_end": read2_path is not None,
    }
    if read2_path:
        meta["read2"] = read2_path
    if instrument:
        meta["instrument"] = instrument
    if run_id:
        meta["run_id"] = run_id
    if lane:
        meta["lane"] = lane
    if barcode:
        meta["barcode"] = barcode
    return meta


def build_bam_metadata(
    *,
    bam_path: str,
    reference_genome: str | None = None,
    aligner: str | None = None,
    sorted: bool = True,
    indexed: bool = True,
) -> dict:
    return {
        "format": "bam",
        "bam_path": bam_path,
        "reference_genome": reference_genome,
        "aligner": aligner,
        "sorted": sorted,
        "indexed": indexed,
    }


def build_vcf_metadata(
    *,
    vcf_path: str,
    reference_genome: str | None = None,
    caller: str | None = None,
    filter_status: str | None = None,
) -> dict:
    return {
        "format": "vcf",
        "vcf_path": vcf_path,
        "reference_genome": reference_genome,
        "caller": caller,
        "filter_status": filter_status or "unfiltered",
    }


def build_rnaseq_metadata(
    *,
    file_path: str,
    quantification_method: str | None = None,
    reference_transcriptome: str | None = None,
) -> dict:
    return {
        "format": "rnaseq",
        "file_path": file_path,
        "quantification_method": quantification_method,
        "reference_transcriptome": reference_transcriptome,
    }


def build_csv_variant_metadata(
    *,
    file_path: str,
    delimiter: str = ",",
    has_header: bool = True,
    column_mapping: dict | None = None,
) -> dict:
    return {
        "format": "csv",
        "file_path": file_path,
        "delimiter": delimiter,
        "has_header": has_header,
        "column_mapping": column_mapping or {},
    }
