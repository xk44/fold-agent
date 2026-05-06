"""Safe report generation helpers for FoldAgent."""

from __future__ import annotations

from backend.app.models import CandidateAntigen, Case

RESEARCH_LABEL = "Research candidate only — not administerable"
COMMON_WARNING = (
    "Not medical advice. Not veterinary advice. Not treatment instructions. "
    "Professional oversight required."
)


def _candidate_row(candidate: CandidateAntigen) -> dict:
    variant = candidate.variant
    prediction_scores = candidate.prediction_scores or {}
    uncertainty_flags = candidate.uncertainty_flags or {}
    return {
        "gene": variant.gene if variant else None,
        "protein_change": variant.protein_change if variant else None,
        "binding_rank": prediction_scores.get("binding_rank"),
        "immunogenicity": prediction_scores.get("immunogenicity"),
        "mhc_context": candidate.mhc_context,
        "uncertainty_flags": uncertainty_flags,
    }


def build_candidate_review_report(case: Case, candidates: list[CandidateAntigen]) -> dict:
    top_candidate = candidates[0] if candidates else None
    top_candidate_gene = None
    structure_status = None
    structure_backend = None
    structure_model_cif = None
    structure_source_url = None
    structure_output_format = None
    ranking_score = None
    ptm = None
    iptm = None
    chain_pair_iptm = None
    if top_candidate and top_candidate.variant is not None:
        top_candidate_gene = top_candidate.variant.gene
    if top_candidate and top_candidate.structure_evidence:
        structure_status = top_candidate.structure_evidence.get("alphafold_status")
        structure_backend = top_candidate.structure_evidence.get("backend")
        structure_model_cif = top_candidate.structure_evidence.get("model_cif")
        structure_source_url = top_candidate.structure_evidence.get("source_url")
        structure_output_format = top_candidate.structure_evidence.get("output_format")
        ranking_score = top_candidate.structure_evidence.get("ranking_score")
        ptm = top_candidate.structure_evidence.get("ptm")
        iptm = top_candidate.structure_evidence.get("iptm")
        chain_pair_iptm = top_candidate.structure_evidence.get("chain_pair_iptm")

    structure_summary_parts = [part for part in [structure_backend, structure_status] if part]
    if ranking_score is not None:
        structure_summary_parts.append(f"ranking_score={ranking_score}")
    if ptm is not None:
        structure_summary_parts.append(f"ptm={ptm}")
    if iptm is not None:
        structure_summary_parts.append(f"iptm={iptm}")
    structure_summary = (
        ", ".join(structure_summary_parts) if structure_summary_parts else "not available"
    )
    candidate_table = [_candidate_row(candidate) for candidate in candidates]
    tool_versions = {
        "alignment": "mock_alignment v0.1.0-mock",
        "variant_calling": "mock_variant_calling v0.1.0-mock",
        "annotation": "mock_annotation v0.1.0-mock",
        "candidate_prioritization": "mock_candidate_prioritization v0.1.0-mock",
        "alphafold": structure_backend or "mock v0.1.0-mock",
    }
    missing_data_checklist = [
        "real sequencing data",
        "real variant calling",
        "real annotation",
        "real MHC/HLA/DLA typing",
        "RNA-seq expression validation",
        "professional oncologist review",
        "professional immunologist review",
        "IRB or veterinary ethics review",
    ]
    safety_labels = [
        RESEARCH_LABEL,
        "Structure prediction only — not clinical validation",
        "No dosing, injection, formulation, or manufacturing instructions",
        "Professional review required before action",
    ]

    content_text = (
        f"Candidate review report for case {case.id}. "
        f"Species: {case.species.value}. "
        f"Diagnosis summary: {case.diagnosis_summary or 'not provided'}. "
        f"Candidate count: {len(candidates)}. "
        f"Top candidate: {top_candidate_gene or 'not available'}. "
        f"Structure evidence: {structure_summary}. "
        "This report summarizes research-candidate information for expert review only. "
        f"{COMMON_WARNING}"
    )
    return {
        "report_type": "candidate_review",
        "content_text": content_text,
        "content_json": {
            "content_text": content_text,
            "summary": case.diagnosis_summary,
            "species": case.species.value,
            "candidate_count": len(candidates),
            "candidate_table": candidate_table,
            "missing_data_checklist": missing_data_checklist,
            "tool_versions": tool_versions,
            "safety_labels": safety_labels,
            "review_status": "unreviewed",
            "top_candidate_gene": top_candidate_gene,
            "structure_status": structure_status,
            "structure_backend": structure_backend,
            "model_cif": structure_model_cif,
            "source_url": structure_source_url,
            "output_format": structure_output_format,
            "ranking_score": ranking_score,
            "ptm": ptm,
            "iptm": iptm,
            "chain_pair_iptm": chain_pair_iptm,
            "warnings": [COMMON_WARNING, RESEARCH_LABEL],
        },
    }


def build_ethics_package_report(case: Case) -> dict:
    species_label = case.species.value
    consent_templates = {
        "owner_or_subject_consent": f"{species_label.title()} consent template required before any research coordination handoff.",
        "data_use_consent": "Explicit consent required for genomic data processing, sharing, and retention.",
    }
    privacy_notices = [
        "Genomic data may carry identifying risk and should be handled with least-privilege access.",
        "Local-first storage is preferred; external transfer requires explicit approval and logging.",
    ]
    risk_benefit_summary = {
        "benefits": [
            "Research coordination artifact for expert review",
            "Clear audit trail of evidence and uncertainty",
        ],
        "risks": [
            "Misinterpretation of research outputs as treatment guidance",
            "Privacy exposure if genomic data is transferred without controls",
        ],
    }
    professional_oversight_checklist = [
        "licensed professional assigned",
        "consent reviewed",
        "jurisdiction checked",
        "research-only labeling confirmed",
    ]
    jurisdiction_warning = "User must consult local regulations, IRB/ethics rules, and professional licensing requirements before any real-world action."
    content_text = (
        f"Ethics package draft for case {case.id}. "
        f"Species: {case.species.value}. "
        "Professional oversight, consent tracking, privacy review, and jurisdiction-specific review are required. "
        f"{COMMON_WARNING}"
    )
    return {
        "report_type": "ethics_package",
        "content_text": content_text,
        "content_json": {
            "content_text": content_text,
            "species": case.species.value,
            "requirements": [
                "professional oversight",
                "consent review",
                "jurisdiction check",
            ],
            "consent_templates": consent_templates,
            "privacy_notices": privacy_notices,
            "risk_benefit_summary": risk_benefit_summary,
            "professional_oversight_checklist": professional_oversight_checklist,
            "jurisdiction_warning": jurisdiction_warning,
            "warnings": [COMMON_WARNING, RESEARCH_LABEL],
        },
    }
