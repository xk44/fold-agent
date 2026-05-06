"""Tests for structure_analysis_ext — Phase 24 Tier 2."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.structure_analysis_ext import (
    CALIBRATION_DATA,
    DynamicsProfile,
    MSAEnsembleResult,
    MSASubsample,
    ProteinClass,
    annotate_structure_with_dynamics,
    auto_calibrate,
    calibrate_confidence,
    classify_protein,
    cluster_msa_conformations,
    generate_msa_subsamples,
    get_calibration_curve,
    predict_dynamics,
    run_msa_ensemble,
)

SEQ_GLOBULAR = "ACDEFGHIKLMNPQRSTVWY"  # 20 AA, one of each
SEQ_HYDROPHOBIC = "VVVVVVVLLLLLLIIIIIMMMFFFWWW"  # all hydrophobic
SEQ_IDR = "GGGGGPPPPPSSSSSGGGGG"  # high G/P/S → IDR
SEQ_CYSTEINE = "ACCCCCCCCCCCCDEFGHIK"  # >8% cys → metalloprotein
SEQ_ANTIBODY = "ACDEFGHIKLCXXXXXXXXXCNPQRSTVW"  # C-X{10+}-C motif → antibody
SEQ_FIBROUS = "GAGAGAGAGAGAGAGAGAGA"  # high G/A → fibrous
SEQ_EMPTY = ""


# ---------------------------------------------------------------------------
# Feature 1: MSA subsamples
# ---------------------------------------------------------------------------


def test_generate_msa_subsamples_count() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=10)
    assert len(subs) == 10


def test_generate_msa_subsamples_default() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR)
    assert len(subs) == 20


def test_generate_msa_subsamples_types() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=5)
    for s in subs:
        assert isinstance(s, MSASubsample)
        assert isinstance(s.subsample_id, int)
        assert isinstance(s.msa_depth, int)
        assert isinstance(s.diversity_score, float)


def test_generate_msa_subsamples_depth_range() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=30, depth_range=(64, 256))
    for s in subs:
        assert 64 <= s.msa_depth <= 256


def test_generate_msa_subsamples_diversity_bounded() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    for s in subs:
        assert 0.0 <= s.diversity_score <= 1.0


def test_generate_msa_subsamples_deterministic() -> None:
    subs1 = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=10)
    subs2 = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=10)
    assert [s.msa_depth for s in subs1] == [s.msa_depth for s in subs2]


def test_generate_msa_subsamples_ids_sequential() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=5)
    assert [s.subsample_id for s in subs] == list(range(5))


# ---------------------------------------------------------------------------
# Feature 1: cluster_msa_conformations
# ---------------------------------------------------------------------------


def test_cluster_returns_msa_ensemble_result() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    assert isinstance(result, MSAEnsembleResult)


def test_cluster_population_weights_sum_to_one() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    total = sum(st.population_weight for st in result.states)
    assert abs(total - 1.0) < 1e-6


def test_cluster_n_clusters_consistent() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    assert result.n_clusters == len(result.states)


def test_cluster_structural_classes_valid() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    valid = {"ground_state", "alternative", "rare"}
    for st in result.states:
        assert st.structural_class in valid


def test_cluster_first_state_is_ground_state() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    assert result.states[0].structural_class == "ground_state"


def test_cluster_depth_range_populated() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20, depth_range=(32, 512))
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    lo, hi = result.msa_depth_range
    assert lo <= hi
    assert lo >= 32
    assert hi <= 512


def test_cluster_empty_subsamples() -> None:
    result = cluster_msa_conformations(SEQ_GLOBULAR, [])
    assert result.n_clusters == 0
    assert result.states == []


def test_cluster_pdb_data_present() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=10)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    for st in result.states:
        assert len(st.pdb_data) > 0


def test_cluster_ground_state_confidence_bounded() -> None:
    subs = generate_msa_subsamples(SEQ_GLOBULAR, n_subsamples=20)
    result = cluster_msa_conformations(SEQ_GLOBULAR, subs)
    assert 0.0 <= result.ground_state_confidence <= 1.0


# ---------------------------------------------------------------------------
# Feature 1: run_msa_ensemble (full pipeline)
# ---------------------------------------------------------------------------


def test_run_msa_ensemble_basic() -> None:
    result = run_msa_ensemble(SEQ_GLOBULAR)
    assert isinstance(result, MSAEnsembleResult)
    assert result.sequence == SEQ_GLOBULAR
    assert result.n_subsamples == 20


def test_run_msa_ensemble_custom_n() -> None:
    result = run_msa_ensemble(SEQ_GLOBULAR, n_subsamples=5)
    assert result.n_subsamples == 5


def test_run_msa_ensemble_functional_diversity_non_negative() -> None:
    result = run_msa_ensemble(SEQ_GLOBULAR)
    assert result.functional_diversity >= 0.0


# ---------------------------------------------------------------------------
# Feature 2: predict_dynamics
# ---------------------------------------------------------------------------


def test_predict_dynamics_returns_profile() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    assert isinstance(p, DynamicsProfile)


def test_predict_dynamics_residue_count() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    assert len(p.residues) == len(SEQ_GLOBULAR)


def test_predict_dynamics_backbone_flex_bounded() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    for r in p.residues:
        assert 0.0 <= r.backbone_flexibility <= 1.0


def test_predict_dynamics_bfactor_positive() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    for r in p.residues:
        assert r.predicted_bfactor > 0.0


def test_predict_dynamics_dynamics_class_valid() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    valid = {"rigid", "flexible", "highly_flexible", "hinge"}
    for r in p.residues:
        assert r.dynamics_class in valid


def test_predict_dynamics_overall_class_valid() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    assert p.overall_dynamics_class in {"rigid_globular", "partially_flexible", "highly_dynamic"}


def test_predict_dynamics_glycine_flexible() -> None:
    # G-rich sequence should show high flexibility
    p = predict_dynamics("GGGGG")
    assert p.mean_flexibility > 0.6


def test_predict_dynamics_tryptophan_rigid() -> None:
    p = predict_dynamics("WWWWW")
    # W is 0.15 base — terminals boost, but interior should be rigid
    assert p.residues[2].dynamics_class in {"rigid", "flexible"}


def test_predict_dynamics_empty_sequence() -> None:
    p = predict_dynamics("")
    assert p.residues == []
    assert p.mean_flexibility == 0.0


def test_predict_dynamics_hinge_residues_subset_of_indices() -> None:
    p = predict_dynamics("GGGWWWWGGGWWW")
    for h in p.hinge_residues:
        assert 0 <= h < len(p.sequence)


def test_predict_dynamics_flexible_regions_valid_ranges() -> None:
    p = predict_dynamics(SEQ_GLOBULAR)
    for start, end in p.flexible_regions:
        assert start <= end
        assert start >= 0
        assert end < len(SEQ_GLOBULAR)


# ---------------------------------------------------------------------------
# Feature 2: annotate_structure_with_dynamics
# ---------------------------------------------------------------------------

_SAMPLE_PDB = """\
ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00  0.00           C
ATOM      2  CA  GLY A   2       2.000   3.000   4.000  1.00  0.00           C
ATOM      3  CA  TRP A   3       3.000   4.000   5.000  1.00  0.00           C
END"""


def test_annotate_dynamics_returns_string() -> None:
    p = predict_dynamics("AGW")
    out = annotate_structure_with_dynamics(_SAMPLE_PDB, p)
    assert isinstance(out, str)


def test_annotate_dynamics_preserves_atom_lines() -> None:
    p = predict_dynamics("AGW")
    out = annotate_structure_with_dynamics(_SAMPLE_PDB, p)
    atom_lines = [l for l in out.splitlines() if l.startswith("ATOM")]
    assert len(atom_lines) == 3


def test_annotate_dynamics_bfactor_injected() -> None:
    p = predict_dynamics("AGW")
    out = annotate_structure_with_dynamics(_SAMPLE_PDB, p)
    # First ATOM line should no longer have "  0.00" in B-factor position
    first_atom = [l for l in out.splitlines() if l.startswith("ATOM")][0]
    # B-factor col 60-66 should be a non-zero float for ALA
    bf_str = first_atom[60:66].strip()
    assert float(bf_str) > 0.0


# ---------------------------------------------------------------------------
# Feature 3: calibration curves
# ---------------------------------------------------------------------------


def test_calibration_data_has_all_classes() -> None:
    for pc in ProteinClass:
        assert pc in CALIBRATION_DATA


def test_calibration_curve_bin_lengths() -> None:
    for pc, curve in CALIBRATION_DATA.items():
        assert len(curve.plddt_bins) == len(curve.actual_accuracy) == 10


def test_calibration_curve_accuracy_bounded() -> None:
    for pc, curve in CALIBRATION_DATA.items():
        for acc in curve.actual_accuracy:
            assert 0.0 <= acc <= 1.0


def test_get_calibration_curve_returns_correct_class() -> None:
    curve = get_calibration_curve(ProteinClass.membrane)
    assert curve.protein_class == ProteinClass.membrane


def test_membrane_overconfident_range_set() -> None:
    curve = get_calibration_curve(ProteinClass.membrane)
    assert curve.overconfident_range is not None
    lo, hi = curve.overconfident_range
    assert lo >= 70.0


def test_idr_underconfident_range_set() -> None:
    curve = get_calibration_curve(ProteinClass.idr_rich)
    assert curve.underconfident_range is not None
    lo, hi = curve.underconfident_range
    assert hi <= 40.0


def test_calibrate_confidence_keys() -> None:
    result = calibrate_confidence(75.0, ProteinClass.globular)
    assert "raw_plddt" in result
    assert "adjusted_confidence" in result
    assert "calibration_offset" in result
    assert "warning" in result


def test_calibrate_confidence_membrane_warning_high_plddt() -> None:
    result = calibrate_confidence(85.0, ProteinClass.membrane)
    assert result["warning"] is not None
    assert "overconfident" in result["warning"].lower()


def test_calibrate_confidence_idr_warning_low_plddt() -> None:
    result = calibrate_confidence(25.0, ProteinClass.idr_rich)
    assert result["warning"] is not None
    assert "underconfident" in result["warning"].lower()


def test_calibrate_confidence_globular_no_warning() -> None:
    result = calibrate_confidence(80.0, ProteinClass.globular)
    assert result["warning"] is None


def test_calibrate_confidence_clamped_above_100() -> None:
    result = calibrate_confidence(120.0, ProteinClass.globular)
    assert result["raw_plddt"] == 100.0


def test_calibrate_confidence_clamped_below_0() -> None:
    result = calibrate_confidence(-10.0, ProteinClass.globular)
    assert result["raw_plddt"] == 0.0


# ---------------------------------------------------------------------------
# Feature 3: classify_protein
# ---------------------------------------------------------------------------


def test_classify_protein_idr() -> None:
    assert classify_protein(SEQ_IDR) == ProteinClass.idr_rich


def test_classify_protein_metalloprotein() -> None:
    # Sequence with >8% cys
    seq = "C" * 10 + "ACDEFGHIKLMNPQRSTVWY"
    result = classify_protein(seq)
    assert result == ProteinClass.metalloprotein


def test_classify_protein_membrane_long_hydrophobic() -> None:
    seq = "V" * 20  # long stretch of hydrophobic residues
    assert classify_protein(seq) == ProteinClass.membrane


def test_classify_protein_fibrous() -> None:
    # Fibrous: high G/A but G below 35% GPS threshold — use mostly A with some G
    seq = "A" * 25 + "G" * 5  # ga_content=1.0 but gps_content=G/30=0.167 < 0.35
    assert classify_protein(seq) == ProteinClass.fibrous


def test_classify_protein_globular_default() -> None:
    # Balanced sequence should fall through to globular
    seq = "ACDEFGHIKLMNPQRSTVWY" * 3
    result = classify_protein(seq)
    assert result in {ProteinClass.globular, ProteinClass.enzyme}


def test_classify_protein_empty() -> None:
    assert classify_protein("") == ProteinClass.globular


# ---------------------------------------------------------------------------
# Feature 3: auto_calibrate
# ---------------------------------------------------------------------------


def test_auto_calibrate_returns_classified_as() -> None:
    result = auto_calibrate(SEQ_GLOBULAR, 75.0)
    assert "classified_as" in result
    assert result["classified_as"] in [pc.value for pc in ProteinClass]


def test_auto_calibrate_adjusted_confidence_bounded() -> None:
    result = auto_calibrate(SEQ_GLOBULAR, 80.0)
    assert 0.0 <= result["adjusted_confidence"] <= 1.0


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_api_msa_ensemble(client: TestClient) -> None:
    resp = client.post("/structure-ext/msa-ensemble", json={"sequence": SEQ_GLOBULAR})
    assert resp.status_code == 200
    data = resp.json()
    assert "states" in data
    assert data["n_subsamples"] == 20


def test_api_msa_ensemble_custom_n(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/msa-ensemble", json={"sequence": SEQ_GLOBULAR, "n_subsamples": 5}
    )
    assert resp.status_code == 200
    assert resp.json()["n_subsamples"] == 5


def test_api_msa_subsamples(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/msa-subsamples", json={"sequence": SEQ_GLOBULAR, "n_subsamples": 8}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_subsamples"] == 8
    assert len(data["subsamples"]) == 8


def test_api_msa_subsamples_depth_range(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/msa-subsamples",
        json={"sequence": SEQ_GLOBULAR, "n_subsamples": 5, "depth_min": 64, "depth_max": 128},
    )
    assert resp.status_code == 200
    for s in resp.json()["subsamples"]:
        assert 64 <= s["msa_depth"] <= 128


def test_api_dynamics_profile(client: TestClient) -> None:
    resp = client.post("/structure-ext/dynamics-profile", json={"sequence": SEQ_GLOBULAR})
    assert resp.status_code == 200
    data = resp.json()
    assert "residues" in data
    assert len(data["residues"]) == len(SEQ_GLOBULAR)


def test_api_annotate_dynamics(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/annotate-dynamics",
        json={"pdb_data": _SAMPLE_PDB, "sequence": "AGW"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "annotated_pdb" in data
    assert "ATOM" in data["annotated_pdb"]


def test_api_calibration_curve_globular(client: TestClient) -> None:
    resp = client.get("/structure-ext/calibration/globular")
    assert resp.status_code == 200
    data = resp.json()
    assert data["protein_class"] == "globular"
    assert len(data["plddt_bins"]) == 10


def test_api_calibration_curve_membrane(client: TestClient) -> None:
    resp = client.get("/structure-ext/calibration/membrane")
    assert resp.status_code == 200
    assert resp.json()["overconfident_range"] is not None


def test_api_calibration_curve_invalid(client: TestClient) -> None:
    resp = client.get("/structure-ext/calibration/unknown_class")
    assert resp.status_code == 422


def test_api_calibrate_confidence(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/calibrate-confidence",
        json={"plddt": 75.0, "protein_class": "globular"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_plddt"] == 75.0
    assert "adjusted_confidence" in data


def test_api_classify_protein(client: TestClient) -> None:
    resp = client.post("/structure-ext/classify-protein", json={"sequence": SEQ_IDR})
    assert resp.status_code == 200
    assert resp.json()["protein_class"] == "idr_rich"


def test_api_auto_calibrate(client: TestClient) -> None:
    resp = client.post(
        "/structure-ext/auto-calibrate",
        json={"sequence": SEQ_GLOBULAR, "plddt": 80.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "adjusted_confidence" in data
    assert "classified_as" in data


def test_api_safety_label_present(client: TestClient) -> None:
    resp = client.post("/structure-ext/msa-ensemble", json={"sequence": SEQ_GLOBULAR})
    assert "safety_label" in resp.json()
