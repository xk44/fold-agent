"""Tests for Reproducibility Infrastructure — Phase 24 Tier 1."""

from __future__ import annotations

import json
import sys

import pytest
from fastapi.testclient import TestClient

from backend.app.reproducibility import (
    DATABASE_VERSION_REGISTRY,
    EDAM_ONTOLOGY_TERMS,
    SCHEMA_ORG_CONTEXT,
    TOOL_VERSION_REGISTRY,
    DatabaseVersion,
    EnvironmentSnapshot,
    FAIRMetadata,
    FAIRReport,
    PipelineManifest,
    ToolVersion,
    capture_environment,
    create_fair_report,
    create_manifest,
    generate_fair_metadata,
    generate_rerun_command,
    get_manifest,
    list_manifests,
    store_manifest,
    suggest_repository,
    validate_fair_compliance,
    verify_manifest,
    _manifest_store,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_manifest_store():
    """Ensure each test starts with a clean manifest store."""
    _manifest_store.clear()
    yield
    _manifest_store.clear()


def _make_manifest(tools: list[str] | None = None) -> PipelineManifest:
    return create_manifest(
        tool_names=tools or ["mock", "alphafold2_local"],
        inputs={"sequence": "MKTAYIAKQRQISFVKSHFSRQ"},
        outputs={"plddt": 85.3, "pdb": "ATOM..."},
        seeds={"numpy": 42, "torch": 7},
    )


def _make_fair_report(kw: list[str] | None = None) -> FAIRReport:
    meta = generate_fair_metadata(
        title="Test Protein Prediction",
        description="A test neoantigen structure prediction",
        creators=["Researcher A"],
        keywords=kw or ["protein", "structure", "neoantigen"],
    )
    return create_fair_report({"plddt": 85.3, "sequence": "MKTY"}, meta)


# ---------------------------------------------------------------------------
# EnvironmentSnapshot tests
# ---------------------------------------------------------------------------

class TestEnvironmentSnapshot:
    def test_captures_real_python_version(self):
        env = capture_environment()
        assert sys.version in env.python_version

    def test_platform_non_empty(self):
        env = capture_environment()
        assert env.platform and len(env.platform) > 0

    def test_cpu_count_positive(self):
        env = capture_environment()
        assert env.cpu_count >= 1

    def test_env_hash_is_sha256(self):
        env = capture_environment()
        assert len(env.env_hash) == 64
        assert all(c in "0123456789abcdef" for c in env.env_hash)

    def test_gpu_available_is_bool(self):
        env = capture_environment()
        assert isinstance(env.gpu_available, bool)

    def test_snapshot_is_dataclass(self):
        env = capture_environment()
        assert isinstance(env, EnvironmentSnapshot)


# ---------------------------------------------------------------------------
# PipelineManifest creation tests
# ---------------------------------------------------------------------------

class TestManifestCreation:
    def test_manifest_id_is_uuid(self):
        m = _make_manifest()
        import uuid
        uuid.UUID(m.manifest_id)  # raises if invalid

    def test_created_at_is_iso(self):
        from datetime import datetime, timezone
        m = _make_manifest()
        dt = datetime.fromisoformat(m.created_at)
        assert dt.tzinfo is not None

    def test_tool_versions_populated(self):
        m = _make_manifest(["mock", "alphafold2_local"])
        assert len(m.tool_versions) == 2
        names = {t.name for t in m.tool_versions}
        assert "mock" in names
        assert "alphafold2_local" in names

    def test_known_tool_gets_correct_version(self):
        m = _make_manifest(["alphafold2_local"])
        tv = m.tool_versions[0]
        assert tv.version == TOOL_VERSION_REGISTRY["alphafold2_local"]

    def test_unknown_tool_gets_unknown_version(self):
        m = create_manifest(["nonexistent_tool"], {}, {})
        tv = m.tool_versions[0]
        assert tv.version == "unknown"

    def test_tool_checksum_is_sha256(self):
        m = _make_manifest(["mock"])
        tv = m.tool_versions[0]
        assert tv.checksum and len(tv.checksum) == 64

    def test_tool_source_local_for_local_backends(self):
        m = _make_manifest(["mock"])
        assert m.tool_versions[0].source == "local"

    def test_tool_source_cloud_for_cloud_backends(self):
        m = create_manifest(["alphafold_server"], {}, {})
        assert m.tool_versions[0].source == "cloud"

    def test_all_db_versions_present(self):
        m = _make_manifest()
        db_names = {d.name for d in m.database_versions}
        for k in DATABASE_VERSION_REGISTRY:
            assert k in db_names

    def test_input_hashes_computed(self):
        m = create_manifest(["mock"], {"seq": "MKTY"}, {})
        assert "seq" in m.input_hashes
        assert len(m.input_hashes["seq"]) == 64

    def test_output_hashes_computed(self):
        m = create_manifest(["mock"], {}, {"result": 42})
        assert "result" in m.output_hashes

    def test_seeds_stored(self):
        m = create_manifest(["mock"], {}, {}, seeds={"np": 123})
        assert m.random_seeds == {"np": 123}

    def test_seeds_default_empty(self):
        m = create_manifest(["mock"], {}, {})
        assert m.random_seeds == {}

    def test_reproducibility_score_in_range(self):
        m = _make_manifest()
        assert 0.0 <= m.reproducibility_score <= 1.0

    def test_all_known_tools_give_max_score(self):
        m = create_manifest(list(TOOL_VERSION_REGISTRY.keys()), {}, {})
        assert m.reproducibility_score == 1.0

    def test_rerun_command_contains_manifest_id(self):
        m = _make_manifest()
        assert m.manifest_id in m.rerun_command

    def test_environment_captured(self):
        m = _make_manifest()
        assert isinstance(m.environment, EnvironmentSnapshot)


# ---------------------------------------------------------------------------
# Manifest verification tests
# ---------------------------------------------------------------------------

class TestManifestVerification:
    def test_verify_own_manifest_passes(self):
        m = _make_manifest()
        ok, issues = verify_manifest(m)
        assert ok is True
        assert issues == []

    def test_verify_detects_python_version_mismatch(self):
        m = _make_manifest()
        m.environment.python_version = "1.0.0 (fake)"
        ok, issues = verify_manifest(m)
        assert ok is False
        assert any("Python version" in i for i in issues)

    def test_verify_detects_platform_mismatch(self):
        m = _make_manifest()
        m.environment.platform = "FakeOS-99"
        ok, issues = verify_manifest(m)
        assert ok is False
        assert any("Platform" in i for i in issues)

    def test_verify_detects_tool_version_mismatch(self):
        m = _make_manifest(["mock"])
        m.tool_versions[0].version = "0.0.1-fake"
        ok, issues = verify_manifest(m)
        assert ok is False
        assert any("mock" in i for i in issues)

    def test_verify_detects_unknown_tool(self):
        m = _make_manifest()
        m.tool_versions.append(ToolVersion(name="ghost_tool", version="1.0", source="local"))
        ok, issues = verify_manifest(m)
        assert ok is False
        assert any("ghost_tool" in i for i in issues)

    def test_verify_returns_all_issues(self):
        m = _make_manifest(["mock", "boltz1"])
        m.environment.python_version = "0.0"
        m.tool_versions[0].version = "999"
        ok, issues = verify_manifest(m)
        assert ok is False
        assert len(issues) >= 2


# ---------------------------------------------------------------------------
# Rerun command tests
# ---------------------------------------------------------------------------

class TestRerunCommand:
    def test_contains_neovax_run(self):
        m = _make_manifest()
        cmd = generate_rerun_command(m)
        assert cmd.startswith("neovax run")

    def test_contains_manifest_id_flag(self):
        m = _make_manifest()
        cmd = generate_rerun_command(m)
        assert "--manifest-id" in cmd

    def test_contains_tools_flag(self):
        m = _make_manifest(["mock"])
        cmd = generate_rerun_command(m)
        assert "--tools" in cmd
        assert "mock" in cmd

    def test_contains_seeds_when_present(self):
        m = create_manifest(["mock"], {}, {}, seeds={"np": 42})
        cmd = generate_rerun_command(m)
        assert "--seeds" in cmd
        assert "np=42" in cmd

    def test_no_seeds_flag_when_empty(self):
        m = create_manifest(["mock"], {}, {}, seeds={})
        cmd = generate_rerun_command(m)
        assert "--seeds" not in cmd


# ---------------------------------------------------------------------------
# Manifest store tests
# ---------------------------------------------------------------------------

class TestManifestStore:
    def test_store_returns_manifest_id(self):
        m = _make_manifest()
        mid = store_manifest(m)
        assert mid == m.manifest_id

    def test_get_manifest_returns_stored(self):
        m = _make_manifest()
        store_manifest(m)
        retrieved = get_manifest(m.manifest_id)
        assert retrieved is not None
        assert retrieved.manifest_id == m.manifest_id

    def test_get_manifest_returns_none_for_missing(self):
        assert get_manifest("nonexistent-id") is None

    def test_list_manifests_shows_summaries(self):
        m1 = _make_manifest(["mock"])
        m2 = _make_manifest(["boltz1"])
        store_manifest(m1)
        store_manifest(m2)
        summaries = list_manifests()
        assert len(summaries) == 2
        ids = {s["manifest_id"] for s in summaries}
        assert m1.manifest_id in ids
        assert m2.manifest_id in ids

    def test_list_manifest_summary_keys(self):
        m = _make_manifest()
        store_manifest(m)
        summaries = list_manifests()
        assert len(summaries) == 1
        s = summaries[0]
        assert "manifest_id" in s
        assert "created_at" in s
        assert "tool_count" in s
        assert "reproducibility_score" in s

    def test_list_empty_store(self):
        assert list_manifests() == []


# ---------------------------------------------------------------------------
# FAIR metadata tests
# ---------------------------------------------------------------------------

class TestFAIRMetadata:
    def test_persistent_id_format(self):
        meta = generate_fair_metadata("Title", "Desc", ["A"], ["protein"])
        assert meta.persistent_id.startswith("neovax:pred/")
        pid_suffix = meta.persistent_id.split("/", 2)[-1]
        import uuid
        uuid.UUID(pid_suffix)

    def test_unique_ids_per_call(self):
        m1 = generate_fair_metadata("T", "D", ["A"], ["k"])
        m2 = generate_fair_metadata("T", "D", ["A"], ["k"])
        assert m1.persistent_id != m2.persistent_id

    def test_license_is_cc_by(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["k"])
        assert "creativecommons.org" in meta.license

    def test_edam_terms_added_for_structure_keywords(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["protein", "structure"])
        assert EDAM_ONTOLOGY_TERMS["protein_structure_prediction"] in meta.ontology_terms

    def test_edam_terms_added_for_variant_keywords(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["variant", "mutation"])
        assert EDAM_ONTOLOGY_TERMS["variant_effect"] in meta.ontology_terms

    def test_edam_terms_added_for_neoantigen_keywords(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["neoantigen", "vaccine"])
        assert EDAM_ONTOLOGY_TERMS["neoantigen"] in meta.ontology_terms

    def test_json_format_always_present(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["other"])
        assert EDAM_ONTOLOGY_TERMS["json_format"] in meta.ontology_terms

    def test_schema_version_set(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["k"])
        assert meta.schema_version == "1.0"

    def test_creators_stored(self):
        meta = generate_fair_metadata("T", "D", ["Alice", "Bob"], ["k"])
        assert meta.creators == ["Alice", "Bob"]

    def test_keywords_stored(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["foo", "bar"])
        assert "foo" in meta.keywords and "bar" in meta.keywords


# ---------------------------------------------------------------------------
# FAIR report tests
# ---------------------------------------------------------------------------

class TestFAIRReport:
    def test_report_has_metadata(self):
        r = _make_fair_report()
        assert isinstance(r.metadata, FAIRMetadata)

    def test_machine_readable_is_valid_json(self):
        r = _make_fair_report()
        parsed = json.loads(r.machine_readable_json_ld)
        assert isinstance(parsed, dict)

    def test_json_ld_has_schema_org_context(self):
        r = _make_fair_report()
        parsed = json.loads(r.machine_readable_json_ld)
        assert "schema.org" in parsed["@context"]

    def test_json_ld_has_type_dataset(self):
        r = _make_fair_report()
        parsed = json.loads(r.machine_readable_json_ld)
        assert parsed["@type"] == "Dataset"

    def test_json_ld_has_identifier(self):
        r = _make_fair_report()
        parsed = json.loads(r.machine_readable_json_ld)
        assert parsed["identifier"] == r.metadata.persistent_id

    def test_human_readable_summary_contains_pid(self):
        r = _make_fair_report()
        assert r.metadata.persistent_id in r.human_readable_summary

    def test_human_readable_contains_research_warning(self):
        r = _make_fair_report()
        assert "RESEARCH USE ONLY" in r.human_readable_summary

    def test_deposition_ready_true_for_complete_metadata(self):
        r = _make_fair_report()
        assert r.deposition_ready is True

    def test_deposition_not_ready_if_no_creators(self):
        meta = generate_fair_metadata("T", "D", [], ["k"])
        r = create_fair_report({"x": 1}, meta)
        assert r.deposition_ready is False

    def test_content_stored(self):
        meta = generate_fair_metadata("T", "D", ["A"], ["k"])
        data = {"plddt": 88.0, "seq": "MKTY"}
        r = create_fair_report(data, meta)
        assert r.content == data


# ---------------------------------------------------------------------------
# FAIR compliance validation tests
# ---------------------------------------------------------------------------

class TestFAIRComplianceValidation:
    def test_all_scores_in_range(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        for key in ("findable", "accessible", "interoperable", "reusable", "overall"):
            assert 0.0 <= result[key] <= 1.0

    def test_complete_report_high_scores(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        assert result["findable"] >= 0.75
        assert result["accessible"] >= 0.75
        assert result["interoperable"] >= 0.75
        assert result["reusable"] >= 0.75

    def test_findable_checks_present(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        checks = result["details"]["findable_checks"]
        assert checks["has_persistent_id"] is True
        assert checks["has_title"] is True

    def test_accessible_checks_present(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        checks = result["details"]["accessible_checks"]
        assert checks["has_format_mimetype"] is True

    def test_interoperable_checks_edam(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        checks = result["details"]["interoperable_checks"]
        assert checks["has_edam_terms"] is True

    def test_reusable_checks_license(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        checks = result["details"]["reusable_checks"]
        assert checks["has_license"] is True
        assert checks["has_creators"] is True

    def test_overall_average_of_four(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        expected = (
            result["findable"] + result["accessible"]
            + result["interoperable"] + result["reusable"]
        ) / 4.0
        assert abs(result["overall"] - expected) < 0.001

    def test_deposition_ready_in_result(self):
        r = _make_fair_report()
        result = validate_fair_compliance(r)
        assert "deposition_ready" in result


# ---------------------------------------------------------------------------
# Repository suggestion tests
# ---------------------------------------------------------------------------

class TestRepositorySuggestion:
    def test_structure_keywords_suggest_pdb(self):
        r = _make_fair_report(kw=["protein_structure", "pdb"])
        repo = suggest_repository(r)
        assert "Protein Data Bank" in repo

    def test_genomic_keywords_suggest_ena(self):
        r = _make_fair_report(kw=["variant", "genomic", "vcf"])
        repo = suggest_repository(r)
        assert "Nucleotide Archive" in repo

    def test_neoantigen_keywords_suggest_zenodo(self):
        r = _make_fair_report(kw=["neoantigen", "mhc"])
        repo = suggest_repository(r)
        assert "Zenodo" in repo

    def test_generic_keywords_suggest_figshare(self):
        r = _make_fair_report(kw=["analysis", "result"])
        repo = suggest_repository(r)
        assert "Figshare" in repo


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestReproducibilityAPI:
    def test_create_manifest_endpoint(self, client: TestClient):
        resp = client.post("/reproducibility/create-manifest", json={
            "tool_names": ["mock", "boltz1"],
            "inputs": {"sequence": "MKTY"},
            "outputs": {"score": 0.9},
            "seeds": {"np": 42},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "manifest_id" in data
        assert "reproducibility_score" in data

    def test_list_manifests_empty(self, client: TestClient):
        resp = client.get("/reproducibility/manifests")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_manifests_after_create(self, client: TestClient):
        client.post("/reproducibility/create-manifest", json={
            "tool_names": ["mock"],
            "inputs": {},
            "outputs": {},
        })
        resp = client.get("/reproducibility/manifests")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_manifest_by_id(self, client: TestClient):
        create_resp = client.post("/reproducibility/create-manifest", json={
            "tool_names": ["mock"],
            "inputs": {"x": 1},
            "outputs": {},
        })
        mid = create_resp.json()["manifest_id"]
        resp = client.get(f"/reproducibility/manifests/{mid}")
        assert resp.status_code == 200
        assert resp.json()["manifest_id"] == mid

    def test_get_manifest_not_found(self, client: TestClient):
        resp = client.get("/reproducibility/manifests/nonexistent-id-999")
        assert resp.status_code == 404

    def test_verify_manifest_endpoint(self, client: TestClient):
        create_resp = client.post("/reproducibility/create-manifest", json={
            "tool_names": ["mock"],
            "inputs": {},
            "outputs": {},
        })
        mid = create_resp.json()["manifest_id"]
        resp = client.post("/reproducibility/verify-manifest", json={"manifest_id": mid})
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data
        assert "issues" in data

    def test_verify_manifest_not_found(self, client: TestClient):
        resp = client.post("/reproducibility/verify-manifest", json={"manifest_id": "ghost"})
        assert resp.status_code == 404

    def test_fair_create_report_endpoint(self, client: TestClient):
        resp = client.post("/reproducibility/fair/create-report", json={
            "prediction_data": {"plddt": 88.0},
            "title": "Test Report",
            "description": "A test",
            "creators": ["Researcher"],
            "keywords": ["protein", "structure"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "persistent_id" in data
        assert "machine_readable_json_ld" in data
        assert "deposition_ready" in data

    def test_fair_validate_endpoint(self, client: TestClient):
        # First create a report, then validate
        create_resp = client.post("/reproducibility/fair/create-report", json={
            "prediction_data": {"plddt": 85.0},
            "title": "Val Test",
            "description": "Validation test",
            "creators": ["Alice"],
            "keywords": ["neoantigen"],
        })
        assert create_resp.status_code == 200
        report_data = create_resp.json()
        report_data["description"] = "Validation test"
        resp = client.post("/reproducibility/fair/validate", json=report_data)
        assert resp.status_code == 200
        data = resp.json()
        assert "findable" in data
        assert "accessible" in data
        assert "interoperable" in data
        assert "reusable" in data
        assert "overall" in data

    def test_environment_endpoint(self, client: TestClient):
        resp = client.get("/reproducibility/environment")
        assert resp.status_code == 200
        data = resp.json()
        assert "python_version" in data
        assert "platform" in data
        assert "cpu_count" in data

    def test_tool_registry_endpoint(self, client: TestClient):
        resp = client.get("/reproducibility/tool-registry")
        assert resp.status_code == 200
        data = resp.json()
        assert "mock" in data
        assert "alphafold2_local" in data
        assert len(data) >= 15
