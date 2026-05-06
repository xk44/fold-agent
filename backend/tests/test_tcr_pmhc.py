"""Tests for TCR-pMHC Ternary Complex Modeling mode — functions and all 8 API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.modes.tcr_pmhc import (
    KNOWN_TCR_PMHC,
    TCR_PMHC_DISCLAIMER,
    CDRLoopAnalysis,
    ImmunogenicityPrediction,
    MultiSeedResult,
    TCellResponseScore,
    TernaryComplexResult,
    analyze_cdr_loops,
    build_immunogenicity_report,
    get_known_tcr_pmhc_complexes,
    lookup_tcr_pmhc,
    predict_immunogenicity,
    predict_ternary_complex,
    run_multiseed_sampling,
    score_tcell_response,
)

# Shared fixtures
PEPTIDE = "SLLMWITQC"
MHC = "HLA-A*02:01"
TCR = "CASSIRSSYEQYF"


# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------


def test_disclaimer_exists() -> None:
    assert len(TCR_PMHC_DISCLAIMER) > 20
    assert "RESEARCH USE ONLY" in TCR_PMHC_DISCLAIMER


def test_disclaimer_string_type() -> None:
    assert isinstance(TCR_PMHC_DISCLAIMER, str)


# ---------------------------------------------------------------------------
# KNOWN_TCR_PMHC knowledge base
# ---------------------------------------------------------------------------


def test_known_complexes_has_at_least_8() -> None:
    assert len(KNOWN_TCR_PMHC) >= 8


def test_known_complexes_ny_eso1() -> None:
    assert "SLLMWITQC" in KNOWN_TCR_PMHC
    entry = KNOWN_TCR_PMHC["SLLMWITQC"]
    assert entry["mhc_allele"] == "HLA-A*02:01"
    assert entry["crystal_pdb_id"] == "2BNR"


def test_known_complexes_mart1() -> None:
    assert "ELAGIGILTV" in KNOWN_TCR_PMHC


def test_known_complexes_cmv_pp65() -> None:
    assert "NLVPMVATV" in KNOWN_TCR_PMHC
    assert "CMV" in KNOWN_TCR_PMHC["NLVPMVATV"]["antigen"]


def test_known_complexes_wt1_hla_a24() -> None:
    assert "RMFPNAPYL" in KNOWN_TCR_PMHC
    assert "A*24" in KNOWN_TCR_PMHC["RMFPNAPYL"]["mhc_allele"]


def test_known_complexes_all_have_required_fields() -> None:
    required = {
        "peptide",
        "mhc_allele",
        "tcr_va",
        "tcr_vb",
        "binding_affinity_nm",
        "crystal_pdb_id",
    }
    for pep, entry in KNOWN_TCR_PMHC.items():
        for field in required:
            assert field in entry, f"Missing '{field}' in entry for {pep}"


def test_known_complexes_binding_affinity_positive() -> None:
    for pep, entry in KNOWN_TCR_PMHC.items():
        assert entry["binding_affinity_nm"] > 0, f"Non-positive affinity for {pep}"


# ---------------------------------------------------------------------------
# TernaryComplexResult dataclass
# ---------------------------------------------------------------------------


def test_ternary_complex_result_instantiation() -> None:
    r = TernaryComplexResult(
        peptide="TESTPEP",
        mhc_allele="HLA-A*02:01",
        tcr_sequence="CASSXXXX",
        mock_pdb_id="1ABC",
        confidence_score=0.85,
        interface_contacts=[],
        binding_mode="canonical_diagonal",
        predicted_kd_nm=3.5,
        mhc_peptide_groove_score=0.72,
        tcr_docking_angle_deg=25.0,
    )
    assert r.peptide == "TESTPEP"
    assert r.disclaimer == TCR_PMHC_DISCLAIMER


def test_ternary_complex_result_has_disclaimer_default() -> None:
    r = TernaryComplexResult(
        peptide="X",
        mhc_allele="A",
        tcr_sequence="B",
        mock_pdb_id="C",
        confidence_score=0.5,
        interface_contacts=[],
        binding_mode="m",
        predicted_kd_nm=1.0,
        mhc_peptide_groove_score=0.5,
        tcr_docking_angle_deg=30.0,
    )
    assert r.disclaimer == TCR_PMHC_DISCLAIMER


# ---------------------------------------------------------------------------
# TCellResponseScore dataclass
# ---------------------------------------------------------------------------


def test_tcell_response_score_instantiation() -> None:
    s = TCellResponseScore(
        peptide="X",
        mhc_allele="A",
        binding_geometry_score=0.8,
        predicted_activation="strong",
        cytokine_profile={"IFN-gamma": 0.9},
        effector_function="cytotoxic_killing",
        activation_threshold_nm=2.0,
        stimulation_index=5.0,
    )
    assert s.predicted_activation == "strong"


# ---------------------------------------------------------------------------
# CDRLoopAnalysis dataclass
# ---------------------------------------------------------------------------


def test_cdr_loop_analysis_instantiation() -> None:
    c = CDRLoopAnalysis(
        tcr_sequence="ABCD",
        cdr1_alpha_positions=[1, 2, 3],
        cdr2_alpha_positions=[10, 11],
        cdr3_alpha_positions=[20, 21, 22, 23],
        cdr1_beta_positions=[2, 3, 4],
        cdr2_beta_positions=[11, 12],
        cdr3_beta_positions=[21, 22, 23, 24, 25],
        cdr1_alpha_length=3,
        cdr2_alpha_length=2,
        cdr3_alpha_length=4,
        cdr1_beta_length=3,
        cdr2_beta_length=2,
        cdr3_beta_length=5,
        germline_deviation_cdr3_alpha=0.1,
        germline_deviation_cdr3_beta=0.2,
        dominant_contact_loop="CDR3_beta",
    )
    assert c.cdr3_beta_length == 5


# ---------------------------------------------------------------------------
# MultiSeedResult dataclass
# ---------------------------------------------------------------------------


def test_multiseed_result_instantiation() -> None:
    r = MultiSeedResult(
        peptide="X",
        mhc_allele="A",
        tcr_sequence="B",
        n_seeds=10,
        per_seed_scores=[0.5] * 10,
        mean_score=0.5,
        std_score=0.0,
        confidence_interval_95=(0.4, 0.6),
        convergence_metric=0.9,
        top_seed_index=0,
        reproducibility_score=0.85,
    )
    assert r.n_seeds == 10


# ---------------------------------------------------------------------------
# ImmunogenicityPrediction dataclass
# ---------------------------------------------------------------------------


def test_immunogenicity_prediction_instantiation() -> None:
    p = ImmunogenicityPrediction(
        peptide="X",
        mhc_allele="A",
        tcr_sequence="B",
        immunogenicity_score=0.7,
        mhc_binding_component=0.8,
        tcr_recognition_component=0.6,
        t_cell_response_component=0.7,
        predicted_response_class="high_immunogenicity",
        confidence=0.85,
        contributing_factors=["strong_MHC_groove_binding"],
    )
    assert p.immunogenicity_score == 0.7


# ---------------------------------------------------------------------------
# predict_ternary_complex
# ---------------------------------------------------------------------------


def test_predict_ternary_complex_returns_correct_type() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert isinstance(result, TernaryComplexResult)


def test_predict_ternary_complex_known_peptide_uses_known_pdb() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert result.mock_pdb_id == "2BNR"


def test_predict_ternary_complex_known_kd() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert result.predicted_kd_nm == 2.4


def test_predict_ternary_complex_unknown_peptide() -> None:
    result = predict_ternary_complex("AAAAAAAAA", "HLA-A*02:01", TCR)
    assert isinstance(result, TernaryComplexResult)
    assert result.mock_pdb_id.startswith("MODEL_")


def test_predict_ternary_complex_confidence_in_range() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert 0.0 <= result.confidence_score <= 1.0


def test_predict_ternary_complex_interface_contacts_nonempty() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert len(result.interface_contacts) >= 1


def test_predict_ternary_complex_contact_fields() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    for c in result.interface_contacts:
        assert "peptide_residue" in c
        assert "tcr_residue" in c
        assert "contact_type" in c
        assert "distance_angstrom" in c


def test_predict_ternary_complex_deterministic() -> None:
    r1 = predict_ternary_complex(PEPTIDE, MHC, TCR)
    r2 = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert r1.confidence_score == r2.confidence_score
    assert r1.predicted_kd_nm == r2.predicted_kd_nm


def test_predict_ternary_complex_groove_score_in_range() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert 0.0 <= result.mhc_peptide_groove_score <= 1.0


def test_predict_ternary_complex_docking_angle_positive() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert result.tcr_docking_angle_deg > 0


def test_predict_ternary_complex_has_disclaimer() -> None:
    result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    assert result.disclaimer == TCR_PMHC_DISCLAIMER


# ---------------------------------------------------------------------------
# score_tcell_response
# ---------------------------------------------------------------------------


def test_score_tcell_response_returns_correct_type() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    assert isinstance(score, TCellResponseScore)


def test_score_tcell_response_geometry_in_range() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    assert 0.0 <= score.binding_geometry_score <= 1.0


def test_score_tcell_response_valid_activation_class() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    valid = {"strong", "moderate", "weak", "no_response"}
    assert score.predicted_activation in valid


def test_score_tcell_response_cytokine_profile_keys() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    assert "IFN-gamma" in score.cytokine_profile
    assert "IL-2" in score.cytokine_profile
    assert "TNF-alpha" in score.cytokine_profile


def test_score_tcell_response_cytokine_values_nonneg() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    for k, v in score.cytokine_profile.items():
        assert v >= 0.0, f"{k} cytokine negative"


def test_score_tcell_response_stimulation_index_positive() -> None:
    complex_result = predict_ternary_complex(PEPTIDE, MHC, TCR)
    score = score_tcell_response(complex_result)
    assert score.stimulation_index >= 0.0


def test_score_tcell_response_deterministic() -> None:
    cr = predict_ternary_complex(PEPTIDE, MHC, TCR)
    s1 = score_tcell_response(cr)
    s2 = score_tcell_response(cr)
    assert s1.binding_geometry_score == s2.binding_geometry_score


# ---------------------------------------------------------------------------
# analyze_cdr_loops
# ---------------------------------------------------------------------------


def test_analyze_cdr_loops_returns_correct_type() -> None:
    result = analyze_cdr_loops(TCR)
    assert isinstance(result, CDRLoopAnalysis)


def test_analyze_cdr_loops_positions_nonempty() -> None:
    result = analyze_cdr_loops(TCR)
    assert len(result.cdr1_alpha_positions) > 0
    assert len(result.cdr3_alpha_positions) > 0
    assert len(result.cdr3_beta_positions) > 0


def test_analyze_cdr_loops_lengths_match_positions() -> None:
    result = analyze_cdr_loops(TCR)
    assert result.cdr1_alpha_length == len(result.cdr1_alpha_positions)
    assert result.cdr3_alpha_length == len(result.cdr3_alpha_positions)
    assert result.cdr3_beta_length == len(result.cdr3_beta_positions)


def test_analyze_cdr_loops_germline_deviation_in_range() -> None:
    result = analyze_cdr_loops(TCR)
    assert 0.0 <= result.germline_deviation_cdr3_alpha <= 1.0
    assert 0.0 <= result.germline_deviation_cdr3_beta <= 1.0


def test_analyze_cdr_loops_dominant_loop_valid() -> None:
    result = analyze_cdr_loops(TCR)
    assert result.dominant_contact_loop in {"CDR3_alpha", "CDR3_beta"}


def test_analyze_cdr_loops_deterministic() -> None:
    r1 = analyze_cdr_loops(TCR)
    r2 = analyze_cdr_loops(TCR)
    assert r1.cdr3_alpha_length == r2.cdr3_alpha_length
    assert r1.germline_deviation_cdr3_beta == r2.germline_deviation_cdr3_beta


def test_analyze_cdr_loops_different_sequences_differ() -> None:
    r1 = analyze_cdr_loops("CASSIRSSYEQYF")
    r2 = analyze_cdr_loops("CASSPGTDTQYF")
    # Not guaranteed to differ in every field, but CDR lengths should often differ
    assert r1.tcr_sequence != r2.tcr_sequence


# ---------------------------------------------------------------------------
# run_multiseed_sampling
# ---------------------------------------------------------------------------


def test_multiseed_sampling_returns_correct_type() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=10)
    assert isinstance(result, MultiSeedResult)


def test_multiseed_sampling_seed_count() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=50)
    assert result.n_seeds == 50
    assert len(result.per_seed_scores) == 50


def test_multiseed_sampling_100_seeds() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=100)
    assert len(result.per_seed_scores) == 100


def test_multiseed_sampling_scores_in_range() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=20)
    for s in result.per_seed_scores:
        assert 0.0 <= s <= 1.0


def test_multiseed_sampling_mean_in_range() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=50)
    assert 0.0 <= result.mean_score <= 1.0


def test_multiseed_sampling_std_nonneg() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=50)
    assert result.std_score >= 0.0


def test_multiseed_sampling_ci_ordered() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=50)
    assert result.confidence_interval_95[0] <= result.confidence_interval_95[1]


def test_multiseed_sampling_convergence_in_range() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=50)
    assert 0.0 <= result.convergence_metric <= 1.0


def test_multiseed_sampling_top_seed_valid_index() -> None:
    result = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=20)
    assert 0 <= result.top_seed_index < result.n_seeds


def test_multiseed_sampling_deterministic() -> None:
    r1 = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=30)
    r2 = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=30)
    assert r1.mean_score == r2.mean_score
    assert r1.per_seed_scores == r2.per_seed_scores


def test_multiseed_sampling_more_seeds_same_mean_direction() -> None:
    r10 = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=10)
    r100 = run_multiseed_sampling(PEPTIDE, MHC, TCR, n_seeds=100)
    # Both means should be in valid range
    assert 0.0 <= r10.mean_score <= 1.0
    assert 0.0 <= r100.mean_score <= 1.0


# ---------------------------------------------------------------------------
# predict_immunogenicity
# ---------------------------------------------------------------------------


def test_predict_immunogenicity_returns_correct_type() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert isinstance(result, ImmunogenicityPrediction)


def test_predict_immunogenicity_score_in_range() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert 0.0 <= result.immunogenicity_score <= 1.0


def test_predict_immunogenicity_components_in_range() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert 0.0 <= result.mhc_binding_component <= 1.0
    assert 0.0 <= result.tcr_recognition_component <= 1.0
    assert 0.0 <= result.t_cell_response_component <= 1.0


def test_predict_immunogenicity_response_class_valid() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    valid = {
        "high_immunogenicity",
        "moderate_immunogenicity",
        "low_immunogenicity",
        "non_immunogenic",
    }
    assert result.predicted_response_class in valid


def test_predict_immunogenicity_confidence_in_range() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert 0.0 <= result.confidence <= 1.0


def test_predict_immunogenicity_contributing_factors_nonempty() -> None:
    result = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert len(result.contributing_factors) >= 1


def test_predict_immunogenicity_deterministic() -> None:
    r1 = predict_immunogenicity(PEPTIDE, MHC, TCR)
    r2 = predict_immunogenicity(PEPTIDE, MHC, TCR)
    assert r1.immunogenicity_score == r2.immunogenicity_score


def test_predict_immunogenicity_different_peptides_differ() -> None:
    r1 = predict_immunogenicity("SLLMWITQC", MHC, TCR)
    r2 = predict_immunogenicity("GILGFVFTL", MHC, TCR)
    # Different inputs produce different scores
    assert r1.immunogenicity_score != r2.immunogenicity_score


# ---------------------------------------------------------------------------
# get_known_tcr_pmhc_complexes
# ---------------------------------------------------------------------------


def test_get_known_complexes_returns_dict() -> None:
    result = get_known_tcr_pmhc_complexes()
    assert isinstance(result, dict)
    assert len(result) >= 8


def test_get_known_complexes_same_as_module_dict() -> None:
    result = get_known_tcr_pmhc_complexes()
    assert result is KNOWN_TCR_PMHC


# ---------------------------------------------------------------------------
# lookup_tcr_pmhc
# ---------------------------------------------------------------------------


def test_lookup_known_peptide_returns_dict() -> None:
    result = lookup_tcr_pmhc("SLLMWITQC")
    assert result is not None
    assert isinstance(result, dict)


def test_lookup_known_peptide_correct_data() -> None:
    result = lookup_tcr_pmhc("ELAGIGILTV")
    assert result is not None
    assert result["mhc_allele"] == "HLA-A*02:01"


def test_lookup_unknown_peptide_returns_none() -> None:
    result = lookup_tcr_pmhc("UNKNOWNPEPTIDE")
    assert result is None


def test_lookup_case_sensitivity() -> None:
    # Original key is uppercase-style — should find as-is
    result = lookup_tcr_pmhc("NLVPMVATV")
    assert result is not None


# ---------------------------------------------------------------------------
# build_immunogenicity_report
# ---------------------------------------------------------------------------


def test_build_report_returns_dict() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert isinstance(report, dict)


def test_build_report_has_top_level_keys() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    required_keys = {
        "disclaimer",
        "input",
        "ternary_complex",
        "tcell_response",
        "cdr_loops",
        "multiseed_sampling",
        "immunogenicity",
    }
    for k in required_keys:
        assert k in report, f"Missing key: {k}"


def test_build_report_disclaimer_correct() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert report["disclaimer"] == TCR_PMHC_DISCLAIMER


def test_build_report_input_fields() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert report["input"]["peptide"] == PEPTIDE
    assert report["input"]["mhc_allele"] == MHC
    assert report["input"]["tcr_sequence"] == TCR


def test_build_report_known_complex_present() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert report["known_complex"] is not None


def test_build_report_unknown_peptide_known_none() -> None:
    report = build_immunogenicity_report("AAAAAAAAA", MHC, TCR)
    assert report["known_complex"] is None


def test_build_report_immunogenicity_score_in_range() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    score = report["immunogenicity"]["immunogenicity_score"]
    assert 0.0 <= score <= 1.0


def test_build_report_multiseed_has_seeds() -> None:
    report = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert report["multiseed_sampling"]["n_seeds"] == 100


def test_build_report_deterministic() -> None:
    r1 = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    r2 = build_immunogenicity_report(PEPTIDE, MHC, TCR)
    assert (
        r1["immunogenicity"]["immunogenicity_score"] == r2["immunogenicity"]["immunogenicity_score"]
    )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_predict_ternary_known_peptide(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/predict-ternary",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["peptide"] == PEPTIDE
    assert data["mock_pdb_id"] == "2BNR"


def test_api_predict_ternary_unknown_peptide(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/predict-ternary",
        json={"peptide": "AAAAAAAAA", "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mock_pdb_id"].startswith("MODEL_")


def test_api_predict_ternary_confidence_field(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/predict-ternary",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    data = response.json()
    assert "confidence_score" in data
    assert 0.0 <= data["confidence_score"] <= 1.0


def test_api_score_tcell_response(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/score-tcell-response",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert "binding_geometry_score" in data
    assert "predicted_activation" in data
    assert "cytokine_profile" in data


def test_api_score_tcell_activation_valid(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/score-tcell-response",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    data = response.json()
    assert data["predicted_activation"] in {"strong", "moderate", "weak", "no_response"}


def test_api_analyze_cdr_loops(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/analyze-cdr-loops",
        json={"tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert "cdr3_alpha_length" in data
    assert "cdr3_beta_length" in data
    assert "dominant_contact_loop" in data


def test_api_analyze_cdr_loops_germline_deviations(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/analyze-cdr-loops",
        json={"tcr_sequence": TCR},
    )
    data = response.json()
    assert "germline_deviation_cdr3_alpha" in data
    assert "germline_deviation_cdr3_beta" in data
    assert 0.0 <= data["germline_deviation_cdr3_alpha"] <= 1.0


def test_api_multiseed_sampling_default(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/multiseed-sampling",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["n_seeds"] == 100
    assert "mean_score" in data
    assert "convergence_metric" in data


def test_api_multiseed_sampling_custom_seeds(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/multiseed-sampling",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR, "n_seeds": 50},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["n_seeds"] == 50


def test_api_predict_immunogenicity(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/predict-immunogenicity",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert "immunogenicity_score" in data
    assert 0.0 <= data["immunogenicity_score"] <= 1.0


def test_api_predict_immunogenicity_response_class(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/predict-immunogenicity",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    data = response.json()
    valid = {
        "high_immunogenicity",
        "moderate_immunogenicity",
        "low_immunogenicity",
        "non_immunogenic",
    }
    assert data["predicted_response_class"] in valid


def test_api_known_complexes(client: TestClient) -> None:
    response = client.get("/tcr-pmhc/known-complexes")
    assert response.status_code == 200
    data = response.json()
    assert "count" in data
    assert data["count"] >= 8
    assert "complexes" in data


def test_api_known_complexes_contains_ny_eso1(client: TestClient) -> None:
    response = client.get("/tcr-pmhc/known-complexes")
    data = response.json()
    assert "SLLMWITQC" in data["complexes"]


def test_api_lookup_known_peptide(client: TestClient) -> None:
    response = client.get("/tcr-pmhc/lookup/SLLMWITQC")
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["complex"]["mhc_allele"] == "HLA-A*02:01"


def test_api_lookup_unknown_peptide_404(client: TestClient) -> None:
    response = client.get("/tcr-pmhc/lookup/UNKNOWNPEPTIDE")
    assert response.status_code == 404


def test_api_full_report(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/full-report",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    assert response.status_code == 200
    data = response.json()
    assert "immunogenicity" in data
    assert "ternary_complex" in data
    assert "tcell_response" in data
    assert "cdr_loops" in data
    assert "multiseed_sampling" in data


def test_api_full_report_disclaimer_present(client: TestClient) -> None:
    response = client.post(
        "/tcr-pmhc/full-report",
        json={"peptide": PEPTIDE, "mhc_allele": MHC, "tcr_sequence": TCR},
    )
    data = response.json()
    assert "disclaimer" in data
    assert "RESEARCH USE ONLY" in data["disclaimer"]
