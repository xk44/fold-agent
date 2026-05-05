"""Tests for Drug Discovery mode — functions and all 8 API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.modes.drug_discovery import (
    APPROVED_DRUG_LIBRARY,
    KNOWN_DRUG_TARGETS,
    AllostericSite,
    BindingSite,
    CompoundHit,
    CovalentHit,
    RepurposingCandidate,
    build_drug_discovery_report,
    find_repurposing_candidates,
    predict_allosteric_sites,
    predict_binding_sites,
    screen_compound_library,
    screen_covalent_candidates,
)


# ---------------------------------------------------------------------------
# predict_binding_sites
# ---------------------------------------------------------------------------


def test_binding_sites_egfr_returns_sites() -> None:
    sites = predict_binding_sites("EGFR")
    assert len(sites) >= 1
    assert all(isinstance(s, BindingSite) for s in sites)


def test_binding_sites_egfr_has_atp_site() -> None:
    sites = predict_binding_sites("EGFR")
    ids = [s.site_id for s in sites]
    assert "EGFR_ATP" in ids


def test_binding_sites_kras_has_covalent_pocket() -> None:
    sites = predict_binding_sites("KRAS")
    types = [s.pocket_type for s in sites]
    assert "covalent" in types


def test_binding_sites_unknown_gene_returns_empty() -> None:
    sites = predict_binding_sites("UNKNOWNGENE99")
    assert sites == []


def test_binding_sites_case_insensitive() -> None:
    upper = predict_binding_sites("EGFR")
    lower = predict_binding_sites("egfr")
    assert len(upper) == len(lower)


def test_binding_sites_all_20_targets_have_data() -> None:
    targets = ["EGFR", "BRAF", "ABL1", "HER2", "VEGFR", "ALK", "KRAS", "TP53",
               "PIK3CA", "PTEN", "CDK4", "MET", "RET", "FLT3", "JAK2", "BTK",
               "BCL2", "IDH1", "FGFR", "MDM2"]
    for gene in targets:
        sites = predict_binding_sites(gene)
        assert len(sites) >= 1, f"No binding sites for {gene}"


def test_binding_site_druggability_in_range() -> None:
    for gene in KNOWN_DRUG_TARGETS:
        for site in predict_binding_sites(gene):
            assert 0.0 <= site.druggability_score <= 1.0, f"{site.site_id} score out of range"


# ---------------------------------------------------------------------------
# screen_compound_library
# ---------------------------------------------------------------------------


def test_virtual_screen_egfr_returns_hits() -> None:
    hits = screen_compound_library("EGFR")
    assert len(hits) >= 1
    assert all(isinstance(h, CompoundHit) for h in hits)


def test_virtual_screen_hits_sorted_by_docking_score() -> None:
    hits = screen_compound_library("ABL1")
    scores = [h.docking_score for h in hits]
    assert scores == sorted(scores)


def test_virtual_screen_passes_lipinski_for_small_molecules() -> None:
    hits = screen_compound_library("BRAF")
    for h in hits:
        assert h.passes_lipinski is True  # all BRAF drugs are small molecules


def test_virtual_screen_unknown_target_returns_empty() -> None:
    hits = screen_compound_library("UNKNOWNXYZ")
    assert hits == []


def test_virtual_screen_library_field_stored() -> None:
    hits = screen_compound_library("EGFR", library="custom_lib")
    assert all(h.library == "custom_lib" for h in hits)


# ---------------------------------------------------------------------------
# screen_covalent_candidates
# ---------------------------------------------------------------------------


def test_covalent_screen_egfr_c797_returns_osimertinib() -> None:
    hits = screen_covalent_candidates("EGFR", ["C797"])
    names = [h.compound_name for h in hits]
    assert "Osimertinib" in names


def test_covalent_screen_kras_c12_returns_sotorasib() -> None:
    hits = screen_covalent_candidates("KRAS", ["C12"])
    names = [h.compound_name for h in hits]
    assert "Sotorasib" in names


def test_covalent_screen_btk_c481_returns_ibrutinib() -> None:
    hits = screen_covalent_candidates("BTK", ["C481"])
    names = [h.compound_name for h in hits]
    assert "Ibrutinib" in names


def test_covalent_screen_no_cysteines_returns_empty() -> None:
    hits = screen_covalent_candidates("EGFR", [])
    assert hits == []


def test_covalent_hit_irreversibility_field() -> None:
    hits = screen_covalent_candidates("EGFR", ["C797"])
    for h in hits:
        assert h.irreversibility in {"irreversible", "reversible_covalent"}


def test_covalent_screen_returns_covalent_hit_instances() -> None:
    hits = screen_covalent_candidates("BTK", ["C481"])
    assert all(isinstance(h, CovalentHit) for h in hits)


# ---------------------------------------------------------------------------
# find_repurposing_candidates
# ---------------------------------------------------------------------------


def test_repurposing_egfr_returns_candidates() -> None:
    cands = find_repurposing_candidates("EGFR")
    assert len(cands) >= 1
    assert all(isinstance(c, RepurposingCandidate) for c in cands)


def test_repurposing_sorted_by_similarity_desc() -> None:
    cands = find_repurposing_candidates("EGFR")
    scores = [c.target_similarity_score for c in cands]
    assert scores == sorted(scores, reverse=True)


def test_repurposing_target_field_correct() -> None:
    cands = find_repurposing_candidates("KRAS")
    for c in cands:
        assert c.repurposing_target == "KRAS"


def test_repurposing_unknown_gene_returns_empty() -> None:
    cands = find_repurposing_candidates("UNKNOWNXYZ")
    assert cands == []


def test_repurposing_no_duplicates_by_drug_name() -> None:
    cands = find_repurposing_candidates("EGFR")
    names = [c.drug_name for c in cands]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# predict_allosteric_sites
# ---------------------------------------------------------------------------


def test_allosteric_kras_returns_sites() -> None:
    sites = predict_allosteric_sites("KRAS")
    assert len(sites) >= 1
    assert all(isinstance(s, AllostericSite) for s in sites)


def test_allosteric_abl1_has_myristoyl_site() -> None:
    sites = predict_allosteric_sites("ABL1")
    ids = [s.site_id for s in sites]
    assert "ABL1_MYRISTOYL" in ids


def test_allosteric_unknown_gene_returns_empty() -> None:
    sites = predict_allosteric_sites("RANDOMGENE")
    assert sites == []


def test_allosteric_druggability_in_range() -> None:
    for sites in [predict_allosteric_sites(g) for g in ["EGFR", "KRAS", "BCL2", "IDH1"]]:
        for site in sites:
            assert 0.0 <= site.druggability_score <= 1.0


# ---------------------------------------------------------------------------
# build_drug_discovery_report
# ---------------------------------------------------------------------------


def test_report_case_not_found(client: TestClient) -> None:
    # Indirectly test via API endpoint
    response = client.get(
        "/cases/nonexistent-case/drug-discovery/report",
        params={"target_genes": "EGFR"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_binding_sites_egfr(client: TestClient) -> None:
    response = client.post("/drug-discovery/binding-sites", json={"gene": "EGFR"})
    assert response.status_code == 200
    data = response.json()
    assert data["gene"] == "EGFR"
    assert data["count"] >= 1
    assert isinstance(data["sites"], list)


def test_api_binding_sites_unknown_gene_returns_empty(client: TestClient) -> None:
    response = client.post("/drug-discovery/binding-sites", json={"gene": "NOPE99"})
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_api_virtual_screen(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/virtual-screen",
        json={"target_gene": "ABL1", "library": "approved_drugs"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "ABL1"
    assert data["hit_count"] >= 1
    assert isinstance(data["hits"], list)


def test_api_virtual_screen_default_library(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/virtual-screen",
        json={"target_gene": "BRAF"},
    )
    assert response.status_code == 200
    assert response.json()["library"] == "approved_drugs"


def test_api_covalent_screen(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/covalent-screen",
        json={"target_gene": "EGFR", "reactive_cysteines": ["C797"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "EGFR"
    names = [h["compound_name"] for h in data["hits"]]
    assert "Osimertinib" in names


def test_api_covalent_screen_no_cysteines(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/covalent-screen",
        json={"target_gene": "TP53", "reactive_cysteines": []},
    )
    assert response.status_code == 200
    assert response.json()["hit_count"] == 0


def test_api_repurposing(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/repurposing",
        json={"target_gene": "EGFR"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["target_gene"] == "EGFR"
    assert data["candidate_count"] >= 1


def test_api_allosteric_sites(client: TestClient) -> None:
    response = client.post(
        "/drug-discovery/allosteric-sites",
        json={"gene": "KRAS"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["gene"] == "KRAS"
    assert data["count"] >= 1


def test_api_known_targets(client: TestClient) -> None:
    response = client.get("/drug-discovery/known-targets")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 20
    assert "EGFR" in data["targets"]
    assert "KRAS" in data["targets"]


def test_api_approved_drugs(client: TestClient) -> None:
    response = client.get("/drug-discovery/approved-drugs")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 30
    names = [d["name"] for d in data["drugs"]]
    assert "Imatinib" in names
    assert "Sotorasib" in names
    assert "Trastuzumab" in names


def test_api_case_drug_discovery_report(client: TestClient) -> None:
    # Create a case first
    create_resp = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Drug discovery test case"},
    )
    assert create_resp.status_code == 201
    case_id = create_resp.json()["id"]

    response = client.get(
        f"/cases/{case_id}/drug-discovery/report",
        params={"target_genes": "EGFR,KRAS,BRAF"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert set(data["target_genes"]) == {"EGFR", "KRAS", "BRAF"}
    assert data["summary"]["total_targets_analyzed"] == 3
    assert data["summary"]["total_binding_sites"] >= 3
    assert "targets" in data


def test_api_case_drug_discovery_report_empty_genes(client: TestClient) -> None:
    create_resp = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "Empty genes test"},
    )
    case_id = create_resp.json()["id"]
    response = client.get(
        f"/cases/{case_id}/drug-discovery/report",
        params={"target_genes": ""},
    )
    assert response.status_code == 422
