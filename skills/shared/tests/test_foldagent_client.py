"""Tests for FoldAgentClient — health endpoint 503 parity.

Verifies that ``FoldAgentClient.health()`` preserves the degraded 503 payload
instead of flattening it into a generic ``httpx.HTTPStatusError``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from skills.shared.foldagent_client import FoldAgentClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    """Build a fake ``httpx.Response`` with the given status and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=MagicMock(spec=httpx.Request),
        response=resp,
    )
    return resp


# ---------------------------------------------------------------------------
# health() — 200 OK
# ---------------------------------------------------------------------------


class TestHealthOk:
    def test_healthy_returns_payload(self) -> None:
        client = FoldAgentClient(base_url="http://localhost:8000")
        payload = {
            "status": "ok",
            "version": "0.1.0-alpha",
            "mode": "demo",
            "db_status": "ok",
            "database_url": "sqlite:///test.db",
            "db_init_mode": "create_all",
            "tables_present": 8,
            "tables_expected": 8,
            "missing_tables": [],
            "extra_tables": [],
            "error": None,
        }
        mock_resp = _mock_response(200, payload)
        mock_resp.raise_for_status.side_effect = None  # 200 should not raise
        with patch.object(client.client, "get", return_value=mock_resp):
            result = client.health()
        assert result["status"] == "ok"
        assert result["db_status"] == "ok"
        assert result["tables_present"] == result["tables_expected"]


# ---------------------------------------------------------------------------
# health() — 503 degraded (the critical parity fix)
# ---------------------------------------------------------------------------


class TestHealthDegraded503:
    def test_degraded_503_returns_payload_without_raising(self) -> None:
        """health() must return the structured degraded body on 503, not raise."""
        client = FoldAgentClient(base_url="http://localhost:8000")
        payload = {
            "status": "degraded",
            "version": "0.1.0-alpha",
            "mode": "demo",
            "db_status": "degraded",
            "database_url": "sqlite:///test.db",
            "db_init_mode": "create_all",
            "tables_present": 0,
            "tables_expected": 8,
            "missing_tables": ["background_jobs", "cases", "samples"],
            "extra_tables": [],
            "error": None,
        }
        mock_resp = _mock_response(503, payload)
        with patch.object(client.client, "get", return_value=mock_resp):
            result = client.health()
        assert result["status"] == "degraded"
        assert result["db_status"] == "degraded"
        assert "background_jobs" in result["missing_tables"]
        assert result["tables_present"] == 0
        assert result["tables_expected"] == 8

    def test_degraded_503_preserves_db_error_field(self) -> None:
        """When the DB connection fails, the error field propagates."""
        client = FoldAgentClient(base_url="http://localhost:8000")
        payload = {
            "status": "degraded",
            "version": "0.1.0-alpha",
            "mode": "demo",
            "db_status": "degraded",
            "database_url": "sqlite:///missing.db",
            "db_init_mode": "create_all",
            "tables_present": 0,
            "tables_expected": 8,
            "missing_tables": ["background_jobs", "cases"],
            "extra_tables": [],
            "error": "no such table: cases",
        }
        mock_resp = _mock_response(503, payload)
        with patch.object(client.client, "get", return_value=mock_resp):
            result = client.health()
        assert result["error"] == "no such table: cases"


# ---------------------------------------------------------------------------
# health() — unexpected error codes still raise
# ---------------------------------------------------------------------------


class TestHealthUnexpectedErrors:
    def test_500_raises(self) -> None:
        """Non-200/503 status codes should still raise an error."""
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response(500, {"detail": "internal error"})
        with (
            patch.object(client.client, "get", return_value=mock_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.health()

    def test_401_raises(self) -> None:
        """401 Unauthorized should still raise."""
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response(401, {"detail": "unauthorized"})
        with (
            patch.object(client.client, "get", return_value=mock_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.health()

    def test_404_raises(self) -> None:
        """404 Not Found should still raise."""
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response(404, {"detail": "not found"})
        with (
            patch.object(client.client, "get", return_value=mock_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            client.health()


# ---------------------------------------------------------------------------
# health() — API key is forwarded
# ---------------------------------------------------------------------------


class TestHealthApiKeyForwarded:
    def test_health_forwards_api_key_in_headers(self) -> None:
        """health() should include Authorization header when api_key is set."""
        client = FoldAgentClient(base_url="http://localhost:8000", api_key="secret-key")
        payload = {"status": "ok", "version": "0.1.0-alpha", "mode": "demo"}
        mock_resp = _mock_response(200, payload)
        mock_resp.raise_for_status.side_effect = None
        with patch.object(client.client, "get", return_value=mock_resp) as mock_get:
            client.health()
        call_headers = mock_get.call_args[1].get(
            "headers", mock_get.call_args[0][0] if mock_get.call_args[0] else {}
        )
        assert "Authorization" in call_headers
        assert call_headers["Authorization"] == "Bearer secret-key"


class TestStructureJobClientParity:
    def test_create_structure_job_posts_current_route_and_payload(self) -> None:
        client = FoldAgentClient(base_url="http://localhost:8000")
        payload = {
            "id": "structure-1",
            "case_id": "case-1",
            "candidate_id": "candidate-1",
            "backend_used": "alphafold3_local",
            "input_hash": "sha256:input",
            "output_path": "artifacts/case-1/model.cif",
            "confidence_metrics": {"ranking_score": 0.82, "ptm": 0.74},
            "status": "completed",
        }
        mock_resp = _mock_response(201, payload)
        mock_resp.raise_for_status.side_effect = None

        with patch.object(client.client, "post", return_value=mock_resp) as mock_post:
            result = client.create_structure_job(
                "case-1",
                candidate_id="candidate-1",
                backend_used="alphafold3_local",
                input_hash="sha256:input",
                output_path="artifacts/case-1/model.cif",
                confidence_metrics={"ranking_score": 0.82, "ptm": 0.74},
            )

        assert result == payload
        mock_post.assert_called_once_with(
            "/cases/case-1/structure-jobs",
            json={
                "candidate_id": "candidate-1",
                "backend_used": "alphafold3_local",
                "input_hash": "sha256:input",
                "output_path": "artifacts/case-1/model.cif",
                "confidence_metrics": {"ranking_score": 0.82, "ptm": 0.74},
            },
            params=None,
            headers={"Content-Type": "application/json"},
        )

    def test_create_structure_job_keeps_minimal_payload_small(self) -> None:
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response(
            201,
            {
                "id": "structure-1",
                "case_id": "case-1",
                "candidate_id": "candidate-1",
                "backend_used": "mock",
            },
        )
        mock_resp.raise_for_status.side_effect = None

        with patch.object(client.client, "post", return_value=mock_resp) as mock_post:
            client.create_structure_job("case-1", "candidate-1", "mock")

        assert mock_post.call_args.kwargs["json"] == {
            "candidate_id": "candidate-1",
            "backend_used": "mock",
        }


class TestMrnaSafetyGateClientParity:
    def test_safety_mrna_gate_posts_dedicated_endpoint(self) -> None:
        client = FoldAgentClient(base_url="http://localhost:8000")
        payload = {
            "status": "requires_expert_approval",
            "allowed": False,
            "blocked": False,
            "needs_approval": True,
            "reason": "mRNA sequence-level export requires expert review",
            "blocked_patterns": [],
        }
        mock_resp = _mock_response(200, payload)
        mock_resp.raise_for_status.side_effect = None

        with patch.object(client.client, "post", return_value=mock_resp) as mock_post:
            result = client.safety_mrna_gate(
                "export_sequence",
                species_mode="dog",
                content="AUGGCC",
                is_export=True,
                involves_sequence_data=True,
            )

        assert result == payload
        mock_post.assert_called_once_with(
            "/safety/mrna-gate",
            json={
                "action": "export_sequence",
                "species_mode": "dog",
                "content": "AUGGCC",
                "is_export": True,
                "involves_sequence_data": True,
            },
            params=None,
            headers={"Content-Type": "application/json"},
        )
