"""Tests for Gene Therapy mode — functions and all 8 API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.gene_therapy import (
    AAV_SEROTYPES,
    EDITOR_SPECS,
    KNOWN_CAS_VARIANTS,
    PAM_DATABASE,
    CasVariant,
    EditorResult,
    GuideRNA,
    PAMAnalysis,
    TransgeneSafety,
    analyze_pam_specificity,
    design_guides,
    model_base_edit,
    model_capsid_receptor,
    model_prime_edit,
    predict_cas_structure,
    recommend_serotype,
    score_guide,
    score_transgene_safety,
)


# ---------------------------------------------------------------------------
# KNOWN_CAS_VARIANTS / predict_cas_structure
# ---------------------------------------------------------------------------


def test_known_cas_variants_has_12_entries() -> None:
    assert len(KNOWN_CAS_VARIANTS) >= 12


def test_known_cas_variants_contains_spcas9() -> None:
    assert "SpCas9" in KNOWN_CAS_VARIANTS


def test_known_cas_variants_contains_ascas12a() -> None:
    assert "AsCas12a" in KNOWN_CAS_VARIANTS


def test_known_cas_variants_contains_abe8e() -> None:
    assert "ABE8e" in KNOWN_CAS_VARIANTS


def test_known_cas_variants_contains_pe2() -> None:
    assert "PE2" in KNOWN_CAS_VARIANTS


def test_cas_variant_dataclass_fields() -> None:
    v = KNOWN_CAS_VARIANTS["SpCas9"]
    assert isinstance(v, CasVariant)
    assert v.cas_type == "Cas9"
    assert v.pam_sequence == "NGG"
    assert v.editing_type == "DSB"
    assert 0.0 < v.af_confidence <= 1.0


def test_cas_variant_spcas9_sequence_length() -> None:
    v = KNOWN_CAS_VARIANTS["SpCas9"]
    assert v.sequence_length > 1000


def test_predict_cas_structure_known_variant() -> None:
    result = predict_cas_structure("SpCas9")
    assert result["found"] is True
    assert result["cas_type"] == "Cas9"
    assert result["af_confidence"] > 0.0
    assert isinstance(result["domains"], list)
    assert len(result["domains"]) >= 2


def test_predict_cas_structure_unknown_variant() -> None:
    result = predict_cas_structure("FakeCas999")
    assert result["found"] is False
    assert result["af_confidence"] == 0.0
    assert result["domains"] == []


def test_predict_cas_structure_cas12_domains() -> None:
    result = predict_cas_structure("AsCas12a")
    assert result["found"] is True
    domain_names = [d["name"] for d in result["domains"]]
    assert any("RuvC" in n for n in domain_names)


def test_predict_cas_structure_cas13_domains() -> None:
    result = predict_cas_structure("Cas13a")
    assert result["found"] is True
    domain_names = [d["name"] for d in result["domains"]]
    assert any("HEPN" in n for n in domain_names)


# ---------------------------------------------------------------------------
# design_guides / score_guide
# ---------------------------------------------------------------------------


def test_design_guides_returns_correct_count() -> None:
    guides = design_guides("BRCA1", "SpCas9", 5)
    assert len(guides) == 5


def test_design_guides_returns_guide_rna_instances() -> None:
    guides = design_guides("TP53", "SpCas9", 3)
    assert all(isinstance(g, GuideRNA) for g in guides)


def test_design_guides_target_sequence_length_20() -> None:
    guides = design_guides("EGFR", "SpCas9", 4)
    for g in guides:
        assert len(g.target_sequence) == 20


def test_design_guides_gc_content_range() -> None:
    guides = design_guides("KRAS", "SpCas9", 10)
    for g in guides:
        assert 0.0 <= g.gc_content <= 1.0


def test_design_guides_pam_matches_cas_type() -> None:
    guides = design_guides("SMN1", "SaCas9", 3)
    for g in guides:
        assert g.pam == "NNGRRT"


def test_design_guides_strand_valid() -> None:
    guides = design_guides("DMD", "SpCas9", 5)
    for g in guides:
        assert g.strand in ("+", "-")


def test_design_guides_scores_in_range() -> None:
    guides = design_guides("MECP2", "ABE8e", 5)
    for g in guides:
        assert 0.0 <= g.off_target_score <= 1.0
        assert 0.0 <= g.efficiency_score <= 1.0
        assert 0.0 <= g.self_complementarity <= 1.0


def test_design_guides_deterministic() -> None:
    g1 = design_guides("CFTR", "SpCas9", 3)
    g2 = design_guides("CFTR", "SpCas9", 3)
    assert [g.target_sequence for g in g1] == [g.target_sequence for g in g2]


def test_score_guide_gc_content() -> None:
    result = score_guide("GCGCGCGCGCGCGCGCGCGC")
    assert result["gc_content"] == 1.0


def test_score_guide_at_rich_sequence() -> None:
    result = score_guide("ATATATATATATATATAT AT".replace(" ", ""))
    assert result["gc_content"] == 0.0


def test_score_guide_homopolymer_penalty() -> None:
    # AAAA run triggers penalty
    result = score_guide("ACGTAAAAGCTAGCTAGCTA")
    assert result["homopolymer_penalty"] > 0.0


def test_score_guide_no_homopolymer() -> None:
    result = score_guide("ACGTACGTACGTACGTACGT")
    assert result["homopolymer_penalty"] == 0.0


def test_score_guide_empty_sequence() -> None:
    result = score_guide("")
    assert result["gc_content"] == 0.0
    assert result["length"] == 0


def test_score_guide_gc_optimal_flag() -> None:
    result = score_guide("AATTCCGGAATTCCGGAATT")  # 50% GC
    assert result["gc_optimal"] is True


# ---------------------------------------------------------------------------
# analyze_pam_specificity
# ---------------------------------------------------------------------------


def test_pam_analysis_spcas9_canonical_pam() -> None:
    result = analyze_pam_specificity("SpCas9")
    assert isinstance(result, PAMAnalysis)
    assert result.canonical_pam == "NGG"


def test_pam_analysis_sacas9_long_pam() -> None:
    result = analyze_pam_specificity("SaCas9")
    assert result.canonical_pam == "NNGRRT"
    assert result.specificity_score > 0.80


def test_pam_analysis_cas12_pam() -> None:
    result = analyze_pam_specificity("AsCas12a")
    assert result.canonical_pam == "TTTV"


def test_pam_analysis_unknown_cas_falls_back() -> None:
    result = analyze_pam_specificity("UnknownCas")
    # Falls back to SpCas9 defaults
    assert result.canonical_pam == "NGG"


def test_pam_analysis_alternative_pams_list() -> None:
    result = analyze_pam_specificity("SpCas9")
    assert isinstance(result.alternative_pams, list)
    assert len(result.alternative_pams) >= 1


def test_pam_analysis_specificity_score_range() -> None:
    for cas_type in PAM_DATABASE:
        result = analyze_pam_specificity(cas_type)
        assert 0.0 <= result.specificity_score <= 1.0, f"{cas_type} score out of range"


# ---------------------------------------------------------------------------
# recommend_serotype / model_capsid_receptor
# ---------------------------------------------------------------------------


def test_recommend_serotype_liver_returns_aav8() -> None:
    serotypes = recommend_serotype("liver")
    names = [s.name for s in serotypes]
    assert "AAV8" in names


def test_recommend_serotype_cns_top_result() -> None:
    serotypes = recommend_serotype("CNS")
    # PHP.eB or AAV9 should be near top
    assert serotypes[0].name in {"AAV-PHP.eB", "AAV9", "AAVrh10"}


def test_recommend_serotype_sorted_descending() -> None:
    serotypes = recommend_serotype("muscle")
    scores = [s.transduction_efficiency.get("muscle", 0.0) for s in serotypes]
    assert scores == sorted(scores, reverse=True)


def test_recommend_serotype_unknown_tissue_returns_empty() -> None:
    serotypes = recommend_serotype("unknowntissueXYZ")
    assert serotypes == []


def test_model_capsid_receptor_known_serotype() -> None:
    result = model_capsid_receptor("AAV9")
    assert result["found"] is True
    assert "docking_score" in result
    assert "contact_residues" in result


def test_model_capsid_receptor_unknown_serotype() -> None:
    result = model_capsid_receptor("AAV999")
    assert result["found"] is False


# ---------------------------------------------------------------------------
# score_transgene_safety
# ---------------------------------------------------------------------------


def test_transgene_safety_returns_dataclass() -> None:
    result = score_transgene_safety("SMN1", "A" * 300)
    assert isinstance(result, TransgeneSafety)


def test_transgene_safety_gene_field_preserved() -> None:
    result = score_transgene_safety("CFTR", "ATGCATGC")
    assert result.gene == "CFTR"


def test_transgene_safety_integration_risk_levels() -> None:
    result = score_transgene_safety("AAV_TRANSGENE", "ATGCATGC")
    assert result.integration_risk in {"low", "moderate", "high"}


def test_transgene_safety_immunogenicity_cas9() -> None:
    result = score_transgene_safety("cas9", "ATGCATGC")
    assert result.immunogenicity_risk == "high"


def test_transgene_safety_expression_level_long_seq() -> None:
    result = score_transgene_safety("SMN1", "A" * 3000)
    assert result.expression_level_estimate == "high"


def test_transgene_safety_expression_level_short_seq() -> None:
    result = score_transgene_safety("SMN1", "A" * 100)
    assert result.expression_level_estimate == "low"


# ---------------------------------------------------------------------------
# model_base_edit / model_prime_edit
# ---------------------------------------------------------------------------


def test_model_base_edit_returns_editor_result() -> None:
    seq = "ACGTACGTACGTACGTACGT"
    result = model_base_edit(seq, 5, "ABE8e")
    assert isinstance(result, EditorResult)


def test_model_base_edit_editor_type_abe() -> None:
    result = model_base_edit("ACGTACGTACGTACGTACGT", 5, "ABE8e")
    assert result.editor_type == "ABE"


def test_model_base_edit_editor_type_cbe() -> None:
    result = model_base_edit("ACGTACGTACGTACGTACGT", 5, "BE4max")
    assert result.editor_type == "CBE"


def test_model_base_edit_efficiency_in_window_higher() -> None:
    seq = "ACGTACGTACGTACGTACGT"
    in_window = model_base_edit(seq, 6, "ABE8e")
    out_window = model_base_edit(seq, 18, "ABE8e")
    assert in_window.efficiency_estimate > out_window.efficiency_estimate


def test_model_base_edit_edit_window_tuple() -> None:
    result = model_base_edit("ACGTACGTACGTACGTACGT", 5, "ABE8e")
    assert isinstance(result.edit_window, tuple)
    assert len(result.edit_window) == 2


def test_model_base_edit_bystander_list() -> None:
    result = model_base_edit("ACGTACGTACGTACGTACGT", 5, "ABE8e")
    assert isinstance(result.bystander_edits, list)


def test_model_prime_edit_returns_dict() -> None:
    result = model_prime_edit("ACGTACGTACGTACGTACGT", "T")
    assert isinstance(result, dict)
    assert "efficiency_estimate" in result
    assert "pegRNA_length" in result


def test_model_prime_edit_efficiency_decreases_with_longer_edit() -> None:
    seq = "ACGTACGTACGTACGTACGT"
    short = model_prime_edit(seq, "A")
    long_edit = model_prime_edit(seq, "ACGTACGTACGT")
    assert short["efficiency_estimate"] >= long_edit["efficiency_estimate"]


def test_editor_specs_has_all_editors() -> None:
    for editor in ["ABE8e", "BE4max", "PE2", "PE3"]:
        assert editor in EDITOR_SPECS


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_cas_variants_list(client: TestClient) -> None:
    response = client.get("/gene-therapy/cas-variants")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 12
    assert "SpCas9" in data["variants"]
    assert "AsCas12a" in data["variants"]


def test_api_cas_variants_spcas9_fields(client: TestClient) -> None:
    response = client.get("/gene-therapy/cas-variants")
    assert response.status_code == 200
    v = response.json()["variants"]["SpCas9"]
    assert v["pam_sequence"] == "NGG"
    assert v["editing_type"] == "DSB"


def test_api_design_guides_default(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/design-guides",
        json={"target_gene": "BRCA1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "BRCA1"
    assert data["cas_type"] == "SpCas9"
    assert data["n_guides"] == 5
    assert len(data["guides"]) == 5


def test_api_design_guides_custom_params(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/design-guides",
        json={"target_gene": "CFTR", "cas_type": "SaCas9", "n_guides": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cas_type"] == "SaCas9"
    assert data["n_guides"] == 3
    for g in data["guides"]:
        assert g["pam"] == "NNGRRT"


def test_api_score_guide(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/score-guide",
        json={"guide_sequence": "ACGTACGTACGTACGTACGT"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "gc_content" in data
    assert "homopolymer_penalty" in data
    assert "self_comp_score" in data


def test_api_pam_analysis_spcas9(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/pam-analysis",
        json={"cas_type": "SpCas9"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cas_type"] == "SpCas9"
    assert data["canonical_pam"] == "NGG"
    assert isinstance(data["alternative_pams"], list)
    assert isinstance(data["specificity_score"], float)


def test_api_pam_analysis_sacas9(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/pam-analysis",
        json={"cas_type": "SaCas9"},
    )
    assert response.status_code == 200
    assert response.json()["canonical_pam"] == "NNGRRT"


def test_api_recommend_serotype_liver(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/recommend-serotype",
        json={"target_tissue": "liver"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_tissue"] == "liver"
    assert data["count"] >= 1
    names = [s["name"] for s in data["serotypes"]]
    assert "AAV8" in names


def test_api_recommend_serotype_unknown_tissue(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/recommend-serotype",
        json={"target_tissue": "unknownXYZ"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_api_transgene_safety(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/transgene-safety",
        json={"gene": "SMN1", "sequence": "ATGCATGCATGC"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gene"] == "SMN1"
    assert data["integration_risk"] in {"low", "moderate", "high"}
    assert data["immunogenicity_risk"] in {"low", "moderate", "high"}
    assert data["expression_level_estimate"] in {"low", "moderate", "high"}


def test_api_base_edit(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/base-edit",
        json={
            "target_sequence": "ACGTACGTACGTACGTACGT",
            "position": 5,
            "editor": "ABE8e",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["editor"] == "ABE8e"
    assert data["editor_type"] == "ABE"
    assert "efficiency_estimate" in data
    assert isinstance(data["edit_window"], list)
    assert len(data["edit_window"]) == 2


def test_api_base_edit_default_editor(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/base-edit",
        json={"target_sequence": "ACGTACGTACGTACGTACGT", "position": 6},
    )
    assert response.status_code == 200
    assert response.json()["editor"] == "ABE8e"


def test_api_prime_edit(client: TestClient) -> None:
    response = client.post(
        "/gene-therapy/prime-edit",
        json={
            "target_sequence": "ACGTACGTACGTACGTACGT",
            "desired_edit": "G",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "efficiency_estimate" in data
    assert "pegRNA_length" in data
    assert "spacer" in data
    assert data["target_sequence"] == "ACGTACGTACGTACGTACGT"
    assert data["desired_edit"] == "G"
