"""Tests for Enzyme Engineering mode — functions and all 6 API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.modes.enzyme_engineering import (
    KNOWN_PRODRUG_SYSTEMS,
    KNOWN_THERAPEUTIC_ENZYMES,
    EnzymeSubstrate,
    ERTDesign,
    MutationSuggestion,
    ProdugSystem,
    design_ert,
    find_prodrug_system,
    model_enzyme_substrate,
    suggest_mutations,
)

# ---------------------------------------------------------------------------
# model_enzyme_substrate
# ---------------------------------------------------------------------------


def test_model_enzyme_substrate_gba_returns_known_data() -> None:
    result = model_enzyme_substrate("GBA", "glucocerebroside")
    assert isinstance(result, EnzymeSubstrate)
    assert result.enzyme_gene == "GBA"
    assert result.kcat_estimate == 4.2


def test_model_enzyme_substrate_gla_known() -> None:
    result = model_enzyme_substrate("GLA", "globotriaosylceramide")
    assert result.enzyme_gene == "GLA"
    assert len(result.active_site_residues) > 0


def test_model_enzyme_substrate_case_insensitive() -> None:
    upper = model_enzyme_substrate("GBA", "glucocerebroside")
    lower = model_enzyme_substrate("gba", "glucocerebroside")
    assert upper.kcat_estimate == lower.kcat_estimate


def test_model_enzyme_substrate_unknown_returns_mock() -> None:
    result = model_enzyme_substrate("FAKEENZ", "fakesubstrate")
    assert result.enzyme_gene == "FAKEENZ"
    assert result.binding_mode == "predicted_hydrolysis"
    assert result.kcat_estimate > 0
    assert result.km_estimate_um > 0


def test_model_enzyme_substrate_active_site_nonempty() -> None:
    result = model_enzyme_substrate("GAA", "glycogen")
    assert len(result.active_site_residues) >= 1


def test_model_enzyme_substrate_km_positive() -> None:
    for gene in ["GBA", "GLA", "GAA", "IDUA", "ADA"]:
        result = model_enzyme_substrate(gene, "")
        assert result.km_estimate_um > 0, f"km <= 0 for {gene}"


def test_known_therapeutic_enzymes_has_10_entries() -> None:
    assert len(KNOWN_THERAPEUTIC_ENZYMES) == 10


def test_known_therapeutic_enzymes_contains_expected() -> None:
    assert "GBA" in KNOWN_THERAPEUTIC_ENZYMES
    assert "GLA" in KNOWN_THERAPEUTIC_ENZYMES
    assert "GAA" in KNOWN_THERAPEUTIC_ENZYMES
    assert "ADA" in KNOWN_THERAPEUTIC_ENZYMES


# ---------------------------------------------------------------------------
# suggest_mutations
# ---------------------------------------------------------------------------


def test_suggest_mutations_gba_activity() -> None:
    mutations = suggest_mutations("GBA", "activity")
    assert len(mutations) >= 1
    assert all(isinstance(m, MutationSuggestion) for m in mutations)


def test_suggest_mutations_gba_stability() -> None:
    mutations = suggest_mutations("GBA", "stability")
    assert len(mutations) >= 1
    assert all(m.predicted_effect == "stability" for m in mutations)


def test_suggest_mutations_gba_immunogenicity() -> None:
    mutations = suggest_mutations("GBA", "immunogenicity")
    assert len(mutations) >= 1


def test_suggest_mutations_invalid_objective_defaults_to_activity() -> None:
    mutations = suggest_mutations("GBA", "nonsense_objective")
    result_default = suggest_mutations("GBA", "activity")
    assert len(mutations) == len(result_default)


def test_suggest_mutations_unknown_enzyme_returns_empty() -> None:
    mutations = suggest_mutations("FAKEENZYME", "activity")
    assert mutations == []


def test_suggest_mutations_confidence_in_range() -> None:
    for obj in ["activity", "stability", "half_life", "immunogenicity", "specificity"]:
        for m in suggest_mutations("GBA", obj):
            assert 0.0 <= m.confidence <= 1.0, f"{obj} confidence out of range"


def test_suggest_mutations_gla_activity() -> None:
    mutations = suggest_mutations("GLA", "activity")
    assert len(mutations) >= 1


def test_suggest_mutations_each_has_rationale() -> None:
    mutations = suggest_mutations("ADA", "activity")
    for m in mutations:
        assert len(m.rationale) > 0


# ---------------------------------------------------------------------------
# design_ert
# ---------------------------------------------------------------------------


def test_design_ert_gba_gaucher() -> None:
    result = design_ert("GBA", "Gaucher disease")
    assert isinstance(result, ERTDesign)
    assert result.disease == "Gaucher disease"
    assert len(result.wild_type_issues) >= 1
    assert len(result.suggested_modifications) >= 1


def test_design_ert_gla_fabry() -> None:
    result = design_ert("GLA", "Fabry disease")
    assert result is not None
    assert "Fabry" in result.disease


def test_design_ert_unknown_enzyme_returns_none() -> None:
    result = design_ert("FAKEENZYME", "unknown disease")
    assert result is None


def test_design_ert_glycosylation_sites_nonempty() -> None:
    result = design_ert("GAA", "Pompe disease")
    assert result is not None
    assert len(result.glycosylation_sites) > 0


def test_design_ert_half_life_improvement_nonempty() -> None:
    for gene in ["GBA", "GLA", "GAA", "IDUA", "ADA"]:
        result = design_ert(gene, "")
        assert result is not None
        assert len(result.half_life_improvement) > 0


def test_design_ert_case_insensitive() -> None:
    upper = design_ert("GBA", "Gaucher disease")
    lower = design_ert("gba", "Gaucher disease")
    assert upper is not None and lower is not None
    assert upper.disease == lower.disease


# ---------------------------------------------------------------------------
# find_prodrug_system
# ---------------------------------------------------------------------------


def test_find_prodrug_hsvtk_ganciclovir() -> None:
    result = find_prodrug_system("HSV-TK")
    assert result is not None
    assert isinstance(result, ProdugSystem)
    assert result.prodrug == "Ganciclovir"


def test_find_prodrug_cd_5fc() -> None:
    result = find_prodrug_system("CD")
    assert result is not None
    assert "5-FC" in result.prodrug or "5-Fluorocytosine" in result.prodrug


def test_find_prodrug_tymp_capecitabine() -> None:
    result = find_prodrug_system("TYMP")
    assert result is not None
    assert result.prodrug == "Capecitabine"
    assert "5-FU" in result.active_drug or "5-Fluorouracil" in result.active_drug


def test_find_prodrug_unknown_returns_none() -> None:
    result = find_prodrug_system("UNKNOWNENZ")
    assert result is None


def test_find_prodrug_tumor_selectivity_nonempty() -> None:
    for key in KNOWN_PRODRUG_SYSTEMS:
        result = find_prodrug_system(key)
        assert result is not None
        assert len(result.tumor_selectivity) > 0


def test_known_prodrug_systems_has_6_entries() -> None:
    assert len(KNOWN_PRODRUG_SYSTEMS) == 6


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_enzyme_model_substrate_gba(client: TestClient) -> None:
    response = client.post(
        "/enzyme/model-substrate",
        json={"enzyme_gene": "GBA", "substrate": "glucocerebroside"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enzyme_gene"] == "GBA"
    assert data["kcat_estimate"] == 4.2


def test_api_enzyme_model_substrate_unknown(client: TestClient) -> None:
    response = client.post(
        "/enzyme/model-substrate",
        json={"enzyme_gene": "FAKEENZ", "substrate": "fakesubstrate"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["binding_mode"] == "predicted_hydrolysis"


def test_api_enzyme_suggest_mutations_gba_activity(client: TestClient) -> None:
    response = client.post(
        "/enzyme/suggest-mutations",
        json={"enzyme_gene": "GBA", "objective": "activity"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enzyme_gene"] == "GBA"
    assert data["objective"] == "activity"
    assert data["suggestion_count"] >= 1


def test_api_enzyme_suggest_mutations_default_objective(client: TestClient) -> None:
    response = client.post(
        "/enzyme/suggest-mutations",
        json={"enzyme_gene": "GBA"},
    )
    assert response.status_code == 200
    assert response.json()["objective"] == "activity"


def test_api_enzyme_suggest_mutations_unknown_enzyme(client: TestClient) -> None:
    response = client.post(
        "/enzyme/suggest-mutations",
        json={"enzyme_gene": "FAKEENZ", "objective": "activity"},
    )
    assert response.status_code == 200
    assert response.json()["suggestion_count"] == 0


def test_api_enzyme_design_ert_gba(client: TestClient) -> None:
    response = client.post(
        "/enzyme/design-ert",
        json={"enzyme_gene": "GBA", "disease": "Gaucher disease"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["enzyme_gene"] == "GBA"
    assert len(data["wild_type_issues"]) >= 1
    assert len(data["suggested_modifications"]) >= 1


def test_api_enzyme_design_ert_unknown_404(client: TestClient) -> None:
    response = client.post(
        "/enzyme/design-ert",
        json={"enzyme_gene": "FAKEENZ", "disease": "unknown"},
    )
    assert response.status_code == 404


def test_api_enzyme_known_therapeutic(client: TestClient) -> None:
    response = client.get("/enzyme/known-therapeutic")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 10
    assert "GBA" in data["enzymes"]
    assert "ADA" in data["enzymes"]


def test_api_enzyme_prodrug_systems(client: TestClient) -> None:
    response = client.get("/enzyme/prodrug-systems")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 6
    assert "HSV-TK" in data["systems"]


def test_api_enzyme_prodrug_lookup_found(client: TestClient) -> None:
    response = client.post(
        "/enzyme/prodrug-lookup",
        json={"enzyme_gene": "HSV-TK"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is True
    assert data["system"]["prodrug"] == "Ganciclovir"


def test_api_enzyme_prodrug_lookup_not_found(client: TestClient) -> None:
    response = client.post(
        "/enzyme/prodrug-lookup",
        json={"enzyme_gene": "EGFR"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["found"] is False
    assert data["system"] is None
