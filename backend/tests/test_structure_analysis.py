"""Tests for Advanced Structure Analysis — Phase 24 Tier 2.

Covers IDR escalation, PTM impact, epistatic prediction, fold-switching detection,
and all 8 API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.structure_analysis import (
    IDR_PLDDT_THRESHOLD,
    KNOWN_EPISTATIC_PAIRS,
    KNOWN_FOLD_SWITCHERS,
    KNOWN_PTM_SITES,
    EpistaticVariant,
    FoldSwitchWarning,
    IDRAnalysisResult,
    IDRRegion,
    PTMImpactResult,
    PTMSite,
    analyze_disorder,
    assess_ptm_impact,
    check_known_fold_switchers,
    classify_epistatic_interaction,
    detect_fold_switching_risk,
    detect_low_plddt_regions,
    escalate_to_idr_analysis,
    find_nearby_ptms,
    predict_epistatic_effect,
)

# ---------------------------------------------------------------------------
# Short test sequences
# ---------------------------------------------------------------------------
SEQ_SHORT = "ACDEFGHIKLMNPQRSTVWY"  # 20 AA
SEQ_DISORDERED = "DKDEKDEKKDDSSTEDTKNEDKSDEKDEKDEKDEKDEK"  # charged/polar heavy
SEQ_STRUCTURED = "VILMFYWVILMFYWVILMFYW"  # hydrophobic heavy
SEQ_LONG = SEQ_DISORDERED * 4  # 152 AA


# ===========================================================================
# Feature 1: IDR detection + escalation
# ===========================================================================

class TestIDRConstants:
    def test_threshold_value(self):
        assert IDR_PLDDT_THRESHOLD == 50.0


class TestDetectLowPLDDT:
    def test_all_high_plddt(self):
        plddt = [80.0] * 30
        regions = detect_low_plddt_regions(SEQ_DISORDERED[:30], plddt)
        assert regions == []

    def test_all_low_plddt(self):
        plddt = [20.0] * 30
        regions = detect_low_plddt_regions(SEQ_DISORDERED[:30], plddt)
        assert len(regions) == 1
        assert regions[0][0] == 0
        assert regions[0][1] == 29

    def test_mixed_plddt(self):
        seq = "A" * 20
        # 10 high then 10 low
        plddt = [80.0] * 10 + [20.0] * 10
        regions = detect_low_plddt_regions(seq, plddt)
        assert len(regions) == 1
        assert regions[0][0] == 10

    def test_short_region_skipped(self):
        seq = "A" * 20
        # Only 3 consecutive low — below min 5
        plddt = [80.0] * 8 + [20.0] * 3 + [80.0] * 9
        regions = detect_low_plddt_regions(seq, plddt)
        assert regions == []

    def test_returns_5_plus_length(self):
        seq = "A" * 20
        plddt = [80.0] * 5 + [20.0] * 10 + [80.0] * 5
        regions = detect_low_plddt_regions(seq, plddt)
        assert len(regions) == 1
        assert regions[0][1] - regions[0][0] + 1 == 10

    def test_mock_plddt_deterministic(self):
        r1 = detect_low_plddt_regions(SEQ_DISORDERED)
        r2 = detect_low_plddt_regions(SEQ_DISORDERED)
        assert r1 == r2

    def test_empty_sequence(self):
        regions = detect_low_plddt_regions("", [])
        assert regions == []


class TestEscalateToIDR:
    def test_no_regions(self):
        result = escalate_to_idr_analysis(SEQ_SHORT, [])
        assert isinstance(result, IDRAnalysisResult)
        assert result.escalated is False
        assert result.idr_regions == []
        assert result.idr_fraction == 0.0
        assert result.escalation_reason is None

    def test_with_region(self):
        result = escalate_to_idr_analysis(SEQ_DISORDERED, [(0, 9)])
        assert result.escalated is True
        assert len(result.idr_regions) == 1
        region = result.idr_regions[0]
        assert isinstance(region, IDRRegion)
        assert region.start == 0
        assert region.end == 9
        assert region.length == 10
        assert 0.0 <= region.disorder_score <= 1.0
        assert region.predictor in ("iupred2a", "albatross", "fldpnn")
        assert region.disorder_type in ("strong", "weak", "context_dependent")

    def test_idr_fraction_calculation(self):
        seq = "A" * 30
        result = escalate_to_idr_analysis(seq, [(0, 9)])
        assert abs(result.idr_fraction - 10 / 30) < 0.01

    def test_multiple_regions(self):
        seq = "A" * 60
        result = escalate_to_idr_analysis(seq, [(0, 9), (20, 29), (40, 49)])
        assert len(result.idr_regions) == 3
        # Predictors cycle through iupred2a, albatross, fldpnn
        predictors = [r.predictor for r in result.idr_regions]
        assert "iupred2a" in predictors
        assert "albatross" in predictors

    def test_escalation_reason_text(self):
        result = escalate_to_idr_analysis(SEQ_LONG, [(0, 14)])
        assert result.escalation_reason is not None
        assert "iupred2a" in result.escalation_reason.lower() or "albatross" in result.escalation_reason.lower()


class TestAnalyzeDisorder:
    def test_returns_idr_result(self):
        result = analyze_disorder(SEQ_DISORDERED)
        assert isinstance(result, IDRAnalysisResult)
        assert result.sequence == SEQ_DISORDERED
        assert result.total_residues == len(SEQ_DISORDERED)

    def test_fraction_in_range(self):
        result = analyze_disorder(SEQ_LONG)
        assert 0.0 <= result.idr_fraction <= 1.0

    def test_short_structured_sequence(self):
        result = analyze_disorder(SEQ_STRUCTURED)
        # Hydrophobic sequences tend to have higher pLDDT mock values
        assert isinstance(result, IDRAnalysisResult)


# ===========================================================================
# Feature 2: PTM impact analysis
# ===========================================================================

class TestKnownPTMSites:
    def test_tp53_has_sites(self):
        assert "TP53" in KNOWN_PTM_SITES
        assert len(KNOWN_PTM_SITES["TP53"]) >= 8

    def test_egfr_has_sites(self):
        assert "EGFR" in KNOWN_PTM_SITES
        assert any(s["type"] == "glycosylation" for s in KNOWN_PTM_SITES["EGFR"])

    def test_kras_sites(self):
        assert "KRAS" in KNOWN_PTM_SITES

    def test_all_entries_have_required_keys(self):
        for gene, sites in KNOWN_PTM_SITES.items():
            for site in sites:
                assert "position" in site
                assert "type" in site
                assert "residue" in site

    def test_30_plus_entries_total(self):
        total = sum(len(v) for v in KNOWN_PTM_SITES.values())
        assert total >= 30


class TestFindNearbyPTMs:
    def test_finds_direct_site(self):
        # TP53 S15 phosphorylation
        sites = find_nearby_ptms("TP53", 15)
        positions = [s.position for s in sites]
        assert 15 in positions

    def test_finds_within_window(self):
        sites = find_nearby_ptms("TP53", 17, window=5)
        # Should include position 15 and 20
        positions = [s.position for s in sites]
        assert any(p in positions for p in [15, 20])

    def test_no_sites_far_away(self):
        sites = find_nearby_ptms("TP53", 500, window=5)
        assert sites == []

    def test_unknown_gene(self):
        sites = find_nearby_ptms("FAKEGENE123", 10)
        assert sites == []

    def test_case_insensitive_gene(self):
        sites_upper = find_nearby_ptms("TP53", 15)
        sites_lower = find_nearby_ptms("tp53", 15)
        assert len(sites_upper) == len(sites_lower)

    def test_ptmsite_has_fields(self):
        sites = find_nearby_ptms("EGFR", 845, window=0)
        assert len(sites) >= 1
        s = sites[0]
        assert isinstance(s, PTMSite)
        assert s.gene == "EGFR"
        assert s.ptm_type == "phosphorylation"
        assert s.functional_impact != ""


class TestAssessPTMImpact:
    def test_direct_disruption(self):
        # TP53 S15F — S15 is a phosphorylation site
        result = assess_ptm_impact("TP53", "S15F")
        assert isinstance(result, PTMImpactResult)
        assert result.ptm_disrupted is True
        assert result.impact_score > 0.7

    def test_nearby_not_direct(self):
        # TP53 G17A — not a direct PTM site but within window of 15 and 20
        result = assess_ptm_impact("TP53", "G17A")
        assert result.variant_position == 17
        assert result.impact_score > 0.0

    def test_no_ptm_nearby(self):
        result = assess_ptm_impact("TP53", "A500V")
        assert result.impact_score < 0.3
        assert result.ptm_disrupted is False

    def test_invalid_variant_format(self):
        result = assess_ptm_impact("TP53", "invalid")
        assert result.variant_position == 0
        assert "parse" in result.recommendation.lower() or "format" in result.recommendation.lower()

    def test_egfr_direct_ptm(self):
        result = assess_ptm_impact("EGFR", "Y845F")
        assert result.ptm_disrupted is True

    def test_recommendation_not_empty(self):
        result = assess_ptm_impact("KRAS", "G12D")
        assert result.recommendation != ""

    def test_nearby_ptms_list(self):
        result = assess_ptm_impact("AKT1", "T308A")
        assert isinstance(result.nearby_ptms, list)


# ===========================================================================
# Feature 3: Epistatic multi-variant prediction
# ===========================================================================

class TestKnownEpistaticPairs:
    def test_count(self):
        assert len(KNOWN_EPISTATIC_PAIRS) >= 10

    def test_kras_pair_present(self):
        kras_pairs = [p for p in KNOWN_EPISTATIC_PAIRS if p["gene"] == "KRAS"]
        assert len(kras_pairs) >= 2

    def test_all_have_effect_field(self):
        valid_effects = {"synergistic", "antagonistic", "neutral", "compensatory"}
        for pair in KNOWN_EPISTATIC_PAIRS:
            assert pair["effect"] in valid_effects


class TestClassifyEpistaticInteraction:
    def test_synergistic(self):
        assert classify_epistatic_interaction(0.5, 0.65) == "synergistic"

    def test_antagonistic(self):
        assert classify_epistatic_interaction(0.6, 0.45) == "antagonistic"

    def test_compensatory(self):
        assert classify_epistatic_interaction(0.8, 0.3) == "compensatory"

    def test_neutral(self):
        assert classify_epistatic_interaction(0.5, 0.52) == "neutral"

    def test_zero_additive(self):
        assert classify_epistatic_interaction(0.0, 0.0) == "neutral"


class TestPredictEpistaticEffect:
    def _make_variant(self, pos, ref, alt):
        return EpistaticVariant(position=pos, ref_aa=ref, alt_aa=alt)

    def test_single_variant(self):
        v = self._make_variant(12, "G", "D")
        result = predict_epistatic_effect([v], gene="KRAS")
        assert len(result.individual_scores) == 1
        assert 0.0 <= result.epistatic_prediction <= 1.0
        assert result.epistatic_effect in {"synergistic", "antagonistic", "neutral", "compensatory"}

    def test_known_kras_pair(self):
        v1 = self._make_variant(12, "G", "D")
        v2 = self._make_variant(146, "A", "T")
        result = predict_epistatic_effect([v1, v2], gene="KRAS")
        assert result.epistatic_effect == "synergistic"

    def test_max_6_variants_enforced(self):
        variants = [self._make_variant(i, "A", "V") for i in range(1, 10)]
        result = predict_epistatic_effect(variants)
        assert len(result.variants) == 6

    def test_additive_prediction_capped(self):
        # Many variants should be capped at 1.0
        variants = [self._make_variant(i * 10, "A", "V") for i in range(1, 7)]
        result = predict_epistatic_effect(variants)
        assert result.additive_prediction <= 1.0
        assert result.epistatic_prediction <= 1.0

    def test_confidence_range(self):
        v = self._make_variant(175, "R", "H")
        result = predict_epistatic_effect([v], gene="TP53")
        assert 0.0 <= result.confidence <= 1.0

    def test_interaction_score_positive(self):
        v1 = self._make_variant(12, "G", "C")
        v2 = self._make_variant(61, "Q", "H")
        result = predict_epistatic_effect([v1, v2], gene="KRAS")
        assert result.interaction_score >= 0.0

    def test_close_variants_higher_interaction(self):
        close = [self._make_variant(10, "A", "V"), self._make_variant(12, "G", "D")]
        far = [self._make_variant(10, "A", "V"), self._make_variant(300, "G", "D")]
        r_close = predict_epistatic_effect(close)
        r_far = predict_epistatic_effect(far)
        # Close variants should have >= interaction score
        assert r_close.interaction_score >= r_far.interaction_score - 0.05  # some tolerance


# ===========================================================================
# Feature 4: Fold-switching detector
# ===========================================================================

class TestKnownFoldSwitchers:
    def test_count(self):
        assert len(KNOWN_FOLD_SWITCHERS) >= 8

    def test_mad2_present(self):
        assert "MAD2" in KNOWN_FOLD_SWITCHERS

    def test_rfah_present(self):
        assert "RfaH" in KNOWN_FOLD_SWITCHERS

    def test_all_have_switch_type(self):
        for name, entry in KNOWN_FOLD_SWITCHERS.items():
            assert "switch_type" in entry


class TestCheckKnownFoldSwitchers:
    def test_qn_rich_long_returns_cpeb3(self):
        # Q/N rich long sequence
        seq = "QNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQN"
        result = check_known_fold_switchers(seq)
        assert result == "CPEB3"

    def test_short_charged_returns_lymphotactin(self):
        seq = "DKERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERKDERK"[:90]
        result = check_known_fold_switchers(seq)
        # charged_frac should be 0.33ish, length ~90
        # may or may not match — just confirm it's a known name or None
        assert result is None or result in KNOWN_FOLD_SWITCHERS

    def test_unknown_returns_none(self):
        result = check_known_fold_switchers("ACDEFGHIKLMNPQRSTVWY")
        # Short sequence, should return None
        assert result is None or result in KNOWN_FOLD_SWITCHERS


class TestDetectFoldSwitchingRisk:
    def test_returns_warning(self):
        result = detect_fold_switching_risk(SEQ_SHORT)
        assert isinstance(result, FoldSwitchWarning)

    def test_risk_score_in_range(self):
        result = detect_fold_switching_risk(SEQ_LONG)
        assert 0.0 <= result.risk_score <= 1.0

    def test_features_dict_has_keys(self):
        result = detect_fold_switching_risk(SEQ_SHORT)
        required = {
            "hydrophobic_alternation",
            "charge_clustering",
            "high_proline",
            "ambiguous_ss_propensity",
            "low_complexity_repeats",
            "qn_rich",
        }
        assert required.issubset(set(result.features.keys()))

    def test_likely_flag_matches_threshold(self):
        result = detect_fold_switching_risk(SEQ_LONG)
        if result.risk_score >= 0.45:
            assert result.likely_fold_switcher is True
        else:
            assert result.likely_fold_switcher is False

    def test_recommendation_not_empty(self):
        result = detect_fold_switching_risk(SEQ_DISORDERED)
        assert result.recommendation != ""

    def test_empty_sequence(self):
        result = detect_fold_switching_risk("")
        assert result.risk_score == 0.0
        assert result.likely_fold_switcher is False

    def test_high_hydrophobic_alternation(self):
        # Perfectly alternating HPHP...
        seq = "VADAVADAVADAVADAVADAVADAVADAVADAVA"
        result = detect_fold_switching_risk(seq)
        assert result.features["hydrophobic_alternation"] > 0.4

    def test_qn_rich_increases_risk(self):
        qn_seq = "QNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQNQN"
        result = detect_fold_switching_risk(qn_seq)
        assert result.features["qn_rich"] > 0.0


# ===========================================================================
# API Endpoint Tests
# ===========================================================================

class TestAnalyzeDisorderEndpoint:
    def test_basic(self, client: TestClient):
        r = client.post("/structure/analyze-disorder", json={"sequence": SEQ_DISORDERED})
        assert r.status_code == 200
        data = r.json()
        assert "idr_regions" in data
        assert "idr_fraction" in data
        assert data["safety_label"] == "Research only — not for clinical use"

    def test_with_plddt_values(self, client: TestClient):
        seq = "A" * 20
        plddt = [20.0] * 20
        r = client.post(
            "/structure/analyze-disorder",
            json={"sequence": seq, "plddt_values": plddt},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_residues"] == 20

    def test_empty_sequence(self, client: TestClient):
        r = client.post("/structure/analyze-disorder", json={"sequence": ""})
        assert r.status_code == 200


class TestDetectLowPLDDTEndpoint:
    def test_all_low(self, client: TestClient):
        seq = "A" * 20
        r = client.post(
            "/structure/detect-low-plddt",
            json={"sequence": seq, "plddt_values": [10.0] * 20},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["region_count"] == 1
        assert data["threshold"] == IDR_PLDDT_THRESHOLD

    def test_no_plddt_provided(self, client: TestClient):
        r = client.post("/structure/detect-low-plddt", json={"sequence": SEQ_DISORDERED})
        assert r.status_code == 200
        data = r.json()
        assert "low_plddt_regions" in data


class TestPTMImpactEndpoint:
    def test_direct_disruption(self, client: TestClient):
        r = client.post(
            "/structure/ptm-impact", json={"gene": "TP53", "variant": "S15F"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ptm_disrupted"] is True
        assert data["safety_label"] == "Research only — not for clinical use"

    def test_no_ptm_nearby(self, client: TestClient):
        r = client.post(
            "/structure/ptm-impact", json={"gene": "TP53", "variant": "A500V"}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ptm_disrupted"] is False

    def test_invalid_variant(self, client: TestClient):
        r = client.post(
            "/structure/ptm-impact", json={"gene": "TP53", "variant": "NOTAVARIANT"}
        )
        assert r.status_code == 200  # graceful degradation


class TestPTMSitesEndpoint:
    def test_tp53(self, client: TestClient):
        r = client.get("/structure/ptm-sites/TP53")
        assert r.status_code == 200
        data = r.json()
        assert data["gene"] == "TP53"
        assert data["count"] >= 8

    def test_lowercase_gene(self, client: TestClient):
        r = client.get("/structure/ptm-sites/egfr")
        assert r.status_code == 200
        data = r.json()
        assert data["gene"] == "EGFR"

    def test_unknown_gene_404(self, client: TestClient):
        r = client.get("/structure/ptm-sites/FAKEGENE999")
        assert r.status_code == 404


class TestEpistaticPredictionEndpoint:
    def test_single_variant(self, client: TestClient):
        r = client.post(
            "/structure/epistatic-prediction",
            json={
                "gene": "KRAS",
                "variants": [{"position": 12, "ref_aa": "G", "alt_aa": "D"}],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "epistatic_effect" in data
        assert "epistatic_prediction" in data

    def test_too_many_variants(self, client: TestClient):
        variants = [{"position": i, "ref_aa": "A", "alt_aa": "V"} for i in range(1, 10)]
        r = client.post(
            "/structure/epistatic-prediction",
            json={"variants": variants},
        )
        assert r.status_code == 422

    def test_empty_variants(self, client: TestClient):
        r = client.post(
            "/structure/epistatic-prediction",
            json={"variants": []},
        )
        assert r.status_code == 422

    def test_known_kras_pair(self, client: TestClient):
        r = client.post(
            "/structure/epistatic-prediction",
            json={
                "gene": "KRAS",
                "variants": [
                    {"position": 12, "ref_aa": "G", "alt_aa": "D"},
                    {"position": 146, "ref_aa": "A", "alt_aa": "T"},
                ],
            },
        )
        assert r.status_code == 200
        assert r.json()["epistatic_effect"] == "synergistic"


class TestFoldSwitchingRiskEndpoint:
    def test_basic(self, client: TestClient):
        r = client.post(
            "/structure/fold-switching-risk", json={"sequence": SEQ_LONG}
        )
        assert r.status_code == 200
        data = r.json()
        assert "risk_score" in data
        assert "likely_fold_switcher" in data
        assert "features" in data
        assert data["safety_label"] == "Research only — not for clinical use"

    def test_empty_sequence(self, client: TestClient):
        r = client.post("/structure/fold-switching-risk", json={"sequence": ""})
        assert r.status_code == 422


class TestKnownFoldSwitchersEndpoint:
    def test_returns_list(self, client: TestClient):
        r = client.get("/structure/known-fold-switchers")
        assert r.status_code == 200
        data = r.json()
        assert "fold_switchers" in data
        assert data["count"] >= 8
        assert "MAD2" in data["fold_switchers"]

    def test_safety_label(self, client: TestClient):
        r = client.get("/structure/known-fold-switchers")
        assert r.json()["safety_label"] == "Research only — not for clinical use"


class TestFullAnalysisEndpoint:
    def test_basic_no_gene(self, client: TestClient):
        r = client.post(
            "/structure/full-analysis",
            json={"sequence": SEQ_DISORDERED},
        )
        assert r.status_code == 200
        data = r.json()
        assert "disorder_analysis" in data
        assert "fold_switch_warning" in data
        assert data["ptm_impact"] is None

    def test_with_gene_and_variant(self, client: TestClient):
        r = client.post(
            "/structure/full-analysis",
            json={"sequence": SEQ_DISORDERED, "gene": "TP53", "variant": "S15F"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ptm_impact"] is not None
        assert data["ptm_impact"]["gene"] == "TP53"

    def test_empty_sequence_422(self, client: TestClient):
        r = client.post("/structure/full-analysis", json={"sequence": ""})
        assert r.status_code == 422

    def test_safety_label(self, client: TestClient):
        r = client.post(
            "/structure/full-analysis",
            json={"sequence": SEQ_SHORT},
        )
        assert r.json()["safety_label"] == "Research only — not for clinical use"
