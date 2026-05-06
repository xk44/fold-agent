"""FoldAgent Demo Mode (Phase 21)

Provides demo case creation, synthetic dataset generation, and demo data reset.
All demo data is clearly marked as synthetic — not for clinical use.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import uuid4

from backend.app.models import (
    CandidateAntigen,
    Case,
    Report,
    ReviewStatusEnum,
    Sample,
    SampleTypeEnum,
    SpeciesEnum,
    StructureJob,
    StructureJobStatusEnum,
    Subject,
    Variant,
)
from backend.app.safety.audit import log_action

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Demo mode flag
# ---------------------------------------------------------------------------

DEMO_MODE: bool = os.environ.get("FOLDAGENT_DEMO_MODE", "false").lower() in ("1", "true", "yes")

# Tag applied to every demo-created record so reset can find them
_DEMO_TAG = "foldagent_demo_created"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEMO_VARIANTS: list[dict] = [
    {
        "genomic_coordinates": "chr4:55589767 A>T",
        "gene": "KIT",
        "transcript": "ENST00000288135.6",
        "protein_change": "p.Asp816Val",
        "caller_source": "mock_mutect2",
        "quality_metrics": {
            "tumor_vaf": 0.42,
            "normal_vaf": 0.01,
            "depth": 187,
            "mock": True,
        },
        "annotation_source": "Ensembl VEP v110",
    },
    {
        "genomic_coordinates": "chr17:7674220 G>A",
        "gene": "TP53",
        "transcript": "ENST00000269305.9",
        "protein_change": "p.Arg248Trp",
        "caller_source": "mock_mutect2",
        "quality_metrics": {
            "tumor_vaf": 0.61,
            "normal_vaf": 0.00,
            "depth": 243,
            "mock": True,
        },
        "annotation_source": "Ensembl VEP v110",
    },
    {
        "genomic_coordinates": "chr12:25398284 C>T",
        "gene": "KRAS",
        "transcript": "ENST00000256078.10",
        "protein_change": "p.Gly12Asp",
        "caller_source": "mock_mutect2",
        "quality_metrics": {
            "tumor_vaf": 0.35,
            "normal_vaf": 0.00,
            "depth": 302,
            "mock": True,
        },
        "annotation_source": "Ensembl VEP v110",
    },
    {
        "genomic_coordinates": "chr9:21974695 C>T",
        "gene": "CDKN2A",
        "transcript": "ENST00000304494.7",
        "protein_change": "p.Arg80Ter",
        "caller_source": "mock_strelka2",
        "quality_metrics": {
            "tumor_vaf": 0.28,
            "normal_vaf": 0.00,
            "depth": 156,
            "mock": True,
        },
        "annotation_source": "Ensembl VEP v110",
    },
    {
        "genomic_coordinates": "chr13:32338728 T>A",
        "gene": "BRCA2",
        "transcript": "ENST00000380152.8",
        "protein_change": "p.Tyr42Cys",
        "caller_source": "mock_strelka2",
        "quality_metrics": {
            "tumor_vaf": 0.19,
            "normal_vaf": 0.00,
            "depth": 98,
            "mock": True,
        },
        "annotation_source": "Ensembl VEP v110",
    },
]

_DEMO_CANDIDATES: list[dict] = [
    {
        "peptide_metadata": {
            "sequence": "SLYNTVATL",
            "length": 9,
            "position": 816,
            "allele": "HLA-A*02:01",
        },
        "mhc_context": "HLA-A*02:01 / mock MHC-I binding context",
        "prediction_scores": {
            "binding_rank": 0.38,
            "netmhcpan_ic50_nM": 42.1,
            "immunogenicity_score": 0.74,
            "mock": True,
        },
        "expression_evidence": {
            "rna_support": True,
            "tpm": 18.2,
            "expression_percentile": 72,
            "dataset": "mock_rnaseq",
        },
        "structure_evidence": {
            "alphafold_status": "mock_completed",
            "plddt_mean": 0.81,
        },
        "uncertainty_flags": {
            "synthetic_demo": True,
            "professional_review_required": True,
            "binding_prediction_unvalidated": True,
        },
    },
    {
        "peptide_metadata": {
            "sequence": "VVGAVGVGK",
            "length": 9,
            "position": 12,
            "allele": "HLA-A*02:01",
        },
        "mhc_context": "HLA-A*02:01 / mock MHC-I binding context",
        "prediction_scores": {
            "binding_rank": 0.52,
            "netmhcpan_ic50_nM": 87.4,
            "immunogenicity_score": 0.61,
            "mock": True,
        },
        "expression_evidence": {
            "rna_support": True,
            "tpm": 34.7,
            "expression_percentile": 85,
            "dataset": "mock_rnaseq",
        },
        "structure_evidence": {
            "alphafold_status": "mock_completed",
            "plddt_mean": 0.77,
        },
        "uncertainty_flags": {
            "synthetic_demo": True,
            "professional_review_required": True,
            "binding_prediction_unvalidated": True,
        },
    },
    {
        "peptide_metadata": {
            "sequence": "HMTEVVRHC",
            "length": 9,
            "position": 248,
            "allele": "HLA-B*07:02",
        },
        "mhc_context": "HLA-B*07:02 / mock MHC-I binding context",
        "prediction_scores": {
            "binding_rank": 0.71,
            "netmhcpan_ic50_nM": 312.0,
            "immunogenicity_score": 0.49,
            "mock": True,
        },
        "expression_evidence": {
            "rna_support": False,
            "tpm": 4.1,
            "expression_percentile": 31,
            "dataset": "mock_rnaseq",
        },
        "structure_evidence": {
            "alphafold_status": "mock_pending",
            "plddt_mean": None,
        },
        "uncertainty_flags": {
            "synthetic_demo": True,
            "professional_review_required": True,
            "low_expression_warning": True,
            "binding_prediction_unvalidated": True,
        },
    },
]


def _tag() -> dict:
    return {_DEMO_TAG: True}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_demo_case(db: Session) -> dict:
    """Create a complete demo case with samples, variants, candidates, structure job, and report.

    Returns a summary dict with all created IDs.
    Marks every record with ``foldagent_demo_created=True`` so ``reset_demo_data`` can remove them.
    """
    from backend.app.reports import RESEARCH_LABEL, build_candidate_review_report

    case = Case(
        id=str(uuid4()),
        species=SpeciesEnum.dog,
        diagnosis_summary="Canine mast cell tumor — Grade II, right flank (SYNTHETIC DEMO)",
        supervising_professional="Dr. Demo Veterinarian (synthetic)",
        consent_status="demo",
        review_status="unreviewed",
    )
    db.add(case)
    db.flush()

    subject = Subject(
        id=str(uuid4()),
        case_id=case.id,
        anonymized_display_name="DEMO-ROSIE-001",
        metadata_json={
            "species": "Canis lupus familiaris",
            "breed": "Labrador Retriever",
            "age_years": 8,
            "weight_kg": 32.5,
            "sex": "female_spayed",
            "demo": True,
        },
        privacy_flags=_tag(),
    )
    db.add(subject)
    db.flush()

    sample_types = [
        (SampleTypeEnum.tumor, "/demo/data/tumor.bam", "sha256:demo_tumor_001"),
        (SampleTypeEnum.normal, "/demo/data/normal.bam", "sha256:demo_normal_001"),
        (SampleTypeEnum.rna, "/demo/data/rna.fastq.gz", "sha256:demo_rna_001"),
    ]
    samples = []
    for stype, fpath, checksum in sample_types:
        s = Sample(
            id=str(uuid4()),
            case_id=case.id,
            subject_id=subject.id,
            sample_type=stype,
            file_paths={stype.value: fpath},
            checksum=checksum,
            source_lab="Demo Veterinary Oncology Lab",
            custody_metadata=_tag(),
        )
        db.add(s)
        samples.append(s)
    db.flush()

    tumor_sample = samples[0]
    variants = []
    for vdata in _DEMO_VARIANTS:
        v = Variant(
            id=str(uuid4()),
            case_id=case.id,
            sample_id=tumor_sample.id,
            genomic_coordinates=vdata["genomic_coordinates"],
            gene=vdata["gene"],
            transcript=vdata["transcript"],
            protein_change=vdata["protein_change"],
            caller_source=vdata["caller_source"],
            quality_metrics={**vdata["quality_metrics"], **_tag()},
            annotation_source=vdata["annotation_source"],
            review_status=ReviewStatusEnum.unreviewed,
        )
        db.add(v)
        variants.append(v)
    db.flush()

    candidates = []
    for i, cdata in enumerate(_DEMO_CANDIDATES):
        variant = variants[i % len(variants)]
        c = CandidateAntigen(
            id=str(uuid4()),
            case_id=case.id,
            variant_id=variant.id,
            peptide_metadata=cdata["peptide_metadata"],
            mhc_context=cdata["mhc_context"],
            prediction_scores=cdata["prediction_scores"],
            expression_evidence=cdata["expression_evidence"],
            structure_evidence=cdata["structure_evidence"],
            uncertainty_flags={**cdata["uncertainty_flags"], **_tag()},
            review_status=ReviewStatusEnum.unreviewed,
        )
        db.add(c)
        candidates.append(c)
    db.flush()

    structure_job = StructureJob(
        id=str(uuid4()),
        case_id=case.id,
        candidate_id=candidates[0].id,
        backend_used="mock",
        input_hash="sha256:demo_structure_input_001",
        output_path="/demo/output/structure_001.pdb",
        confidence_metrics={
            "plddt_mean": 0.81,
            "plddt_min": 0.63,
            "ptm": 0.79,
            "mock": True,
            **_tag(),
        },
        visualization_path="/demo/output/structure_001_viz.png",
        status=StructureJobStatusEnum.completed,
    )
    db.add(structure_job)
    db.flush()

    report_data = build_candidate_review_report(case, candidates)
    report = Report(
        id=str(uuid4()),
        case_id=case.id,
        report_type=report_data["report_type"],
        generated_by="demo.create_demo_case",
        content_json={**report_data["content_json"], **_tag()},
        safety_label=RESEARCH_LABEL,
    )
    db.add(report)
    db.flush()

    log_action(
        db,
        case_id=case.id,
        actor="demo",
        action="demo.case_created",
        inputs={"demo_mode": True},
        outputs={
            "case_id": case.id,
            "subject_id": subject.id,
            "sample_count": len(samples),
            "variant_count": len(variants),
            "candidate_count": len(candidates),
        },
        details=_tag(),
    )
    db.commit()

    return {
        "case_id": case.id,
        "subject_id": subject.id,
        "species": case.species.value,
        "subject_display_name": subject.anonymized_display_name,
        "sample_count": len(samples),
        "variant_count": len(variants),
        "candidate_count": len(candidates),
        "structure_job_id": structure_job.id,
        "report_id": report.id,
        "demo": True,
    }


def create_synthetic_dataset(db: Session, n_cases: int = 3) -> list[dict]:
    """Create multiple demo cases with varying data completeness.

    - Case 0: full data (all samples, 5 variants, 3 candidates, structure job, report)
    - Case 1: partial data (tumor+normal only, 2 variants, 1 candidate, no structure job)
    - Case 2+: minimal data (tumor only, 1 variant, no candidates)

    Returns a list of summary dicts, one per case.
    """
    from backend.app.reports import RESEARCH_LABEL, build_candidate_review_report

    results = []
    for i in range(n_cases):
        if i == 0:
            # Full case — reuse create_demo_case
            summary = create_demo_case(db)
            summary["completeness"] = "full"
            results.append(summary)
            continue

        case = Case(
            id=str(uuid4()),
            species=SpeciesEnum.dog,
            diagnosis_summary=f"Synthetic demo case {i} — partial data (DEMO)",
            supervising_professional="Dr. Demo Veterinarian (synthetic)",
            consent_status="demo",
            review_status="unreviewed",
        )
        db.add(case)
        db.flush()

        subject = Subject(
            id=str(uuid4()),
            case_id=case.id,
            anonymized_display_name=f"DEMO-SYNTH-{i:03d}",
            metadata_json={"demo": True, "case_index": i},
            privacy_flags=_tag(),
        )
        db.add(subject)
        db.flush()

        if i == 1:
            # Partial: tumor + normal, 2 variants, 1 candidate
            partial_types = [
                (
                    SampleTypeEnum.tumor,
                    f"/demo/data/partial_{i}_tumor.bam",
                    f"sha256:partial_{i}_tumor",
                ),
                (
                    SampleTypeEnum.normal,
                    f"/demo/data/partial_{i}_normal.bam",
                    f"sha256:partial_{i}_normal",
                ),
            ]
        else:
            # Minimal: tumor only
            partial_types = [
                (
                    SampleTypeEnum.tumor,
                    f"/demo/data/minimal_{i}_tumor.bam",
                    f"sha256:minimal_{i}_tumor",
                ),
            ]

        samples = []
        for stype, fpath, checksum in partial_types:
            s = Sample(
                id=str(uuid4()),
                case_id=case.id,
                subject_id=subject.id,
                sample_type=stype,
                file_paths={stype.value: fpath},
                checksum=checksum,
                source_lab="Demo Lab",
                custody_metadata=_tag(),
            )
            db.add(s)
            samples.append(s)
        db.flush()

        variant_count = 2 if i == 1 else 1
        tumor_sample = samples[0]
        variants = []
        for j in range(variant_count):
            vdata = _DEMO_VARIANTS[j]
            v = Variant(
                id=str(uuid4()),
                case_id=case.id,
                sample_id=tumor_sample.id,
                genomic_coordinates=vdata["genomic_coordinates"],
                gene=vdata["gene"],
                transcript=vdata.get("transcript"),
                protein_change=vdata.get("protein_change"),
                caller_source=vdata["caller_source"],
                quality_metrics={**vdata["quality_metrics"], **_tag()},
                annotation_source=vdata["annotation_source"],
                review_status=ReviewStatusEnum.unreviewed,
            )
            db.add(v)
            variants.append(v)
        db.flush()

        candidates = []
        if i == 1 and variants:
            cdata = _DEMO_CANDIDATES[0]
            c = CandidateAntigen(
                id=str(uuid4()),
                case_id=case.id,
                variant_id=variants[0].id,
                peptide_metadata=cdata["peptide_metadata"],
                mhc_context=cdata["mhc_context"],
                prediction_scores=cdata["prediction_scores"],
                expression_evidence=cdata["expression_evidence"],
                structure_evidence=cdata["structure_evidence"],
                uncertainty_flags={**cdata["uncertainty_flags"], **_tag()},
                review_status=ReviewStatusEnum.unreviewed,
            )
            db.add(c)
            candidates.append(c)
            db.flush()

            report_data = build_candidate_review_report(case, candidates)
            report = Report(
                id=str(uuid4()),
                case_id=case.id,
                report_type=report_data["report_type"],
                generated_by="demo.create_synthetic_dataset",
                content_json={**report_data["content_json"], **_tag()},
                safety_label=RESEARCH_LABEL,
            )
            db.add(report)
            db.flush()

        log_action(
            db,
            case_id=case.id,
            actor="demo",
            action="demo.synthetic_case_created",
            inputs={"case_index": i},
            outputs={"case_id": case.id, "completeness": "partial" if i == 1 else "minimal"},
            details=_tag(),
        )
        db.commit()

        results.append(
            {
                "case_id": case.id,
                "subject_id": subject.id,
                "species": case.species.value,
                "subject_display_name": subject.anonymized_display_name,
                "sample_count": len(samples),
                "variant_count": len(variants),
                "candidate_count": len(candidates),
                "structure_job_id": None,
                "report_id": None,
                "completeness": "partial" if i == 1 else "minimal",
                "demo": True,
            }
        )

    return results


def reset_demo_data(db: Session) -> dict:
    """Clear all demo-created records (those tagged with foldagent_demo_created=True).

    Deletes in dependency order to avoid FK constraint violations.
    Returns counts of deleted records per model.
    """
    from backend.app.models import AuditLog

    def _is_demo(obj) -> bool:
        """Check if any JSON field carries the demo tag."""
        for attr in (
            "custody_metadata",
            "quality_metrics",
            "uncertainty_flags",
            "confidence_metrics",
            "content_json",
            "privacy_flags",
            "metadata_json",
        ):
            val = getattr(obj, attr, None)
            if isinstance(val, dict) and val.get(_DEMO_TAG):
                return True
        return False

    counts: dict[str, int] = {}

    # Collect demo case IDs via audit logs
    demo_case_ids: set[str] = set()
    for log in db.query(AuditLog).filter(AuditLog.actor == "demo").all():
        if log.case_id:
            demo_case_ids.add(log.case_id)

    if not demo_case_ids:
        return {"deleted": counts, "demo_case_ids_found": 0}

    # Delete in FK-safe order
    for model_cls, label in [
        (StructureJob, "structure_jobs"),
        (CandidateAntigen, "candidate_antigens"),
        (Variant, "variants"),
        (Sample, "samples"),
        (Report, "reports"),
        (Subject, "subjects"),
        (AuditLog, "audit_logs"),
        (Case, "cases"),
    ]:
        deleted = 0
        if model_cls is AuditLog:
            rows = db.query(AuditLog).filter(AuditLog.case_id.in_(demo_case_ids)).all()
        elif model_cls is Case:
            rows = db.query(Case).filter(Case.id.in_(demo_case_ids)).all()
        else:
            rows = db.query(model_cls).filter(model_cls.case_id.in_(demo_case_ids)).all()  # type: ignore[attr-defined]
        for row in rows:
            db.delete(row)
            deleted += 1
        if deleted:
            counts[label] = deleted
        db.flush()

    db.commit()
    return {"deleted": counts, "demo_case_ids_found": len(demo_case_ids)}
