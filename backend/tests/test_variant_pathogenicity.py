"""Tests for Variant Pathogenicity Mode (AlphaMissense Integration).

Covers:
  - AlphaMissense lookup (known hit, miss, edge scores)
  - Score classification thresholds (all 3 categories)
  - Batch lookup
  - Variant-to-structure mapping (critical vs non-critical residues)
  - Germline/somatic classification at different VAFs
  - Stability impact for different mutation types
  - Pathogenicity report builder
  - All 6 API endpoints
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.variant_pathogenicity import (
    ALPHAMISSENSE_SCORES,
    KNOWN_CRITICAL_RESIDUES,
    PathogenicityScore,
    StabilityImpact,
    VariantOrigin,
    VariantStructureMapping,
    batch_lookup,
    build_pathogenicity_report,
    classify_score,
    classify_variant_origin,
    estimate_stability_impact,
    lookup_alphamissense,
    map_variant_to_structure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(client: TestClient) -> str:
    resp = client.post("/cases", json={"species": "demo", "diagnosis_summary": "pathogenicity test"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_variant(client: TestClient, case_id: str, gene: str, protein_change: str) -> str:
    resp = client.post(
        f"/cases/{case_id}/variants",
        json={
            "genomic_coordinates": "chr17:7674220",
            "gene": gene,
            "protein_change": protein_change,
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# AlphaMissense lookup
# ---------------------------------------------------------------------------


class TestAlphaMissenseLookup:
    def test_known_hit_tp53_r175h(self):
        ps = lookup_alphamissense("TP53", "R175H")
        assert ps is not None
        assert ps.gene == "TP53"
        assert ps.mutation == "R175H"
        assert ps.score == pytest.approx(0.981)
        assert ps.classification == "likely_pathogenic"
        assert ps.source == "alphamissense_stub"

    def test_known_hit_kras_g12v(self):
        ps = lookup_alphamissense("KRAS", "G12V")
        assert ps is not None
        assert ps.score > 0.9
        assert ps.classification == "likely_pathogenic"

    def test_known_benign_ldlr(self):
        ps = lookup_alphamissense("LDLR", "V408M")
        assert ps is not None
        assert ps.classification == "likely_benign"
        assert ps.score < 0.34

    def test_case_insensitive_gene(self):
        ps = lookup_alphamissense("tp53", "R175H")
        assert ps is not None
        assert ps.classification == "likely_pathogenic"

    def test_unknown_variant_returns_none(self):
        ps = lookup_alphamissense("FAKEGENE", "X999Z")
        assert ps is None

    def test_returns_pathogenicity_score_dataclass(self):
        ps = lookup_alphamissense("BRAF", "V600E")
        assert isinstance(ps, PathogenicityScore)

    def test_confidence_field_set(self):
        ps = lookup_alphamissense("TP53", "R248W")
        assert ps is not None
        assert ps.confidence in {"high", "moderate", "low"}


# ---------------------------------------------------------------------------
# classify_score thresholds
# ---------------------------------------------------------------------------


class TestClassifyScore:
    def test_below_benign_threshold(self):
        assert classify_score(0.0) == "likely_benign"
        assert classify_score(0.339) == "likely_benign"

    def test_at_benign_boundary(self):
        assert classify_score(0.34) == "uncertain"

    def test_uncertain_range(self):
        assert classify_score(0.34) == "uncertain"
        assert classify_score(0.45) == "uncertain"
        assert classify_score(0.564) == "uncertain"

    def test_pathogenic_above_threshold(self):
        assert classify_score(0.565) == "likely_pathogenic"
        assert classify_score(1.0) == "likely_pathogenic"

    def test_all_three_categories_distinct(self):
        cats = {classify_score(0.1), classify_score(0.45), classify_score(0.9)}
        assert cats == {"likely_benign", "uncertain", "likely_pathogenic"}


# ---------------------------------------------------------------------------
# Batch lookup
# ---------------------------------------------------------------------------


class TestBatchLookup:
    def test_all_known(self):
        variants = [
            {"gene": "TP53", "mutation": "R175H"},
            {"gene": "KRAS", "mutation": "G12V"},
        ]
        results = batch_lookup(variants)
        assert len(results) == 2

    def test_partial_match(self):
        variants = [
            {"gene": "TP53", "mutation": "R175H"},
            {"gene": "UNKNOWN", "mutation": "X1Y"},
        ]
        results = batch_lookup(variants)
        assert len(results) == 1
        assert results[0].gene == "TP53"

    def test_empty_input(self):
        assert batch_lookup([]) == []

    def test_no_matches(self):
        variants = [{"gene": "FAKEGENE", "mutation": "Z99A"}]
        results = batch_lookup(variants)
        assert results == []

    def test_returns_list_of_pathogenicity_scores(self):
        variants = [{"gene": "BRAF", "mutation": "V600E"}]
        results = batch_lookup(variants)
        assert all(isinstance(r, PathogenicityScore) for r in results)


# ---------------------------------------------------------------------------
# Variant-to-structure mapping
# ---------------------------------------------------------------------------


class TestMapVariantToStructure:
    def test_known_critical_residue_tp53_r175h(self):
        v = {"id": "v1", "gene": "TP53", "protein_change": "R175H"}
        m = map_variant_to_structure(v)
        assert isinstance(m, VariantStructureMapping)
        assert m.residue_position == 175
        assert m.structural_impact == "high"
        assert m.gene == "TP53"

    def test_known_critical_kras_g12v(self):
        v = {"id": "v2", "gene": "KRAS", "mutation": "G12V"}
        m = map_variant_to_structure(v)
        assert m.residue_position == 12
        assert m.structural_impact == "high"

    def test_non_critical_residue(self):
        v = {"id": "v3", "gene": "TP53", "protein_change": "A50V"}
        m = map_variant_to_structure(v)
        assert m.residue_position == 50
        assert m.structural_impact in {"low", "moderate"}

    def test_unknown_gene_and_mutation(self):
        v = {"id": "v4", "gene": "UNKNOWNGENE", "protein_change": ""}
        m = map_variant_to_structure(v)
        assert m.structural_impact == "unknown"
        assert m.residue_position is None

    def test_domain_assigned_for_known_gene(self):
        v = {"id": "v5", "gene": "TP53", "protein_change": "R175H"}
        m = map_variant_to_structure(v)
        assert m.domain is not None
        assert "domain" in m.domain.lower()

    def test_variant_id_preserved(self):
        v = {"id": "test-uuid", "gene": "KRAS", "mutation": "G12D"}
        m = map_variant_to_structure(v)
        assert m.variant_id == "test-uuid"

    def test_known_critical_residues_dict_populated(self):
        assert "TP53" in KNOWN_CRITICAL_RESIDUES
        assert 175 in KNOWN_CRITICAL_RESIDUES["TP53"]
        assert "KRAS" in KNOWN_CRITICAL_RESIDUES
        assert 12 in KNOWN_CRITICAL_RESIDUES["KRAS"]


# ---------------------------------------------------------------------------
# Germline vs somatic classification
# ---------------------------------------------------------------------------


class TestClassifyVariantOrigin:
    def test_high_vaf_germline(self):
        assert classify_variant_origin({"vaf": 0.5}) == VariantOrigin.germline.value

    def test_vaf_exactly_above_germline_threshold(self):
        assert classify_variant_origin({"vaf": 0.41}) == VariantOrigin.germline.value

    def test_low_vaf_somatic(self):
        assert classify_variant_origin({"vaf": 0.1}) == VariantOrigin.somatic.value

    def test_vaf_just_below_somatic_threshold(self):
        assert classify_variant_origin({"vaf": 0.29}) == VariantOrigin.somatic.value

    def test_borderline_uncertain(self):
        origin = classify_variant_origin({"vaf": 0.35})
        assert origin == VariantOrigin.uncertain.value

    def test_no_vaf_returns_uncertain(self):
        assert classify_variant_origin({}) == VariantOrigin.uncertain.value

    def test_vaf_in_quality_metrics(self):
        v = {"quality_metrics": {"vaf": 0.05}}
        assert classify_variant_origin(v) == VariantOrigin.somatic.value

    def test_invalid_vaf_returns_uncertain(self):
        assert classify_variant_origin({"vaf": "not-a-float"}) == VariantOrigin.uncertain.value

    def test_origin_enum_values(self):
        assert VariantOrigin.germline.value == "germline"
        assert VariantOrigin.somatic.value == "somatic"
        assert VariantOrigin.uncertain.value == "uncertain"


# ---------------------------------------------------------------------------
# Stability impact
# ---------------------------------------------------------------------------


class TestEstimateStabilityImpact:
    def test_conservative_substitution_low_impact(self):
        # I→L: both medium hydrophobic, same charge → low
        impact = estimate_stability_impact("TP53", "I255L")
        assert isinstance(impact, StabilityImpact)
        assert not impact.destabilizing
        assert impact.ddg_estimate < 1.5

    def test_large_size_change_high_destabilizing(self):
        # G→W: tiny → large
        impact = estimate_stability_impact("TP53", "G245W")
        assert impact.destabilizing
        assert impact.ddg_estimate >= 3.0

    def test_hydrophobic_polar_swap_destabilizing(self):
        # I→D: hydrophobic to charged polar
        impact = estimate_stability_impact("KRAS", "I36D")
        assert impact.destabilizing

    def test_charge_change_moderate_destabilizing(self):
        # R→H: both positive, slight charge shift; class: moderate
        impact = estimate_stability_impact("TP53", "R175H")
        assert impact.ddg_estimate >= 0.5

    def test_unknown_mutation_format(self):
        impact = estimate_stability_impact("TP53", "del175")
        assert impact.ddg_estimate == 0.0
        assert not impact.destabilizing
        assert impact.confidence == "low"

    def test_confidence_field_present(self):
        impact = estimate_stability_impact("BRAF", "V600E")
        assert impact.confidence in {"high", "moderate", "low"}

    def test_returns_stability_impact_dataclass(self):
        impact = estimate_stability_impact("EGFR", "L858R")
        assert isinstance(impact, StabilityImpact)


# ---------------------------------------------------------------------------
# build_pathogenicity_report
# ---------------------------------------------------------------------------


class TestBuildPathogenicityReport:
    def test_missing_case_returns_error(self, client: TestClient):
        from backend.app.db import SessionLocal

        with SessionLocal() as db:
            report = build_pathogenicity_report("nonexistent-case-id", db)
        assert report["error"] == "case_not_found"

    def test_empty_case_zero_variants(self, client: TestClient):
        case_id = _make_case(client)
        from backend.app.db import SessionLocal

        with SessionLocal() as db:
            report = build_pathogenicity_report(case_id, db)
        assert report["case_id"] == case_id
        assert report["total_variants"] == 0
        assert report["variants"] == []

    def test_report_with_known_variant(self, client: TestClient):
        case_id = _make_case(client)
        _add_variant(client, case_id, "TP53", "R175H")
        from backend.app.db import SessionLocal

        with SessionLocal() as db:
            report = build_pathogenicity_report(case_id, db)
        assert report["total_variants"] == 1
        assert report["pathogenic_count"] == 1
        v = report["variants"][0]
        assert v["gene"] == "TP53"
        assert v["alphamissense"]["score"] == pytest.approx(0.981)
        assert v["alphamissense"]["classification"] == "likely_pathogenic"

    def test_report_structure_fields(self, client: TestClient):
        case_id = _make_case(client)
        _add_variant(client, case_id, "KRAS", "G12V")
        from backend.app.db import SessionLocal

        with SessionLocal() as db:
            report = build_pathogenicity_report(case_id, db)
        v = report["variants"][0]
        assert "structure" in v
        assert "stability" in v
        assert "origin" in v
        assert v["structure"]["structural_impact"] == "high"

    def test_report_counts_sum_correct(self, client: TestClient):
        case_id = _make_case(client)
        _add_variant(client, case_id, "TP53", "R175H")   # pathogenic
        _add_variant(client, case_id, "LDLR", "V408M")   # benign
        from backend.app.db import SessionLocal

        with SessionLocal() as db:
            report = build_pathogenicity_report(case_id, db)
        total = (
            report["pathogenic_count"]
            + report["benign_count"]
            + report["uncertain_count"]
            + report["unknown_count"]
        )
        assert total == report["total_variants"]


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestPathogenicityEndpoints:
    def test_get_case_pathogenicity_report_404(self, client: TestClient):
        resp = client.get("/cases/nonexistent-xxx/variants/pathogenicity")
        assert resp.status_code == 404

    def test_get_case_pathogenicity_report_empty(self, client: TestClient):
        case_id = _make_case(client)
        resp = client.get(f"/cases/{case_id}/variants/pathogenicity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == case_id
        assert data["total_variants"] == 0

    def test_get_case_pathogenicity_report_with_variant(self, client: TestClient):
        case_id = _make_case(client)
        _add_variant(client, case_id, "BRAF", "V600E")
        resp = client.get(f"/cases/{case_id}/variants/pathogenicity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_variants"] == 1
        assert data["pathogenic_count"] == 1

    def test_post_alphamissense_lookup_found(self, client: TestClient):
        resp = client.post(
            "/variants/alphamissense-lookup",
            json={"gene": "TP53", "mutation": "R175H"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["score"] == pytest.approx(0.981)
        assert data["classification"] == "likely_pathogenic"

    def test_post_alphamissense_lookup_not_found(self, client: TestClient):
        resp = client.post(
            "/variants/alphamissense-lookup",
            json={"gene": "FAKE", "mutation": "X99Z"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False
        assert data["score"] is None

    def test_post_batch_pathogenicity(self, client: TestClient):
        resp = client.post(
            "/variants/batch-pathogenicity",
            json={
                "variants": [
                    {"gene": "TP53", "mutation": "R175H"},
                    {"gene": "KRAS", "mutation": "G12V"},
                    {"gene": "FAKE", "mutation": "X1Y"},
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requested"] == 3
        assert data["found"] == 2
        assert len(data["results"]) == 2

    def test_post_batch_pathogenicity_empty(self, client: TestClient):
        resp = client.post("/variants/batch-pathogenicity", json={"variants": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] == 0

    def test_post_stability_impact(self, client: TestClient):
        resp = client.post(
            "/variants/stability-impact",
            json={"gene": "TP53", "mutation": "G245W"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["destabilizing"] is True
        assert data["ddg_estimate"] >= 3.0
        assert data["confidence"] in {"high", "moderate", "low"}

    def test_post_stability_impact_conservative(self, client: TestClient):
        resp = client.post(
            "/variants/stability-impact",
            json={"gene": "KRAS", "mutation": "I55L"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["destabilizing"] is False

    def test_post_classify_origin_germline(self, client: TestClient):
        resp = client.post("/variants/classify-origin", json={"vaf": 0.5})
        assert resp.status_code == 200
        assert resp.json()["origin"] == "germline"

    def test_post_classify_origin_somatic(self, client: TestClient):
        resp = client.post("/variants/classify-origin", json={"vaf": 0.1})
        assert resp.status_code == 200
        assert resp.json()["origin"] == "somatic"

    def test_post_classify_origin_uncertain(self, client: TestClient):
        resp = client.post("/variants/classify-origin", json={"vaf": 0.35})
        assert resp.status_code == 200
        assert resp.json()["origin"] == "uncertain"

    def test_post_classify_origin_no_vaf(self, client: TestClient):
        resp = client.post("/variants/classify-origin", json={})
        assert resp.status_code == 200
        assert resp.json()["origin"] == "uncertain"

    def test_post_classify_origin_quality_metrics(self, client: TestClient):
        resp = client.post(
            "/variants/classify-origin",
            json={"quality_metrics": {"vaf": 0.05}},
        )
        assert resp.status_code == 200
        assert resp.json()["origin"] == "somatic"

    def test_get_known_pathogenic(self, client: TestClient):
        resp = client.get("/variants/known-pathogenic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == len(ALPHAMISSENSE_SCORES)
        assert len(data["variants"]) == data["count"]
        # Verify sorted descending by score
        scores = [v["score"] for v in data["variants"]]
        assert scores == sorted(scores, reverse=True)

    def test_known_pathogenic_includes_tp53(self, client: TestClient):
        resp = client.get("/variants/known-pathogenic")
        variants = resp.json()["variants"]
        genes = {v["gene"] for v in variants}
        assert "TP53" in genes
        assert "KRAS" in genes
