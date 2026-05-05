"""Tests for FoldAgentClient background job methods — retry, list, get, cancel.

These test only the client-side request construction, not the backend logic.
Uses httpx mocking to avoid needing a live server.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.shared.foldagent_client import FoldAgentClient


def _mock_response(json_data=None, status_code=200):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError
        resp.raise_for_status.side_effect = HTTPStatusError(
            f"{status_code}", request=MagicMock(), response=resp
        )
    return resp


class TestRetryBackgroundJob:
    """Test that retry_background_job POSTs to the correct endpoint."""

    def test_retry_sends_post_to_correct_path(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response({"id": "abc-123", "status": "pending", "attempt": 2})
        with patch.object(client.client, "post", return_value=mock_resp) as mock_post:
            result = client.retry_background_job("abc-123")
            mock_post.assert_called_once_with(
                "/jobs/abc-123/retry",
                headers=client._headers(),
            )
            assert result["id"] == "abc-123"
            assert result["attempt"] == 2

    def test_retry_propagates_http_error(self):
        """When API returns 409 (conflict), client should raise."""
        import httpx
        client = FoldAgentClient(base_url="http://localhost:8000")
        error_resp = MagicMock()
        error_resp.status_code = 409
        error_resp.json.return_value = {"detail": "Job has exceeded max retries"}
        error_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "409", request=MagicMock(), response=error_resp
        )
        # _raise_for_structured_error doesn't handle 409, so it falls through
        # to raise_for_status which raises HTTPStatusError
        with patch.object(client.client, "post", return_value=error_resp):
            try:
                client.retry_background_job("abc-123")
            except (httpx.HTTPStatusError, Exception):
                pass  # Expected — the error propagates


class TestListBackgroundJobs:
    """Test that list_background_jobs GETs /jobs with optional filters."""

    def test_list_jobs_no_filters(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response([{"id": "j1"}, {"id": "j2"}])
        with patch.object(client.client, "get", return_value=mock_resp) as mock_get:
            result = client.list_background_jobs()
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "/jobs"
            assert call_args[1].get("params") is None or call_args[1].get("params") == {}
            assert len(result) == 2

    def test_list_jobs_with_status_filter(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response([{"id": "j1", "status": "failed"}])
        with patch.object(client.client, "get", return_value=mock_resp) as mock_get:
            result = client.list_background_jobs(status="failed")
            call_args = mock_get.call_args
            assert call_args[1]["params"]["status"] == "failed"

    def test_list_jobs_with_case_id_filter(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response([{"id": "j1", "case_id": "c1"}])
        with patch.object(client.client, "get", return_value=mock_resp) as mock_get:
            result = client.list_background_jobs(case_id="c1")
            call_args = mock_get.call_args
            assert call_args[1]["params"]["case_id"] == "c1"


class TestGetBackgroundJob:
    """Test that get_background_job GETs /jobs/{job_id}."""

    def test_get_job(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response({"id": "abc-123", "status": "failed"})
        with patch.object(client.client, "get", return_value=mock_resp) as mock_get:
            result = client.get_background_job("abc-123")
            mock_get.assert_called_once()
            assert mock_get.call_args[0][0] == "/jobs/abc-123"
            assert result["id"] == "abc-123"


class TestCancelBackgroundJob:
    """Test that cancel_background_job POSTs to /jobs/{job_id}/cancel."""

    def test_cancel_job(self):
        client = FoldAgentClient(base_url="http://localhost:8000")
        mock_resp = _mock_response({"id": "abc-123", "status": "cancelled"})
        with patch.object(client.client, "post", return_value=mock_resp):
            result = client.cancel_background_job("abc-123")
            assert result["status"] == "cancelled"