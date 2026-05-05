"""Tests for Protein Misfolding Mode.

Covers:
  - MisfoldingRisk assessment (known genes, unknown genes, mutations, risk levels)
  - Aggregation region identification (scoring, merging, mechanisms)
  - Chaperone target lookup (known genes, unknown genes)
  - Prion-like domain detection (Q/N-rich windows)
  - LSD analysis (known genes, unknown genes)
  - Neurodegeneration analysis (all 5 diseases, aliases)
  - All 7 API endpoints
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.protein_misfolding import (
    AggregationRegion,
    ChaperoneTarget,
    HYDROPHOBICITY,
    BETA_PROPENSITY,
    KNOWN_CHAPERONE_TARGETS,
    LYSOSOMAL_STORAGE_DISORDERS,
    LSDAnalysis,
    MISFOLDING_DISEASES,
    MisfoldingRisk,
    NeurodegAnalysis,
    PrionDomain,
    analyze_lsd,
    analyze_neurodegeneration,
    assess_misfolding_risk,
    detect_prion_domains,
    find_chaperone_targets,
    identify_aggregation_regions,
)


# ---------------------------------------------------------------------------
# MisfoldingRisk assessment
# ---------------------------------------------------------------------------


class TestAssessMisfoldingRisk:
    def test_known_disease_gene_no_mutations(self):
        result = assess_misfolding_risk("CFTR")
        assert isinstance(result, MisfoldingRisk)
        assert result.gene == "CFTR"
        assert result.risk_level in {"high", "moderate"}
        assert result.known_misfolding_disease is not None
        assert "cystic fibrosis" in result.known_misfolding_disease.lower()

    def test_known_gene_with_destabilizing_mutation_is_high_risk(self):
        result = assess_misfolding_risk("SOD1", ["A4V"])
        assert result.risk_level == "high"
        assert result.confidence == "high"
        assert "A4V" in result.destabilizing_mutations

    def test_known_disease_gene_elevates_to_moderate_without_mutations(self):
        result = assess_misfolding_risk("TTR")
        assert result.risk_level in {"moderate", "high"}
        assert result.known_misfolding_disease is not None

    def test_unknown_gene_no_mutations_is_low_risk(self):
        result = assess_misfolding_risk("UNKNOWNGENE99")
        assert result.risk_level == "low"
        assert result.known_misfolding_disease is None

    def test_case_insensitive_gene(self):
        result = assess_misfolding_risk("snca")
        assert result.gene == "SNCA"
        assert result.known_misfolding_disease is not None

    def test_prnp_prion_disease(self):
        result = assess_misfolding_risk("PRNP")
        assert result.known_misfolding_disease is not None
        assert "prion" in result.known_misfolding_disease.lower()

    def test_htt_huntingtons(self):
        result = assess_misfolding_risk("HTT")
        assert result.known_misfolding_disease is not None
        assert "huntington" in result.known_misfolding_disease.lower()

    def test_aggregation_regions_returned_for_snca(self):
        result = assess_misfolding_risk("SNCA")
        assert isinstance(result.aggregation_prone_regions, list)
        assert len(result.aggregation_prone_regions) > 0

    def test_confidence_field_valid(self):
        for gene in ["CFTR", "UNKNOWNGENE99"]:
            result = assess_misfolding_risk(gene)
            assert result.confidence in {"high", "moderate", "low"}

    def test_misfolding_diseases_dict_populated(self):
        assert "APP" in MISFOLDING_DISEASES
        assert "SNCA" in MISFOLDING_DISEASES
        assert "PRNP" in MISFOLDING_DISEASES
        assert len(MISFOLDING_DISEASES) >= 15


# ---------------------------------------------------------------------------
# Aggregation region identification
# ---------------------------------------------------------------------------

# Highly hydrophobic + beta-sheet-prone sequence: VVIVVIV (Val/Ile-rich)
_HYDROPHOBIC_SEQ = "VVIVVIVVVIVVIV"
# Q/N-rich prion-like sequence
_QN_RICH_SEQ = "QNQNQNQNQNQNQN"
# Short sequence (below window size)
_SHORT_SEQ = "ACDEF"


class TestIdentifyAggregationRegions:
    def test_hydrophobic_sequence_flags_regions(self):
        regions = identify_aggregation_regions(_HYDROPHOBIC_SEQ)
        assert isinstance(regions, list)
        assert len(regions) > 0

    def test_returns_aggregation_region_dataclass(self):
        regions = identify_aggregation_regions(_HYDROPHOBIC_SEQ)
        for r in regions:
            assert isinstance(r, AggregationRegion)

    def test_region_fields_populated(self):
        regions = identify_aggregation_regions(_HYDROPHOBIC_SEQ)
        assert len(regions) > 0
        r = regions[0]
        assert r.start >= 0
        assert r.end > r.start
        assert isinstance(r.sequence, str)
        assert isinstance(r.score, float)
        assert r.mechanism in {"amyloid", "amorphous", "prion-like"}

    def test_short_sequence_returns_empty(self):
        assert identify_aggregation_regions(_SHORT_SEQ) == []

    def test_empty_sequence_returns_empty(self):
        assert identify_aggregation_regions("") == []

    def test_qn_rich_flags_prion_like(self):
        regions = identify_aggregation_regions(_QN_RICH_SEQ)
        if regions:
            assert any(r.mechanism == "prion-like" for r in regions)

    def test_hydrophobicity_dict_covers_standard_amino_acids(self):
        for aa in "ACDEFGHIKLMNPQRSTVWY":
            assert aa in HYDROPHOBICITY

    def test_beta_propensity_dict_covers_standard_amino_acids(self):
        for aa in "ACDEFGHIKLMNPQRSTVWY":
            assert aa in BETA_PROPENSITY

    def test_regions_sorted_by_start(self):
        seq = _HYDROPHOBIC_SEQ * 3
        regions = identify_aggregation_regions(seq)
        starts = [r.start for r in regions]
        assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Chaperone target lookup
# ---------------------------------------------------------------------------


class TestFindChaperoneTargets:
    def test_cftr_returns_target(self):
        target = find_chaperone_targets("CFTR")
        assert target is not None
        assert isinstance(target, ChaperoneTarget)
        assert target.gene == "CFTR"

    def test_cftr_has_lumacaftor(self):
        target = find_chaperone_targets("CFTR")
        assert any("lumacaftor" in c.lower() for c in target.known_chaperones)

    def test_ttr_has_tafamidis(self):
        target = find_chaperone_targets("TTR")
        assert target is not None
        assert any("tafamidis" in c.lower() for c in target.known_chaperones)

    def test_gla_migalastat(self):
        target = find_chaperone_targets("GLA")
        assert target is not None
        assert any("migalastat" in c.lower() for c in target.known_chaperones)

    def test_gba_isofagomine(self):
        target = find_chaperone_targets("GBA")
        assert target is not None
        assert any("isofagomine" in c.lower() for c in target.known_chaperones)

    def test_unknown_gene_returns_none(self):
        assert find_chaperone_targets("FAKEGENE999") is None

    def test_case_insensitive(self):
        assert find_chaperone_targets("cftr") is not None

    def test_mechanism_field_valid(self):
        for gene in KNOWN_CHAPERONE_TARGETS:
            t = find_chaperone_targets(gene)
            assert t.mechanism in {"stabilization", "folding_correction", "trafficking_rescue"}

    def test_known_chaperone_targets_populated(self):
        assert len(KNOWN_CHAPERONE_TARGETS) >= 8


# ---------------------------------------------------------------------------
# Prion-like domain detection
# ---------------------------------------------------------------------------

# TDP-43 C-terminal domain is Q/N-rich
_PRION_SEQ = "QNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQN"
_NORMAL_SEQ = "ACDEFGHIKLMACDEFGHIKLMACDEFGHIKLMACDEFGHIKLMACDEFGHIKLMACDEFGHIKLMACDEF"


class TestDetectPrionDomains:
    def test_qn_rich_sequence_detected(self):
        domains = detect_prion_domains(_PRION_SEQ)
        assert len(domains) > 0

    def test_returns_prion_domain_dataclass(self):
        domains = detect_prion_domains(_PRION_SEQ)
        for d in domains:
            assert isinstance(d, PrionDomain)

    def test_domain_fields_populated(self):
        domains = detect_prion_domains(_PRION_SEQ)
        assert len(domains) > 0
        d = domains[0]
        assert d.start >= 0
        assert d.end > d.start
        assert d.q_n_content > 0.3
        assert 0.0 <= d.gln_asn_ratio <= 1.0
        assert 0.0 <= d.prion_score <= 1.0

    def test_non_qn_sequence_no_domains(self):
        assert detect_prion_domains(_NORMAL_SEQ) == []

    def test_short_sequence_returns_empty(self):
        assert detect_prion_domains("QNQNQN") == []

    def test_empty_sequence_returns_empty(self):
        assert detect_prion_domains("") == []


# ---------------------------------------------------------------------------
# LSD analysis
# ---------------------------------------------------------------------------


class TestAnalyzeLSD:
    def test_gba_gaucher(self):
        result = analyze_lsd("GBA")
        assert result is not None
        assert isinstance(result, LSDAnalysis)
        assert "gaucher" in result.disease_name.lower()

    def test_gla_fabry(self):
        result = analyze_lsd("GLA")
        assert result is not None
        assert "fabry" in result.disease_name.lower()

    def test_gaa_pompe(self):
        result = analyze_lsd("GAA")
        assert result is not None
        assert "pompe" in result.disease_name.lower()

    def test_hexa_tay_sachs(self):
        result = analyze_lsd("HEXA")
        assert result is not None
        assert "tay-sachs" in result.disease_name.lower()

    def test_unknown_gene_returns_none(self):
        assert analyze_lsd("FAKEGENE") is None

    def test_case_insensitive(self):
        assert analyze_lsd("gba") is not None

    def test_therapy_type_valid(self):
        for gene in LYSOSOMAL_STORAGE_DISORDERS:
            result = analyze_lsd(gene)
            assert result.therapy_type in {"ERT", "SRT", "chaperone", "gene_therapy"}

    def test_available_therapies_nonempty(self):
        result = analyze_lsd("GBA")
        assert len(result.available_therapies) > 0

    def test_lsd_dict_has_12_entries(self):
        assert len(LYSOSOMAL_STORAGE_DISORDERS) >= 12


# ---------------------------------------------------------------------------
# Neurodegeneration analysis
# ---------------------------------------------------------------------------


class TestAnalyzeNeurodegeneration:
    def test_alzheimers_exact(self):
        result = analyze_neurodegeneration("alzheimers")
        assert result is not None
        assert isinstance(result, NeurodegAnalysis)
        assert "alzheimer" in result.disease.lower()

    def test_alzheimers_alias(self):
        assert analyze_neurodegeneration("alzheimer") is not None

    def test_parkinsons(self):
        result = analyze_neurodegeneration("parkinsons")
        assert result is not None
        assert "α-synuclein" in result.key_protein or "synuclein" in result.key_protein.lower()

    def test_als(self):
        result = analyze_neurodegeneration("als")
        assert result is not None
        assert "sod1" in result.key_protein.lower() or "tdp" in result.key_protein.lower()

    def test_huntingtons(self):
        result = analyze_neurodegeneration("huntingtons")
        assert result is not None
        assert "huntingtin" in result.key_protein.lower()

    def test_prion(self):
        result = analyze_neurodegeneration("prion")
        assert result is not None
        assert "prp" in result.key_protein.lower() or "prnp" in result.key_protein.lower()

    def test_unknown_disease_returns_none(self):
        assert analyze_neurodegeneration("totally_fake_disease") is None

    def test_known_mutations_populated(self):
        result = analyze_neurodegeneration("alzheimers")
        assert len(result.known_mutations) > 0

    def test_therapeutic_strategies_populated(self):
        result = analyze_neurodegeneration("parkinsons")
        assert len(result.therapeutic_strategies) > 0

    def test_structural_targets_populated(self):
        result = analyze_neurodegeneration("als")
        assert len(result.structural_targets) > 0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestMisfoldingAPI:
    def test_assess_risk_known_gene(self, client: TestClient):
        resp = client.post("/misfolding/assess-risk", json={"gene": "CFTR"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["gene"] == "CFTR"
        assert data["risk_level"] in {"high", "moderate", "low"}
        assert "known_misfolding_disease" in data
        assert "confidence" in data

    def test_assess_risk_with_mutations(self, client: TestClient):
        resp = client.post(
            "/misfolding/assess-risk",
            json={"gene": "SOD1", "mutations": ["A4V"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk_level"] == "high"
        assert "A4V" in data["destabilizing_mutations"]

    def test_aggregation_regions_hydrophobic(self, client: TestClient):
        resp = client.post(
            "/misfolding/aggregation-regions",
            json={"protein_sequence": _HYDROPHOBIC_SEQ},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "region_count" in data
        assert "regions" in data
        assert data["sequence_length"] == len(_HYDROPHOBIC_SEQ)

    def test_aggregation_regions_empty_sequence(self, client: TestClient):
        resp = client.post("/misfolding/aggregation-regions", json={"protein_sequence": ""})
        assert resp.status_code == 422

    def test_chaperone_targets_known_gene(self, client: TestClient):
        resp = client.post("/misfolding/chaperone-targets", json={"gene": "TTR"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["target"]["mechanism"] in {"stabilization", "folding_correction", "trafficking_rescue"}

    def test_chaperone_targets_unknown_gene(self, client: TestClient):
        resp = client.post("/misfolding/chaperone-targets", json={"gene": "NOPE99"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False
        assert data["target"] is None

    def test_prion_domains_qn_rich(self, client: TestClient):
        resp = client.post(
            "/misfolding/prion-domains",
            json={"protein_sequence": _PRION_SEQ},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain_count"] > 0
        assert "domains" in data

    def test_prion_domains_empty_sequence(self, client: TestClient):
        resp = client.post("/misfolding/prion-domains", json={"protein_sequence": ""})
        assert resp.status_code == 422

    def test_lsd_analysis_known_gene(self, client: TestClient):
        resp = client.post("/misfolding/lsd-analysis", json={"gene": "GBA"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "gaucher" in data["analysis"]["disease_name"].lower()

    def test_lsd_analysis_unknown_gene(self, client: TestClient):
        resp = client.post("/misfolding/lsd-analysis", json={"gene": "UNKNOWNGENE"})
        assert resp.status_code == 200
        assert resp.json()["found"] is False

    def test_neurodegeneration_alzheimers(self, client: TestClient):
        resp = client.post("/misfolding/neurodegeneration", json={"disease": "alzheimers"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "alzheimer" in data["disease"].lower()

    def test_neurodegeneration_unknown(self, client: TestClient):
        resp = client.post("/misfolding/neurodegeneration", json={"disease": "fake_disease"})
        assert resp.status_code == 200
        assert resp.json()["found"] is False

    def test_known_diseases_endpoint(self, client: TestClient):
        resp = client.get("/misfolding/known-diseases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 15
        assert len(data["diseases"]) == data["count"]
        genes = {d["gene"] for d in data["diseases"]}
        assert "SNCA" in genes
        assert "PRNP" in genes
        assert "APP" in genes
