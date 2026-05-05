"""Tests for Drug Discovery Extensions Tier 2 (Phase 24).

Covers all 5 features + 10 API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.drug_discovery_ext import (
    AMINO_ACID_PROPERTIES,
    CHEMBL_MOCK_SIMILARITIES,
    KNOWN_CRYPTIC_SITES,
    BatchDDGResult,
    CrypticSite,
    DDGPrediction,
    DockingResult,
    DrugPipelineResult,
    PocketResult,
    TherapeuticReasoningResult,
    AllostericSite,
    AllosteryResult,
    ReasoningStep,
    _parse_variant,
    batch_predict_ddg,
    detect_cryptic_sites,
    dock_compound,
    predict_allostery,
    predict_ddg,
    predict_pockets,
    run_drug_pipeline,
    run_therapeutic_reasoning,
)
from backend.app.main import app

client = TestClient(app)

_MOCK_PDB = (
    "ATOM      1  CA  ALA A   1      1.000   2.000   3.000  1.00 10.00           C\n"
    * 50
)
_SEQ = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY" * 3


# ---------------------------------------------------------------------------
# Unit tests — Feature 1: Pocket prediction
# ---------------------------------------------------------------------------

class TestPredictPockets:
    def test_returns_list(self):
        result = predict_pockets(_MOCK_PDB, gene="KRAS")
        assert isinstance(result, list)

    def test_count_in_range(self):
        result = predict_pockets(_MOCK_PDB, gene="KRAS")
        assert 2 <= len(result) <= 5

    def test_pocket_result_type(self):
        result = predict_pockets(_MOCK_PDB, gene="EGFR")
        assert all(isinstance(p, PocketResult) for p in result)

    def test_rank_one_is_first(self):
        result = predict_pockets(_MOCK_PDB, gene="BRAF")
        assert result[0].rank == 1

    def test_sorted_by_druggability(self):
        result = predict_pockets(_MOCK_PDB, gene="ABL1")
        scores = [p.druggability_score for p in result]
        assert scores == sorted(scores, reverse=True)

    def test_druggability_in_range(self):
        result = predict_pockets(_MOCK_PDB, gene="TP53")
        for p in result:
            assert 0.0 <= p.druggability_score <= 1.0

    def test_center_is_3tuple(self):
        result = predict_pockets(_MOCK_PDB, gene="KRAS")
        for p in result:
            assert len(p.center) == 3

    def test_volume_positive(self):
        result = predict_pockets(_MOCK_PDB, gene="KRAS")
        for p in result:
            assert p.volume_angstrom3 > 0

    def test_residues_nonempty(self):
        result = predict_pockets(_MOCK_PDB, gene="KRAS")
        for p in result:
            assert len(p.residues) >= 6

    def test_deterministic(self):
        a = predict_pockets(_MOCK_PDB, gene="EGFR")
        b = predict_pockets(_MOCK_PDB, gene="EGFR")
        assert [p.druggability_score for p in a] == [p.druggability_score for p in b]

    def test_different_gene_different_result(self):
        a = predict_pockets(_MOCK_PDB, gene="EGFR")
        b = predict_pockets(_MOCK_PDB, gene="KRAS")
        assert [p.pocket_id for p in a] != [p.pocket_id for p in b] or \
               [p.druggability_score for p in a] != [p.druggability_score for p in b]


# ---------------------------------------------------------------------------
# Unit tests — Feature 1: Docking
# ---------------------------------------------------------------------------

class TestDockCompound:
    def setup_method(self):
        self.pockets = predict_pockets(_MOCK_PDB, gene="EGFR")
        self.top = self.pockets[0]

    def test_returns_docking_result(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert isinstance(result, DockingResult)

    def test_binding_energy_negative(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert result.binding_energy_kcal < 0

    def test_score_in_range(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert 0.0 <= result.score <= 1.0

    def test_pose_rmsd_positive(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert result.pose_rmsd > 0

    def test_contact_residues_nonempty(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert len(result.contact_residues) >= 3

    def test_compound_name_preserved(self):
        result = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "MyDrug")
        assert result.compound_name == "MyDrug"

    def test_deterministic(self):
        a = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        b = dock_compound(self.top, "CC(=O)Oc1ccccc1C(=O)O", "aspirin")
        assert a.binding_energy_kcal == b.binding_energy_kcal


# ---------------------------------------------------------------------------
# Unit tests — Feature 1: Full pipeline
# ---------------------------------------------------------------------------

class TestRunDrugPipeline:
    def test_returns_pipeline_result(self):
        result = run_drug_pipeline("EGFR")
        assert isinstance(result, DrugPipelineResult)

    def test_has_pockets(self):
        result = run_drug_pipeline("EGFR")
        assert len(result.pockets) >= 2

    def test_has_docking_results(self):
        result = run_drug_pipeline("EGFR")
        assert len(result.docking_results) > 0

    def test_best_compound_is_string(self):
        result = run_drug_pipeline("KRAS")
        assert isinstance(result.best_compound, str)

    def test_runtime_positive(self):
        result = run_drug_pipeline("BRAF")
        assert result.pipeline_runtime_sec >= 0

    def test_custom_library(self):
        lib = [{"name": "TestDrug", "smiles": "CC"}]
        result = run_drug_pipeline("ABL1", compound_library=lib)
        assert result.best_compound == "TestDrug"

    def test_docking_sorted_by_energy(self):
        result = run_drug_pipeline("EGFR")
        energies = [d.binding_energy_kcal for d in result.docking_results]
        assert energies == sorted(energies)


# ---------------------------------------------------------------------------
# Unit tests — Feature 2: Cryptic sites
# ---------------------------------------------------------------------------

class TestDetectCrypticSites:
    def test_returns_list(self):
        sites = detect_cryptic_sites(_SEQ, gene="KRAS")
        assert isinstance(sites, list)

    def test_known_gene_has_site(self):
        sites = detect_cryptic_sites(_SEQ, gene="ABL1")
        assert len(sites) >= 1

    def test_known_gene_site_type(self):
        sites = detect_cryptic_sites(_SEQ, gene="ABL1")
        assert isinstance(sites[0], CrypticSite)

    def test_trigger_valid(self):
        sites = detect_cryptic_sites(_SEQ, gene="MAPK14")
        valid = {"ligand_induced", "conformational", "allosteric"}
        for s in sites:
            assert s.trigger in valid

    def test_opening_prob_in_range(self):
        sites = detect_cryptic_sites(_SEQ, gene="IL2")
        for s in sites:
            assert 0.0 <= s.opening_probability <= 1.0

    def test_druggability_in_range(self):
        sites = detect_cryptic_sites(_SEQ, gene="MDM2")
        for s in sites:
            assert 0.0 <= s.druggability_if_open <= 1.0

    def test_confidence_in_range(self):
        sites = detect_cryptic_sites(_SEQ, gene="HIV1_PR")
        for s in sites:
            assert 0.0 <= s.confidence <= 1.0

    def test_known_cryptic_db_count(self):
        assert len(KNOWN_CRYPTIC_SITES) == 8

    def test_de_novo_for_unknown_gene(self):
        # Unknown gene should still run without error
        hydrophobic_seq = "VVILMFFYWWCAILVMFFYW" * 10
        sites = detect_cryptic_sites(hydrophobic_seq, gene="UNKNOWNGENE999")
        assert isinstance(sites, list)


# ---------------------------------------------------------------------------
# Unit tests — Feature 3: Allostery
# ---------------------------------------------------------------------------

class TestPredictAllostery:
    def test_returns_allostery_result(self):
        result = predict_allostery(_SEQ, gene="EGFR")
        assert isinstance(result, AllosteryResult)

    def test_known_gene_active_site(self):
        result = predict_allostery(_SEQ, gene="EGFR")
        assert len(result.active_site_residues) >= 1

    def test_allosteric_sites_nonempty(self):
        result = predict_allostery(_SEQ, gene="KRAS")
        assert len(result.allosteric_sites) >= 1

    def test_allosteric_site_type(self):
        result = predict_allostery(_SEQ, gene="BRAF")
        for s in result.allosteric_sites:
            assert isinstance(s, AllostericSite)

    def test_modulation_type_valid(self):
        result = predict_allostery(_SEQ, gene="ABL1")
        valid = {"positive", "negative", "switch"}
        for s in result.allosteric_sites:
            assert s.modulation_type in valid

    def test_communication_score_in_range(self):
        result = predict_allostery(_SEQ, gene="EGFR")
        for s in result.allosteric_sites:
            assert 0.0 <= s.communication_score <= 1.0

    def test_druggability_in_range(self):
        result = predict_allostery(_SEQ, gene="KRAS")
        for s in result.allosteric_sites:
            assert 0.0 <= s.druggability <= 1.0

    def test_pathways_match_site_count(self):
        result = predict_allostery(_SEQ, gene="EGFR")
        assert len(result.communication_pathways) == len(result.allosteric_sites)

    def test_overall_potential_in_range(self):
        result = predict_allostery(_SEQ, gene="EGFR")
        assert 0.0 <= result.overall_allosteric_potential <= 1.0

    def test_custom_active_site_residues(self):
        result = predict_allostery(_SEQ, gene="NOVEL", active_site_residues=[10, 25, 50])
        assert len(result.active_site_residues) >= 1


# ---------------------------------------------------------------------------
# Unit tests — Feature 4: Therapeutic reasoning
# ---------------------------------------------------------------------------

class TestTherapeuticReasoning:
    def test_returns_result(self):
        result = run_therapeutic_reasoning("EGFR", "T790M")
        assert isinstance(result, TherapeuticReasoningResult)

    def test_has_six_steps(self):
        result = run_therapeutic_reasoning("EGFR", "T790M")
        assert len(result.steps) == 6

    def test_steps_are_ordered(self):
        result = run_therapeutic_reasoning("KRAS", "G12C")
        step_nums = [s.step for s in result.steps]
        assert step_nums == list(range(1, 7))

    def test_step_type(self):
        result = run_therapeutic_reasoning("ABL1", "T315I")
        for s in result.steps:
            assert isinstance(s, ReasoningStep)

    def test_step_confidence_in_range(self):
        result = run_therapeutic_reasoning("BRAF", "V600E")
        for s in result.steps:
            assert 0.0 <= s.confidence <= 1.0

    def test_known_gene_has_drug_matches(self):
        result = run_therapeutic_reasoning("EGFR", "L858R")
        assert len(result.existing_drug_matches) > 0

    def test_drug_match_fields(self):
        result = run_therapeutic_reasoning("ABL1", "T315I")
        for m in result.existing_drug_matches:
            assert "drug" in m
            assert "pocket_similarity" in m

    def test_novel_target_score_in_range(self):
        result = run_therapeutic_reasoning("KRAS", "G12D")
        assert 0.0 <= result.novel_target_score <= 1.0

    def test_chain_confidence_in_range(self):
        result = run_therapeutic_reasoning("EGFR", "T790M")
        assert 0.0 <= result.reasoning_chain_confidence <= 1.0

    def test_final_recommendation_nonempty(self):
        result = run_therapeutic_reasoning("BRAF", "V600E")
        assert len(result.final_recommendation) > 10

    def test_chembl_mock_count(self):
        assert len(CHEMBL_MOCK_SIMILARITIES) == 15


# ---------------------------------------------------------------------------
# Unit tests — Feature 5: DDG prediction
# ---------------------------------------------------------------------------

class TestPredictDDG:
    def test_returns_ddg_prediction(self):
        result = predict_ddg("EGFR", "T790M")
        assert isinstance(result, DDGPrediction)

    def test_stability_effect_valid(self):
        valid = {"stabilizing", "neutral", "destabilizing", "highly_destabilizing"}
        result = predict_ddg("BRAF", "V600E")
        assert result.stability_effect in valid

    def test_confidence_in_range(self):
        result = predict_ddg("KRAS", "G12C")
        assert 0.0 <= result.confidence <= 1.0

    def test_consensus_is_mean(self):
        result = predict_ddg("ABL1", "T315I")
        expected = round((result.ddg_foldx + result.ddg_rosetta + result.ddg_spurs) / 3.0, 2)
        assert abs(result.consensus_ddg - expected) < 0.01

    def test_deterministic(self):
        a = predict_ddg("EGFR", "T790M")
        b = predict_ddg("EGFR", "T790M")
        assert a.consensus_ddg == b.consensus_ddg

    def test_parse_variant_basic(self):
        parsed = _parse_variant("V600E")
        assert parsed == ("V", 600, "E")

    def test_parse_variant_invalid(self):
        parsed = _parse_variant("not_a_variant")
        assert parsed is None

    def test_aa_properties_count(self):
        assert len(AMINO_ACID_PROPERTIES) == 20

    def test_aa_properties_fields(self):
        for aa, props in AMINO_ACID_PROPERTIES.items():
            assert "hydrophobicity" in props
            assert "charge" in props
            assert "size" in props
            assert "flexibility" in props


class TestBatchPredictDDG:
    def test_returns_batch_result(self):
        result = batch_predict_ddg("EGFR", ["T790M", "L858R", "C797S"])
        assert isinstance(result, BatchDDGResult)

    def test_variant_count(self):
        variants = ["T790M", "L858R", "C797S"]
        result = batch_predict_ddg("EGFR", variants)
        assert len(result.variants) == 3

    def test_counts_add_up(self):
        variants = ["T790M", "L858R", "G12C", "G12D", "V600E"]
        result = batch_predict_ddg("MIXED", variants)
        neutral = sum(1 for p in result.variants if p.stability_effect == "neutral")
        assert result.destabilizing_count + result.stabilizing_count + neutral <= len(variants)

    def test_most_destabilizing_is_variant(self):
        result = batch_predict_ddg("KRAS", ["G12C", "G12D", "G12V"])
        if result.most_destabilizing is not None:
            assert result.most_destabilizing in ["G12C", "G12D", "G12V"]

    def test_single_variant(self):
        result = batch_predict_ddg("TP53", ["R248W"])
        assert len(result.variants) == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestApiPocketPrediction:
    def test_post_pocket_prediction_200(self):
        resp = client.post("/drug-ext/pocket-prediction", json={"pdb_data": _MOCK_PDB, "gene": "EGFR"})
        assert resp.status_code == 200

    def test_response_has_pockets(self):
        resp = client.post("/drug-ext/pocket-prediction", json={"pdb_data": _MOCK_PDB, "gene": "KRAS"})
        data = resp.json()
        assert "pockets" in data
        assert data["pocket_count"] >= 2

    def test_response_has_safety_label(self):
        resp = client.post("/drug-ext/pocket-prediction", json={"pdb_data": _MOCK_PDB, "gene": "BRAF"})
        assert "safety_label" in resp.json()


class TestApiDockCompound:
    def test_post_dock_200(self):
        resp = client.post("/drug-ext/dock-compound", json={
            "pdb_data": _MOCK_PDB,
            "gene": "EGFR",
            "compound_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "compound_name": "aspirin",
        })
        assert resp.status_code == 200

    def test_response_has_docking_result(self):
        resp = client.post("/drug-ext/dock-compound", json={
            "pdb_data": _MOCK_PDB,
            "gene": "EGFR",
            "compound_smiles": "CC(=O)Oc1ccccc1C(=O)O",
            "compound_name": "aspirin",
        })
        data = resp.json()
        assert "docking_result" in data
        assert data["docking_result"]["binding_energy_kcal"] < 0


class TestApiFullPipeline:
    def test_post_full_pipeline_200(self):
        resp = client.post("/drug-ext/full-pipeline", json={"target_gene": "EGFR"})
        assert resp.status_code == 200

    def test_response_best_compound(self):
        resp = client.post("/drug-ext/full-pipeline", json={"target_gene": "EGFR"})
        data = resp.json()
        assert "best_compound" in data
        assert data["best_compound"] is not None

    def test_custom_library(self):
        resp = client.post("/drug-ext/full-pipeline", json={
            "target_gene": "KRAS",
            "compound_library": [{"name": "FakeDrug", "smiles": "CC"}],
        })
        assert resp.status_code == 200
        assert resp.json()["best_compound"] == "FakeDrug"


class TestApiCrypticSites:
    def test_post_cryptic_sites_200(self):
        resp = client.post("/drug-ext/cryptic-sites", json={"sequence": _SEQ, "gene": "ABL1"})
        assert resp.status_code == 200

    def test_response_structure(self):
        resp = client.post("/drug-ext/cryptic-sites", json={"sequence": _SEQ, "gene": "ABL1"})
        data = resp.json()
        assert "cryptic_sites" in data
        assert data["cryptic_site_count"] >= 1

    def test_get_known_cryptic_sites_200(self):
        resp = client.get("/drug-ext/known-cryptic-sites")
        assert resp.status_code == 200

    def test_known_cryptic_sites_count(self):
        resp = client.get("/drug-ext/known-cryptic-sites")
        data = resp.json()
        assert data["count"] == 8
        assert "proteins" in data


class TestApiAllostery:
    def test_post_allostery_200(self):
        resp = client.post("/drug-ext/allostery", json={"sequence": _SEQ, "gene": "EGFR"})
        assert resp.status_code == 200

    def test_response_has_allosteric_sites(self):
        resp = client.post("/drug-ext/allostery", json={"sequence": _SEQ, "gene": "KRAS"})
        data = resp.json()
        assert "allosteric_sites" in data
        assert data["allosteric_site_count"] >= 1

    def test_response_has_pathways(self):
        resp = client.post("/drug-ext/allostery", json={"sequence": _SEQ, "gene": "EGFR"})
        data = resp.json()
        assert "communication_pathways" in data

    def test_response_has_safety_label(self):
        resp = client.post("/drug-ext/allostery", json={"sequence": _SEQ, "gene": "BRAF"})
        assert "safety_label" in resp.json()


class TestApiTherapeuticReasoning:
    def test_post_therapeutic_reasoning_200(self):
        resp = client.post("/drug-ext/therapeutic-reasoning", json={"gene": "EGFR", "variant": "T790M"})
        assert resp.status_code == 200

    def test_response_has_steps(self):
        resp = client.post("/drug-ext/therapeutic-reasoning", json={"gene": "EGFR", "variant": "T790M"})
        data = resp.json()
        assert data["step_count"] == 6

    def test_response_has_drug_matches(self):
        resp = client.post("/drug-ext/therapeutic-reasoning", json={"gene": "ABL1", "variant": "T315I"})
        data = resp.json()
        assert len(data["existing_drug_matches"]) > 0

    def test_response_has_recommendation(self):
        resp = client.post("/drug-ext/therapeutic-reasoning", json={"gene": "KRAS", "variant": "G12C"})
        assert len(resp.json()["final_recommendation"]) > 10


class TestApiDDG:
    def test_post_predict_ddg_200(self):
        resp = client.post("/drug-ext/predict-ddg", json={"gene": "EGFR", "variant": "T790M"})
        assert resp.status_code == 200

    def test_post_predict_ddg_fields(self):
        resp = client.post("/drug-ext/predict-ddg", json={"gene": "BRAF", "variant": "V600E"})
        data = resp.json()
        assert "consensus_ddg" in data
        assert "stability_effect" in data
        assert "ddg_foldx" in data
        assert "ddg_rosetta" in data
        assert "ddg_spurs" in data

    def test_post_batch_ddg_200(self):
        resp = client.post("/drug-ext/batch-ddg", json={
            "gene": "EGFR",
            "variants": ["T790M", "L858R", "C797S"],
        })
        assert resp.status_code == 200

    def test_post_batch_ddg_count(self):
        resp = client.post("/drug-ext/batch-ddg", json={
            "gene": "KRAS",
            "variants": ["G12C", "G12D"],
        })
        assert resp.json()["variant_count"] == 2

    def test_post_batch_ddg_empty_422(self):
        resp = client.post("/drug-ext/batch-ddg", json={"gene": "EGFR", "variants": []})
        assert resp.status_code == 422

    def test_get_amino_acid_properties_200(self):
        resp = client.get("/drug-ext/amino-acid-properties")
        assert resp.status_code == 200

    def test_get_amino_acid_properties_count(self):
        resp = client.get("/drug-ext/amino-acid-properties")
        data = resp.json()
        assert data["property_count"] == 20
        assert "properties" in data
        assert len(data["properties"]) == 20
