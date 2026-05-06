"""Tests for Conformational Ensemble Sampling (Phase 23)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.conformational_ensemble import (
    ConformationalState,
    EnsembleResult,
    calculate_flexibility_profile,
    get_dominant_state,
    sample_conformational_ensemble,
)

_SEQ = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSY"
_SHORT = "ACDE"


# ---------------------------------------------------------------------------
# sample_conformational_ensemble — unit tests
# ---------------------------------------------------------------------------


def test_returns_ensemble_result() -> None:
    result = sample_conformational_ensemble(_SEQ)
    assert isinstance(result, EnsembleResult)


def test_sequence_preserved() -> None:
    result = sample_conformational_ensemble(_SEQ)
    assert result.sequence == _SEQ


def test_n_samples_preserved() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=30)
    assert result.n_samples == 30


def test_n_clusters_bounded() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=100)
    assert 1 <= result.n_clusters <= 5


def test_n_clusters_minimum_one() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=1)
    assert result.n_clusters >= 1


def test_states_count_equals_n_clusters() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=50)
    assert len(result.states) == result.n_clusters


def test_population_weights_sum_to_one() -> None:
    result = sample_conformational_ensemble(_SEQ)
    total = sum(s.population_weight for s in result.states)
    assert abs(total - 1.0) < 1e-4


def test_plddt_in_range() -> None:
    result = sample_conformational_ensemble(_SEQ)
    for s in result.states:
        assert 0.0 <= s.plddt_mean <= 100.0


def test_rmsd_reference_is_zero_for_state_0() -> None:
    result = sample_conformational_ensemble(_SEQ)
    state0 = next(s for s in result.states if s.state_id == 0)
    assert state0.rmsd_to_reference == 0.0


def test_diversity_score_non_negative() -> None:
    result = sample_conformational_ensemble(_SEQ)
    assert result.diversity_score >= 0.0


def test_converged_true_for_large_n() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=50)
    assert result.converged is True


def test_converged_false_for_small_n() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=5)
    assert result.converged is False


def test_deterministic() -> None:
    r1 = sample_conformational_ensemble(_SEQ, n_samples=30)
    r2 = sample_conformational_ensemble(_SEQ, n_samples=30)
    assert r1.n_clusters == r2.n_clusters
    assert r1.diversity_score == r2.diversity_score


def test_pdb_data_nonempty() -> None:
    result = sample_conformational_ensemble(_SHORT)
    for s in result.states:
        assert len(s.pdb_data) > 0


# ---------------------------------------------------------------------------
# get_dominant_state — unit tests
# ---------------------------------------------------------------------------


def test_get_dominant_state_type() -> None:
    result = sample_conformational_ensemble(_SEQ)
    dominant = get_dominant_state(result)
    assert isinstance(dominant, ConformationalState)


def test_get_dominant_state_is_max_weight() -> None:
    result = sample_conformational_ensemble(_SEQ, n_samples=50)
    dominant = get_dominant_state(result)
    assert dominant.population_weight == max(s.population_weight for s in result.states)


def test_get_dominant_state_raises_on_empty() -> None:
    empty = EnsembleResult(sequence="A", n_samples=0, states=[])
    with pytest.raises(ValueError):
        get_dominant_state(empty)


# ---------------------------------------------------------------------------
# calculate_flexibility_profile — unit tests
# ---------------------------------------------------------------------------


def test_flexibility_profile_residue_count() -> None:
    result = sample_conformational_ensemble(_SEQ)
    profile = calculate_flexibility_profile(result)
    assert len(profile["residue_indices"]) == len(_SEQ)
    assert len(profile["flexibility_scores"]) == len(_SEQ)


def test_flexibility_profile_scores_positive() -> None:
    result = sample_conformational_ensemble(_SEQ)
    profile = calculate_flexibility_profile(result)
    assert all(s >= 0.0 for s in profile["flexibility_scores"])


def test_flexibility_profile_mean_positive() -> None:
    result = sample_conformational_ensemble(_SEQ)
    profile = calculate_flexibility_profile(result)
    assert profile["mean_flexibility"] > 0.0


def test_flexibility_profile_empty_sequence() -> None:
    result = EnsembleResult(sequence="", n_samples=0)
    profile = calculate_flexibility_profile(result)
    assert profile["residue_indices"] == []
    assert profile["flexibility_scores"] == []
    assert profile["mean_flexibility"] == 0.0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_conformational_sampling_200(client: TestClient) -> None:
    resp = client.post("/ensemble/conformational-sampling", json={"sequence": _SEQ})
    assert resp.status_code == 200


def test_api_conformational_sampling_has_states(client: TestClient) -> None:
    resp = client.post(
        "/ensemble/conformational-sampling", json={"sequence": _SEQ, "n_samples": 20}
    )
    data = resp.json()
    assert "states" in data
    assert len(data["states"]) >= 1


def test_api_dominant_state_200(client: TestClient) -> None:
    resp = client.post("/ensemble/dominant-state", json={"sequence": _SEQ})
    assert resp.status_code == 200


def test_api_dominant_state_has_population_weight(client: TestClient) -> None:
    resp = client.post("/ensemble/dominant-state", json={"sequence": _SEQ})
    data = resp.json()
    assert "population_weight" in data
    assert 0.0 < data["population_weight"] <= 1.0


def test_api_flexibility_profile_200(client: TestClient) -> None:
    resp = client.post("/ensemble/flexibility-profile", json={"sequence": _SHORT})
    assert resp.status_code == 200


def test_api_flexibility_profile_has_profile(client: TestClient) -> None:
    resp = client.post("/ensemble/flexibility-profile", json={"sequence": _SEQ})
    data = resp.json()
    assert "profile" in data
    assert "flexibility_scores" in data["profile"]
