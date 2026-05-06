"""Tests for backend/app/alphafold_backends.py (Phase 6 abstraction)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.alphafold_backends import (
    AlphaFold2LocalBackend,
    AlphaFold3LocalBackend,
    AlphaFoldDBBackend,
    AlphaFoldServerBackend,
    BackendSelector,
    ColabFoldBackend,
    LocalColabFoldBackend,
    MockBackend,
    PredictionResult,
    StructureCache,
    _make_input_hash,
    predict_with_cache,
)

# ---------------------------------------------------------------------------
# validate() — each backend
# ---------------------------------------------------------------------------


def test_mock_backend_validate_always_available() -> None:
    b = MockBackend()
    v = b.validate()
    assert v.name == "mock"
    assert v.available is True
    assert v.cloud is False
    assert v.gpu_required is False
    assert v.privacy_risk == "none"


def test_colabfold_validate_returns_validation() -> None:
    b = ColabFoldBackend()
    v = b.validate()
    assert v.name == "colabfold"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False


def test_local_colabfold_validate() -> None:
    b = LocalColabFoldBackend()
    v = b.validate()
    assert v.name == "local_colabfold"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False
    assert v.privacy_risk == "none"


def test_alphafold2_local_validate() -> None:
    b = AlphaFold2LocalBackend()
    v = b.validate()
    assert v.name == "alphafold2_local"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False


def test_alphafold3_local_validate() -> None:
    b = AlphaFold3LocalBackend()
    v = b.validate()
    assert v.name == "alphafold3_local"
    assert isinstance(v.available, bool)
    assert v.gpu_required is True
    assert v.cloud is False


def test_alphafold_server_validate_is_cloud_high_privacy() -> None:
    b = AlphaFoldServerBackend()
    v = b.validate()
    assert v.name == "alphafold_server"
    assert v.available is True
    assert v.cloud is True
    assert v.privacy_risk == "high"


def test_alphafold_db_validate_is_cloud() -> None:
    b = AlphaFoldDBBackend()
    v = b.validate()
    assert v.name == "alphafold_db"
    assert v.available is True
    assert v.cloud is True


# ---------------------------------------------------------------------------
# MockBackend.predict()
# ---------------------------------------------------------------------------


def test_mock_backend_predict_returns_pdb_and_confidence() -> None:
    b = MockBackend()
    result = b.predict("ACDEFGHIKLM", {})
    assert isinstance(result, PredictionResult)
    assert result.pdb_data is not None
    assert "ATOM" in result.pdb_data or "END" in result.pdb_data
    assert result.backend_name == "mock"
    assert result.duration_seconds >= 0.0
    assert result.cached is False
    assert "pLDDT_mean" in result.confidence
    assert "pAE_mean" in result.confidence


def test_mock_backend_predict_different_sequences() -> None:
    b = MockBackend()
    r1 = b.predict("ACDE", {})
    r2 = b.predict("MTEYK", {})
    assert r1.pdb_data != r2.pdb_data  # different sequences → different PDB


# ---------------------------------------------------------------------------
# StructureCache
# ---------------------------------------------------------------------------


def test_structure_cache_miss_then_hit() -> None:
    cache = StructureCache()
    StructureCache.clear()

    h = _make_input_hash("TESTSEQ", {})
    assert cache.get(h) is None

    result = PredictionResult(
        pdb_data="ATOM...",
        confidence={"pLDDT_mean": 80.0},
        backend_name="mock",
        duration_seconds=0.01,
    )
    cache.put(h, result)
    cached = cache.get(h)
    assert cached is not None
    assert cached.backend_name == "mock"


def test_structure_cache_stats_track_hits_misses() -> None:
    StructureCache.clear()
    cache = StructureCache()
    h = _make_input_hash("STATSEQ", {"opt": 1})

    cache.get(h)  # miss
    result = PredictionResult(
        pdb_data="pdb", confidence={}, backend_name="mock", duration_seconds=0.001
    )
    cache.put(h, result)
    cache.get(h)  # hit
    cache.get(h)  # hit

    stats = StructureCache.stats()
    assert stats["hits"] >= 2
    assert stats["misses"] >= 1
    assert stats["size"] >= 1


def test_predict_with_cache_returns_cached_on_second_call() -> None:
    StructureCache.clear()
    b = MockBackend()
    r1 = predict_with_cache(b, "CACHESEQ", {})
    r2 = predict_with_cache(b, "CACHESEQ", {})
    assert r1.cached is False
    assert r2.cached is True
    assert r1.pdb_data == r2.pdb_data


# ---------------------------------------------------------------------------
# BackendSelector
# ---------------------------------------------------------------------------


def test_selector_returns_mock_when_preferred() -> None:
    sel = BackendSelector()
    b = sel.select_backend(preferred="mock", allow_cloud=False, allow_fallback=False)
    assert b.name == "mock"


def test_selector_falls_back_to_mock_when_preferred_unavailable() -> None:
    """Prefer a backend that won't be available (e.g. alphafold2_local on CI),
    and verify the selector falls back to mock."""
    sel = BackendSelector()
    # alphafold2_local is almost certainly unavailable on CI
    b2 = AlphaFold2LocalBackend()
    v = b2.validate()
    if v.available:
        pytest.skip("alphafold2_local is actually available — fallback not triggered")
    b = sel.select_backend(preferred="alphafold2_local", allow_cloud=False, allow_fallback=True)
    assert b is not None
    assert b.name != "alphafold2_local"


def test_selector_raises_when_preferred_unavailable_no_fallback() -> None:
    sel = BackendSelector()
    b2 = AlphaFold2LocalBackend()
    v = b2.validate()
    if v.available:
        pytest.skip("alphafold2_local is actually available")
    with pytest.raises(RuntimeError, match="not available"):
        sel.select_backend(preferred="alphafold2_local", allow_cloud=False, allow_fallback=False)


def test_selector_blocks_cloud_when_not_allowed() -> None:
    sel = BackendSelector()
    with pytest.raises(PermissionError, match="allow_cloud=False"):
        sel.select_backend(preferred="alphafold_server", allow_cloud=False, allow_fallback=False)


def test_selector_allows_cloud_when_permitted() -> None:
    sel = BackendSelector()
    b = sel.select_backend(preferred="alphafold_server", allow_cloud=True, allow_fallback=False)
    assert b.name == "alphafold_server"


def test_selector_unknown_backend_raises_key_error() -> None:
    sel = BackendSelector()
    with pytest.raises(KeyError, match="Unknown backend"):
        sel.select_backend(preferred="does_not_exist", allow_cloud=False, allow_fallback=False)


def test_get_all_backend_statuses_returns_all() -> None:
    sel = BackendSelector()
    statuses = sel.get_all_backend_statuses()
    names = [s.name for s in statuses]
    for expected in [
        "mock",
        "colabfold",
        "local_colabfold",
        "alphafold2_local",
        "alphafold3_local",
        "alphafold_server",
        "alphafold_db",
    ]:
        assert expected in names


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_api_list_v2_backends(client: TestClient) -> None:
    response = client.get("/alphafold/v2/backends")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 7
    names = [item["name"] for item in data]
    assert "mock" in names
    assert "alphafold_server" in names
    for item in data:
        assert "available" in item
        assert "reason" in item
        assert "gpu_required" in item
        assert "cloud" in item
        assert "privacy_risk" in item


def test_api_validate_mock_backend(client: TestClient) -> None:
    response = client.get("/alphafold/v2/backends/mock/validate")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "mock"
    assert data["available"] is True


def test_api_validate_unknown_backend_404(client: TestClient) -> None:
    response = client.get("/alphafold/v2/backends/does_not_exist/validate")
    assert response.status_code == 404


def test_api_predict_with_mock_backend(client: TestClient) -> None:
    StructureCache.clear()
    response = client.post(
        "/alphafold/v2/predict",
        json={
            "sequence": "MTEYKLVVVG",
            "backend": "mock",
            "allow_cloud": False,
            "allow_fallback": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["backend_name"] == "mock"
    assert data["pdb_data"] is not None
    assert "pLDDT_mean" in data["confidence"]
    assert data["cached"] is False


def test_api_predict_second_call_is_cached(client: TestClient) -> None:
    StructureCache.clear()
    seq = "CACHEDSEQTEST"
    body = {"sequence": seq, "backend": "mock", "allow_cloud": False, "allow_fallback": False}
    r1 = client.post("/alphafold/v2/predict", json=body)
    r2 = client.post("/alphafold/v2/predict", json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True


def test_api_predict_cloud_blocked_without_permission(client: TestClient) -> None:
    response = client.post(
        "/alphafold/v2/predict",
        json={
            "sequence": "ACDE",
            "backend": "alphafold_server",
            "allow_cloud": False,
            "allow_fallback": False,
        },
    )
    assert response.status_code == 403


def test_api_predict_fallback_when_preferred_unavailable(client: TestClient) -> None:
    b2 = AlphaFold2LocalBackend()
    if b2.validate().available:
        pytest.skip("alphafold2_local is actually available")
    response = client.post(
        "/alphafold/v2/predict",
        json={
            "sequence": "MTEYK",
            "backend": "alphafold2_local",
            "allow_cloud": False,
            "allow_fallback": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["backend_name"] != "alphafold2_local"


def test_api_cache_stats(client: TestClient) -> None:
    StructureCache.clear()
    response = client.get("/alphafold/v2/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert "hits" in data
    assert "misses" in data
    assert "size" in data


def test_api_cache_stats_after_predict(client: TestClient) -> None:
    StructureCache.clear()
    client.post(
        "/alphafold/v2/predict",
        json={"sequence": "STATSTEST", "backend": "mock"},
    )
    response = client.get("/alphafold/v2/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["size"] >= 1
