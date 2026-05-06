import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.report_preview import (
    format_candidate_review_operator_summary,
    format_ethics_package_operator_summary,
    format_report_preview,
    summarize_candidate_review_operator_state,
    summarize_ethics_package_operator_state,
)

# ---------------------------------------------------------------------------
# Candidate-review operator summary tests (TDD: written first)
# ---------------------------------------------------------------------------


def test_summarize_candidate_review_operator_state_extracts_key_metrics() -> None:
    summary = summarize_candidate_review_operator_state(
        {
            "report_type": "candidate_review",
            "case_id": "case-789",
            "content_json": {
                "summary": "demo summary",
                "top_candidate_gene": "TP53",
                "candidate_count": 3,
                "species": "human",
                "candidate_table": [
                    {
                        "gene": "TP53",
                        "protein_change": "p.R175H",
                        "binding_rank": 0.4,
                        "immunogenicity": 0.71,
                        "mhc_context": "HLA-A*02:01",
                    },
                    {
                        "gene": "KRAS",
                        "protein_change": "p.G12D",
                        "binding_rank": 0.55,
                        "immunogenicity": 0.6,
                        "mhc_context": "HLA-A*02:01",
                    },
                ],
                "structure_backend": "alphafold3_local",
                "structure_status": "completed",
                "ranking_score": 0.91,
                "ptm": 0.72,
                "iptm": 0.88,
                "missing_data_checklist": [
                    "RNA-seq expression validation",
                    "professional oncologist review",
                ],
                "tool_versions": {"alphafold": "alphafold3_local"},
                "safety_labels": ["Research candidate only — not administerable"],
                "review_status": "unreviewed",
            },
        },
        case_detail={
            "species": "human",
            "consent_status": "pending",
            "review_status": "unreviewed",
        },
    )

    assert summary["report_type"] == "candidate_review"
    assert summary["candidate_count"] == 3
    assert summary["top_candidate_gene"] == "TP53"
    assert summary["review_status"] == "unreviewed"
    assert summary["structure_status"] == "completed"
    assert summary["structure_backend"] == "alphafold3_local"
    assert summary["safety_label_count"] == 1
    assert summary["missing_data_count"] == 2
    assert summary["has_structure_evidence"] is True
    assert summary["needs_review_attention"] is True
    assert summary["needs_structure_attention"] is False
    assert summary["species_matches_case"] is True
    assert summary["report_species"] == "human"
    assert summary["case_species"] == "human"


def test_summarize_candidate_review_operator_state_flags_structure_attention() -> None:
    summary = summarize_candidate_review_operator_state(
        {
            "report_type": "candidate_review",
            "case_id": "case-999",
            "content_json": {
                "summary": "no structure yet",
                "top_candidate_gene": "BRAF",
                "candidate_count": 1,
                "species": "canine",
                "structure_backend": None,
                "structure_status": None,
                "ranking_score": None,
                "ptm": None,
                "iptm": None,
                "missing_data_checklist": [],
                "safety_labels": ["Research candidate only — not administerable"],
                "review_status": "expert_accepted_for_further_research",
            },
        },
        case_detail={
            "species": "canine",
            "consent_status": "received",
            "review_status": "approved",
        },
    )

    assert summary["has_structure_evidence"] is False
    assert summary["needs_structure_attention"] is True
    assert summary["needs_review_attention"] is False
    assert summary["species_matches_case"] is True
    assert summary["missing_data_count"] == 0
    assert summary["structure_status"] == "n/a"
    assert summary["structure_backend"] == "n/a"


def test_summarize_candidate_review_operator_state_flags_species_mismatch() -> None:
    summary = summarize_candidate_review_operator_state(
        {
            "report_type": "candidate_review",
            "case_id": "case-species-mismatch",
            "content_json": {
                "summary": "species mismatch demo",
                "top_candidate_gene": "TP53",
                "candidate_count": 2,
                "species": "human",
                "structure_backend": "alphafold_db",
                "structure_status": "completed",
                "ranking_score": 0.8,
                "ptm": 0.65,
                "iptm": 0.7,
                "missing_data_checklist": ["real sequencing data"],
                "safety_labels": [
                    "Research candidate only — not administerable",
                    "No dosing instructions",
                ],
                "review_status": "unreviewed",
            },
        },
        case_detail={
            "species": "canine",
            "consent_status": "pending",
            "review_status": "unreviewed",
        },
    )

    assert summary["species_matches_case"] is False
    assert summary["report_species"] == "human"
    assert summary["case_species"] == "canine"
    assert summary["safety_label_count"] == 2
    assert summary["needs_review_attention"] is True


def test_summarize_candidate_review_operator_state_handles_empty_payload() -> None:
    summary = summarize_candidate_review_operator_state({}, case_detail={})

    assert summary["report_type"] == "report"
    assert summary["candidate_count"] == 0
    assert summary["top_candidate_gene"] == "n/a"
    assert summary["review_status"] == "unknown"
    assert summary["structure_status"] == "n/a"
    assert summary["has_structure_evidence"] is False
    assert summary["needs_structure_attention"] is True
    assert summary["needs_review_attention"] is True
    assert summary["safety_label_count"] == 0
    assert summary["missing_data_count"] == 0


def test_format_candidate_review_operator_summary_produces_readable_text() -> None:
    summary_dict = {
        "report_type": "candidate_review",
        "candidate_count": 3,
        "top_candidate_gene": "TP53",
        "review_status": "unreviewed",
        "structure_status": "completed",
        "structure_backend": "alphafold3_local",
        "safety_label_count": 1,
        "missing_data_count": 2,
        "has_structure_evidence": True,
        "needs_review_attention": True,
        "needs_structure_attention": False,
        "species_matches_case": True,
        "report_species": "human",
        "case_species": "human",
        "ranking_score": 0.91,
        "ptm": 0.72,
        "iptm": 0.88,
    }
    text = format_candidate_review_operator_summary(summary_dict)

    assert "Candidate Review Operator Summary" in text
    assert "candidates=3" in text
    assert "top_gene=TP53" in text
    assert "review_status=unreviewed" in text
    assert "structure=completed" in text
    assert "warnings" in text.lower() or "attention" in text.lower() or "review" in text.lower()


def test_format_candidate_review_operator_summary_handles_minimal() -> None:
    summary_dict = {
        "report_type": "candidate_review",
        "candidate_count": 0,
        "top_candidate_gene": "n/a",
        "review_status": "unknown",
        "structure_status": "n/a",
        "structure_backend": "n/a",
        "safety_label_count": 0,
        "missing_data_count": 0,
        "has_structure_evidence": False,
        "needs_review_attention": True,
        "needs_structure_attention": True,
        "species_matches_case": True,
        "report_species": "n/a",
        "case_species": "n/a",
        "ranking_score": "n/a",
        "ptm": "n/a",
        "iptm": "n/a",
    }
    text = format_candidate_review_operator_summary(summary_dict)

    assert "candidates=0" in text
    assert "top_gene=n/a" in text


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_format_candidate_review_preview_surfaces_sections() -> None:
    preview = format_report_preview(
        {
            "report_type": "candidate_review",
            "case_id": "case-123",
            "content_json": {
                "summary": "demo summary",
                "top_candidate_gene": "TP53",
                "candidate_count": 2,
                "candidate_table": [
                    {
                        "gene": "TP53",
                        "protein_change": "p.R175H",
                        "binding_rank": 0.4,
                        "immunogenicity": 0.71,
                        "mhc_context": "HLA-A*02:01",
                    }
                ],
                "structure_backend": "alphafold3_local",
                "structure_status": "completed",
                "ranking_score": 0.91,
                "ptm": 0.72,
                "iptm": 0.88,
                "missing_data_checklist": ["RNA-seq expression validation"],
                "tool_versions": {"alphafold": "alphafold3_local"},
                "safety_labels": ["Research candidate only — not administerable"],
                "review_status": "unreviewed",
            },
        }
    )

    assert "Candidate Review" in preview
    assert "Top candidate gene: TP53" in preview
    assert "Structure evidence" in preview
    assert "ranking_score=0.91" in preview
    assert "Missing data checklist" in preview
    assert "Tool versions" in preview


def test_format_ethics_package_preview_surfaces_sections() -> None:
    preview = format_report_preview(
        {
            "report_type": "ethics_package",
            "case_id": "case-456",
            "content_json": {
                "species": "dog",
                "consent_templates": {"owner_or_subject_consent": "Owner consent required"},
                "privacy_notices": ["Local-first storage preferred"],
                "risk_benefit_summary": {
                    "risks": ["privacy exposure"],
                    "benefits": ["clear audit trail"],
                },
                "professional_oversight_checklist": ["licensed professional assigned"],
                "jurisdiction_warning": "Consult local regulations",
            },
        }
    )

    assert "Ethics Package" in preview
    assert "Consent templates" in preview
    assert "Privacy notices" in preview
    assert "Risk and benefit summary" in preview
    assert "Jurisdiction warning" in preview


def test_summarize_ethics_package_operator_state_flags_governance_attention() -> None:
    summary = summarize_ethics_package_operator_state(
        {
            "report_type": "ethics_package",
            "case_id": "case-456",
            "content_json": {
                "species": "dog",
                "consent_templates": {"owner_or_subject_consent": "Owner consent required"},
                "privacy_notices": ["Local-first storage preferred"],
                "risk_benefit_summary": {
                    "risks": ["privacy exposure"],
                    "benefits": ["clear audit trail"],
                },
                "professional_oversight_checklist": [
                    "licensed professional assigned",
                    "ethics review pending",
                ],
                "jurisdiction_warning": "Consult local regulations",
            },
        },
        case_detail={
            "consent_status": "pending",
            "review_status": "unreviewed",
            "species": "dog",
        },
    )

    assert summary["consent_status"] == "pending"
    assert summary["review_status"] == "unreviewed"
    assert summary["consent_template_count"] == 1
    assert summary["oversight_item_count"] == 2
    assert summary["needs_consent_attention"] is True
    assert summary["needs_review_attention"] is True
    assert summary["species_matches_case"] is True


def test_format_ethics_package_operator_summary_produces_readable_text() -> None:
    text = format_ethics_package_operator_summary(
        {
            "report_type": "ethics_package",
            "report_species": "dog",
            "case_species": "dog",
            "species_matches_case": True,
            "consent_status": "pending",
            "review_status": "unreviewed",
            "consent_template_count": 1,
            "privacy_notice_count": 2,
            "risk_count": 3,
            "benefit_count": 1,
            "oversight_item_count": 4,
            "needs_consent_attention": True,
            "needs_review_attention": True,
            "jurisdiction_warning": "Consult local veterinary regulations.",
        }
    )

    assert "Ethics Package Operator Summary" in text
    assert "consent_status=pending" in text
    assert "review_status=unreviewed" in text
    assert "species=dog" in text
    assert "consent_templates=1" in text
    assert "privacy_notices=2" in text
    assert "risks=3" in text
    assert "benefits=1" in text
    assert "oversight_items=4" in text
    assert "Jurisdiction: Consult local veterinary regulations." in text
    assert "Consent status needs attention" in text
    assert "Review status needs attention" in text


def test_format_ethics_package_operator_summary_handles_minimal() -> None:
    text = format_ethics_package_operator_summary({})

    assert "Ethics Package Operator Summary" in text
    assert "consent_status=unknown" in text
    assert "review_status=unknown" in text
    assert "species=n/a" in text
    assert "consent_templates=0" in text
    assert "privacy_notices=0" in text


def test_format_ethics_package_operator_summary_flags_species_mismatch() -> None:
    text = format_ethics_package_operator_summary(
        {
            "report_species": "human",
            "case_species": "canine",
            "species_matches_case": False,
            "consent_status": "received",
            "review_status": "approved",
            "needs_consent_attention": False,
            "needs_review_attention": False,
            "jurisdiction_warning": "n/a",
        }
    )

    assert "report species (human) does not match case species (canine)" in text
