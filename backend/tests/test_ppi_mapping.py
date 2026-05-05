"""Tests for PPI Mapping mode — functions and all 6 API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.ppi_mapping import (
    KNOWN_CANCER_PPIS,
    KNOWN_HOST_PATHOGEN_PPIS,
    CombinationTarget,
    DruggabilityScore,
    HostPathogenPPI,
    PPIResult,
    PathwayNode,
    SIGNALING_PATHWAYS,
    assess_interface_druggability,
    map_to_pathway,
    predict_host_pathogen_ppi,
    predict_ppi,
    suggest_combinations,
)


# ---------------------------------------------------------------------------
# predict_ppi
# ---------------------------------------------------------------------------


def test_predict_ppi_known_tp53_mdm2() -> None:
    result = predict_ppi("TP53", "MDM2")
    assert isinstance(result, PPIResult)
    assert result.confidence_score == 0.98
    assert result.interaction_type == "direct"


def test_predict_ppi_returns_ppi_result_instance() -> None:
    result = predict_ppi("MYC", "MAX")
    assert isinstance(result, PPIResult)


def test_predict_ppi_known_bcl2_bax_confidence() -> None:
    result = predict_ppi("BCL2", "BAX")
    assert result.confidence_score >= 0.9
    assert result.interaction_type == "direct"


def test_predict_ppi_case_insensitive() -> None:
    upper = predict_ppi("EGFR", "GRB2")
    lower = predict_ppi("egfr", "grb2")
    assert upper.confidence_score == lower.confidence_score


def test_predict_ppi_unknown_pair_returns_predicted() -> None:
    result = predict_ppi("GENEX", "GENEY")
    assert result.interaction_type == "predicted"
    assert 0.0 <= result.confidence_score <= 1.0


def test_predict_ppi_known_pair_has_interface_residues() -> None:
    result = predict_ppi("BRCA1", "BARD1")
    assert len(result.interface_residues_a) > 0
    assert len(result.interface_residues_b) > 0


def test_predict_ppi_akt1_mtor_indirect() -> None:
    result = predict_ppi("AKT1", "MTOR")
    assert result.interaction_type == "indirect"


def test_predict_ppi_biological_context_nonempty() -> None:
    result = predict_ppi("RB1", "E2F1")
    assert len(result.biological_context) > 0


def test_known_cancer_ppis_has_20_entries() -> None:
    assert len(KNOWN_CANCER_PPIS) == 20


def test_known_cancer_ppis_contains_expected_pairs() -> None:
    assert "TP53-MDM2" in KNOWN_CANCER_PPIS
    assert "BCL2-BAX" in KNOWN_CANCER_PPIS
    assert "PDCD1-CD274" in KNOWN_CANCER_PPIS
    assert "CDK4-CCND1" in KNOWN_CANCER_PPIS


# ---------------------------------------------------------------------------
# assess_interface_druggability
# ---------------------------------------------------------------------------


def test_druggability_tp53_mdm2_is_high() -> None:
    result = assess_interface_druggability("TP53", "MDM2")
    assert result.druggability == "high"
    assert "Nutlin-3a" in result.known_inhibitors


def test_druggability_bcl2_bax_venetoclax() -> None:
    result = assess_interface_druggability("BCL2", "BAX")
    assert result.druggability == "high"
    assert "Venetoclax" in result.known_inhibitors


def test_druggability_returns_dataclass() -> None:
    result = assess_interface_druggability("MYC", "MAX")
    assert isinstance(result, DruggabilityScore)


def test_druggability_ctnnb_apc_undruggable() -> None:
    result = assess_interface_druggability("CTNNB1", "APC")
    assert result.druggability == "undruggable"
    assert result.known_inhibitors == []


def test_druggability_unknown_pair_returns_low() -> None:
    result = assess_interface_druggability("GENEA", "GENEB")
    assert result.druggability == "low"


def test_druggability_interface_area_positive() -> None:
    result = assess_interface_druggability("TP53", "MDM2")
    assert result.interface_area_a2 > 0


def test_druggability_pdcd1_cd274_has_checkpoint_inhibitors() -> None:
    result = assess_interface_druggability("PDCD1", "CD274")
    names = " ".join(result.known_inhibitors)
    assert "Pembrolizumab" in names or "Nivolumab" in names


# ---------------------------------------------------------------------------
# map_to_pathway
# ---------------------------------------------------------------------------


def test_pathway_mapping_egfr_hits_ras_mapk() -> None:
    result = map_to_pathway(["EGFR"])
    assert "RAS-MAPK" in result


def test_pathway_mapping_egfr_also_hits_pi3k() -> None:
    result = map_to_pathway(["EGFR"])
    assert "PI3K-AKT-mTOR" in result


def test_pathway_mapping_tp53_hits_p53_pathway() -> None:
    result = map_to_pathway(["TP53"])
    assert "p53" in result


def test_pathway_mapping_unknown_gene_no_pathways() -> None:
    result = map_to_pathway(["UNKNOWNGENEABC"])
    assert result == {}


def test_pathway_mapping_multiple_genes_counts_correctly() -> None:
    result = map_to_pathway(["KRAS", "BRAF", "MAP2K1"])
    assert result["RAS-MAPK"]["hit_count"] == 3


def test_pathway_mapping_ctnnb1_hits_wnt() -> None:
    result = map_to_pathway(["CTNNB1"])
    assert "Wnt-beta-catenin" in result


def test_pathway_mapping_stat3_hits_jak_stat() -> None:
    result = map_to_pathway(["STAT3"])
    assert "JAK-STAT" in result


def test_pathway_mapping_notch1_hits_notch() -> None:
    result = map_to_pathway(["NOTCH1"])
    assert "Notch" in result


def test_signaling_pathways_has_6_entries() -> None:
    assert len(SIGNALING_PATHWAYS) == 6


# ---------------------------------------------------------------------------
# predict_host_pathogen_ppi
# ---------------------------------------------------------------------------


def test_host_pathogen_ace2_spike_found() -> None:
    result = predict_host_pathogen_ppi("ACE2", "Spike")
    assert result is not None
    assert isinstance(result, HostPathogenPPI)
    assert result.pathogen_name == "SARS-CoV-2"
    assert result.therapeutic_target is True


def test_host_pathogen_cd4_gp120_found() -> None:
    result = predict_host_pathogen_ppi("CD4", "gp120")
    assert result is not None
    assert result.pathogen_name == "HIV-1"


def test_host_pathogen_tp53_e6_oncoviral() -> None:
    result = predict_host_pathogen_ppi("TP53", "E6")
    assert result is not None
    assert result.interaction_type == "oncoviral_degradation"


def test_host_pathogen_unknown_returns_none() -> None:
    result = predict_host_pathogen_ppi("KRAS", "FakeProtein")
    assert result is None


def test_known_host_pathogen_ppis_has_10_entries() -> None:
    assert len(KNOWN_HOST_PATHOGEN_PPIS) == 10


def test_host_pathogen_case_insensitive_host() -> None:
    result = predict_host_pathogen_ppi("ace2", "Spike")
    assert result is not None


# ---------------------------------------------------------------------------
# suggest_combinations
# ---------------------------------------------------------------------------


def test_combinations_brca_genes_suggest_parp_atr() -> None:
    combos = suggest_combinations(["BRCA1", "BRCA2"])
    targets = [(c.target_a, c.target_b) for c in combos]
    assert ("PARP1", "ATR") in targets


def test_combinations_sorted_by_synergy_desc() -> None:
    combos = suggest_combinations(["EGFR", "KRAS", "BRAF", "BCL2", "BRCA1"])
    scores = [c.synergy_score for c in combos]
    assert scores == sorted(scores, reverse=True)


def test_combinations_returns_combination_target_instances() -> None:
    combos = suggest_combinations(["EGFR"])
    assert all(isinstance(c, CombinationTarget) for c in combos)


def test_combinations_empty_genes_returns_empty() -> None:
    combos = suggest_combinations([])
    assert combos == []


def test_combinations_unknown_genes_returns_empty() -> None:
    combos = suggest_combinations(["FAKEGENEXYZ"])
    assert combos == []


def test_combinations_pdcd1_suggests_checkpoint_combo() -> None:
    combos = suggest_combinations(["PDCD1"])
    targets = [(c.target_a, c.target_b) for c in combos]
    assert ("PDCD1", "CTLA4") in targets


def test_combinations_each_has_known_combinations_list() -> None:
    combos = suggest_combinations(["BRAF", "KRAS"])
    for c in combos:
        assert isinstance(c.known_combinations, list)
        assert len(c.known_combinations) >= 1


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_ppi_predict_tp53_mdm2(client: TestClient) -> None:
    response = client.post("/ppi/predict", json={"gene_a": "TP53", "gene_b": "MDM2"})
    assert response.status_code == 200
    data = response.json()
    assert data["confidence_score"] == 0.98
    assert data["interaction_type"] == "direct"


def test_api_ppi_predict_unknown_pair(client: TestClient) -> None:
    response = client.post("/ppi/predict", json={"gene_a": "FAKEA", "gene_b": "FAKEB"})
    assert response.status_code == 200
    data = response.json()
    assert data["interaction_type"] == "predicted"
    assert 0.0 <= data["confidence_score"] <= 1.0


def test_api_ppi_druggability_tp53_mdm2(client: TestClient) -> None:
    response = client.post("/ppi/druggability", json={"gene_a": "TP53", "gene_b": "MDM2"})
    assert response.status_code == 200
    data = response.json()
    assert data["druggability"] == "high"
    assert "Nutlin-3a" in data["known_inhibitors"]


def test_api_ppi_druggability_unknown(client: TestClient) -> None:
    response = client.post("/ppi/druggability", json={"gene_a": "AAA", "gene_b": "BBB"})
    assert response.status_code == 200
    assert response.json()["druggability"] == "low"


def test_api_ppi_pathway_mapping_egfr(client: TestClient) -> None:
    response = client.post("/ppi/pathway-mapping", json={"genes": ["EGFR", "KRAS"]})
    assert response.status_code == 200
    data = response.json()
    assert data["pathways_hit"] >= 1
    assert "RAS-MAPK" in data["mapping"]


def test_api_ppi_pathway_mapping_empty(client: TestClient) -> None:
    response = client.post("/ppi/pathway-mapping", json={"genes": []})
    assert response.status_code == 200
    assert response.json()["pathways_hit"] == 0


def test_api_ppi_host_pathogen_found(client: TestClient) -> None:
    response = client.post(
        "/ppi/host-pathogen", json={"host_gene": "ACE2", "pathogen_protein": "Spike"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["interaction"]["pathogen_name"] == "SARS-CoV-2"


def test_api_ppi_host_pathogen_not_found(client: TestClient) -> None:
    response = client.post(
        "/ppi/host-pathogen", json={"host_gene": "EGFR", "pathogen_protein": "FakeViral"}
    )
    assert response.status_code == 200
    assert response.json()["found"] is False
    assert response.json()["interaction"] is None


def test_api_ppi_combination_targets_brca(client: TestClient) -> None:
    response = client.post(
        "/ppi/combination-targets", json={"mutated_genes": ["BRCA1", "BRCA2"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["combination_count"] >= 1
    targets = [(c["target_a"], c["target_b"]) for c in data["combinations"]]
    assert ("PARP1", "ATR") in targets


def test_api_ppi_combination_targets_empty(client: TestClient) -> None:
    response = client.post("/ppi/combination-targets", json={"mutated_genes": []})
    assert response.status_code == 200
    assert response.json()["combination_count"] == 0


def test_api_ppi_known_interactions(client: TestClient) -> None:
    response = client.get("/ppi/known-interactions")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 20
    assert "TP53-MDM2" in data["interactions"]
    assert data["host_pathogen_count"] == 10
