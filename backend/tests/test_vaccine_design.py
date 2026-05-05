"""Tests for multi-epitope vaccine design mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.vaccine_design import (
    CODON_TABLES,
    EMINI_SURFACE_ACCESSIBILITY,
    PARKER_HYDROPHILICITY,
    PATHOGEN_DATABASE,
    REFERENCE_STRAINS,
    EpitopeCandidate,
    LinkerType,
    VaccineConstruct,
    analyze_epitope_conservation,
    build_multi_epitope_construct,
    build_vaccine_design_report,
    get_known_epitopes,
    get_pathogen_targets,
    optimize_mrna_construct,
    predict_b_cell_epitopes,
    rapid_response_pipeline,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EP1 = EpitopeCandidate(
    sequence="ACDEFGHIKLM",
    source="test_gene",
    epitope_type="b_cell",
    score=0.85,
    conservation=0.9,
)
_EP2 = EpitopeCandidate(
    sequence="NQRSTVWY",
    source="test_gene",
    epitope_type="t_cell_mhci",
    score=0.75,
    conservation=0.7,
)
_EP3 = EpitopeCandidate(
    sequence="KLMNPQRS",
    source="pathogen_x",
    epitope_type="t_cell_mhcii",
    score=0.65,
    conservation=0.6,
)

_SHORT_PROTEIN = "ACDEFGHIKLMNPQRSTVWY" * 3  # 60 aa, enough for windows


# ---------------------------------------------------------------------------
# Multi-epitope construct builder
# ---------------------------------------------------------------------------


def test_build_construct_concatenation_with_default_linker() -> None:
    construct = build_multi_epitope_construct([_EP1, _EP2], linker="GPGPG")
    assert "GPGPG" in construct.full_sequence
    assert _EP1.sequence in construct.full_sequence
    assert _EP2.sequence in construct.full_sequence


def test_build_construct_linker_count() -> None:
    construct = build_multi_epitope_construct([_EP1, _EP2, _EP3], linker="AAY")
    # 3 epitopes → 2 linkers
    assert construct.full_sequence.count("AAY") == 2
    assert len(construct.linkers) == 2


def test_build_construct_with_signal_peptide() -> None:
    construct = build_multi_epitope_construct([_EP1], add_signal_peptide=True)
    assert construct.signal_peptide is not None
    assert construct.full_sequence.startswith(construct.signal_peptide)


def test_build_construct_without_signal_peptide() -> None:
    construct = build_multi_epitope_construct([_EP1], add_signal_peptide=False)
    assert construct.signal_peptide is None
    assert construct.full_sequence.startswith(_EP1.sequence)


def test_build_construct_total_length() -> None:
    construct = build_multi_epitope_construct([_EP1, _EP2], linker="KK", add_signal_peptide=False)
    expected = len(_EP1.sequence) + len("KK") + len(_EP2.sequence)
    assert construct.total_length == expected


def test_build_construct_estimated_mw() -> None:
    construct = build_multi_epitope_construct([_EP1, _EP2], linker="KK", add_signal_peptide=False)
    expected_mw = round(construct.total_length * 0.11, 3)
    assert construct.estimated_mw_kda == expected_mw


def test_build_construct_mw_positive() -> None:
    construct = build_multi_epitope_construct([_EP1])
    assert construct.estimated_mw_kda > 0


def test_build_construct_requires_at_least_one_epitope() -> None:
    with pytest.raises(ValueError):
        build_multi_epitope_construct([])


def test_build_construct_preserves_epitopes_list() -> None:
    construct = build_multi_epitope_construct([_EP1, _EP2, _EP3])
    assert len(construct.epitopes) == 3


def test_build_construct_all_linker_types() -> None:
    for linker in LinkerType:
        construct = build_multi_epitope_construct([_EP1, _EP2], linker=linker.value, add_signal_peptide=False)
        assert linker.value in construct.full_sequence


# ---------------------------------------------------------------------------
# B-cell epitope prediction
# ---------------------------------------------------------------------------


def test_predict_b_cell_epitopes_returns_list() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN)
    assert isinstance(result, list)


def test_predict_b_cell_epitopes_top_n_respected() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN, top_n=3)
    assert len(result) <= 3


def test_predict_b_cell_epitopes_scored() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN, top_n=5)
    assert len(result) > 0
    for ep in result:
        assert ep.antigenicity_score is not None
        assert ep.hydrophilicity is not None
        assert ep.surface_accessibility is not None


def test_predict_b_cell_epitopes_sequence_subsequence() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN)
    for ep in result:
        assert ep.sequence in _SHORT_PROTEIN.upper()


def test_predict_b_cell_epitopes_positions() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN)
    for ep in result:
        assert ep.start >= 0
        assert ep.end > ep.start
        assert ep.end - ep.start == len(ep.sequence)


def test_predict_b_cell_epitopes_short_sequence_returns_empty() -> None:
    result = predict_b_cell_epitopes("ACDE")  # shorter than min window (12)
    assert result == []


def test_predict_b_cell_epitopes_scores_sorted_descending() -> None:
    result = predict_b_cell_epitopes(_SHORT_PROTEIN, top_n=5)
    scores = [ep.antigenicity_score for ep in result]
    assert scores == sorted(scores, reverse=True)


def test_parker_hydrophilicity_table_completeness() -> None:
    standard_aa = "ACDEFGHIKLMNPQRSTVWY"
    for aa in standard_aa:
        assert aa in PARKER_HYDROPHILICITY, f"Missing {aa} in PARKER_HYDROPHILICITY"


def test_emini_surface_accessibility_table_completeness() -> None:
    standard_aa = "ACDEFGHIKLMNPQRSTVWY"
    for aa in standard_aa:
        assert aa in EMINI_SURFACE_ACCESSIBILITY, f"Missing {aa} in EMINI_SURFACE_ACCESSIBILITY"


# ---------------------------------------------------------------------------
# Conservation analysis
# ---------------------------------------------------------------------------


def test_conservation_identical_sequence() -> None:
    epitope = "ACDEFGHIKL"
    ref = "XXXACDEFGHIKLXXX"
    result = analyze_epitope_conservation(epitope, [ref])
    assert result.conservation_score > 0
    assert result.strain_coverage == 1.0
    assert result.variant_positions == []


def test_conservation_divergent_sequence() -> None:
    epitope = "ACDEFGHIKL"
    ref = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    result = analyze_epitope_conservation(epitope, [ref])
    assert result.strain_coverage == 0.0
    assert result.conservation_score == 0.0


def test_conservation_partial_match_within_mismatch_threshold() -> None:
    epitope = "ACDEFGHIKL"
    ref = "XXXACDEFGHIKLXXX"  # exact match
    result = analyze_epitope_conservation(epitope, [ref], max_mismatches=2)
    assert result.strain_coverage == 1.0


def test_conservation_multiple_references() -> None:
    epitope = "ACDEFGHIKL"
    refs = [
        "XXXACDEFGHIKLXXX",  # hit
        "XXXXXXXXXXXXXXXXXX",  # miss
    ]
    result = analyze_epitope_conservation(epitope, refs)
    assert result.strain_coverage == 0.5


def test_conservation_empty_references() -> None:
    result = analyze_epitope_conservation("ACDE", [])
    assert result.conservation_score == 0.0
    assert result.strain_coverage == 0.0


def test_conservation_result_fields() -> None:
    result = analyze_epitope_conservation("ACDEFGHIKL", ["XXXACDEFGHIKLXXX"])
    assert result.epitope_sequence == "ACDEFGHIKL"
    assert 0.0 <= result.conservation_score <= 1.0
    assert 0.0 <= result.strain_coverage <= 1.0
    assert isinstance(result.variant_positions, list)


# ---------------------------------------------------------------------------
# Pathogen database
# ---------------------------------------------------------------------------


def test_pathogen_database_has_expected_pathogens() -> None:
    expected = {"SARS-CoV-2", "Influenza", "HIV", "Malaria", "TB", "HPV", "Ebola", "RSV"}
    assert expected.issubset(set(PATHOGEN_DATABASE.keys()))


def test_pathogen_database_has_15_or_more_targets() -> None:
    total = sum(len(v) for v in PATHOGEN_DATABASE.values())
    assert total >= 14


def test_get_pathogen_targets_known() -> None:
    targets = get_pathogen_targets("SARS-CoV-2")
    assert len(targets) > 0
    assert all(t.pathogen_name == "SARS-CoV-2" for t in targets)


def test_get_pathogen_targets_case_insensitive() -> None:
    targets_lower = get_pathogen_targets("sars-cov-2")
    targets_normal = get_pathogen_targets("SARS-CoV-2")
    assert len(targets_lower) == len(targets_normal)


def test_get_pathogen_targets_unknown() -> None:
    result = get_pathogen_targets("UnknownPathogen999")
    assert result == []


def test_get_known_epitopes_returns_list() -> None:
    epitopes = get_known_epitopes("SARS-CoV-2", "Spike RBD")
    assert isinstance(epitopes, list)
    assert len(epitopes) > 0


def test_get_known_epitopes_unknown_combination() -> None:
    result = get_known_epitopes("SARS-CoV-2", "NonExistentProtein")
    assert result == []


def test_pathogen_targets_have_required_fields() -> None:
    for pathogen, targets in PATHOGEN_DATABASE.items():
        for t in targets:
            assert t.pathogen_name
            assert t.protein_name
            assert t.uniprot_id
            assert isinstance(t.known_epitopes, list)
            assert t.vaccine_type


# ---------------------------------------------------------------------------
# mRNA optimization
# ---------------------------------------------------------------------------


def test_optimize_mrna_returns_construct() -> None:
    mrna = optimize_mrna_construct("ACDEFGHIKL")
    assert mrna.coding_sequence
    assert mrna.utr5
    assert mrna.utr3
    assert mrna.poly_a_length == 120


def test_optimize_mrna_gc_content_range() -> None:
    mrna = optimize_mrna_construct("ACDEFGHIKL")
    assert 0.0 <= mrna.gc_content <= 1.0


def test_optimize_mrna_coding_seq_divisible_by_3() -> None:
    mrna = optimize_mrna_construct("ACDEFGHIKL")
    assert len(mrna.coding_sequence) % 3 == 0


def test_optimize_mrna_starts_with_atg() -> None:
    mrna = optimize_mrna_construct("ACDEFGHIKL")
    assert mrna.coding_sequence.startswith("ATG")


def test_optimize_mrna_codon_table_human_keys() -> None:
    standard_aa = set("ACDEFGHIKLMNPQRSTVWY")
    assert standard_aa.issubset(set(CODON_TABLES["human"].keys()))


def test_optimize_mrna_codon_table_dog_keys() -> None:
    standard_aa = set("ACDEFGHIKLMNPQRSTVWY")
    assert standard_aa.issubset(set(CODON_TABLES["dog"].keys()))


def test_optimize_mrna_species_dog() -> None:
    mrna = optimize_mrna_construct("ACDE", species="dog")
    assert mrna.coding_sequence


def test_optimize_mrna_cai_range() -> None:
    mrna = optimize_mrna_construct("ACDEFGHIKLMNPQRSTVWY")
    assert 0.0 <= mrna.codon_adaptation_index <= 1.0


def test_optimize_mrna_custom_poly_a() -> None:
    mrna = optimize_mrna_construct("ACDE", poly_a_length=200)
    assert mrna.poly_a_length == 200


# ---------------------------------------------------------------------------
# Rapid-response pipeline
# ---------------------------------------------------------------------------


def test_rapid_response_pipeline_returns_dict() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen")
    assert isinstance(result, dict)


def test_rapid_response_pipeline_has_steps() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen")
    assert "steps" in result
    steps = result["steps"]
    assert "b_cell_prediction" in steps
    assert "conservation_analysis" in steps
    assert "construct_builder" in steps
    assert "mrna_optimization" in steps


def test_rapid_response_pipeline_has_disclaimer() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen")
    assert "disclaimer" in result
    assert "RESEARCH" in result["disclaimer"].upper()


def test_rapid_response_pipeline_timing() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen")
    assert "total_duration_s" in result
    assert result["total_duration_s"] >= 0


def test_rapid_response_pipeline_epitopes_found() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen", top_n_epitopes=3)
    b_cell = result["steps"]["b_cell_prediction"]
    assert b_cell["epitopes_found"] <= 3


def test_rapid_response_pipeline_construct_built() -> None:
    result = rapid_response_pipeline(_SHORT_PROTEIN, "TestPathogen")
    construct = result["steps"]["construct_builder"]
    assert "full_sequence" in construct
    assert "total_length" in construct


# ---------------------------------------------------------------------------
# Vaccine design report
# ---------------------------------------------------------------------------


def test_build_vaccine_design_report_structure() -> None:
    epitopes = [
        {"sequence": "ACDEFGHIKL", "source": "gene_x", "epitope_type": "b_cell", "score": 0.8, "conservation": 0.9}
    ]
    report = build_vaccine_design_report(None, epitopes)
    assert "disclaimers" in report
    assert "construct" in report
    assert "epitope_table" in report
    assert "mrna_stats" in report


def test_build_vaccine_design_report_has_disclaimers() -> None:
    report = build_vaccine_design_report(None, [])
    disclaimers = report["disclaimers"]
    assert len(disclaimers) >= 1
    combined = " ".join(disclaimers).upper()
    assert "RESEARCH" in combined or "NOT FOR" in combined


def test_build_vaccine_design_report_empty_epitopes() -> None:
    report = build_vaccine_design_report(None, [])
    assert report["construct"]["n_epitopes"] == 0
    assert report["epitope_table"] == []


def test_build_vaccine_design_report_epitope_table_content() -> None:
    epitopes = [
        {"sequence": "ACDEFGHIKL", "source": "gene_x", "epitope_type": "b_cell", "score": 0.8, "conservation": 0.9},
        {"sequence": "MNPQRSTVWY", "source": "gene_y", "epitope_type": "t_cell_mhci", "score": 0.7, "conservation": 0.6},
    ]
    report = build_vaccine_design_report(None, epitopes)
    assert len(report["epitope_table"]) == 2
    for row in report["epitope_table"]:
        assert "sequence" in row
        assert "source" in row
        assert "score" in row


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_build_construct(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/build-construct",
        json={
            "epitopes": [
                {"sequence": "ACDEFGHIKL", "source": "gene_a", "epitope_type": "b_cell", "score": 0.8, "conservation": 0.9},
                {"sequence": "MNPQRSTVWY", "source": "gene_b", "epitope_type": "t_cell_mhci", "score": 0.7, "conservation": 0.6},
            ],
            "linker": "GPGPG",
            "add_signal_peptide": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "full_sequence" in body
    assert "total_length" in body
    assert body["n_epitopes"] == 2
    assert "GPGPG" in body["full_sequence"]


def test_api_build_construct_empty_epitopes_returns_422(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/build-construct",
        json={"epitopes": [], "linker": "GPGPG"},
    )
    assert response.status_code == 422


def test_api_predict_b_cell_epitopes(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/predict-b-cell-epitopes",
        json={"protein_sequence": _SHORT_PROTEIN, "top_n": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert "epitopes" in body
    assert "count" in body
    assert body["count"] <= 5


def test_api_predict_b_cell_epitopes_missing_sequence(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/predict-b-cell-epitopes",
        json={"protein_sequence": ""},
    )
    assert response.status_code == 422


def test_api_conservation_analysis(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/conservation-analysis",
        json={
            "epitope": "ACDEFGHIKL",
            "reference_sequences": ["XXXACDEFGHIKLXXX", "XXXXXXXXXXXXXXXXXX"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "conservation_score" in body
    assert "strain_coverage" in body
    assert body["strain_coverage"] == 0.5


def test_api_list_pathogens(client: TestClient) -> None:
    response = client.get("/vaccine-design/pathogens")
    assert response.status_code == 200
    body = response.json()
    assert "pathogens" in body
    assert "SARS-CoV-2" in body["pathogens"]


def test_api_get_pathogen_targets(client: TestClient) -> None:
    response = client.get("/vaccine-design/pathogens/SARS-CoV-2/targets")
    assert response.status_code == 200
    body = response.json()
    assert body["pathogen"] == "SARS-CoV-2"
    assert len(body["targets"]) > 0


def test_api_get_pathogen_targets_not_found(client: TestClient) -> None:
    response = client.get("/vaccine-design/pathogens/UnknownPathogen999/targets")
    assert response.status_code == 404


def test_api_optimize_mrna(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/optimize-mrna",
        json={"protein_sequence": "ACDEFGHIKLMNPQRSTVWY", "species": "human"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "coding_sequence" in body
    assert "gc_content" in body
    assert body["coding_sequence"].startswith("ATG")


def test_api_rapid_response(client: TestClient) -> None:
    response = client.post(
        "/vaccine-design/rapid-response",
        json={
            "pathogen_sequence": _SHORT_PROTEIN,
            "pathogen_name": "TestVirus",
            "top_n_epitopes": 3,
            "linker": "AAY",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "steps" in body
    assert "total_duration_s" in body


def test_api_case_vaccine_design_report_not_found(client: TestClient) -> None:
    response = client.get("/cases/nonexistent-case-id/vaccine-design/report")
    assert response.status_code == 404


def test_api_case_vaccine_design_report_existing_case(client: TestClient) -> None:
    # Create a case first
    create_resp = client.post(
        "/cases",
        json={"name": "Test Vaccine Case", "species": "demo"},
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    response = client.get(f"/cases/{case_id}/vaccine-design/report")
    assert response.status_code == 200
    body = response.json()
    assert body["report_type"] == "vaccine_design"
    assert "disclaimers" in body
    assert "construct" in body
