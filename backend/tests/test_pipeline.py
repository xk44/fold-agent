"""Tests for the Phase 5 pipeline step framework.

Covers: PipelineStep subclasses, StepResult, PipelineRunner, parallel
execution, retry decorator, error classification, and the 3 new API endpoints.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app.pipeline.framework import (
    AlignmentStep,
    AnnotationStep,
    BindingPredictionStep,
    ErrorCategory,
    FRAMEWORK_STEPS,
    PipelineError,
    PipelineRunner,
    PipelineStep,
    StepFailedError,
    StepResult,
    StepTimeoutError,
    VariantCallingStep,
    run_parallel_steps,
    with_retry,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class _PassStep(PipelineStep):
    @property
    def name(self) -> str:
        return "pass_step"

    def execute(self, input_data: dict) -> dict:
        return {"done": True}


class _FailStep(PipelineStep):
    @property
    def name(self) -> str:
        return "fail_step"

    def execute(self, input_data: dict) -> dict:
        raise RuntimeError("deliberate failure")


class _TimeoutStep(PipelineStep):
    @property
    def name(self) -> str:
        return "timeout_step"

    def execute(self, input_data: dict) -> dict:
        raise StepTimeoutError("timed out")


class _MissingToolStep(PipelineStep):
    @property
    def name(self) -> str:
        return "missing_tool_step"

    def execute(self, input_data: dict) -> dict:
        raise FileNotFoundError("bwa-mem2 not found")


class _InputErrorStep(PipelineStep):
    @property
    def name(self) -> str:
        return "input_error_step"

    def execute(self, input_data: dict) -> dict:
        raise ValueError("bad input")


class _ResourceErrorStep(PipelineStep):
    @property
    def name(self) -> str:
        return "resource_error_step"

    def execute(self, input_data: dict) -> dict:
        raise MemoryError("OOM")


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------


def test_step_result_defaults() -> None:
    r = StepResult(step_name="foo", status="success")
    assert r.output == {}
    assert r.error is None
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.error_category is None


def test_step_result_to_dict() -> None:
    r = StepResult(
        step_name="bar",
        status="failed",
        error="boom",
        error_category=ErrorCategory.runtime_error,
    )
    d = r.to_dict()
    assert d["step_name"] == "bar"
    assert d["status"] == "failed"
    assert d["error"] == "boom"
    assert d["error_category"] == "runtime_error"


def test_step_result_to_dict_no_category() -> None:
    r = StepResult(step_name="x", status="success")
    assert r.to_dict()["error_category"] is None


# ---------------------------------------------------------------------------
# PipelineStep subclass execution
# ---------------------------------------------------------------------------


def test_pass_step_returns_success() -> None:
    result = _PassStep().run({})
    assert result.status == "success"
    assert result.step_name == "pass_step"
    assert result.output == {"done": True}
    assert result.duration_seconds is not None and result.duration_seconds >= 0


def test_fail_step_returns_failed_with_category() -> None:
    result = _FailStep().run({})
    assert result.status == "failed"
    assert result.error_category == ErrorCategory.runtime_error


def test_timeout_step_returns_timeout_category() -> None:
    result = _TimeoutStep().run({})
    assert result.status == "failed"
    assert result.error_category == ErrorCategory.timeout


def test_missing_tool_step_returns_tool_missing() -> None:
    result = _MissingToolStep().run({})
    assert result.status == "failed"
    assert result.error_category == ErrorCategory.tool_missing


def test_input_error_step_returns_input_error() -> None:
    result = _InputErrorStep().run({})
    assert result.status == "failed"
    assert result.error_category == ErrorCategory.input_error


def test_resource_error_step_returns_resource_error() -> None:
    result = _ResourceErrorStep().run({})
    assert result.status == "failed"
    assert result.error_category == ErrorCategory.resource_error


def test_concrete_steps_are_abstract_compliant() -> None:
    for step in [AlignmentStep(), VariantCallingStep(), AnnotationStep(), BindingPredictionStep()]:
        result = step.run({})
        assert result.status == "success"
        assert result.step_name == step.name
        assert isinstance(result.output, dict)


def test_alignment_step_name() -> None:
    assert AlignmentStep().name == "alignment"


def test_variant_calling_step_name() -> None:
    assert VariantCallingStep().name == "variant_calling"


def test_annotation_step_name() -> None:
    assert AnnotationStep().name == "annotation"


def test_binding_prediction_step_name() -> None:
    assert BindingPredictionStep().name == "binding_prediction"


# ---------------------------------------------------------------------------
# PipelineRunner sequential execution
# ---------------------------------------------------------------------------


def test_runner_all_pass() -> None:
    runner = PipelineRunner([_PassStep(), _PassStep()])
    results = runner.run()
    assert len(results) == 2
    assert all(r.status == "success" for r in results)


def test_runner_stops_and_skips_on_failure() -> None:
    runner = PipelineRunner([_PassStep(), _FailStep(), _PassStep()])
    results = runner.run()
    assert len(results) == 3
    assert results[0].status == "success"
    assert results[1].status == "failed"
    assert results[2].status == "skipped"


def test_runner_passes_outputs_to_next_step() -> None:
    class _Producer(PipelineStep):
        @property
        def name(self) -> str:
            return "producer"

        def execute(self, input_data: dict) -> dict:
            return {"key": "value"}

    class _Consumer(PipelineStep):
        @property
        def name(self) -> str:
            return "consumer"

        def execute(self, input_data: dict) -> dict:
            assert input_data.get("key") == "value"
            return {}

    runner = PipelineRunner([_Producer(), _Consumer()])
    results = runner.run()
    assert all(r.status == "success" for r in results)


def test_runner_empty_steps() -> None:
    runner = PipelineRunner([])
    results = runner.run()
    assert results == []


# ---------------------------------------------------------------------------
# Parallel step execution
# ---------------------------------------------------------------------------


def test_run_parallel_steps_all_pass() -> None:
    steps = [_PassStep(), AlignmentStep(), AnnotationStep()]
    results = run_parallel_steps(steps, max_workers=3)
    assert len(results) == 3
    assert all(r.status == "success" for r in results)


def test_run_parallel_steps_one_fails() -> None:
    steps = [_PassStep(), _FailStep(), _PassStep()]
    results = run_parallel_steps(steps, max_workers=3)
    statuses = {r.step_name: r.status for r in results}
    assert statuses["pass_step"] == "success"
    assert statuses["fail_step"] == "failed"


def test_run_parallel_steps_result_count() -> None:
    steps = [AlignmentStep(), VariantCallingStep(), AnnotationStep(), BindingPredictionStep()]
    results = run_parallel_steps(steps, max_workers=2)
    assert len(results) == 4


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


def test_retry_succeeds_on_second_attempt() -> None:
    call_count = {"n": 0}

    @with_retry(max_attempts=3, backoff_factor=0.0)
    def flaky() -> str:
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    assert flaky() == "ok"
    assert call_count["n"] == 2


def test_retry_raises_after_max_attempts() -> None:
    @with_retry(max_attempts=2, backoff_factor=0.0)
    def always_fails() -> None:
        raise RuntimeError("always")

    with pytest.raises(RuntimeError, match="always"):
        always_fails()


def test_retry_does_not_retry_unrelated_exceptions() -> None:
    call_count = {"n": 0}

    @with_retry(max_attempts=3, backoff_factor=0.0)
    def wrong_exc() -> None:
        call_count["n"] += 1
        raise ValueError("not retried")

    with pytest.raises(ValueError):
        wrong_exc()
    assert call_count["n"] == 1


def test_retry_preserves_return_value_on_first_success() -> None:
    @with_retry(max_attempts=3, backoff_factor=0.0)
    def instant_success() -> int:
        return 42

    assert instant_success() == 42


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def test_error_category_values() -> None:
    assert ErrorCategory.input_error == "input_error"
    assert ErrorCategory.tool_missing == "tool_missing"
    assert ErrorCategory.runtime_error == "runtime_error"
    assert ErrorCategory.timeout == "timeout"
    assert ErrorCategory.resource_error == "resource_error"


def test_pipeline_error_hierarchy() -> None:
    assert issubclass(StepFailedError, PipelineError)
    assert issubclass(StepTimeoutError, PipelineError)
    assert issubclass(StepTimeoutError, TimeoutError)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_list_pipeline_steps(client: TestClient) -> None:
    response = client.get("/pipeline/steps")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == len(FRAMEWORK_STEPS)
    names = [item["name"] for item in payload]
    assert "alignment" in names
    assert "variant_calling" in names
    assert "annotation" in names
    assert "binding_prediction" in names
    for item in payload:
        assert "name" in item
        assert "description" in item


def test_pipeline_dry_run_all_valid(client: TestClient) -> None:
    response = client.post(
        "/pipeline/dry-run",
        json={"steps": ["alignment", "variant_calling"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert set(payload["valid"]) == {"alignment", "variant_calling"}
    assert payload["unknown"] == []


def test_pipeline_dry_run_with_unknown_step(client: TestClient) -> None:
    response = client.post(
        "/pipeline/dry-run",
        json={"steps": ["alignment", "nonexistent_step"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "alignment" in payload["valid"]
    assert "nonexistent_step" in payload["unknown"]


def test_pipeline_dry_run_empty_steps(client: TestClient) -> None:
    response = client.post("/pipeline/dry-run", json={"steps": []})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["valid"] == []
    assert payload["unknown"] == []


def test_pipeline_dry_run_missing_steps_key(client: TestClient) -> None:
    response = client.post("/pipeline/dry-run", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True


def test_get_pipeline_status_missing_case(client: TestClient) -> None:
    response = client.get("/cases/no-such-case-id/pipeline/status")
    assert response.status_code == 404


def test_get_pipeline_status_returns_latest_run(client: TestClient) -> None:
    create = client.post(
        "/cases",
        json={"species": "demo", "diagnosis_summary": "status test"},
    )
    case_id = create.json()["id"]

    run_resp = client.post(f"/cases/{case_id}/pipeline/run")
    assert run_resp.status_code == 201

    status_resp = client.get(f"/cases/{case_id}/pipeline/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["case_id"] == case_id
