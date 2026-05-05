"""Mock analysis data helpers for FoldAgent.

Seeds synthetic variants/candidates so the dashboard and reports have structured
research data before real bioinformatics wrappers land.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.models import CandidateAntigen, Case, ReviewStatusEnum, Variant


def ensure_mock_analysis_data(db: Session, case: Case) -> tuple[list[Variant], list[CandidateAntigen]]:
    variants = db.query(Variant).filter(Variant.case_id == case.id).order_by(Variant.created_at.asc()).all()
    candidates = (
        db.query(CandidateAntigen)
        .filter(CandidateAntigen.case_id == case.id)
        .order_by(CandidateAntigen.created_at.asc())
        .all()
    )
    if variants and candidates:
        return variants, candidates

    variant = Variant(
        id=str(uuid4()),
        case_id=case.id,
        genomic_coordinates="chr12:25398284 C>T",
        gene="KIT",
        transcript="NM_000222.3",
        protein_change="p.Asp816Val",
        caller_source="mock_mutect2",
        quality_metrics={"tumor_vaf": 0.42, "depth": 187, "mock": True},
        annotation_source="mock_vep",
        review_status=ReviewStatusEnum.unreviewed,
    )
    db.add(variant)
    db.flush()

    candidate = CandidateAntigen(
        id=str(uuid4()),
        case_id=case.id,
        variant_id=variant.id,
        peptide_metadata={"sequence": "SLYNTVATL", "length": 9},
        mhc_context="HLA-A*02:01 / demo MHC context",
        prediction_scores={"binding_rank": 0.4, "immunogenicity": 0.71, "mock": True},
        expression_evidence={"rna_support": "synthetic", "tpm": 18.2},
        structure_evidence={"alphafold_status": "mock_available"},
        uncertainty_flags={"synthetic": True, "professional_review_required": True},
        expert_review_notes=None,
        review_status=ReviewStatusEnum.unreviewed,
    )
    db.add(candidate)
    db.flush()

    return [variant], [candidate]
