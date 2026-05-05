"""Tests for backend/app/workflow_integration.py — Phase 24 Tier 1."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.workflow_integration import (
    TASK_CLASS_BENCHMARKS,
    TOOL_VERSIONS,
    BackendRecommendation,
    BatchResult,
    EnsembleHeatmapResult,
    NormalizedStructure,
    PerResidueDisagreement,
    SequenceProvenance,
    VersionPin,
    check_all_versions,
    compute_ensemble_heatmap,
    detect_format,
    get_version_manifest,
    normalize_pdb,
    pin_version,
    recommend_backend,
    run_batch_prediction,
)

_SEQ = "ACDEFGHIKLMNPQRSTVWY"
_SHORT = "MKTLL"
_BACKENDS = ["mock", "boltz1", "esmfold"]


# ---------------------------------------------------------------------------
# Feature 1: Per-residue ensemble disagreement heatmap
# ---------------------------------------------------------------------------


def test_heatmap_returns_correct_type() -> None:
    result = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    assert isinstance(result, EnsembleHeatmapResult)


def test_heatmap_length_matches_sequence() -> None:
    result = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    assert len(result.per_residue) == len(_SHORT)


def test_heatmap_per_residue_type() -> None:
    result = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    for pr in result.per_residue:
        assert isinstance(pr, PerResidueDisagreement)


def test_heatmap_plddt_values_count_matches_backends() -> None:
    result = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    for pr in result.per_residue:
        assert len(pr.plddt_values) == len(_BACKENDS)


def test_heatmap_disagreement_level_valid_values() -> None:
    result = compute_ensemble_heatmap(_SEQ, _BACKENDS)
    valid = {"low", "medium", "high"}
    for pr in result.per_residue:
        assert pr.disagreement_level in valid


def test_heatmap_residue_index_sequential() -> None:
    result = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    for idx, pr in enumerate(result.per_residue):
        assert pr.residue_index == idx


def test_heatmap_mean_plddt_in_range() -> None:
    result = compute_ensemble_heatmap(_SEQ, _BACKENDS)
    for pr in result.per_residue:
        assert 0.0 <= pr.mean_plddt <= 100.0


def test_heatmap_std_plddt_non_negative() -> None:
    result = compute_ensemble_heatmap(_SEQ, _BACKENDS)
    for pr in result.per_residue:
        assert pr.std_plddt >= 0.0


def test_heatmap_deterministic() -> None:
    r1 = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    r2 = compute_ensemble_heatmap(_SHORT, _BACKENDS)
    for pr1, pr2 in zip(r1.per_residue, r2.per_residue):
        assert pr1.plddt_values == pr2.plddt_values
        assert pr1.mean_plddt == pr2.mean_plddt


def test_heatmap_overall_disagreement_non_negative() -> None:
    result = compute_ensemble_heatmap(_SEQ, _BACKENDS)
    assert result.overall_disagreement >= 0.0


def test_heatmap_high_disagreement_regions_are_tuples() -> None:
    result = compute_ensemble_heatmap(_SEQ, _BACKENDS)
    for region in result.high_disagreement_regions:
        assert isinstance(region, tuple)
        assert len(region) == 2
        assert region[0] <= region[1]


def test_heatmap_single_backend_zero_std() -> None:
    result = compute_ensemble_heatmap(_SHORT, ["mock"])
    for pr in result.per_residue:
        assert pr.std_plddt == 0.0
        assert pr.disagreement_level == "low"


def test_heatmap_low_classification_for_single_backend() -> None:
    result = compute_ensemble_heatmap(_SHORT, ["mock"])
    for pr in result.per_residue:
        assert pr.disagreement_level == "low"


# ---------------------------------------------------------------------------
# Feature 2: Input-type-aware backend selector
# ---------------------------------------------------------------------------


def test_task_class_benchmarks_has_expected_classes() -> None:
    expected = {"monomer", "multimer", "antibody_antigen", "small_molecule", "nucleic_acid"}
    assert expected.issubset(TASK_CLASS_BENCHMARKS)


def test_recommend_monomer_returns_recommendation() -> None:
    rec = recommend_backend("monomer")
    assert isinstance(rec, BackendRecommendation)
    assert rec.task_class == "monomer"
    assert rec.recommended


def test_recommend_multimer_returns_recommendation() -> None:
    rec = recommend_backend("multimer")
    assert rec.task_class == "multimer"
    assert rec.recommended


def test_recommend_antibody_antigen() -> None:
    rec = recommend_backend("antibody_antigen")
    assert rec.task_class == "antibody_antigen"


def test_recommend_small_molecule() -> None:
    rec = recommend_backend("small_molecule")
    assert rec.task_class == "small_molecule"


def test_recommend_nucleic_acid() -> None:
    rec = recommend_backend("nucleic_acid")
    assert rec.task_class == "nucleic_acid"


def test_recommend_accuracy_in_range() -> None:
    for task in TASK_CLASS_BENCHMARKS:
        rec = recommend_backend(task)
        assert 0.0 <= rec.accuracy_estimate <= 1.0


def test_recommend_alternatives_is_list() -> None:
    rec = recommend_backend("monomer")
    assert isinstance(rec.alternatives, list)


def test_recommend_recommended_not_in_alternatives() -> None:
    rec = recommend_backend("monomer")
    assert rec.recommended not in rec.alternatives


def test_recommend_cloud_blocked_by_default() -> None:
    # Cloud backends should not appear when allow_cloud=False
    for task in TASK_CLASS_BENCHMARKS:
        rec = recommend_backend(task, allow_cloud=False)
        cloud_set = {"alphafold_server", "alphafold_db"}
        assert rec.recommended not in cloud_set
        for alt in rec.alternatives:
            assert alt not in cloud_set


def test_recommend_unknown_task_raises() -> None:
    with pytest.raises(ValueError, match="Unknown task class"):
        recommend_backend("nonexistent_task_xyz")


def test_recommend_reasoning_is_string() -> None:
    rec = recommend_backend("monomer")
    assert isinstance(rec.reasoning, str)
    assert len(rec.reasoning) > 0


# ---------------------------------------------------------------------------
# Feature 3: Batch prediction provenance
# ---------------------------------------------------------------------------


def test_batch_result_type() -> None:
    result = run_batch_prediction([_SHORT])
    assert isinstance(result, BatchResult)


def test_batch_total_matches_input() -> None:
    seqs = [_SHORT, _SEQ, "MKTLL"]
    result = run_batch_prediction(seqs)
    assert result.total == 3
    assert result.completed == 3


def test_batch_provenance_count() -> None:
    seqs = [_SHORT, _SEQ]
    result = run_batch_prediction(seqs)
    assert len(result.provenances) == 2


def test_batch_provenance_type() -> None:
    result = run_batch_prediction([_SHORT])
    assert isinstance(result.provenances[0], SequenceProvenance)


def test_batch_input_hash_is_sha256() -> None:
    result = run_batch_prediction([_SHORT])
    h = result.provenances[0].input_hash
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_batch_input_hash_correctness() -> None:
    expected = hashlib.sha256(_SHORT.encode()).hexdigest()
    result = run_batch_prediction([_SHORT])
    assert result.provenances[0].input_hash == expected


def test_batch_manifest_hash_is_sha256() -> None:
    result = run_batch_prediction([_SHORT, _SEQ])
    assert len(result.manifest_hash) == 64


def test_batch_manifest_hash_deterministic() -> None:
    seqs = [_SHORT, _SEQ]
    r1 = run_batch_prediction(seqs)
    r2 = run_batch_prediction(seqs)
    assert r1.manifest_hash == r2.manifest_hash


def test_batch_manifest_hash_changes_with_different_sequences() -> None:
    r1 = run_batch_prediction([_SHORT])
    r2 = run_batch_prediction([_SEQ])
    assert r1.manifest_hash != r2.manifest_hash


def test_batch_backend_version_recorded() -> None:
    result = run_batch_prediction([_SHORT], backend_name="mock")
    assert result.provenances[0].backend_version == "1.0.0"


def test_batch_timestamp_is_iso() -> None:
    result = run_batch_prediction([_SHORT])
    ts = result.provenances[0].timestamp
    # Should be parseable ISO format
    from datetime import datetime
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt is not None


def test_batch_empty_sequences_raises() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        run_batch_prediction([])


def test_batch_pdb_data_present_for_mock() -> None:
    result = run_batch_prediction([_SHORT], backend_name="mock")
    assert result.provenances[0].pdb_data is not None


def test_batch_confidence_has_plddt() -> None:
    result = run_batch_prediction([_SHORT], backend_name="mock")
    conf = result.provenances[0].confidence
    assert "pLDDT_mean" in conf


def test_batch_sequence_ids_unique() -> None:
    result = run_batch_prediction([_SHORT, _SEQ, "MKTLL"])
    ids = [p.sequence_id for p in result.provenances]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Feature 4: PDB/mmCIF normalizer
# ---------------------------------------------------------------------------

_SAMPLE_PDB = """\
REMARK  Test PDB
ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 80.00           C
ATOM      2  CA  GLY A   2       2.000   3.000   4.000  1.00 75.00           C
ATOM      3  CA  SER B   1       3.000   4.000   5.000  1.00 85.00           C
HETATM    4  C1  LIG A 100       5.000   6.000   7.000  1.00 60.00           C
END
"""

_SAMPLE_PDB_WITH_INS = """\
REMARK  Insertion code test
ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 80.00           C
ATOM      2  CA  GLY A   1A      2.000   3.000   4.000  1.00 75.00           C
END
"""

_SAMPLE_MMCIF = """\
data_TEST
loop_
_atom_site.id
_atom_site.label_atom_id
1 CA
"""


def test_detect_format_pdb() -> None:
    assert detect_format(_SAMPLE_PDB) == "pdb"


def test_detect_format_mmcif() -> None:
    assert detect_format(_SAMPLE_MMCIF) == "mmcif"


def test_detect_format_data_prefix() -> None:
    assert detect_format("data_SOMETHING\n_atom_site.id\n") == "mmcif"


def test_normalize_pdb_returns_normalized_structure() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    assert isinstance(result, NormalizedStructure)


def test_normalize_pdb_counts_atoms() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    # 3 ATOM + 1 HETATM = 4 atoms total
    assert result.n_atoms == 4


def test_normalize_pdb_counts_residues() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    # ALA A 1, GLY A 2, SER B 1, LIG A 100 → 4 unique residues
    assert result.n_residues == 4


def test_normalize_pdb_hetatm_warning() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    assert any("HETATM" in w for w in result.warnings)


def test_normalize_pdb_chain_rename() -> None:
    result = normalize_pdb(_SAMPLE_PDB, chain_rename={"A": "X", "B": "Y"})
    assert "A" in result.chain_map or "X" in result.data
    # Both chains should be renamed
    assert result.chain_map.get("A") == "X"
    assert result.chain_map.get("B") == "Y"


def test_normalize_pdb_chain_rename_in_data() -> None:
    result = normalize_pdb(_SAMPLE_PDB, chain_rename={"A": "X"})
    lines = [l for l in result.data.splitlines() if l.startswith(("ATOM", "HETATM"))]
    for line in lines:
        if line[21] not in (" ", "B"):
            assert line[21] == "X"


def test_normalize_pdb_insertion_code_warning() -> None:
    result = normalize_pdb(_SAMPLE_PDB_WITH_INS)
    assert any("insertion code" in w.lower() for w in result.warnings)


def test_normalize_pdb_format_field() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    assert result.format == "pdb"


def test_normalize_mmcif_passthrough() -> None:
    result = normalize_pdb(_SAMPLE_MMCIF)
    assert result.format == "mmcif"
    assert "mmCIF" in result.warnings[0]


def test_normalize_pdb_no_chain_rename_empty_map() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    assert result.chain_map == {}


def test_normalize_pdb_data_is_string() -> None:
    result = normalize_pdb(_SAMPLE_PDB)
    assert isinstance(result.data, str)


# ---------------------------------------------------------------------------
# Feature 5: Version pinning
# ---------------------------------------------------------------------------


def test_tool_versions_has_expected_tools() -> None:
    expected = {"alphafold2_local", "alphafold3_local", "boltz1", "boltz2", "mock"}
    assert expected.issubset(TOOL_VERSIONS)


def test_pin_version_returns_version_pin() -> None:
    pin = pin_version("mock")
    assert isinstance(pin, VersionPin)


def test_pin_version_mock_not_superseded() -> None:
    pin = pin_version("mock")
    assert pin.superseded is False
    assert pin.supersession_warning is None


def test_pin_version_alphafold2_superseded() -> None:
    pin = pin_version("alphafold2_local")
    assert pin.superseded is True
    assert pin.supersession_warning is not None
    assert "alphafold3_local" in pin.supersession_warning


def test_pin_version_boltz1_superseded() -> None:
    pin = pin_version("boltz1")
    assert pin.superseded is True
    assert "boltz2" in pin.supersession_warning


def test_pin_version_unknown_raises() -> None:
    with pytest.raises(KeyError, match="Unknown tool"):
        pin_version("nonexistent_tool_xyz")


def test_pin_version_pinned_matches_current() -> None:
    for name in TOOL_VERSIONS:
        pin = pin_version(name)
        assert pin.pinned_version == pin.current_version


def test_check_all_versions_returns_list() -> None:
    pins = check_all_versions()
    assert isinstance(pins, list)
    assert len(pins) == len(TOOL_VERSIONS)


def test_check_all_versions_all_pins() -> None:
    pins = check_all_versions()
    names = {p.tool_name for p in pins}
    assert names == set(TOOL_VERSIONS)


def test_get_version_manifest_keys() -> None:
    manifest = get_version_manifest()
    assert "versions" in manifest
    assert "superseded" in manifest
    assert "total_tools" in manifest
    assert "manifest_hash" in manifest


def test_get_version_manifest_total_count() -> None:
    manifest = get_version_manifest()
    assert manifest["total_tools"] == len(TOOL_VERSIONS)


def test_get_version_manifest_hash_is_sha256() -> None:
    manifest = get_version_manifest()
    h = manifest["manifest_hash"]
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_get_version_manifest_deterministic() -> None:
    m1 = get_version_manifest()
    m2 = get_version_manifest()
    assert m1["manifest_hash"] == m2["manifest_hash"]


def test_get_version_manifest_superseded_count() -> None:
    manifest = get_version_manifest()
    assert manifest["superseded_count"] >= 1  # at least alphafold2 is superseded


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_api_ensemble_heatmap(client: TestClient) -> None:
    resp = client.post(
        "/workflow/ensemble-heatmap",
        json={"sequence": _SHORT, "backend_names": ["mock", "boltz1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "per_residue" in data
    assert len(data["per_residue"]) == len(_SHORT)
    assert "overall_disagreement" in data


def test_api_ensemble_heatmap_empty_sequence(client: TestClient) -> None:
    resp = client.post(
        "/workflow/ensemble-heatmap",
        json={"sequence": "", "backend_names": ["mock"]},
    )
    assert resp.status_code == 422


def test_api_recommend_backend(client: TestClient) -> None:
    resp = client.post(
        "/workflow/recommend-backend",
        json={"task_class": "monomer"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "recommended" in data
    assert "accuracy_estimate" in data


def test_api_recommend_backend_unknown_task(client: TestClient) -> None:
    resp = client.post(
        "/workflow/recommend-backend",
        json={"task_class": "unknown_xyz"},
    )
    assert resp.status_code == 422


def test_api_recommend_backend_all_task_classes(client: TestClient) -> None:
    for task in TASK_CLASS_BENCHMARKS:
        resp = client.post(
            "/workflow/recommend-backend",
            json={"task_class": task},
        )
        assert resp.status_code == 200, f"Failed for task class: {task}"


def test_api_batch_predict(client: TestClient) -> None:
    resp = client.post(
        "/workflow/batch-predict",
        json={"sequences": [_SHORT, _SEQ], "backend_name": "mock"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["completed"] == 2
    assert len(data["provenances"]) == 2
    assert "manifest_hash" in data


def test_api_batch_predict_provenance_fields(client: TestClient) -> None:
    resp = client.post(
        "/workflow/batch-predict",
        json={"sequences": [_SHORT], "backend_name": "mock"},
    )
    assert resp.status_code == 200
    prov = resp.json()["provenances"][0]
    assert "input_hash" in prov
    assert "backend_version" in prov
    assert "timestamp" in prov
    assert "runtime_seconds" in prov


def test_api_batch_predict_empty_sequences(client: TestClient) -> None:
    resp = client.post(
        "/workflow/batch-predict",
        json={"sequences": []},
    )
    assert resp.status_code == 422


def test_api_normalize_pdb(client: TestClient) -> None:
    resp = client.post(
        "/workflow/normalize-pdb",
        json={"pdb_data": _SAMPLE_PDB},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["n_atoms"] == 4
    assert "warnings" in data


def test_api_normalize_pdb_chain_rename(client: TestClient) -> None:
    resp = client.post(
        "/workflow/normalize-pdb",
        json={"pdb_data": _SAMPLE_PDB, "chain_rename": {"A": "Z"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chain_map"].get("A") == "Z"


def test_api_normalize_pdb_empty_raises(client: TestClient) -> None:
    resp = client.post(
        "/workflow/normalize-pdb",
        json={"pdb_data": ""},
    )
    assert resp.status_code == 422


def test_api_tool_versions(client: TestClient) -> None:
    resp = client.get("/workflow/tool-versions")
    assert resp.status_code == 200
    data = resp.json()
    assert "tool_versions" in data
    assert "mock" in data["tool_versions"]


def test_api_version_pin(client: TestClient) -> None:
    resp = client.get("/workflow/version-pin/mock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "mock"
    assert data["superseded"] is False


def test_api_version_pin_superseded(client: TestClient) -> None:
    resp = client.get("/workflow/version-pin/alphafold2_local")
    assert resp.status_code == 200
    data = resp.json()
    assert data["superseded"] is True
    assert data["supersession_warning"] is not None


def test_api_version_pin_unknown(client: TestClient) -> None:
    resp = client.get("/workflow/version-pin/nonexistent_tool")
    assert resp.status_code == 404


def test_api_version_manifest(client: TestClient) -> None:
    resp = client.get("/workflow/version-manifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert "manifest_hash" in data
    assert "total_tools" in data


def test_api_check_versions_all(client: TestClient) -> None:
    resp = client.post("/workflow/check-versions", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "pins" in data
    assert data["total"] == len(TOOL_VERSIONS)


def test_api_check_versions_filtered(client: TestClient) -> None:
    resp = client.post(
        "/workflow/check-versions",
        json={"tool_names": ["mock", "boltz1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    names = {p["tool_name"] for p in data["pins"]}
    assert names == {"mock", "boltz1"}


def test_api_check_versions_superseded_count(client: TestClient) -> None:
    resp = client.post("/workflow/check-versions", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["superseded_count"] >= 1
