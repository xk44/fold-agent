"""Tests for Molecular Dynamics Handoff (Phase 23)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.md_handoff import (
    MDExportConfig,
    MDExportResult,
    export_for_gromacs,
    export_for_openmm,
    validate_structure_for_md,
)

_MINIMAL_PDB = (
    "ATOM      1  CA  ALA A   1      10.000  10.000  10.000  1.00 50.00           C\n"
    "ATOM      2  CA  GLY A   2      13.800  10.000  10.000  1.00 50.00           C\n"
    "END\n"
)

_EMPTY_PDB = ""


# ---------------------------------------------------------------------------
# MDExportConfig defaults
# ---------------------------------------------------------------------------


def test_config_defaults() -> None:
    cfg = MDExportConfig()
    assert cfg.force_field == "amber14"
    assert cfg.water_model == "tip3p"
    assert cfg.box_padding_nm == 1.0
    assert cfg.ion_concentration_mol == 0.15
    assert cfg.temperature_k == 300.0
    assert cfg.simulation_ns == 100.0


# ---------------------------------------------------------------------------
# export_for_openmm — unit tests
# ---------------------------------------------------------------------------


def test_openmm_returns_md_export_result() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig())
    assert isinstance(result, MDExportResult)


def test_openmm_format_is_openmm() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig())
    assert result.format == "openmm"


def test_openmm_script_contains_integrator() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig())
    assert "LangevinMiddleIntegrator" in result.config_script


def test_openmm_script_contains_force_field() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig(force_field="amber14"))
    assert "amber14" in result.config_script


def test_openmm_script_contains_temperature() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig(temperature_k=310.0))
    assert "310.0" in result.config_script


def test_openmm_runtime_positive() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig(simulation_ns=50.0))
    assert result.estimated_runtime_hours > 0


def test_openmm_topology_data_nonempty() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig())
    assert len(result.topology_data) > 0


def test_openmm_coordinate_data_contains_pdb() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig())
    assert "ATOM" in result.coordinate_data


def test_openmm_unknown_force_field_adds_warning() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig(force_field="xtff99"))
    assert len(result.warnings) > 0


def test_openmm_unknown_water_model_adds_warning() -> None:
    result = export_for_openmm(_MINIMAL_PDB, MDExportConfig(water_model="opc"))
    assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# export_for_gromacs — unit tests
# ---------------------------------------------------------------------------


def test_gromacs_returns_md_export_result() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig())
    assert isinstance(result, MDExportResult)


def test_gromacs_format_is_gromacs() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig())
    assert result.format == "gromacs"


def test_gromacs_script_contains_integrator_md() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig())
    assert "integrator" in result.config_script
    assert "md" in result.config_script


def test_gromacs_script_contains_temperature() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig(temperature_k=298.0))
    assert "298.0" in result.config_script


def test_gromacs_runtime_positive() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig(simulation_ns=200.0))
    assert result.estimated_runtime_hours > 0


def test_gromacs_nsteps_in_script() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig(simulation_ns=10.0))
    # 10 ns / 0.002 ps = 5_000_000 steps
    assert "5000000" in result.config_script


def test_gromacs_unknown_ff_adds_warning() -> None:
    result = export_for_gromacs(_MINIMAL_PDB, MDExportConfig(force_field="opls-aa"))
    assert len(result.warnings) > 0


# ---------------------------------------------------------------------------
# validate_structure_for_md — unit tests
# ---------------------------------------------------------------------------


def test_validate_good_structure_passes() -> None:
    v = validate_structure_for_md(_MINIMAL_PDB)
    assert v["has_atoms"] is True
    assert isinstance(v["passed"], bool)


def test_validate_empty_pdb_fails() -> None:
    v = validate_structure_for_md(_EMPTY_PDB)
    assert v["has_atoms"] is False
    assert v["passed"] is False


def test_validate_returns_n_residues() -> None:
    v = validate_structure_for_md(_MINIMAL_PDB)
    assert v["n_residues"] >= 1


def test_validate_returns_n_chains() -> None:
    v = validate_structure_for_md(_MINIMAL_PDB)
    assert v["n_chains"] >= 1


def test_validate_has_warnings_list() -> None:
    v = validate_structure_for_md(_MINIMAL_PDB)
    assert "warnings" in v
    assert isinstance(v["warnings"], list)


def test_validate_empty_has_warning_message() -> None:
    v = validate_structure_for_md(_EMPTY_PDB)
    assert len(v["warnings"]) >= 1


def test_validate_missing_remark_triggers_flag() -> None:
    pdb_with_missing = "REMARK  MISSING RESIDUES 10-15\n" + _MINIMAL_PDB
    v = validate_structure_for_md(pdb_with_missing)
    assert v["chain_breaks_detected"] is True


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_api_export_openmm_200(client: TestClient) -> None:
    resp = client.post("/md/export-openmm", json={"pdb_data": _MINIMAL_PDB})
    assert resp.status_code == 200


def test_api_export_openmm_has_script(client: TestClient) -> None:
    resp = client.post("/md/export-openmm", json={"pdb_data": _MINIMAL_PDB})
    data = resp.json()
    assert "config_script" in data
    assert len(data["config_script"]) > 0


def test_api_export_gromacs_200(client: TestClient) -> None:
    resp = client.post("/md/export-gromacs", json={"pdb_data": _MINIMAL_PDB})
    assert resp.status_code == 200


def test_api_export_gromacs_has_script(client: TestClient) -> None:
    resp = client.post("/md/export-gromacs", json={"pdb_data": _MINIMAL_PDB})
    data = resp.json()
    assert "config_script" in data
    assert "integrator" in data["config_script"]


def test_api_validate_structure_200(client: TestClient) -> None:
    resp = client.post("/md/validate-structure", json={"pdb_data": _MINIMAL_PDB})
    assert resp.status_code == 200


def test_api_validate_structure_passed_key(client: TestClient) -> None:
    resp = client.post("/md/validate-structure", json={"pdb_data": _MINIMAL_PDB})
    data = resp.json()
    assert "validation" in data
    assert "passed" in data["validation"]


def test_api_validate_empty_pdb(client: TestClient) -> None:
    resp = client.post("/md/validate-structure", json={"pdb_data": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation"]["passed"] is False
