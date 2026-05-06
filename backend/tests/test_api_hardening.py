"""Tests for Phase 14: API Hardening for Agent Consumption.

Covers:
- OpenAPI export with x-safety-level / x-agent-description annotations
- Agent error catalog and format_agent_error()
- Dry-run for all supported actions
- Approval-required list and per-action check
- New API endpoints in main.py
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.agent_errors import (
    AGENT_ERROR_CATALOG,
    AgentError,
    format_agent_error,
)
from backend.app.dry_run import (
    APPROVAL_REQUIRED_ACTIONS,
    SUPPORTED_DRY_RUN_ACTIONS,
    DryRunResult,
    check_approval_required,
    dry_run_action,
)
from backend.app.openapi_export import _classify_safety_level, export_openapi_spec

# ---------------------------------------------------------------------------
# OpenAPI export: safety level classification
# ---------------------------------------------------------------------------


def test_classify_get_is_safe() -> None:
    assert _classify_safety_level("GET", "/cases") == "safe"


def test_classify_delete_is_dangerous() -> None:
    assert _classify_safety_level("DELETE", "/cases/{case_id}") == "dangerous"


def test_classify_export_endpoint_is_dangerous() -> None:
    assert _classify_safety_level("GET", "/cases/{case_id}/bundle/export") == "dangerous"


def test_classify_report_export_dangerous() -> None:
    assert _classify_safety_level("GET", "/reports/{report_id}/export") == "dangerous"


def test_classify_alphafold_run_dangerous() -> None:
    assert _classify_safety_level("POST", "/alphafold/backends/{backend_name}/run") == "dangerous"


def test_classify_post_create_case_requires_review() -> None:
    assert _classify_safety_level("POST", "/cases") == "requires-review"


def test_classify_post_pipeline_run_dangerous() -> None:
    assert _classify_safety_level("POST", "/cases/{case_id}/pipeline/run") == "dangerous"


def test_classify_patch_requires_review() -> None:
    assert _classify_safety_level("PATCH", "/cases/{case_id}") == "requires-review"


# ---------------------------------------------------------------------------
# OpenAPI export: full spec
# ---------------------------------------------------------------------------


def test_export_openapi_spec_returns_dict() -> None:
    spec = export_openapi_spec()
    assert isinstance(spec, dict)
    assert "paths" in spec


def test_export_openapi_spec_has_x_safety_level_on_all_operations() -> None:
    spec = export_openapi_spec()
    paths = spec.get("paths", {})
    assert len(paths) > 0
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                assert "x-safety-level" in operation, (
                    f"Missing x-safety-level on {method.upper()} {path}"
                )


def test_export_openapi_spec_has_x_agent_description_on_all_operations() -> None:
    spec = export_openapi_spec()
    paths = spec.get("paths", {})
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                assert "x-agent-description" in operation, (
                    f"Missing x-agent-description on {method.upper()} {path}"
                )


def test_export_openapi_spec_safety_levels_are_valid_values() -> None:
    valid = {"safe", "requires-review", "dangerous"}
    spec = export_openapi_spec()
    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                level = operation.get("x-safety-level")
                assert level in valid, f"{method.upper()} {path} has invalid level: {level}"


def test_export_openapi_spec_get_health_is_safe() -> None:
    spec = export_openapi_spec()
    health_get = spec["paths"]["/health"]["get"]
    assert health_get["x-safety-level"] == "safe"


def test_export_openapi_spec_delete_case_is_dangerous() -> None:
    spec = export_openapi_spec()
    delete_op = spec["paths"]["/cases/{case_id}"]["delete"]
    assert delete_op["x-safety-level"] == "dangerous"


def test_export_openapi_spec_post_cases_requires_review() -> None:
    spec = export_openapi_spec()
    post_op = spec["paths"]["/cases"]["post"]
    assert post_op["x-safety-level"] == "requires-review"


def test_export_openapi_spec_includes_agent_endpoints() -> None:
    spec = export_openapi_spec()
    paths = spec.get("paths", {})
    assert "/openapi-export" in paths
    assert "/agent/dry-run" in paths
    assert "/agent/approval-required" in paths
    assert "/agent/error-catalog" in paths


# ---------------------------------------------------------------------------
# AgentError dataclass
# ---------------------------------------------------------------------------


def test_agent_error_dataclass_fields() -> None:
    err = AgentError(
        code="TEST_CODE",
        message="Test message",
        suggestion="Do something",
        retry_safe=True,
        documentation_url="https://example.com",
    )
    assert err.code == "TEST_CODE"
    assert err.message == "Test message"
    assert err.suggestion == "Do something"
    assert err.retry_safe is True
    assert err.documentation_url == "https://example.com"


def test_agent_error_documentation_url_optional() -> None:
    err = AgentError(
        code="X",
        message="m",
        suggestion="s",
        retry_safe=False,
    )
    assert err.documentation_url is None


# ---------------------------------------------------------------------------
# AGENT_ERROR_CATALOG
# ---------------------------------------------------------------------------


def test_catalog_has_404_case_not_found() -> None:
    assert "404_case_not_found" in AGENT_ERROR_CATALOG
    assert AGENT_ERROR_CATALOG["404_case_not_found"].retry_safe is False


def test_catalog_has_400_validation_error() -> None:
    assert "400_validation_error" in AGENT_ERROR_CATALOG


def test_catalog_has_403_safety_blocked() -> None:
    assert "403_safety_blocked" in AGENT_ERROR_CATALOG
    assert AGENT_ERROR_CATALOG["403_safety_blocked"].retry_safe is False


def test_catalog_has_409_conflict() -> None:
    assert "409_conflict" in AGENT_ERROR_CATALOG


def test_catalog_has_500_internal_error() -> None:
    assert "500_internal_error" in AGENT_ERROR_CATALOG
    assert AGENT_ERROR_CATALOG["500_internal_error"].retry_safe is True


def test_catalog_has_422_missing_field() -> None:
    assert "422_missing_field" in AGENT_ERROR_CATALOG


def test_catalog_all_entries_are_agent_errors() -> None:
    for key, val in AGENT_ERROR_CATALOG.items():
        assert isinstance(val, AgentError), f"{key} is not an AgentError"


# ---------------------------------------------------------------------------
# format_agent_error
# ---------------------------------------------------------------------------


def test_format_agent_error_404_case_not_found() -> None:
    result = format_agent_error(404, "case_not_found", "Case abc not found")
    assert result["status_code"] == 404
    assert result["code"] == "CASE_NOT_FOUND"
    assert result["error"] is True
    assert result["retry_safe"] is False
    assert "suggestion" in result


def test_format_agent_error_403_safety_blocked() -> None:
    result = format_agent_error(403, "safety_blocked", "Blocked by preflight")
    assert result["code"] == "SAFETY_BLOCKED"
    assert result["retry_safe"] is False


def test_format_agent_error_500_internal_error() -> None:
    result = format_agent_error(500, "internal_error", "Unexpected error")
    assert result["code"] == "INTERNAL_ERROR"
    assert result["retry_safe"] is True


def test_format_agent_error_422_missing_field() -> None:
    result = format_agent_error(422, "missing_field", "Field 'species' required")
    assert result["code"] == "MISSING_FIELD"


def test_format_agent_error_409_conflict() -> None:
    result = format_agent_error(409, "conflict", "Resource already exists")
    assert result["code"] == "CONFLICT"


def test_format_agent_error_unknown_type_fallback() -> None:
    result = format_agent_error(418, "teapot", "I am a teapot")
    assert result["status_code"] == 418
    assert result["error"] is True
    assert "suggestion" in result


def test_format_agent_error_preserves_detail() -> None:
    detail = "Specific detail message"
    result = format_agent_error(404, "not_found", detail)
    assert result["detail"] == detail


# ---------------------------------------------------------------------------
# DryRunResult dataclass
# ---------------------------------------------------------------------------


def test_dry_run_result_fields() -> None:
    r = DryRunResult(
        action="create_case",
        would_affect=["cases table"],
        parameters={"species": "demo"},
        safety_level="requires-review",
        requires_approval=False,
        notes="Would create case",
    )
    assert r.action == "create_case"
    assert r.safety_level == "requires-review"
    assert r.requires_approval is False


# ---------------------------------------------------------------------------
# dry_run_action: each supported action
# ---------------------------------------------------------------------------


def test_dry_run_create_case() -> None:
    result = dry_run_action("create_case", {"species": "demo", "diagnosis_summary": "test"})
    assert result.action == "create_case"
    assert result.requires_approval is False
    assert "cases table" in result.would_affect


def test_dry_run_run_pipeline() -> None:
    result = dry_run_action("run_pipeline", {"case_id": "c1", "steps": ["bwa", "gatk"]})
    assert result.action == "run_pipeline"
    assert result.requires_approval is True
    assert result.safety_level == "dangerous"


def test_dry_run_generate_report() -> None:
    result = dry_run_action("generate_report", {"case_id": "c1", "report_type": "candidate-review"})
    assert result.action == "generate_report"
    assert result.requires_approval is True


def test_dry_run_export_data() -> None:
    result = dry_run_action("export_data", {"case_id": "c1", "format": "json"})
    assert result.action == "export_data"
    assert result.requires_approval is True
    assert result.safety_level == "dangerous"


def test_dry_run_delete_case() -> None:
    result = dry_run_action("delete_case", {"case_id": "c1"})
    assert result.action == "delete_case"
    assert result.requires_approval is True
    assert result.safety_level == "dangerous"
    assert len(result.would_affect) > 3  # affects many tables


def test_dry_run_submit_alphafold() -> None:
    result = dry_run_action(
        "submit_alphafold", {"backend": "alphafold_server", "sequence": "MKTII"}
    )
    assert result.action == "submit_alphafold"
    assert result.requires_approval is True
    assert result.safety_level == "dangerous"


def test_dry_run_unknown_action_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown action"):
        dry_run_action("nonexistent_action", {})


def test_dry_run_all_supported_actions_work() -> None:
    """Smoke-test that every action in SUPPORTED_DRY_RUN_ACTIONS runs without error."""
    params_by_action = {
        "create_case": {"species": "demo"},
        "run_pipeline": {"case_id": "c1"},
        "generate_report": {"case_id": "c1"},
        "export_data": {"case_id": "c1"},
        "delete_case": {"case_id": "c1"},
        "submit_alphafold": {"backend": "mock"},
    }
    for action in SUPPORTED_DRY_RUN_ACTIONS:
        result = dry_run_action(action, params_by_action.get(action, {}))
        assert isinstance(result, DryRunResult)
        assert result.action == action


# ---------------------------------------------------------------------------
# APPROVAL_REQUIRED_ACTIONS
# ---------------------------------------------------------------------------


def test_approval_required_list_nonempty() -> None:
    assert len(APPROVAL_REQUIRED_ACTIONS) > 0


def test_approval_required_includes_delete_case() -> None:
    assert "delete_case" in APPROVAL_REQUIRED_ACTIONS


def test_approval_required_includes_export_data() -> None:
    assert "export_data" in APPROVAL_REQUIRED_ACTIONS


def test_approval_required_includes_submit_alphafold() -> None:
    assert "submit_alphafold" in APPROVAL_REQUIRED_ACTIONS


def test_approval_required_includes_run_pipeline() -> None:
    assert "run_pipeline" in APPROVAL_REQUIRED_ACTIONS


# ---------------------------------------------------------------------------
# check_approval_required
# ---------------------------------------------------------------------------


def test_check_approval_required_delete_case_is_true() -> None:
    result = check_approval_required("delete_case")
    assert result["required"] is True
    assert result["action"] == "delete_case"
    assert result["reason"]
    assert result["approval_prompt"]


def test_check_approval_required_safe_action_is_false() -> None:
    result = check_approval_required("list_cases")
    assert result["required"] is False
    assert result["approval_prompt"] == ""


def test_check_approval_required_returns_all_fields() -> None:
    result = check_approval_required("export_data")
    assert "action" in result
    assert "required" in result
    assert "reason" in result
    assert "approval_prompt" in result


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_get_openapi_export_endpoint(client: TestClient) -> None:
    response = client.get("/openapi-export")
    assert response.status_code == 200
    spec = response.json()
    assert "paths" in spec
    # Verify extensions present on at least one endpoint
    found = False
    for path_item in spec["paths"].values():
        for op in path_item.values():
            if isinstance(op, dict) and "x-safety-level" in op:
                found = True
                break
        if found:
            break
    assert found, "No x-safety-level found in exported spec"


def test_agent_dry_run_endpoint_create_case(client: TestClient) -> None:
    response = client.post(
        "/agent/dry-run",
        json={"action": "create_case", "params": {"species": "demo"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "create_case"
    assert "would_affect" in body
    assert "safety_level" in body
    assert "requires_approval" in body


def test_agent_dry_run_endpoint_delete_case(client: TestClient) -> None:
    response = client.post(
        "/agent/dry-run",
        json={"action": "delete_case", "params": {"case_id": "c1"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requires_approval"] is True
    assert body["safety_level"] == "dangerous"


def test_agent_dry_run_endpoint_unknown_action_returns_400(client: TestClient) -> None:
    response = client.post(
        "/agent/dry-run",
        json={"action": "fly_to_mars", "params": {}},
    )
    assert response.status_code == 400


def test_agent_dry_run_endpoint_missing_action_returns_422(client: TestClient) -> None:
    response = client.post("/agent/dry-run", json={"params": {}})
    assert response.status_code == 422


def test_get_approval_required_endpoint(client: TestClient) -> None:
    response = client.get("/agent/approval-required")
    assert response.status_code == 200
    body = response.json()
    assert "actions" in body
    assert len(body["actions"]) > 0
    action_names = [a["action"] for a in body["actions"]]
    assert "delete_case" in action_names


def test_get_approval_required_specific_action(client: TestClient) -> None:
    response = client.get("/agent/approval-required/delete_case")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "delete_case"
    assert body["required"] is True


def test_get_approval_required_safe_action(client: TestClient) -> None:
    response = client.get("/agent/approval-required/list_cases")
    assert response.status_code == 200
    body = response.json()
    assert body["required"] is False


def test_get_agent_error_catalog_endpoint(client: TestClient) -> None:
    response = client.get("/agent/error-catalog")
    assert response.status_code == 200
    body = response.json()
    assert "errors" in body
    assert len(body["errors"]) > 0
    keys = [e["key"] for e in body["errors"]]
    assert "404_case_not_found" in keys
    assert "403_safety_blocked" in keys
    assert "500_internal_error" in keys


def test_agent_error_catalog_entries_have_all_fields(client: TestClient) -> None:
    response = client.get("/agent/error-catalog")
    assert response.status_code == 200
    for entry in response.json()["errors"]:
        assert "key" in entry
        assert "code" in entry
        assert "message" in entry
        assert "suggestion" in entry
        assert "retry_safe" in entry
