"""Tests for Clinical Variant Integration — Phase 24 Tier 1.

RESEARCH USE ONLY. Not for clinical diagnostic use.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.clinical_variants import (
    MOCK_CLINVAR_DB,
    MOCK_VUS_DATABASE,
    ACMGClassification,
    ACMGCriterion,
    ReclassificationResult,
    StructuralClinVarMapping,
    get_clinvar_stats,
    get_vus_queue,
    lookup_clinvar,
    map_clinvar_to_structure,
    rescore_all_vus,
    rescore_vus,
    score_acmg_criteria,
)

# ---------------------------------------------------------------------------
# Feature 1: ACMG auto-scoring — unit tests
# ---------------------------------------------------------------------------


class TestACMGScoring:
    def test_returns_acmg_classification(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        assert isinstance(result, ACMGClassification)
        assert result.gene == "TP53"
        assert result.variant == "R175H"

    def test_gene_uppercased(self) -> None:
        result = score_acmg_criteria("tp53", "R175H")
        assert result.gene == "TP53"

    def test_evidences_contain_all_criteria(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        criteria_found = {e.criterion for e in result.evidences}
        for criterion in ACMGCriterion:
            assert criterion in criteria_found

    def test_pp3_met_when_high_alphamissense(self) -> None:
        result = score_acmg_criteria("TP53", "R175H", alphamissense_score=0.95)
        pp3 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP3)
        assert pp3.met is True

    def test_pp3_not_met_when_low_alphamissense(self) -> None:
        result = score_acmg_criteria(
            "LDLR", "V408M", alphamissense_score=0.15, conservation_score=0.1
        )
        pp3 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP3)
        assert pp3.met is False

    def test_pp3_met_at_threshold_0_7(self) -> None:
        # Exactly 0.7 should not meet (>0.7)
        result = score_acmg_criteria(
            "GENE1", "A100B", alphamissense_score=0.70, conservation_score=0.0
        )
        pp3 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP3)
        assert pp3.met is False

    def test_pp3_met_above_threshold(self) -> None:
        result = score_acmg_criteria(
            "GENE1", "A100B", alphamissense_score=0.71, conservation_score=0.0
        )
        pp3 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP3)
        assert pp3.met is True

    def test_bp4_met_when_both_scores_low(self) -> None:
        result = score_acmg_criteria(
            "LDLR", "V408M", alphamissense_score=0.10, conservation_score=0.20
        )
        bp4 = next(e for e in result.evidences if e.criterion == ACMGCriterion.BP4)
        assert bp4.met is True

    def test_bp4_not_met_when_am_score_high(self) -> None:
        result = score_acmg_criteria(
            "TP53", "R175H", alphamissense_score=0.95, conservation_score=0.10
        )
        bp4 = next(e for e in result.evidences if e.criterion == ACMGCriterion.BP4)
        assert bp4.met is False

    def test_bp4_not_met_when_cons_score_high(self) -> None:
        result = score_acmg_criteria(
            "TP53", "R175H", alphamissense_score=0.20, conservation_score=0.50
        )
        bp4 = next(e for e in result.evidences if e.criterion == ACMGCriterion.BP4)
        assert bp4.met is False

    def test_pm1_met_in_critical_domain(self) -> None:
        # TP53 R175H is in DNA-binding domain (102-292)
        result = score_acmg_criteria("TP53", "R175H")
        pm1 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PM1)
        assert pm1.met is True

    def test_pm1_not_met_outside_domain(self) -> None:
        # Position 500 is outside all TP53 domains
        result = score_acmg_criteria("TP53", "A500V")
        pm1 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PM1)
        assert pm1.met is False

    def test_pm1_met_via_structural_context(self) -> None:
        result = score_acmg_criteria(
            "MYGENE",
            "X999Y",
            structural_context={"in_critical_domain": True, "domain_name": "active site"},
        )
        pm1 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PM1)
        assert pm1.met is True

    def test_pp2_met_for_constrained_gene(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        pp2 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP2)
        assert pp2.met is True

    def test_pp2_not_met_for_unconstrained_gene(self) -> None:
        result = score_acmg_criteria("LDLR", "V408M")
        pp2 = next(e for e in result.evidences if e.criterion == ACMGCriterion.PP2)
        assert pp2.met is False

    def test_bp1_met_for_truncating_disease_gene(self) -> None:
        result = score_acmg_criteria("BRCA2", "D2723H")
        bp1 = next(e for e in result.evidences if e.criterion == ACMGCriterion.BP1)
        assert bp1.met is True

    def test_overall_score_is_between_0_and_1(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        assert 0.0 <= result.overall_score <= 1.0

    def test_high_am_score_yields_likely_pathogenic_or_pathogenic(self) -> None:
        result = score_acmg_criteria(
            "TP53",
            "R175H",
            alphamissense_score=0.98,
            conservation_score=0.95,
            structural_context={"in_critical_domain": True, "domain_name": "DNA-binding domain"},
        )
        assert result.pathogenicity_class in ("pathogenic", "likely_pathogenic")

    def test_low_am_score_yields_benign_spectrum(self) -> None:
        result = score_acmg_criteria(
            "LDLR",
            "V408M",
            alphamissense_score=0.05,
            conservation_score=0.10,
            structural_context={"in_critical_domain": False},
        )
        assert result.pathogenicity_class in ("benign", "likely_benign", "VUS")

    def test_deterministic_without_scores(self) -> None:
        r1 = score_acmg_criteria("MYGENE", "X999Y")
        r2 = score_acmg_criteria("MYGENE", "X999Y")
        assert r1.pathogenicity_class == r2.pathogenicity_class
        assert r1.overall_score == r2.overall_score

    def test_evidence_has_required_fields(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        for e in result.evidences:
            assert isinstance(e.criterion, ACMGCriterion)
            assert isinstance(e.met, bool)
            assert e.strength in ("supporting", "moderate", "strong", "very_strong")
            assert isinstance(e.evidence_source, str)
            assert isinstance(e.detail, str)

    def test_classification_field_values(self) -> None:
        result = score_acmg_criteria("TP53", "R175H")
        valid_classes = {"pathogenic", "likely_pathogenic", "VUS", "likely_benign", "benign"}
        assert result.pathogenicity_class in valid_classes


# ---------------------------------------------------------------------------
# Feature 2: VUS reclassification queue — unit tests
# ---------------------------------------------------------------------------


class TestVUSQueue:
    def test_vus_database_has_20_entries(self) -> None:
        assert len(MOCK_VUS_DATABASE) == 20

    def test_all_entries_are_vus_class(self) -> None:
        for v in MOCK_VUS_DATABASE:
            assert v.current_class == "VUS"

    def test_get_vus_queue_returns_pending_only(self) -> None:
        queue = get_vus_queue()
        assert all(v.pending_reclassification for v in queue)

    def test_get_vus_queue_returns_list(self) -> None:
        assert isinstance(get_vus_queue(), list)

    def test_rescore_vus_known_entry(self) -> None:
        result = rescore_vus("VUS-001")
        assert isinstance(result, ReclassificationResult)
        assert result.variant_id == "VUS-001"
        assert result.old_class == "VUS"

    def test_rescore_vus_returns_classification(self) -> None:
        result = rescore_vus("VUS-005")  # EGFR G719S — AM=0.723
        valid_classes = {"pathogenic", "likely_pathogenic", "VUS", "likely_benign", "benign"}
        assert result.new_class in valid_classes

    def test_rescore_vus_confidence_in_range(self) -> None:
        result = rescore_vus("VUS-001")
        assert 0.0 <= result.confidence <= 1.0

    def test_rescore_vus_evidence_delta_is_list(self) -> None:
        result = rescore_vus("VUS-001")
        assert isinstance(result.evidence_delta, list)

    def test_rescore_vus_auto_reclassified_bool(self) -> None:
        result = rescore_vus("VUS-001")
        assert isinstance(result.auto_reclassified, bool)

    def test_rescore_vus_unknown_id_raises(self) -> None:
        with pytest.raises(KeyError):
            rescore_vus("VUS-NONEXISTENT")

    def test_rescore_all_vus_returns_list(self) -> None:
        results = rescore_all_vus()
        assert isinstance(results, list)
        assert len(results) == 20

    def test_rescore_all_vus_all_are_results(self) -> None:
        results = rescore_all_vus()
        for r in results:
            assert isinstance(r, ReclassificationResult)

    def test_rescore_all_vus_covers_all_ids(self) -> None:
        results = rescore_all_vus()
        result_ids = {r.variant_id for r in results}
        db_ids = {v.variant_id for v in MOCK_VUS_DATABASE}
        assert result_ids == db_ids

    def test_vus_entry_fields(self) -> None:
        entry = MOCK_VUS_DATABASE[0]
        assert isinstance(entry.variant_id, str)
        assert isinstance(entry.gene, str)
        assert isinstance(entry.variant, str)
        assert isinstance(entry.last_scored, str)
        assert isinstance(entry.pending_reclassification, bool)


# ---------------------------------------------------------------------------
# Feature 3: ClinVar evidence mapping — unit tests
# ---------------------------------------------------------------------------


class TestClinVarLookup:
    def test_clinvar_database_has_30_entries(self) -> None:
        assert len(MOCK_CLINVAR_DB) == 30

    def test_lookup_clinvar_by_gene(self) -> None:
        results = lookup_clinvar("TP53")
        assert len(results) > 0
        assert all(e.gene == "TP53" for e in results)

    def test_lookup_clinvar_case_insensitive_gene(self) -> None:
        r1 = lookup_clinvar("TP53")
        r2 = lookup_clinvar("tp53")
        assert len(r1) == len(r2)

    def test_lookup_clinvar_with_variant(self) -> None:
        results = lookup_clinvar("TP53", "R175H")
        assert len(results) == 1
        assert results[0].variant == "R175H"

    def test_lookup_clinvar_variant_case_insensitive(self) -> None:
        r1 = lookup_clinvar("TP53", "R175H")
        r2 = lookup_clinvar("TP53", "r175h")
        assert len(r1) == len(r2)

    def test_lookup_clinvar_not_found_returns_empty(self) -> None:
        results = lookup_clinvar("FAKEGENE999")
        assert results == []

    def test_lookup_clinvar_variant_not_found(self) -> None:
        results = lookup_clinvar("TP53", "Z999Z")
        assert results == []

    def test_clinvar_evidence_fields(self) -> None:
        entry = MOCK_CLINVAR_DB[0]
        assert isinstance(entry.clinvar_id, str)
        assert isinstance(entry.variant, str)
        assert isinstance(entry.gene, str)
        assert isinstance(entry.significance, str)
        assert 0 <= entry.review_stars <= 4
        assert isinstance(entry.conditions, list)
        assert isinstance(entry.last_updated, str)


class TestStructuralClinVarMapping:
    def test_map_clinvar_returns_mapping(self) -> None:
        result = map_clinvar_to_structure("TP53")
        assert isinstance(result, StructuralClinVarMapping)

    def test_map_clinvar_gene_uppercased(self) -> None:
        result = map_clinvar_to_structure("tp53")
        assert result.gene == "TP53"

    def test_map_clinvar_total_variants_correct(self) -> None:
        result = map_clinvar_to_structure("TP53")
        expected = len(lookup_clinvar("TP53"))
        assert result.total_variants == expected

    def test_map_clinvar_mapped_plus_unmapped_equals_total(self) -> None:
        result = map_clinvar_to_structure("KRAS")
        assert len(result.mapped_variants) + result.unmapped_count == result.total_variants

    def test_map_clinvar_pathogenic_hotspots(self) -> None:
        result = map_clinvar_to_structure("KRAS")
        assert isinstance(result.pathogenic_hotspots, list)
        # KRAS G12 is a well-known hotspot
        hotspot_residues = {h["residue"] for h in result.pathogenic_hotspots}
        assert 12 in hotspot_residues

    def test_map_clinvar_hotspot_has_required_keys(self) -> None:
        result = map_clinvar_to_structure("TP53")
        for hs in result.pathogenic_hotspots:
            assert "residue" in hs
            assert "domain" in hs
            assert "variant_count" in hs
            assert "variants" in hs

    def test_map_clinvar_domain_summary_is_dict(self) -> None:
        result = map_clinvar_to_structure("EGFR")
        assert isinstance(result.domain_summary, dict)

    def test_map_clinvar_domain_summary_has_counts(self) -> None:
        result = map_clinvar_to_structure("EGFR")
        for dom, counts in result.domain_summary.items():
            assert isinstance(dom, str)
            assert isinstance(counts, dict)

    def test_map_clinvar_unknown_gene(self) -> None:
        result = map_clinvar_to_structure("FAKEGENE999")
        assert result.total_variants == 0
        assert result.mapped_variants == []
        assert result.pathogenic_hotspots == []

    def test_get_clinvar_stats_returns_dict(self) -> None:
        stats = get_clinvar_stats()
        assert isinstance(stats, dict)

    def test_get_clinvar_stats_total_entries(self) -> None:
        stats = get_clinvar_stats()
        assert stats["total_entries"] == 30

    def test_get_clinvar_stats_has_significance_distribution(self) -> None:
        stats = get_clinvar_stats()
        assert "significance_distribution" in stats
        assert "Pathogenic" in stats["significance_distribution"]

    def test_get_clinvar_stats_has_gene_distribution(self) -> None:
        stats = get_clinvar_stats()
        assert "gene_distribution" in stats
        assert "TP53" in stats["gene_distribution"]

    def test_get_clinvar_stats_mapped_unmapped_sum(self) -> None:
        stats = get_clinvar_stats()
        assert stats["structurally_mapped"] + stats["unmapped"] == stats["total_entries"]

    def test_get_clinvar_stats_safety_label(self) -> None:
        stats = get_clinvar_stats()
        assert "safety_label" in stats


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestACMGEndpoints:
    def test_post_acmg_score(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/acmg-score",
            json={"gene": "TP53", "variant": "R175H"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["gene"] == "TP53"
        assert data["variant"] == "R175H"
        assert "pathogenicity_class" in data
        assert "overall_score" in data
        assert "evidences" in data

    def test_post_acmg_score_with_am_score(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/acmg-score",
            json={"gene": "KRAS", "variant": "G12V", "alphamissense_score": 0.95},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["pathogenicity_class"] in (
            "pathogenic",
            "likely_pathogenic",
            "VUS",
            "likely_benign",
            "benign",
        )

    def test_post_acmg_score_with_all_params(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/acmg-score",
            json={
                "gene": "EGFR",
                "variant": "L858R",
                "alphamissense_score": 0.89,
                "conservation_score": 0.91,
                "structural_context": {"in_critical_domain": True, "domain_name": "kinase domain"},
            },
        )
        assert response.status_code == 200

    def test_post_acmg_score_missing_gene_fails(self, client: TestClient) -> None:
        response = client.post("/clinical/acmg-score", json={"variant": "R175H"})
        assert response.status_code == 422

    def test_post_acmg_score_missing_variant_fails(self, client: TestClient) -> None:
        response = client.post("/clinical/acmg-score", json={"gene": "TP53"})
        assert response.status_code == 422

    def test_post_acmg_score_safety_label(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/acmg-score",
            json={"gene": "TP53", "variant": "R175H"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "safety_label" in data


class TestVUSEndpoints:
    def test_get_vus_queue(self, client: TestClient) -> None:
        response = client.get("/clinical/vus-queue")
        assert response.status_code == 200
        data = response.json()
        assert "queue" in data
        assert isinstance(data["queue"], list)

    def test_get_vus_queue_all_pending(self, client: TestClient) -> None:
        response = client.get("/clinical/vus-queue")
        assert response.status_code == 200
        for entry in response.json()["queue"]:
            assert entry["pending_reclassification"] is True

    def test_post_rescore_vus_single(self, client: TestClient) -> None:
        response = client.post("/clinical/rescore-vus/VUS-001")
        assert response.status_code == 200
        data = response.json()
        assert data["variant_id"] == "VUS-001"
        assert "new_class" in data
        assert "evidence_delta" in data

    def test_post_rescore_vus_not_found(self, client: TestClient) -> None:
        response = client.post("/clinical/rescore-vus/VUS-NONEXISTENT")
        assert response.status_code == 404

    def test_post_rescore_all_vus(self, client: TestClient) -> None:
        response = client.post("/clinical/rescore-all-vus")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 20

    def test_post_rescore_all_vus_summary(self, client: TestClient) -> None:
        response = client.post("/clinical/rescore-all-vus")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "total" in data["summary"]


class TestClinVarEndpoints:
    def test_get_clinvar_lookup_gene(self, client: TestClient) -> None:
        response = client.get("/clinical/clinvar/lookup/TP53")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) > 0

    def test_get_clinvar_lookup_unknown_gene(self, client: TestClient) -> None:
        response = client.get("/clinical/clinvar/lookup/FAKEGENE999")
        assert response.status_code == 200
        data = response.json()
        assert data["entries"] == []

    def test_post_clinvar_lookup_with_variant(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/clinvar/lookup",
            json={"gene": "TP53", "variant": "R175H"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["variant"] == "R175H"

    def test_post_clinvar_lookup_without_variant(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/clinvar/lookup",
            json={"gene": "KRAS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) > 1

    def test_post_clinvar_map_to_structure(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/clinvar/map-to-structure",
            json={"gene": "TP53"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "gene" in data
        assert "pathogenic_hotspots" in data
        assert "domain_summary" in data

    def test_post_clinvar_map_hotspots_list(self, client: TestClient) -> None:
        response = client.post(
            "/clinical/clinvar/map-to-structure",
            json={"gene": "KRAS"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["pathogenic_hotspots"], list)

    def test_get_clinvar_stats(self, client: TestClient) -> None:
        response = client.get("/clinical/clinvar/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] == 30
        assert "significance_distribution" in data

    def test_get_clinvar_stats_safety_label(self, client: TestClient) -> None:
        response = client.get("/clinical/clinvar/stats")
        assert response.status_code == 200
        assert "safety_label" in response.json()
