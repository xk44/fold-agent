"""Tests for the autoresearch module (Phase 16).

Covers:
- Metric allowed/prohibited classification
- GitSandbox enter/exit/revert
- ExperimentLog record and retrieval
- AutoresearchAdapter safety gate
- BenchmarkResult structure
- All 5 API endpoints via TestClient

RESEARCH ONLY — NOT FOR CLINICAL USE.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from research_modes.autoresearch.adapter import AutoresearchAdapter
from research_modes.autoresearch.benchmark import BenchmarkResult, run_benchmark
from research_modes.autoresearch.config import (
    ALLOWED_METRICS,
    PROHIBITED_METRICS,
    MetricCategory,
    get_all_metrics,
    is_metric_allowed,
)
from research_modes.autoresearch.sandbox import ExperimentLog, GitSandbox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tmp_log(tmp_path: Path) -> ExperimentLog:
    return ExperimentLog(log_path=tmp_path / "test_log.json")


@pytest.fixture
def adapter() -> AutoresearchAdapter:
    return AutoresearchAdapter()


# ---------------------------------------------------------------------------
# config.py — metric classification
# ---------------------------------------------------------------------------

class TestMetricClassification:
    def test_allowed_metrics_nonempty(self):
        assert len(ALLOWED_METRICS) > 0

    def test_prohibited_metrics_nonempty(self):
        assert len(PROHIBITED_METRICS) > 0

    def test_pipeline_execution_time_allowed(self):
        assert is_metric_allowed("pipeline_execution_time_s") is True

    def test_memory_usage_allowed(self):
        assert is_metric_allowed("memory_usage_mb") is True

    def test_cache_hit_rate_allowed(self):
        assert is_metric_allowed("cache_hit_rate") is True

    def test_test_pass_rate_allowed(self):
        assert is_metric_allowed("test_pass_rate") is True

    def test_clinical_outcome_prohibited(self):
        assert is_metric_allowed("clinical_outcome") is False

    def test_binding_affinity_threshold_prohibited(self):
        assert is_metric_allowed("binding_affinity_threshold") is False

    def test_safety_gate_pass_rate_prohibited(self):
        assert is_metric_allowed("safety_gate_pass_rate") is False

    def test_dosage_parameter_prohibited(self):
        assert is_metric_allowed("dosage_parameter") is False

    def test_unknown_metric_not_allowed(self):
        assert is_metric_allowed("totally_unknown_metric_xyz") is False

    def test_get_all_metrics_structure(self):
        result = get_all_metrics()
        assert MetricCategory.allowed in result
        assert MetricCategory.prohibited in result
        assert isinstance(result[MetricCategory.allowed], list)
        assert isinstance(result[MetricCategory.prohibited], list)

    def test_metric_category_enum_values(self):
        assert MetricCategory.allowed == "allowed"
        assert MetricCategory.prohibited == "prohibited"

    def test_no_overlap_between_allowed_and_prohibited(self):
        overlap = set(ALLOWED_METRICS) & set(PROHIBITED_METRICS)
        assert overlap == set(), f"Overlap found: {overlap}"


# ---------------------------------------------------------------------------
# sandbox.py — GitSandbox
# ---------------------------------------------------------------------------

class TestGitSandbox:
    """Tests GitSandbox using mocked subprocess calls."""

    def _make_sandbox(self, tmp_path: Path) -> GitSandbox:
        return GitSandbox(repo_root=tmp_path)

    def test_enter_creates_branch(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        with patch.object(sb, "_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            sb.enter()
            calls = [str(c) for c in mock_git.call_args_list]
            assert any("checkout" in c for c in calls)
            assert sb._entered is True

    def test_exit_clears_entered_flag(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        with patch.object(sb, "_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            sb._entered = True
            sb._original_branch = "main"
            sb.exit()
            assert sb._entered is False

    def test_revert_calls_checkout_original(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        with patch.object(sb, "_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            sb._entered = True
            sb._original_branch = "main"
            sb._changes = ["backend/app/main.py"]
            sb.revert()
            all_calls = mock_git.call_args_list
            # Should have called checkout original with changed files
            checkout_calls = [c for c in all_calls if "checkout" in str(c)]
            assert len(checkout_calls) >= 1

    def test_revert_clears_entered_flag(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        with patch.object(sb, "_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            sb._entered = True
            sb._original_branch = "main"
            sb.revert()
            assert sb._entered is False

    def test_track_change_deduplicates(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        sb.track_change("a.py")
        sb.track_change("a.py")
        sb.track_change("b.py")
        assert sb._changes == ["a.py", "b.py"]

    def test_context_manager_reverts_on_exception(self, tmp_path: Path):
        sb = self._make_sandbox(tmp_path)
        with patch.object(sb, "_git") as mock_git:
            mock_git.return_value = MagicMock(stdout="main\n", returncode=0)
            sb._original_branch = "main"
            with pytest.raises(ValueError):
                with sb:
                    raise ValueError("test error")
            # After exception, entered should be False
            assert sb._entered is False


# ---------------------------------------------------------------------------
# sandbox.py — ExperimentLog
# ---------------------------------------------------------------------------

class TestExperimentLog:
    def test_record_and_retrieve(self, tmp_log: ExperimentLog):
        tmp_log.record("exp-1", "pipeline_execution_time_s", 10.0, 8.5, ["file.py"])
        history = tmp_log.get_history()
        assert len(history) == 1
        assert history[0]["experiment_id"] == "exp-1"
        assert history[0]["metric"] == "pipeline_execution_time_s"
        assert history[0]["before"] == 10.0
        assert history[0]["after"] == 8.5

    def test_record_persists_to_disk(self, tmp_path: Path):
        log_path = tmp_path / "log.json"
        log = ExperimentLog(log_path=log_path)
        log.record("exp-2", "cache_hit_rate", 0.5, 0.7, [])
        assert log_path.exists()
        data = json.loads(log_path.read_text())
        assert len(data) == 1
        assert data[0]["experiment_id"] == "exp-2"

    def test_log_reloads_from_disk(self, tmp_path: Path):
        log_path = tmp_path / "log.json"
        log1 = ExperimentLog(log_path=log_path)
        log1.record("exp-3", "memory_usage_mb", 200.0, 180.0, [])

        log2 = ExperimentLog(log_path=log_path)
        history = log2.get_history()
        assert len(history) == 1
        assert history[0]["experiment_id"] == "exp-3"

    def test_multiple_records(self, tmp_log: ExperimentLog):
        tmp_log.record("e1", "test_pass_rate", 0.9, 0.95, [])
        tmp_log.record("e2", "cache_hit_rate", 0.6, 0.65, [])
        assert len(tmp_log.get_history()) == 2

    def test_reverted_flag_stored(self, tmp_log: ExperimentLog):
        tmp_log.record("e1", "code_coverage", 0.7, 0.65, [], reverted=True)
        assert tmp_log.get_history()[0]["reverted"] is True


# ---------------------------------------------------------------------------
# adapter.py — AutoresearchAdapter
# ---------------------------------------------------------------------------

class TestAutoresearchAdapter:
    def test_propose_allowed_metric_not_blocked(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("pipeline_execution_time_s", 12.0)
        assert proposal["blocked"] is False
        assert proposal["block_reason"] is None
        assert "experiment_id" in proposal
        assert proposal["metric"] == "pipeline_execution_time_s"

    def test_propose_prohibited_metric_blocked(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("clinical_outcome", 0.8)
        assert proposal["blocked"] is True
        assert proposal["block_reason"] is not None
        assert "prohibited" in proposal["block_reason"].lower()

    def test_propose_binding_affinity_blocked(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("binding_affinity_threshold", 500.0)
        assert proposal["blocked"] is True

    def test_propose_safety_gate_rate_blocked(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("safety_gate_pass_rate", 0.99)
        assert proposal["blocked"] is True

    def test_is_safe_returns_false_for_blocked_proposal(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("clinical_outcome", 0.5)
        assert adapter.is_safe(proposal) is False

    def test_is_safe_returns_true_for_allowed_proposal(self, adapter: AutoresearchAdapter):
        proposal = adapter.propose_experiment("cache_hit_rate", 0.7)
        assert adapter.is_safe(proposal) is True

    def test_evaluate_accepts_improvement(self, adapter: AutoresearchAdapter):
        result = adapter.evaluate_experiment(
            "exp-abc",
            {"metric": "pipeline_execution_time_s", "before": 10.0, "after": 7.0, "test_passed": True},
        )
        assert result["recommendation"] == "accept"
        assert result["test_passed"] is True

    def test_evaluate_rejects_failed_tests(self, adapter: AutoresearchAdapter):
        result = adapter.evaluate_experiment(
            "exp-def",
            {"metric": "pipeline_execution_time_s", "before": 10.0, "after": 7.0, "test_passed": False},
        )
        assert result["recommendation"] == "reject"

    def test_evaluate_inconclusive_when_no_improvement(self, adapter: AutoresearchAdapter):
        result = adapter.evaluate_experiment(
            "exp-ghi",
            {"metric": "pipeline_execution_time_s", "before": 10.0, "after": 11.0, "test_passed": True},
        )
        assert result["recommendation"] == "inconclusive"

    def test_evaluate_returns_improvement_pct(self, adapter: AutoresearchAdapter):
        result = adapter.evaluate_experiment(
            "exp-jkl",
            {"metric": "memory_usage_mb", "before": 200.0, "after": 160.0, "test_passed": True},
        )
        assert result["improvement_pct"] is not None
        assert result["improvement_pct"] == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# benchmark.py — BenchmarkResult structure
# ---------------------------------------------------------------------------

class TestBenchmarkResult:
    def test_dataclass_fields_present(self):
        r = BenchmarkResult(
            total_time=5.0,
            step_times={"create_case": 1.0},
            memory_peak_mb=50.0,
            success_rate=1.0,
            steps_run=4,
            steps_passed=4,
        )
        assert r.total_time == 5.0
        assert r.memory_peak_mb == 50.0
        assert r.success_rate == 1.0
        assert r.steps_run == 4
        assert r.steps_passed == 4
        assert "create_case" in r.step_times

    def test_run_benchmark_without_httpx_returns_stub(self):
        """run_benchmark returns a safe stub when httpx is unavailable."""
        with patch("research_modes.autoresearch.benchmark._HAS_HTTPX", False):
            result = run_benchmark("http://localhost:9999")
        assert isinstance(result, BenchmarkResult)
        assert result.success_rate == 0.0
        assert result.steps_run == 0


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class TestAutoresearchAPI:
    def test_list_metrics_returns_allowed_and_prohibited(self, client: TestClient):
        resp = client.get("/autoresearch/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data
        assert "prohibited" in data
        assert len(data["allowed"]) > 0
        assert len(data["prohibited"]) > 0
        assert "disclaimer" in data

    def test_list_metrics_contains_known_allowed(self, client: TestClient):
        resp = client.get("/autoresearch/metrics")
        assert "pipeline_execution_time_s" in resp.json()["allowed"]

    def test_list_metrics_contains_known_prohibited(self, client: TestClient):
        resp = client.get("/autoresearch/metrics")
        assert "clinical_outcome" in resp.json()["prohibited"]

    def test_check_metric_allowed_returns_true(self, client: TestClient):
        resp = client.get("/autoresearch/metrics/cache_hit_rate/allowed")
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_check_metric_allowed_returns_false_for_prohibited(self, client: TestClient):
        resp = client.get("/autoresearch/metrics/clinical_outcome/allowed")
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    def test_propose_experiment_allowed_metric(self, client: TestClient):
        resp = client.post(
            "/autoresearch/experiment/propose",
            json={"metric": "pipeline_execution_time_s", "current_value": 15.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is False
        assert data["metric"] == "pipeline_execution_time_s"
        assert "experiment_id" in data

    def test_propose_experiment_blocks_prohibited(self, client: TestClient):
        resp = client.post(
            "/autoresearch/experiment/propose",
            json={"metric": "clinical_outcome", "current_value": 0.8},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocked"] is True
        assert data["block_reason"] is not None

    def test_evaluate_experiment_returns_recommendation(self, client: TestClient):
        resp = client.post(
            "/autoresearch/experiment/evaluate",
            json={
                "experiment_id": "test-eval-001",
                "metric": "pipeline_execution_time_s",
                "before": 10.0,
                "after": 7.5,
                "test_passed": True,
                "notes": "reduced overhead",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommendation"] == "accept"
        assert data["experiment_id"] == "test-eval-001"

    def test_list_experiments_returns_list(self, client: TestClient):
        resp = client.get("/autoresearch/experiments")
        assert resp.status_code == 200
        data = resp.json()
        assert "experiments" in data
        assert isinstance(data["experiments"], list)
        assert "count" in data

    def test_list_experiments_records_after_evaluate(self, client: TestClient):
        # Evaluate records into log; then list should reflect it
        client.post(
            "/autoresearch/experiment/evaluate",
            json={
                "experiment_id": "list-test-exp",
                "metric": "memory_usage_mb",
                "before": 300.0,
                "after": 280.0,
                "test_passed": True,
            },
        )
        resp = client.get("/autoresearch/experiments")
        experiments = resp.json()["experiments"]
        ids = [e["experiment_id"] for e in experiments]
        assert "list-test-exp" in ids
