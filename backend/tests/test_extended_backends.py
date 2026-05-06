"""Tests for extended backends, ensemble scoring, and research mode safety (Phase 7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.alphafold_backends import (
    _BACKEND_MAP,
    Boltz1Backend,
    Boltz2Backend,
    Chai1Backend,
    ESMFoldBackend,
    OpenFoldBackend,
    PredictionResult,
    ProteinMPNNBackend,
    RFdiffusion2Backend,
    RFdiffusionBackend,
    StructureCache,
)
from backend.app.ensemble import EnsembleResult, compare_backends, run_ensemble
from backend.app.mode_safety import (
    ResearchMode,
    check_mode_safety,
    get_mode_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEQ = "ACDEFGHIKLMNPQRSTVWY"


# ---------------------------------------------------------------------------
# validate() — 8 new backends
# ---------------------------------------------------------------------------


def test_boltz1_validate_structure() -> None:
    b = Boltz1Backend()
    v = b.validate()
    assert v.name == "boltz1"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


def test_boltz2_validate_structure() -> None:
    b = Boltz2Backend()
    v = b.validate()
    assert v.name == "boltz2"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


def test_esmfold_validate_structure() -> None:
    b = ESMFoldBackend()
    v = b.validate()
    assert v.name == "esmfold"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


def test_openfold_validate_structure() -> None:
    b = OpenFoldBackend()
    v = b.validate()
    assert v.name == "openfold"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


def test_rfdiffusion_validate_structure() -> None:
    b = RFdiffusionBackend()
    v = b.validate()
    assert v.name == "rfdiffusion"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False


def test_proteinmpnn_validate_structure() -> None:
    b = ProteinMPNNBackend()
    v = b.validate()
    assert v.name == "proteinmpnn"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False


def test_chai1_validate_structure() -> None:
    b = Chai1Backend()
    v = b.validate()
    assert v.name == "chai1"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    # Chai1 is proprietary — privacy_risk is "low"
    assert v.privacy_risk == "low"


def test_rfdiffusion2_validate_structure() -> None:
    b = RFdiffusion2Backend()
    v = b.validate()
    assert v.name == "rfdiffusion2"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


# ---------------------------------------------------------------------------
# All new backends in _BACKEND_MAP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "boltz1",
        "boltz2",
        "esmfold",
        "openfold",
        "rfdiffusion",
        "proteinmpnn",
        "chai1",
        "rfdiffusion2",
    ],
)
def test_new_backends_registered(name: str) -> None:
    assert name in _BACKEND_MAP


# ---------------------------------------------------------------------------
# predict() — Boltz1, Boltz2, ESMFold (stubs that return results)
# ---------------------------------------------------------------------------


def test_boltz1_predict_returns_pdb_and_plddt() -> None:
    b = Boltz1Backend()
    result = b.predict(SEQ, {})
    assert isinstance(result, PredictionResult)
    assert result.pdb_data is not None
    assert "ATOM" in result.pdb_data
    assert result.backend_name == "boltz1"
    assert "pLDDT_mean" in result.confidence
    assert "pTM" in result.confidence
    assert result.duration_seconds >= 0.0
    assert result.cached is False


def test_boltz2_predict_returns_binding_affinity() -> None:
    b = Boltz2Backend()
    result = b.predict(SEQ, {})
    assert isinstance(result, PredictionResult)
    assert result.pdb_data is not None
    assert "binding_affinity_kcal" in result.confidence
    assert isinstance(result.confidence["binding_affinity_kcal"], float)
    assert result.confidence.get("supports_affinity") is True
    assert "pLDDT_mean" in result.confidence


def test_esmfold_predict_fast_mode() -> None:
    b = ESMFoldBackend()
    result = b.predict(SEQ, {})
    assert isinstance(result, PredictionResult)
    assert result.pdb_data is not None
    assert result.confidence.get("fast_mode") is True
    assert result.confidence.get("msa_used") is False
    assert "pLDDT_mean" in result.confidence


# ---------------------------------------------------------------------------
# RFdiffusion design modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["binder", "scaffold", "symmetric", "enzyme"])
def test_rfdiffusion_predict_design_modes(mode: str) -> None:
    b = RFdiffusionBackend()
    result = b.predict(SEQ, {"design_mode": mode})
    assert result.backend_name == "rfdiffusion"
    assert result.confidence["design_mode"] == mode
    assert result.pdb_data is not None


def test_rfdiffusion_predict_invalid_design_mode_raises() -> None:
    b = RFdiffusionBackend()
    with pytest.raises(ValueError, match="Invalid design_mode"):
        b.predict(SEQ, {"design_mode": "invalid_mode"})


def test_rfdiffusion_predict_default_design_mode() -> None:
    b = RFdiffusionBackend()
    result = b.predict(SEQ, {})
    assert result.confidence["design_mode"] == "binder"


# ---------------------------------------------------------------------------
# ProteinMPNN — inverse folding
# ---------------------------------------------------------------------------


def test_proteinmpnn_predict_returns_sequences() -> None:
    b = ProteinMPNNBackend()
    result = b.predict(SEQ, {"num_sequences": 5})
    assert result.pdb_data is None  # returns sequences, not PDB
    assert "designed_sequences" in result.confidence
    assert len(result.confidence["designed_sequences"]) == 5


def test_proteinmpnn_predict_default_num_sequences() -> None:
    b = ProteinMPNNBackend()
    result = b.predict(SEQ, {})
    assert len(result.confidence["designed_sequences"]) == 3


# ---------------------------------------------------------------------------
# RFdiffusion2 — enzyme design
# ---------------------------------------------------------------------------


def test_rfdiffusion2_predict_reaction_description() -> None:
    b = RFdiffusion2Backend()
    result = b.predict(SEQ, {"reaction_description": "phosphorylation of serine"})
    assert result.backend_name == "rfdiffusion2"
    assert result.confidence["reaction_description"] == "phosphorylation of serine"
    assert result.pdb_data is not None


# ---------------------------------------------------------------------------
# Ensemble — run_ensemble
# ---------------------------------------------------------------------------


def test_ensemble_run_with_mock_backend() -> None:
    StructureCache.clear()
    result = run_ensemble(SEQ, ["mock"], {})
    assert isinstance(result, EnsembleResult)
    assert result.backends_used == ["mock"]
    assert len(result.results) == 1
    assert result.best_result.backend_name == "mock"
    assert isinstance(result.agreement_score, float)


def test_ensemble_run_multiple_stub_backends() -> None:
    StructureCache.clear()
    result = run_ensemble(SEQ, ["mock", "boltz1", "boltz2", "esmfold"], {})
    assert set(result.backends_used) == {"mock", "boltz1", "boltz2", "esmfold"}
    assert len(result.results) == 4
    assert result.consensus_plddt is not None
    assert 0.0 <= result.agreement_score <= 1.0
    assert result.best_result.backend_name in result.backends_used


def test_ensemble_consensus_plddt_is_average() -> None:
    StructureCache.clear()
    result = run_ensemble(SEQ, ["mock", "boltz1"], {})
    plddts = [r.confidence["pLDDT_mean"] for r in result.results]
    expected = sum(plddts) / len(plddts)
    assert abs(result.consensus_plddt - expected) < 1e-6


def test_ensemble_empty_backends_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        run_ensemble(SEQ, [], {})


def test_ensemble_unknown_backend_raises() -> None:
    with pytest.raises(KeyError):
        run_ensemble(SEQ, ["nonexistent_backend_xyz"], {})


def test_ensemble_all_unavailable_raises() -> None:
    """Backends that raise NotImplementedError result in RuntimeError if all fail."""
    with pytest.raises(RuntimeError, match="All backends failed"):
        run_ensemble(SEQ, ["colabfold"], {})


# ---------------------------------------------------------------------------
# Ensemble — compare_backends
# ---------------------------------------------------------------------------


def test_compare_backends_returns_table() -> None:
    StructureCache.clear()
    result = compare_backends(SEQ, ["mock", "boltz1"])
    assert "backends" in result
    assert result["total_backends"] == 2
    assert result["successful"] == 2
    assert result["failed"] == 0
    assert result["best_backend"] in {"mock", "boltz1"}
    assert result["consensus_plddt"] is not None


def test_compare_backends_marks_stubs_as_failed() -> None:
    StructureCache.clear()
    result = compare_backends(SEQ, ["mock", "colabfold"])
    rows = {r["backend"]: r for r in result["backends"]}
    assert rows["mock"]["available"] is True
    assert rows["colabfold"]["available"] is False
    assert rows["colabfold"]["error"] is not None


def test_compare_backends_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        compare_backends(SEQ, [])


def test_compare_backends_unknown_raises() -> None:
    with pytest.raises(KeyError):
        compare_backends(SEQ, ["unknown_xyz"])


# ---------------------------------------------------------------------------
# Mode safety — get_mode_config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [m.value for m in ResearchMode])
def test_get_mode_config_all_modes(mode: str) -> None:
    config = get_mode_config(mode)
    assert "safety_level" in config
    assert "requires_attestation" in config
    assert "requires_ethics_review" in config
    assert "allowed_backends" in config
    assert "prohibited_actions" in config
    assert "disclaimers" in config


def test_get_mode_config_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown research mode"):
        get_mode_config("not_a_real_mode")


def test_gene_therapy_requires_ethics_review() -> None:
    config = get_mode_config("gene_therapy")
    assert config["requires_ethics_review"] is True
    assert config["safety_level"] == "expert_only"
    assert config["requires_attestation"] is True


def test_neoantigen_standard_safety() -> None:
    config = get_mode_config("neoantigen")
    assert config["safety_level"] == "standard"
    assert config["requires_attestation"] is False
    assert config["requires_ethics_review"] is False


# ---------------------------------------------------------------------------
# Mode safety — check_mode_safety
# ---------------------------------------------------------------------------


def test_check_mode_safety_allowed_action() -> None:
    result = check_mode_safety("neoantigen", "run_structure_prediction")
    assert result["allowed"] is True
    assert "permitted" in result["reason"]
    assert isinstance(result["disclaimers"], list)


def test_check_mode_safety_blocked_action() -> None:
    result = check_mode_safety("gene_therapy", "human_germline_editing")
    assert result["allowed"] is False
    assert "prohibited" in result["reason"]
    assert isinstance(result["disclaimers"], list)
    assert len(result["disclaimers"]) > 0


def test_check_mode_safety_drug_discovery_blocked_action() -> None:
    result = check_mode_safety("drug_discovery", "publish_without_ip_review")
    assert result["allowed"] is False


def test_check_mode_safety_returns_safety_level() -> None:
    result = check_mode_safety("gene_therapy", "run_structure_prediction")
    assert result["safety_level"] == "expert_only"
    assert result["requires_attestation"] is True
    assert result["requires_ethics_review"] is True


def test_check_mode_safety_unknown_mode_raises() -> None:
    with pytest.raises(KeyError, match="Unknown research mode"):
        check_mode_safety("fake_mode", "some_action")


# ---------------------------------------------------------------------------
# API — GET /backends/all
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from backend.app.main import app

    return TestClient(app)


def test_api_backends_all_returns_15(client) -> None:
    resp = client.get("/backends/all")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 15
    names = {b["name"] for b in data}
    # original 7
    assert "mock" in names
    assert "colabfold" in names
    assert "alphafold_db" in names
    # new 8
    assert "boltz1" in names
    assert "boltz2" in names
    assert "esmfold" in names
    assert "openfold" in names
    assert "rfdiffusion" in names
    assert "proteinmpnn" in names
    assert "chai1" in names
    assert "rfdiffusion2" in names


def test_api_backends_all_has_description(client) -> None:
    resp = client.get("/backends/all")
    data = resp.json()
    boltz1 = next(b for b in data if b["name"] == "boltz1")
    assert "Boltz-1" in boltz1["description"] or boltz1["description"] != ""


# ---------------------------------------------------------------------------
# API — POST /ensemble/predict
# ---------------------------------------------------------------------------


def test_api_ensemble_predict(client) -> None:
    StructureCache.clear()
    resp = client.post(
        "/ensemble/predict",
        json={"sequence": SEQ, "backends": ["mock", "boltz1"], "options": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["backends_used"]) == {"mock", "boltz1"}
    assert data["consensus_plddt"] is not None
    assert "agreement_score" in data
    assert "best_backend" in data
    assert len(data["results"]) == 2


def test_api_ensemble_predict_unknown_backend_404(client) -> None:
    resp = client.post(
        "/ensemble/predict",
        json={"sequence": SEQ, "backends": ["unknown_xyz"]},
    )
    assert resp.status_code == 404


def test_api_ensemble_predict_empty_backends_400(client) -> None:
    resp = client.post(
        "/ensemble/predict",
        json={"sequence": SEQ, "backends": []},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# API — POST /ensemble/compare
# ---------------------------------------------------------------------------


def test_api_ensemble_compare(client) -> None:
    StructureCache.clear()
    resp = client.post(
        "/ensemble/compare",
        json={"sequence": SEQ, "backends": ["mock", "boltz2"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_backends"] == 2
    assert data["successful"] == 2
    assert "best_backend" in data


def test_api_ensemble_compare_unknown_backend_404(client) -> None:
    resp = client.post(
        "/ensemble/compare",
        json={"sequence": SEQ, "backends": ["no_such_backend"]},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API — GET /modes
# ---------------------------------------------------------------------------


def test_api_modes_list(client) -> None:
    resp = client.get("/modes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == len(list(ResearchMode))
    modes = {m["mode"] for m in data}
    assert "neoantigen" in modes
    assert "gene_therapy" in modes
    assert "enzyme_engineering" in modes


# ---------------------------------------------------------------------------
# API — GET /modes/{mode}
# ---------------------------------------------------------------------------


def test_api_mode_get_valid(client) -> None:
    resp = client.get("/modes/neoantigen")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "neoantigen"
    assert data["safety_level"] == "standard"
    assert isinstance(data["allowed_backends"], list)


def test_api_mode_get_gene_therapy(client) -> None:
    resp = client.get("/modes/gene_therapy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_level"] == "expert_only"
    assert data["requires_ethics_review"] is True


def test_api_mode_get_unknown_404(client) -> None:
    resp = client.get("/modes/fake_mode_xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API — POST /modes/{mode}/check
# ---------------------------------------------------------------------------


def test_api_mode_check_allowed(client) -> None:
    resp = client.post("/modes/neoantigen/check", json={"action": "run_prediction"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["mode"] == "neoantigen"
    assert data["action"] == "run_prediction"


def test_api_mode_check_blocked(client) -> None:
    resp = client.post("/modes/gene_therapy/check", json={"action": "human_germline_editing"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert isinstance(data["disclaimers"], list)


def test_api_mode_check_unknown_mode_404(client) -> None:
    resp = client.post("/modes/nonexistent_mode/check", json={"action": "do_something"})
    assert resp.status_code == 404
