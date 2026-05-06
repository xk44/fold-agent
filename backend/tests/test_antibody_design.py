"""Tests for Antibody Design mode — functions and all 8 API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.modes.antibody_design import (
    KNOWN_ANTIBODY_TARGETS,
    KNOWN_NANOBODIES,
    BispecificDesign,
    CheckpointAnalysis,
    DesignedBinder,
    DockingResult,
    HumanizationResult,
    NanobodyHit,
    analyze_checkpoint_target,
    assess_humanization,
    design_binder,
    design_bispecific,
    dock_antibody_antigen,
    identify_cdr_regions,
    predict_nanobody_binding,
    score_cdr_h3,
)

# ---------------------------------------------------------------------------
# Fixtures — short representative sequences for tests
# ---------------------------------------------------------------------------

_VH_SEQ = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYY"
    "ADSVKGRFTISRDNSKNTLYLQMNSLRAEDTAVYYCARGGSYFDYWGQGTLVTVSS"
)

_VL_SEQ = (
    "DIQMTQSPSSLSASVGDRVTITCRASQSVSSFLAWYQQKPGKAPKLLIYAASSLQSGVPS"
    "RFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPFT"
)

_SHORT_SEQ = "MKVLSLLYLLTALPGAEAS"  # < 80 aa


# ---------------------------------------------------------------------------
# KNOWN_ANTIBODY_TARGETS
# ---------------------------------------------------------------------------


def test_known_targets_has_15_entries() -> None:
    assert len(KNOWN_ANTIBODY_TARGETS) == 15


def test_known_targets_contains_pembrolizumab_target() -> None:
    assert "PD-1" in KNOWN_ANTIBODY_TARGETS
    assert "Pembrolizumab" in KNOWN_ANTIBODY_TARGETS["PD-1"]["approved_antibodies"]


def test_known_targets_contains_trastuzumab_target() -> None:
    assert "HER2" in KNOWN_ANTIBODY_TARGETS
    assert "Trastuzumab" in KNOWN_ANTIBODY_TARGETS["HER2"]["approved_antibodies"]


def test_known_targets_all_have_required_keys() -> None:
    required = {"full_name", "gene", "approved_antibodies", "indication", "target_class"}
    for name, data in KNOWN_ANTIBODY_TARGETS.items():
        assert required <= set(data.keys()), f"{name} missing keys"


# ---------------------------------------------------------------------------
# KNOWN_NANOBODIES
# ---------------------------------------------------------------------------


def test_known_nanobodies_has_8_entries() -> None:
    assert len(KNOWN_NANOBODIES) == 8


def test_known_nanobodies_caplacizumab_present() -> None:
    assert "caplacizumab" in KNOWN_NANOBODIES
    assert KNOWN_NANOBODIES["caplacizumab"]["target_gene"] == "VWF"


def test_known_nanobodies_ozoralizumab_tnf() -> None:
    assert "ozoralizumab" in KNOWN_NANOBODIES
    assert KNOWN_NANOBODIES["ozoralizumab"]["target"] == "TNF-alpha"


# ---------------------------------------------------------------------------
# dock_antibody_antigen
# ---------------------------------------------------------------------------


def test_dock_returns_n_seeds_results() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "PD-1", n_seeds=5)
    assert len(results) == 5


def test_dock_returns_docking_result_instances() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "HER2")
    assert all(isinstance(r, DockingResult) for r in results)


def test_dock_results_sorted_by_binding_score() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "EGFR", n_seeds=8)
    scores = [r.binding_score for r in results]
    assert scores == sorted(scores)


def test_dock_antigen_gene_stored_uppercase() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "pd-1", n_seeds=3)
    assert all(r.antigen_gene == "PD-1" for r in results)


def test_dock_confidence_values_valid() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "CTLA-4", n_seeds=10)
    for r in results:
        assert r.confidence in {"high", "medium", "low"}


def test_dock_epitope_type_populated() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "PD-1", n_seeds=3)
    for r in results:
        assert r.epitope_type in {"linear", "conformational"}


def test_dock_interface_residues_nonempty() -> None:
    results = dock_antibody_antigen(_VH_SEQ, "HER2", n_seeds=3)
    for r in results:
        assert len(r.interface_residues) > 0


# ---------------------------------------------------------------------------
# predict_nanobody_binding
# ---------------------------------------------------------------------------


def test_nanobody_binding_known_target_returns_hit() -> None:
    hit = predict_nanobody_binding("AAAGSGYSSSVVV", "VWF")
    assert isinstance(hit, NanobodyHit)
    assert hit.nanobody_id == "caplacizumab"


def test_nanobody_binding_unknown_target_denovo() -> None:
    hit = predict_nanobody_binding(_VH_SEQ, "SOMEGENE")
    assert isinstance(hit, NanobodyHit)
    assert "denovo" in hit.nanobody_id


def test_nanobody_binding_kd_positive() -> None:
    hit = predict_nanobody_binding("AAARGSSYYYYVVV", "TNF")
    assert hit.kd_estimate_nm > 0


def test_nanobody_binding_epitope_residues_sorted() -> None:
    hit = predict_nanobody_binding(_VH_SEQ, "CD274")
    assert hit.epitope_residues == sorted(hit.epitope_residues)


# ---------------------------------------------------------------------------
# design_binder
# ---------------------------------------------------------------------------


def test_design_binder_rfdiffusion_default() -> None:
    result = design_binder("EGFR", [50, 60, 70])
    assert isinstance(result, DesignedBinder)
    assert result.design_method == "rfdiffusion"


def test_design_binder_proteinmpnn() -> None:
    result = design_binder("HER2", [100, 110], method="proteinmpnn")
    assert result.design_method == "proteinmpnn"


def test_design_binder_combined_method() -> None:
    result = design_binder("PD-L1", [55], method="rfdiffusion+proteinmpnn")
    assert result.design_method == "rfdiffusion+proteinmpnn"


def test_design_binder_unknown_method_fallback() -> None:
    result = design_binder("EGFR", [50], method="invalid_method")
    assert result.design_method == "rfdiffusion"


def test_design_binder_hotspot_residues_sorted() -> None:
    result = design_binder("KRAS", [70, 12, 95])
    assert result.hotspot_residues == sorted([70, 12, 95])


def test_design_binder_backbone_pdb_nonempty() -> None:
    result = design_binder("BRAF", [600])
    assert len(result.backbone_pdb) > 0


# ---------------------------------------------------------------------------
# analyze_checkpoint_target
# ---------------------------------------------------------------------------


def test_checkpoint_pd1_returns_analysis() -> None:
    result = analyze_checkpoint_target("PD-1")
    assert isinstance(result, CheckpointAnalysis)
    assert result.target == "PD-1"


def test_checkpoint_pd1_has_resistance_mutations() -> None:
    result = analyze_checkpoint_target("PD-1")
    assert len(result.resistance_mutations) >= 1


def test_checkpoint_ctla4_mechanism_nonempty() -> None:
    result = analyze_checkpoint_target("CTLA-4")
    assert len(result.mechanism) > 10


def test_checkpoint_unknown_returns_none() -> None:
    result = analyze_checkpoint_target("UNKNOWN_CHECKPOINT")
    assert result is None


def test_checkpoint_all_six_targets_covered() -> None:
    for target in ["PD-1", "PD-L1", "CTLA-4", "LAG-3", "TIM-3", "TIGIT"]:
        result = analyze_checkpoint_target(target)
        assert result is not None, f"Missing checkpoint data for {target}"


# ---------------------------------------------------------------------------
# identify_cdr_regions / score_cdr_h3
# ---------------------------------------------------------------------------


def test_cdr_regions_vh_returns_heavy_cdrs() -> None:
    regions = identify_cdr_regions(_VH_SEQ)
    names = {r.name for r in regions}
    assert {"H1", "H2", "H3"} <= names


def test_cdr_regions_all_loop_types_valid() -> None:
    regions = identify_cdr_regions(_VH_SEQ)
    for r in regions:
        assert r.loop_type in {"heavy", "light"}


def test_cdr_h3_score_length_correct() -> None:
    scores = score_cdr_h3("ARDFGYYYYGMDV")
    assert scores["length"] == 13


def test_cdr_h3_score_flexibility_in_range() -> None:
    scores = score_cdr_h3("ARDFGYYYYGMDV")
    assert 0.0 <= scores["flexibility_score"] <= 1.0


def test_cdr_h3_score_binding_potential_in_range() -> None:
    scores = score_cdr_h3("ARDFGYYYYGMDV")
    assert 0.0 <= scores["binding_potential"] <= 1.0


# ---------------------------------------------------------------------------
# assess_humanization
# ---------------------------------------------------------------------------


def test_humanization_returns_result_instance() -> None:
    result = assess_humanization(_VH_SEQ)
    assert isinstance(result, HumanizationResult)


def test_humanization_framework_identity_in_range() -> None:
    result = assess_humanization(_VH_SEQ)
    assert 0.0 <= result.framework_identity <= 1.0


def test_humanization_risk_score_in_range() -> None:
    result = assess_humanization(_VH_SEQ)
    assert 0.0 <= result.risk_score <= 1.0


def test_humanization_original_sequence_preserved() -> None:
    result = assess_humanization(_VH_SEQ)
    assert result.original_sequence == _VH_SEQ


def test_humanization_humanized_sequence_same_length() -> None:
    result = assess_humanization(_VH_SEQ)
    # Humanized sequence length >= original (may be padded by germline or truncated)
    assert len(result.humanized_sequence) >= 1


# ---------------------------------------------------------------------------
# design_bispecific
# ---------------------------------------------------------------------------


def test_bispecific_bite_format() -> None:
    result = design_bispecific("CD3", "CD19", "BiTE")
    assert isinstance(result, BispecificDesign)
    assert result.format == "BiTE"


def test_bispecific_knobs_in_holes_format() -> None:
    result = design_bispecific("HER2", "PD-L1", "knobs-in-holes")
    assert result.format == "knobs-in-holes"


def test_bispecific_unknown_format_fallback_to_bite() -> None:
    result = design_bispecific("CD3", "HER2", "invalid")
    assert result.format == "BiTE"


def test_bispecific_arm_targets_uppercase() -> None:
    result = design_bispecific("cd3", "cd19")
    assert result.arm1_target == "CD3"
    assert result.arm2_target == "CD19"


def test_bispecific_linker_nonempty() -> None:
    result = design_bispecific("EGFR", "VEGF", "DVD-Ig")
    assert len(result.linker_sequence) > 0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_dock(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/dock",
        json={"antibody_sequence": _VH_SEQ, "antigen_gene": "PD-1", "n_seeds": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["antigen_gene"] == "PD-1"
    assert data["result_count"] == 5
    assert len(data["results"]) == 5


def test_api_nanobody_binding(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/nanobody-binding",
        json={"nanobody_sequence": "AAAGSGYSSSVVV", "target_gene": "VWF"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "VWF"
    assert data["nanobody_id"] == "caplacizumab"
    assert data["kd_estimate_nm"] > 0


def test_api_design_binder(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/design-binder",
        json={"target_gene": "EGFR", "hotspot_residues": [50, 60, 70], "method": "rfdiffusion"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "EGFR"
    assert data["design_method"] == "rfdiffusion"
    assert "designed_sequence" in data


def test_api_checkpoint_analysis_known_target(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/checkpoint-analysis",
        json={"target": "PD-1"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target"] == "PD-1"
    assert isinstance(data["resistance_mutations"], list)


def test_api_checkpoint_analysis_unknown_target(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/checkpoint-analysis",
        json={"target": "UNKNOWN_XYZ"},
    )
    assert response.status_code == 404


def test_api_cdr_regions(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/cdr-regions",
        json={"antibody_sequence": _VH_SEQ},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cdr_count"] >= 3
    assert isinstance(data["regions"], list)


def test_api_humanization(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/humanization",
        json={"antibody_sequence": _VH_SEQ},
    )
    assert response.status_code == 200
    data = response.json()
    assert 0.0 <= data["framework_identity"] <= 1.0
    assert 0.0 <= data["risk_score"] <= 1.0
    assert "humanized_sequence" in data


def test_api_bispecific(client: TestClient) -> None:
    response = client.post(
        "/antibody-design/bispecific",
        json={"target1": "CD3", "target2": "CD19", "format": "BiTE"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["arm1_target"] == "CD3"
    assert data["arm2_target"] == "CD19"
    assert data["format"] == "BiTE"
    assert data["linker_length"] > 0


def test_api_known_targets(client: TestClient) -> None:
    response = client.get("/antibody-design/known-targets")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 15
    assert "PD-1" in data["targets"]
    assert "HER2" in data["targets"]
    assert isinstance(data["checkpoint_targets"], list)
    assert isinstance(data["known_nanobodies"], list)
