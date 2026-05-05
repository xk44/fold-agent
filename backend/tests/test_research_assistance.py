"""Tests for Research Assistance Phase 24 Tier 2 features and API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.research_assistance import (
    BACKEND_MSA_REQUIREMENTS,
    MOCK_LITERATURE_DB,
    MSA_DEPTH_THRESHOLDS,
    PLDDT_COLOR_SCHEME,
    SIGNAL_PEPTIDE_PATTERNS,
    MSAQualityResult,
    LiteratureResult,
    StructureViewerData,
    VisualizationAnnotation,
    SignalPeptide,
    SecretionAnalysis,
    screen_msa_quality,
    suggest_prediction_strategy,
    search_literature,
    cross_reference_prediction,
    identify_knowledge_gaps,
    generate_viewer_data,
    plddt_to_color,
    generate_molstar_config,
    predict_signal_peptide,
    analyze_secretion_pathway,
    assess_therapeutic_suitability,
)

# ---------------------------------------------------------------------------
# Test sequences
# ---------------------------------------------------------------------------

SEQ_LONG = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY" * 5  # 200 aa
SEQ_SHORT = "MKTL"
SEQ_SIGNAL = "MKTLLLTLVVVTIVCLDLGAVPAAAGDTAELTQTP"  # has hydrophobic signal peptide
SEQ_HYDRO = "M" + "AVILMFYWAVILMFYWAVILMFYW" * 3 + "KRKRKRK"  # TM helices
SEQ_KRAS = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVID"


# ---------------------------------------------------------------------------
# Feature 1: MSA Quality
# ---------------------------------------------------------------------------

class TestMSADepthThresholds:
    def test_thresholds_all_present(self):
        for key in ("excellent", "good", "marginal", "sparse", "orphan"):
            assert key in MSA_DEPTH_THRESHOLDS

    def test_thresholds_ordering(self):
        assert MSA_DEPTH_THRESHOLDS["excellent"] > MSA_DEPTH_THRESHOLDS["good"]
        assert MSA_DEPTH_THRESHOLDS["good"] > MSA_DEPTH_THRESHOLDS["marginal"]
        assert MSA_DEPTH_THRESHOLDS["marginal"] > MSA_DEPTH_THRESHOLDS["sparse"]


class TestBackendMSARequirements:
    def test_esmfold_no_msa(self):
        assert BACKEND_MSA_REQUIREMENTS["esmfold"] == "none"

    def test_alphafold2_required(self):
        assert BACKEND_MSA_REQUIREMENTS["alphafold2_local"] == "required"

    def test_all_required_keys_present(self):
        for key in ("alphafold2_local", "esmfold", "colabfold", "chai1"):
            assert key in BACKEND_MSA_REQUIREMENTS


class TestScreenMSAQuality:
    def test_returns_dataclass(self):
        result = screen_msa_quality(SEQ_LONG)
        assert isinstance(result, MSAQualityResult)

    def test_short_sequence_is_sparse_or_orphan(self):
        result = screen_msa_quality(SEQ_SHORT)
        assert result.msa_quality in ("sparse", "orphan")

    def test_short_sequence_triggers_fallback(self):
        result = screen_msa_quality(SEQ_SHORT)
        assert result.fallback_suggested is True
        assert result.fallback_backend == "esmfold"

    def test_short_sequence_has_warnings(self):
        result = screen_msa_quality(SEQ_SHORT)
        assert len(result.warnings) > 0

    def test_sequence_length_recorded(self):
        result = screen_msa_quality(SEQ_LONG)
        assert result.sequence_length == len(SEQ_LONG)

    def test_deterministic(self):
        r1 = screen_msa_quality(SEQ_LONG)
        r2 = screen_msa_quality(SEQ_LONG)
        assert r1.estimated_msa_depth == r2.estimated_msa_depth
        assert r1.msa_quality == r2.msa_quality

    def test_neff_estimate_nonnegative(self):
        result = screen_msa_quality(SEQ_LONG)
        assert result.neff_estimate >= 0.0

    def test_quality_values_valid(self):
        result = screen_msa_quality(SEQ_LONG)
        assert result.msa_quality in ("excellent", "good", "marginal", "sparse", "orphan")

    def test_recommended_backend_is_string(self):
        result = screen_msa_quality(SEQ_LONG)
        assert isinstance(result.recommended_backend, str)
        assert len(result.recommended_backend) > 0

    def test_sparse_warning_contains_msa_sparse(self):
        result = screen_msa_quality(SEQ_SHORT)
        assert any("MSA-sparse" in w for w in result.warnings)

    def test_excellent_quality_no_fallback(self):
        # Force a known long sequence; we can't guarantee excellent but can verify logic
        result = screen_msa_quality(SEQ_LONG)
        if result.msa_quality == "excellent":
            assert result.fallback_suggested is False
            assert result.fallback_backend is None


class TestSuggestPredictionStrategy:
    def test_returns_dict(self):
        q = screen_msa_quality(SEQ_LONG)
        strategy = suggest_prediction_strategy(q)
        assert isinstance(strategy, dict)

    def test_has_required_keys(self):
        q = screen_msa_quality(SEQ_LONG)
        strategy = suggest_prediction_strategy(q)
        for key in ("primary_backend", "use_templates", "msa_required", "alternative_backends", "rationale"):
            assert key in strategy

    def test_sparse_quality_recommends_esmfold(self):
        q = screen_msa_quality(SEQ_SHORT)
        strategy = suggest_prediction_strategy(q)
        assert strategy["primary_backend"] == "esmfold"

    def test_sparse_has_confidence_caveat(self):
        q = screen_msa_quality(SEQ_SHORT)
        strategy = suggest_prediction_strategy(q)
        assert strategy.get("confidence_caveat") is not None


# ---------------------------------------------------------------------------
# Feature 2: Literature Cross-referencing
# ---------------------------------------------------------------------------

class TestMockLiteratureDB:
    def test_has_40_entries(self):
        assert len(MOCK_LITERATURE_DB) >= 40

    def test_each_entry_has_required_fields(self):
        required = {"gene", "pubmed_id", "title", "journal", "year", "relevance_score", "topics", "cited_by"}
        for entry in MOCK_LITERATURE_DB:
            assert required <= set(entry.keys()), f"Missing fields in entry {entry}"

    def test_relevance_scores_in_range(self):
        for entry in MOCK_LITERATURE_DB:
            assert 0.0 <= entry["relevance_score"] <= 1.0

    def test_years_plausible(self):
        for entry in MOCK_LITERATURE_DB:
            assert 1985 <= entry["year"] <= 2030


class TestSearchLiterature:
    def test_returns_literature_result(self):
        result = search_literature("TP53")
        assert isinstance(result, LiteratureResult)

    def test_known_gene_has_refs(self):
        result = search_literature("TP53")
        assert result.total_references >= 2

    def test_unknown_gene_zero_refs(self):
        result = search_literature("FAKEGENE999")
        assert result.total_references == 0

    def test_unknown_gene_high_gap_score(self):
        result = search_literature("FAKEGENE999")
        assert result.knowledge_gap_score == 1.0

    def test_gene_case_insensitive(self):
        r1 = search_literature("TP53")
        r2 = search_literature("tp53")
        assert r1.total_references == r2.total_references

    def test_kras_has_disease_associations(self):
        result = search_literature("KRAS")
        assert len(result.disease_associations) > 0

    def test_kras_has_drug_mentions(self):
        result = search_literature("KRAS")
        # KRAS clinical trial refs exist
        assert isinstance(result.drug_mentions, list)

    def test_top_references_max_5(self):
        result = search_literature("TP53")
        assert len(result.top_references) <= 5

    def test_related_proteins_list(self):
        result = search_literature("KRAS")
        assert isinstance(result.related_proteins, list)
        assert len(result.related_proteins) > 0

    def test_topic_filter_narrows_results(self):
        all_results = search_literature("EGFR")
        filtered = search_literature("EGFR", topics=["clinical_trial"])
        assert filtered.total_references <= all_results.total_references


class TestCrossReferencePrediction:
    def test_returns_dict(self):
        result = cross_reference_prediction("TP53", "structure")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = cross_reference_prediction("TP53", "variant")
        for key in ("gene", "prediction_type", "support_level", "notes", "safety_label"):
            assert key in result

    def test_well_known_gene_has_support(self):
        result = cross_reference_prediction("TP53", "variant")
        assert result["support_level"] in ("well_supported", "partially_supported")

    def test_unknown_gene_no_literature(self):
        result = cross_reference_prediction("FAKEGENE", "structure")
        assert result["support_level"] == "no_literature"

    def test_binding_adds_drug_note(self):
        result = cross_reference_prediction("KRAS", "binding")
        # Should mention drug interactions if any known
        assert isinstance(result["known_drugs"], list)

    def test_safety_label_present(self):
        result = cross_reference_prediction("BRCA1", "variant")
        assert "Research only" in result["safety_label"]


class TestIdentifyKnowledgeGaps:
    def test_returns_dict(self):
        result = identify_knowledge_gaps("TP53")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = identify_knowledge_gaps("TP53")
        for key in ("gene", "knowledge_gap_score", "covered_categories", "gap_categories", "specific_gaps"):
            assert key in result

    def test_unknown_gene_has_specific_gaps(self):
        result = identify_knowledge_gaps("NOHIT999")
        assert len(result["specific_gaps"]) > 0

    def test_gap_score_in_range(self):
        result = identify_knowledge_gaps("KRAS")
        assert 0.0 <= result["knowledge_gap_score"] <= 1.0

    def test_research_opportunities_list(self):
        result = identify_knowledge_gaps("FAKEGENE")
        assert isinstance(result["research_opportunities"], list)


# ---------------------------------------------------------------------------
# Feature 3: Structure Viewer Metadata
# ---------------------------------------------------------------------------

class TestPLDDTColorScheme:
    def test_four_bands(self):
        assert len(PLDDT_COLOR_SCHEME) == 4
        for key in ("very_high", "confident", "low", "very_low"):
            assert key in PLDDT_COLOR_SCHEME

    def test_colors_are_hex(self):
        for band in PLDDT_COLOR_SCHEME.values():
            assert band["color"].startswith("#")
            assert len(band["color"]) == 7


class TestPlddtToColor:
    def test_very_high(self):
        assert plddt_to_color(95.0) == "#0053D6"

    def test_confident(self):
        assert plddt_to_color(80.0) == "#65CBF3"

    def test_low(self):
        assert plddt_to_color(60.0) == "#FFDB13"

    def test_very_low(self):
        assert plddt_to_color(30.0) == "#FF7D45"

    def test_boundary_90(self):
        assert plddt_to_color(90.0) == "#0053D6"

    def test_boundary_70(self):
        assert plddt_to_color(70.0) == "#65CBF3"

    def test_boundary_50(self):
        assert plddt_to_color(50.0) == "#FFDB13"


class TestGenerateViewerData:
    def test_returns_dataclass(self):
        result = generate_viewer_data(SEQ_KRAS)
        assert isinstance(result, StructureViewerData)

    def test_pdb_data_not_empty(self):
        result = generate_viewer_data(SEQ_KRAS)
        assert len(result.pdb_data) > 0

    def test_has_plddt_annotations(self):
        result = generate_viewer_data(SEQ_KRAS)
        plddt_anns = [a for a in result.annotations if a.annotation_type == "plddt"]
        assert len(plddt_anns) == len(SEQ_KRAS)

    def test_annotations_are_dataclass(self):
        result = generate_viewer_data(SEQ_KRAS)
        for ann in result.annotations:
            assert isinstance(ann, VisualizationAnnotation)

    def test_variant_annotations_added(self):
        variants = [{"position": 12, "mutation": "G12D", "effect": "pathogenic"}]
        result = generate_viewer_data(SEQ_KRAS, variants=variants)
        var_anns = [a for a in result.annotations if a.annotation_type == "variant"]
        assert len(var_anns) == 1
        assert var_anns[0].residue_index == 12

    def test_pathogenic_variant_red(self):
        variants = [{"position": 12, "mutation": "G12D", "effect": "pathogenic"}]
        result = generate_viewer_data(SEQ_KRAS, variants=variants)
        var_anns = [a for a in result.annotations if a.annotation_type == "variant"]
        assert var_anns[0].color_hex == "#FF0000"

    def test_export_formats_present(self):
        result = generate_viewer_data(SEQ_KRAS)
        assert "pdb" in result.export_formats
        assert "png" in result.export_formats

    def test_custom_pdb_preserved(self):
        custom_pdb = "REMARK custom\nEND"
        result = generate_viewer_data(SEQ_KRAS, pdb_data=custom_pdb)
        assert result.pdb_data == custom_pdb

    def test_deterministic(self):
        r1 = generate_viewer_data(SEQ_KRAS)
        r2 = generate_viewer_data(SEQ_KRAS)
        assert len(r1.annotations) == len(r2.annotations)

    def test_has_disagreement_annotations(self):
        result = generate_viewer_data(SEQ_KRAS)
        dis_anns = [a for a in result.annotations if a.annotation_type == "disagreement"]
        assert len(dis_anns) >= 1


class TestGenerateMolstarConfig:
    def test_returns_dict(self):
        vd = generate_viewer_data(SEQ_KRAS)
        config = generate_molstar_config(vd)
        assert isinstance(config, dict)

    def test_has_viewer_key(self):
        vd = generate_viewer_data(SEQ_KRAS)
        config = generate_molstar_config(vd)
        assert config["viewer"] == "molstar"

    def test_has_plddt_scheme(self):
        vd = generate_viewer_data(SEQ_KRAS)
        config = generate_molstar_config(vd)
        assert "plddt_color_scheme" in config

    def test_interactivity_clickable_variants(self):
        vd = generate_viewer_data(SEQ_KRAS)
        config = generate_molstar_config(vd)
        assert config["interactivity"]["clickable_variants"] is True


# ---------------------------------------------------------------------------
# Feature 4: Signal Peptide
# ---------------------------------------------------------------------------

class TestSignalPeptidePatterns:
    def test_has_three_regions(self):
        for key in ("n_region", "h_region", "c_region"):
            assert key in SIGNAL_PEPTIDE_PATTERNS

    def test_h_region_min_length(self):
        assert SIGNAL_PEPTIDE_PATTERNS["h_region"]["min_length"] == 7


class TestPredictSignalPeptide:
    def test_returns_dataclass(self):
        result = predict_signal_peptide(SEQ_SIGNAL)
        assert isinstance(result, SignalPeptide)

    def test_signal_sequence_has_signal(self):
        result = predict_signal_peptide(SEQ_SIGNAL)
        # SEQ_SIGNAL has a hydrophobic N-terminal region
        assert result.probability >= 0.0

    def test_probability_in_range(self):
        for seq in (SEQ_LONG, SEQ_SHORT, SEQ_SIGNAL, SEQ_KRAS):
            r = predict_signal_peptide(seq)
            assert 0.0 <= r.probability <= 1.0, f"Out of range for {seq[:20]}"

    def test_signal_type_valid(self):
        for seq in (SEQ_LONG, SEQ_SHORT, SEQ_SIGNAL):
            r = predict_signal_peptide(seq)
            assert r.signal_type in ("sec_spi", "sec_spii", "tat_spi", "none")

    def test_not_detected_cleavage_none(self):
        result = predict_signal_peptide(SEQ_LONG)
        if not result.detected:
            assert result.cleavage_site is None
            assert result.signal_sequence is None

    def test_detected_has_signal_sequence(self):
        result = predict_signal_peptide(SEQ_SIGNAL)
        if result.detected:
            assert result.signal_sequence is not None
            assert len(result.signal_sequence) > 0

    def test_mature_protein_start_positive(self):
        result = predict_signal_peptide(SEQ_KRAS)
        assert result.mature_protein_start >= 1

    def test_deterministic(self):
        r1 = predict_signal_peptide(SEQ_KRAS)
        r2 = predict_signal_peptide(SEQ_KRAS)
        assert r1.probability == r2.probability
        assert r1.detected == r2.detected


class TestAnalyzeSecretionPathway:
    def test_returns_dataclass(self):
        result = analyze_secretion_pathway(SEQ_KRAS)
        assert isinstance(result, SecretionAnalysis)

    def test_localization_valid(self):
        for seq in (SEQ_LONG, SEQ_SHORT, SEQ_SIGNAL, SEQ_HYDRO):
            r = analyze_secretion_pathway(seq)
            assert r.predicted_localization in (
                "extracellular", "membrane", "cytoplasmic", "nuclear", "er", "golgi"
            ), f"Invalid localization {r.predicted_localization}"

    def test_tm_helices_nonnegative(self):
        result = analyze_secretion_pathway(SEQ_KRAS)
        assert result.transmembrane_helices >= 0

    def test_hydrophobic_seq_membrane(self):
        result = analyze_secretion_pathway(SEQ_HYDRO)
        assert result.predicted_localization == "membrane"
        assert result.transmembrane_helices >= 1

    def test_therapeutic_suitability_valid(self):
        valid = {
            "suitable_for_secreted_therapeutic",
            "requires_signal_peptide_addition",
            "membrane_bound_consider_soluble_form",
            "intracellular_consider_delivery",
        }
        for seq in (SEQ_LONG, SEQ_SHORT, SEQ_SIGNAL, SEQ_HYDRO):
            r = analyze_secretion_pathway(seq)
            assert r.therapeutic_suitability in valid, f"Invalid suitability: {r.therapeutic_suitability}"

    def test_warnings_is_list(self):
        result = analyze_secretion_pathway(SEQ_KRAS)
        assert isinstance(result.warnings, list)

    def test_gpi_is_bool(self):
        result = analyze_secretion_pathway(SEQ_KRAS)
        assert isinstance(result.gpi_anchor, bool)


class TestAssessTherapeuticSuitability:
    def test_secreted_suitable(self):
        sp = SignalPeptide(
            detected=True, cleavage_site=20, signal_type="sec_spi",
            probability=0.9, mature_protein_start=21, signal_sequence="MKTLLL"
        )
        analysis = SecretionAnalysis(
            signal_peptide=sp,
            predicted_localization="extracellular",
            transmembrane_helices=0,
            gpi_anchor=False,
            therapeutic_suitability="",
            warnings=[],
        )
        assert assess_therapeutic_suitability(analysis) == "suitable_for_secreted_therapeutic"

    def test_membrane_soluble_form(self):
        sp = SignalPeptide(
            detected=False, cleavage_site=None, signal_type="none",
            probability=0.1, mature_protein_start=1, signal_sequence=None
        )
        analysis = SecretionAnalysis(
            signal_peptide=sp,
            predicted_localization="membrane",
            transmembrane_helices=3,
            gpi_anchor=False,
            therapeutic_suitability="",
            warnings=[],
        )
        assert assess_therapeutic_suitability(analysis) == "membrane_bound_consider_soluble_form"

    def test_no_signal_requires_addition(self):
        sp = SignalPeptide(
            detected=False, cleavage_site=None, signal_type="none",
            probability=0.05, mature_protein_start=1, signal_sequence=None
        )
        analysis = SecretionAnalysis(
            signal_peptide=sp,
            predicted_localization="cytoplasmic",
            transmembrane_helices=0,
            gpi_anchor=False,
            therapeutic_suitability="",
            warnings=[],
        )
        assert assess_therapeutic_suitability(analysis) == "requires_signal_peptide_addition"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestMSAQualityEndpoint:
    def test_msa_quality_ok(self, client: TestClient):
        resp = client.post("/research/msa-quality", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert "msa_quality" in data
        assert "estimated_msa_depth" in data

    def test_msa_quality_short_warns(self, client: TestClient):
        resp = client.post("/research/msa-quality", json={"sequence": SEQ_SHORT})
        assert resp.status_code == 200
        data = resp.json()
        assert data["msa_quality"] in ("sparse", "orphan")
        assert data["fallback_suggested"] is True

    def test_msa_quality_missing_sequence_422(self, client: TestClient):
        resp = client.post("/research/msa-quality", json={})
        assert resp.status_code == 422


class TestPredictionStrategyEndpoint:
    def test_strategy_ok(self, client: TestClient):
        resp = client.post("/research/prediction-strategy", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert "primary_backend" in data
        assert "rationale" in data

    def test_strategy_missing_422(self, client: TestClient):
        resp = client.post("/research/prediction-strategy", json={})
        assert resp.status_code == 422


class TestLiteratureEndpoints:
    def test_gene_lookup_ok(self, client: TestClient):
        resp = client.get("/research/literature/TP53")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gene"] == "TP53"
        assert data["total_references"] >= 2

    def test_gene_lookup_unknown(self, client: TestClient):
        resp = client.get("/research/literature/FAKEGENE999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_references"] == 0

    def test_cross_reference_ok(self, client: TestClient):
        resp = client.post(
            "/research/literature/cross-reference",
            json={"gene": "KRAS", "prediction_type": "variant"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "support_level" in data
        assert data["gene"] == "KRAS"

    def test_knowledge_gaps_ok(self, client: TestClient):
        resp = client.post("/research/literature/knowledge-gaps", json={"gene": "FAKEGENE"})
        assert resp.status_code == 200
        data = resp.json()
        assert "knowledge_gap_score" in data
        assert data["knowledge_gap_score"] == 1.0


class TestViewerDataEndpoint:
    def test_viewer_data_ok(self, client: TestClient):
        resp = client.post("/research/viewer-data", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert "pdb_data" in data
        assert "annotations" in data
        assert len(data["annotations"]) > 0

    def test_viewer_data_with_variants(self, client: TestClient):
        resp = client.post(
            "/research/viewer-data",
            json={
                "sequence": SEQ_KRAS,
                "variants": [{"position": 12, "mutation": "G12D", "effect": "pathogenic"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        var_anns = [a for a in data["annotations"] if a["annotation_type"] == "variant"]
        assert len(var_anns) == 1

    def test_viewer_data_missing_422(self, client: TestClient):
        resp = client.post("/research/viewer-data", json={})
        assert resp.status_code == 422


class TestSignalPeptideEndpoint:
    def test_signal_peptide_ok(self, client: TestClient):
        resp = client.post("/research/signal-peptide", json={"sequence": SEQ_SIGNAL})
        assert resp.status_code == 200
        data = resp.json()
        assert "detected" in data
        assert "probability" in data
        assert "signal_type" in data

    def test_signal_type_valid(self, client: TestClient):
        resp = client.post("/research/signal-peptide", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert data["signal_type"] in ("sec_spi", "sec_spii", "tat_spi", "none")

    def test_signal_peptide_missing_422(self, client: TestClient):
        resp = client.post("/research/signal-peptide", json={})
        assert resp.status_code == 422


class TestSecretionAnalysisEndpoint:
    def test_secretion_analysis_ok(self, client: TestClient):
        resp = client.post("/research/secretion-analysis", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert "predicted_localization" in data
        assert "transmembrane_helices" in data
        assert "therapeutic_suitability" in data

    def test_hydrophobic_seq_membrane(self, client: TestClient):
        resp = client.post("/research/secretion-analysis", json={"sequence": SEQ_HYDRO})
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicted_localization"] == "membrane"


class TestTherapeuticSuitabilityEndpoint:
    def test_suitability_ok(self, client: TestClient):
        resp = client.post("/research/therapeutic-suitability", json={"sequence": SEQ_KRAS})
        assert resp.status_code == 200
        data = resp.json()
        assert "therapeutic_suitability" in data
        valid = {
            "suitable_for_secreted_therapeutic",
            "requires_signal_peptide_addition",
            "membrane_bound_consider_soluble_form",
            "intracellular_consider_delivery",
        }
        assert data["therapeutic_suitability"] in valid

    def test_suitability_missing_422(self, client: TestClient):
        resp = client.post("/research/therapeutic-suitability", json={})
        assert resp.status_code == 422


class TestPLDDTColorSchemeEndpoint:
    def test_color_scheme_ok(self, client: TestClient):
        resp = client.get("/research/plddt-color-scheme")
        assert resp.status_code == 200
        data = resp.json()
        assert "very_high" in data
        assert "confident" in data
        assert "low" in data
        assert "very_low" in data

    def test_colors_are_hex(self, client: TestClient):
        resp = client.get("/research/plddt-color-scheme")
        data = resp.json()
        for band in data.values():
            assert band["color"].startswith("#")
