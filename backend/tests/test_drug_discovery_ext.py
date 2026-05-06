"""Tests for Drug Discovery Extensions — AF3 Co-folding + ADMET (Phase 23)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.modes.drug_discovery import (
    ADMETProfile,
    CoFoldingResult,
    predict_admet,
    predict_cofold,
)

# ---------------------------------------------------------------------------
# predict_cofold — unit tests
# ---------------------------------------------------------------------------


def test_cofold_returns_cofoldingresult() -> None:
    result = predict_cofold("EGFR", "CC(=O)Oc1ccccc1C(=O)O")
    assert isinstance(result, CoFoldingResult)


def test_cofold_target_gene_uppercased() -> None:
    result = predict_cofold("egfr", "CC")
    assert result.target_gene == "EGFR"


def test_cofold_binding_energy_range() -> None:
    result = predict_cofold("BRAF", "c1ccccc1")
    assert -12.0 <= result.binding_energy_kcal <= -3.0


def test_cofold_confidence_known_target_elevated() -> None:
    known = predict_cofold("EGFR", "CC")
    unknown = predict_cofold("FAKEGENE", "CC")
    assert known.confidence >= unknown.confidence


def test_cofold_confidence_in_range() -> None:
    result = predict_cofold("KRAS", "CC(=O)N")
    assert 0.0 <= result.confidence <= 1.0


def test_cofold_pdb_data_nonempty() -> None:
    result = predict_cofold("ABL1", "c1cnc2ccccc2n1")
    assert len(result.predicted_binding_pose) > 0


def test_cofold_pdb_contains_hetatm() -> None:
    result = predict_cofold("EGFR", "c1ccccc1")
    assert "HETATM" in result.predicted_binding_pose


def test_cofold_contact_residues_nonempty() -> None:
    result = predict_cofold("HER2", "CC1=CC=CC=C1")
    assert len(result.contact_residues) >= 1


def test_cofold_contact_residues_positive() -> None:
    result = predict_cofold("ALK", "CC")
    assert all(r > 0 for r in result.contact_residues)


def test_cofold_deterministic() -> None:
    r1 = predict_cofold("KRAS", "Cc1ccc(cc1)S(=O)(=O)N")
    r2 = predict_cofold("KRAS", "Cc1ccc(cc1)S(=O)(=O)N")
    assert r1.binding_energy_kcal == r2.binding_energy_kcal
    assert r1.confidence == r2.confidence
    assert r1.contact_residues == r2.contact_residues


def test_cofold_different_smiles_different_energy() -> None:
    r1 = predict_cofold("EGFR", "CC")
    r2 = predict_cofold("EGFR", "c1ccc2ccccc2c1")
    assert r1.binding_energy_kcal != r2.binding_energy_kcal


def test_cofold_unknown_target_still_returns_result() -> None:
    result = predict_cofold("UNKNOWNTARGET999", "CC")
    assert isinstance(result, CoFoldingResult)
    assert result.target_gene == "UNKNOWNTARGET999"


# ---------------------------------------------------------------------------
# predict_cofold — API endpoint tests
# ---------------------------------------------------------------------------


def test_api_cofold_200(client: TestClient) -> None:
    resp = client.post(
        "/drug-discovery/cofold", json={"target_gene": "EGFR", "ligand_smiles": "CC"}
    )
    assert resp.status_code == 200


def test_api_cofold_has_binding_energy(client: TestClient) -> None:
    resp = client.post(
        "/drug-discovery/cofold", json={"target_gene": "BRAF", "ligand_smiles": "c1ccccc1"}
    )
    data = resp.json()
    assert "binding_energy_kcal" in data
    assert -12.0 <= data["binding_energy_kcal"] <= -3.0


def test_api_cofold_has_contact_residues(client: TestClient) -> None:
    resp = client.post(
        "/drug-discovery/cofold", json={"target_gene": "KRAS", "ligand_smiles": "CCN"}
    )
    data = resp.json()
    assert "contact_residues" in data
    assert isinstance(data["contact_residues"], list)


def test_api_cofold_has_safety_label(client: TestClient) -> None:
    resp = client.post(
        "/drug-discovery/cofold", json={"target_gene": "ABL1", "ligand_smiles": "CC"}
    )
    assert "safety_label" in resp.json()


# ---------------------------------------------------------------------------
# predict_admet — unit tests
# ---------------------------------------------------------------------------


def test_admet_returns_admetprofile() -> None:
    result = predict_admet("Aspirin", "CC(=O)Oc1ccccc1C(=O)O")
    assert isinstance(result, ADMETProfile)


def test_admet_absorption_in_range() -> None:
    result = predict_admet("X", "CC")
    assert 0.0 <= result.absorption <= 1.0


def test_admet_distribution_positive() -> None:
    result = predict_admet("X", "CC")
    assert result.distribution_vd > 0


def test_admet_cyp_risk_valid() -> None:
    result = predict_admet("Drug", "c1ccccc1")
    assert result.metabolism_cyp_risk in {"low", "medium", "high"}


def test_admet_half_life_positive() -> None:
    result = predict_admet("X", "CCCC")
    assert result.excretion_half_life_hours > 0


def test_admet_lipinski_violations_range() -> None:
    result = predict_admet("BigMolecule", "C" * 70)
    assert 0 <= result.lipinski_violations <= 5


def test_admet_large_smiles_increases_violations() -> None:
    small = predict_admet("small", "CC")
    large = predict_admet("large", "C" * 80 + "NNNOOO")
    assert large.lipinski_violations >= small.lipinski_violations


def test_admet_drug_likeness_in_range() -> None:
    result = predict_admet("X", "CC")
    assert 0.0 <= result.drug_likeness_score <= 1.0


def test_admet_deterministic() -> None:
    r1 = predict_admet("Imatinib", "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C")
    r2 = predict_admet("Imatinib", "Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C")
    assert r1.absorption == r2.absorption
    assert r1.lipinski_violations == r2.lipinski_violations


def test_admet_compound_name_preserved() -> None:
    result = predict_admet("MyCompound", "CC")
    assert result.compound_name == "MyCompound"


# ---------------------------------------------------------------------------
# predict_admet — API endpoint tests
# ---------------------------------------------------------------------------


def test_api_admet_200(client: TestClient) -> None:
    resp = client.post(
        "/drug-discovery/admet",
        json={"compound_name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
    )
    assert resp.status_code == 200


def test_api_admet_has_lipinski(client: TestClient) -> None:
    resp = client.post("/drug-discovery/admet", json={"compound_name": "X", "smiles": "CC"})
    data = resp.json()
    assert "lipinski_violations" in data
    assert isinstance(data["lipinski_violations"], int)


def test_api_admet_has_drug_likeness(client: TestClient) -> None:
    resp = client.post("/drug-discovery/admet", json={"compound_name": "X", "smiles": "CC"})
    data = resp.json()
    assert "drug_likeness_score" in data
    assert 0.0 <= data["drug_likeness_score"] <= 1.0


def test_api_admet_has_safety_label(client: TestClient) -> None:
    resp = client.post("/drug-discovery/admet", json={"compound_name": "X", "smiles": "CC"})
    assert "safety_label" in resp.json()
