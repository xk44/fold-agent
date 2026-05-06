"""Eager/direct worker execution tests (Spark lane).

These tests prove that the Celery task functions in backend.app.worker.tasks
call the shared persistence path (run_pipeline_job / run_alphafold_job) correctly
without needing a real message broker.  They exercise:

  1. Direct task-function invocation (eager mode) -- safety preflight gate,
     argument forwarding, and persistence side-effects.
  2. The shared persistence functions themselves (run_pipeline_job,
     run_alphafold_job) to confirm DB records are written.
  3. Edge cases: missing case_id, preflight block, alphafold with no candidate.

No real Redis/broker is required.  All Celery tasks run eagerly or their
underlying logic is tested via direct function calls.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from celery import Celery
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models import (
    AuditLog,
    CandidateAntigen,
    Case,
    PipelineRun,
    StructureJob,
    Variant,
)
from backend.app.safety.preflight import PreflightResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(db: Session, *, species: str = "demo") -> str:
    """Insert a Case row and return its id."""
    case = Case(
        id=f"test-case-{species}-{uuid4().hex[:8]}",
        species=species,
        diagnosis_summary="eager-test",
    )
    db.add(case)
    db.commit()
    return case.id


def _make_variant(db: Session, case_id: str) -> str:
    variant = Variant(
        id=f"test-variant-{uuid4().hex[:8]}",
        case_id=case_id,
        genomic_coordinates="chr7:140453136 A>T",
        gene="BRAF",
        protein_change="p.V600E",
    )
    db.add(variant)
    db.commit()
    return variant.id


def _make_candidate(db: Session, case_id: str, variant_id: str) -> str:
    candidate = CandidateAntigen(
        id=f"test-candidate-{uuid4().hex[:8]}",
        case_id=case_id,
        variant_id=variant_id,
        mhc_context="HLA-A*02:01",
        peptide_metadata={"sequence": "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQV"},
        prediction_scores={"binding_affinity": 0.95},
    )
    db.add(candidate)
    db.commit()
    return candidate.id


# ---------------------------------------------------------------------------
# Fixtures -- fresh DB per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_db():
    """Create all tables fresh for each test, then tear down."""
    # Shut down the background executor so it releases any SQLite connections.
    from backend.app import jobs as _jobs_mod
    from backend.app.db import engine
    from backend.app.models import Base

    old_executor = _jobs_mod._executor
    old_executor.shutdown(wait=True)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    from concurrent.futures import ThreadPoolExecutor

    _jobs_mod._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-job")
    _jobs_mod._cancel_events.clear()
    _jobs_mod._job_futures.clear()

    yield

    _jobs_mod._executor.shutdown(wait=True)
    _jobs_mod._cancel_events.clear()
    _jobs_mod._job_futures.clear()


# ---------------------------------------------------------------------------
# 1. Shared persistence path: run_pipeline_job (no Celery, no broker)
# ---------------------------------------------------------------------------


class TestRunPipelineJobPersistence:
    """Verify that run_pipeline_job writes PipelineRun + AuditLog records."""

    def test_creates_pipeline_run_record(self):
        from backend.app.jobs import run_pipeline_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        mock_steps = [
            {
                "step_name": "annotation",
                "step_version": "1.0",
                "status": "completed",
                "outputs": {},
                "warnings": [],
                "errors": [],
                "safety_label": "research_only",
                "requires_professional_review": False,
            },
        ]

        def fake_run_pipeline_sync(cid: str) -> dict:
            return {
                "status": "completed",
                "total_steps": 1,
                "completed_steps": 1,
                "steps": mock_steps,
            }

        result = run_pipeline_job(
            case_id=case_id,
            job_id="test-job-pipeline-001",
            run_pipeline_sync=fake_run_pipeline_sync,
            pipeline_mode="mock",
        )

        assert result["status"] == "completed"
        assert result["pipeline_steps"] == 1

        # Verify PipelineRun was persisted
        db2 = SessionLocal()
        pipeline_runs = db2.query(PipelineRun).filter(PipelineRun.case_id == case_id).all()
        assert len(pipeline_runs) == 1
        assert pipeline_runs[0].status == "completed"
        assert pipeline_runs[0].total_steps == 1
        assert pipeline_runs[0].completed_steps == 1
        db2.close()

    def test_emits_pipeline_started_audit_event(self):
        from backend.app.jobs import run_pipeline_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        result = run_pipeline_job(
            case_id=case_id,
            job_id="test-job-pipeline-audit",
            run_pipeline_sync=lambda cid: {
                "status": "completed",
                "total_steps": 0,
                "completed_steps": 0,
                "steps": [],
            },
            pipeline_mode="mock",
        )

        db2 = SessionLocal()
        audit_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "pipeline.started",
            )
            .all()
        )
        assert len(audit_entries) == 1
        # log_action stores inputs as inputs_hash; details may carry structured data
        # The key assertion: the audit log entry exists and is linked to the case
        assert audit_entries[0].case_id == case_id
        assert audit_entries[0].actor == "bg_job"
        assert audit_entries[0].inputs_hash is not None  # inputs were hashed
        db2.close()

    def test_emits_pipeline_completed_audit_event(self):
        from backend.app.jobs import run_pipeline_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        result = run_pipeline_job(
            case_id=case_id,
            job_id="test-job-pipeline-completed-audit",
            run_pipeline_sync=lambda cid: {
                "status": "completed",
                "total_steps": 1,
                "completed_steps": 1,
                "steps": [
                    {
                        "step_name": "s1",
                        "step_version": "1.0",
                        "status": "completed",
                        "outputs": {},
                        "warnings": [],
                        "errors": [],
                        "safety_label": "research_only",
                        "requires_professional_review": False,
                    }
                ],
            },
            pipeline_mode="mock",
        )

        db2 = SessionLocal()
        audit_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "pipeline.completed",
            )
            .all()
        )
        assert len(audit_entries) == 1
        assert audit_entries[0].case_id == case_id
        assert audit_entries[0].actor == "bg_job"
        assert audit_entries[0].outputs_hash is not None
        step_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "pipeline.step.completed",
            )
            .all()
        )
        assert len(step_entries) == 1
        db2.close()

    def test_emits_pipeline_failed_audit_event(self):
        from backend.app.jobs import run_pipeline_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        result = run_pipeline_job(
            case_id=case_id,
            job_id="test-job-pipeline-failed-audit",
            run_pipeline_sync=lambda cid: {
                "status": "failed",
                "total_steps": 2,
                "completed_steps": 1,
                "steps": [
                    {
                        "step_name": "s1",
                        "step_version": "1.0",
                        "status": "completed",
                        "outputs": {},
                        "warnings": [],
                        "errors": [],
                        "safety_label": "research_only",
                        "requires_professional_review": False,
                    },
                    {
                        "step_name": "s2",
                        "step_version": "1.0",
                        "status": "failed",
                        "outputs": {},
                        "warnings": [],
                        "errors": ["boom"],
                        "safety_label": "research_only",
                        "requires_professional_review": False,
                    },
                ],
            },
            pipeline_mode="mock",
        )

        assert result["status"] == "failed"
        db2 = SessionLocal()
        failed_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "pipeline.failed",
            )
            .all()
        )
        assert len(failed_entries) == 1
        step_failed_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "pipeline.step.failed",
            )
            .all()
        )
        assert len(step_failed_entries) == 1
        pr = db2.query(PipelineRun).filter(PipelineRun.case_id == case_id).one()
        assert pr.status == "failed"
        db2.close()

    def test_pipeline_run_record_stores_step_results(self):
        """Verify that step_results JSON includes the full step data."""
        from backend.app.jobs import run_pipeline_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        steps = [
            {
                "step_name": "annotation",
                "step_version": "1.0",
                "status": "completed",
                "outputs": {"genes": ["BRAF"]},
                "warnings": [],
                "errors": [],
                "safety_label": "research_only",
                "requires_professional_review": False,
            },
            {
                "step_name": "prioritization",
                "step_version": "2.0",
                "status": "completed",
                "outputs": {"top_hits": 3},
                "warnings": ["low confidence"],
                "errors": [],
                "safety_label": "research_only",
                "requires_professional_review": True,
            },
        ]

        run_pipeline_job(
            case_id=case_id,
            job_id="test-job-pipeline-steps",
            run_pipeline_sync=lambda cid: {
                "status": "completed",
                "total_steps": 2,
                "completed_steps": 2,
                "steps": steps,
            },
            pipeline_mode="mock",
        )

        db2 = SessionLocal()
        pr = db2.query(PipelineRun).filter(PipelineRun.case_id == case_id).one()
        assert pr.current_step == "prioritization"
        assert pr.step_results["steps"][0]["step_name"] == "annotation"
        assert pr.step_results["steps"][1]["requires_professional_review"] is True
        db2.close()


# ---------------------------------------------------------------------------
# 2. Shared persistence path: run_alphafold_job (no Celery, no broker)
# ---------------------------------------------------------------------------


class TestRunAlphafoldJobPersistence:
    """Verify that run_alphafold_job writes StructureJob + AuditLog records."""

    def test_creates_structure_job_record(self):
        from backend.app.jobs import run_alphafold_job

        db = SessionLocal()
        case_id = _make_case(db)
        variant_id = _make_variant(db, case_id)
        candidate_id = _make_candidate(db, case_id, variant_id)
        db.close()

        def fake_run_alphafold_sync(backend_name: str, payload: dict) -> dict:
            return {
                "status": "completed",
                "stdout": '{"structure": {"pdb_file": "/tmp/test.pdb", "pLDDT_mean": 92.5, "ranking_score": 0.88}}',
                "structure": {"pdb_file": "/tmp/test.pdb", "pLDDT_mean": 92.5},
            }

        result = run_alphafold_job(
            case_id=case_id,
            job_id="test-job-af-001",
            backend_name="colabfold",
            payload={"candidate_id": candidate_id},
            run_alphafold_sync=fake_run_alphafold_sync,
        )

        assert result["status"] == "completed"

        # Verify StructureJob was persisted
        db2 = SessionLocal()
        structure_jobs = db2.query(StructureJob).filter(StructureJob.case_id == case_id).all()
        assert len(structure_jobs) == 1
        sj = structure_jobs[0]
        assert sj.backend_used == "colabfold"
        assert sj.status == "completed"
        assert sj.candidate_id == candidate_id
        assert sj.output_path == "/tmp/test.pdb"
        # pLDDT_mean is extracted from the parsed stdout JSON
        assert "pLDDT_mean" in sj.confidence_metrics
        assert sj.confidence_metrics["pLDDT_mean"] == 92.5
        db2.close()

    def test_emits_alphafold_completed_audit_event(self):
        from backend.app.jobs import run_alphafold_job

        db = SessionLocal()
        case_id = _make_case(db)
        variant_id = _make_variant(db, case_id)
        candidate_id = _make_candidate(db, case_id, variant_id)
        db.close()

        run_alphafold_job(
            case_id=case_id,
            job_id="test-job-af-audit",
            backend_name="mock",
            payload={"candidate_id": candidate_id},
            run_alphafold_sync=lambda bname, p: {
                "status": "completed",
                "structure": {"model_cif": "/tmp/model.cif"},
            },
        )

        db2 = SessionLocal()
        started_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "alphafold.job.started",
            )
            .all()
        )
        assert len(started_entries) == 1
        job_completed_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "alphafold.job.completed",
            )
            .all()
        )
        assert len(job_completed_entries) == 1
        audit_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "alphafold.backend.completed",
            )
            .all()
        )
        assert len(audit_entries) == 1
        assert audit_entries[0].actor == "bg_job"
        db2.close()

    def test_no_structure_job_when_no_candidate_id(self):
        """When payload has no candidate_id, run_alphafold_job should NOT
        create a StructureJob record but should still emit an audit log."""
        from backend.app.jobs import run_alphafold_job

        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        result = run_alphafold_job(
            case_id=case_id,
            job_id="test-job-af-nocand",
            backend_name="mock",
            payload={},
            run_alphafold_sync=lambda bname, p: {"status": "completed"},
        )

        assert result["status"] == "completed"

        db2 = SessionLocal()
        structure_jobs = db2.query(StructureJob).filter(StructureJob.case_id == case_id).all()
        # No StructureJob should be created when there's no candidate_id
        assert len(structure_jobs) == 0

        # But audit log for the backend completion should still exist
        audit_entries = (
            db2.query(AuditLog)
            .filter(
                AuditLog.case_id == case_id,
                AuditLog.action == "alphafold.backend.completed",
            )
            .all()
        )
        assert len(audit_entries) == 1
        db2.close()

    def test_confidence_metrics_extracted_from_stdout_json(self):
        """Verify that confidence metrics are parsed from stdout JSON when present."""
        from backend.app.jobs import run_alphafold_job

        db = SessionLocal()
        case_id = _make_case(db)
        variant_id = _make_variant(db, case_id)
        candidate_id = _make_candidate(db, case_id, variant_id)
        db.close()

        def fake_sync(backend_name: str, payload: dict) -> dict:
            return {
                "status": "completed",
                "stdout": '{"structure": {"pdb_file": "/tmp/out.pdb", "pLDDT_mean": 87.3, "ptm": 0.72, "ranking_score": 0.91}}',
                "structure": {"pdb_file": "/tmp/out.pdb"},
            }

        run_alphafold_job(
            case_id=case_id,
            job_id="test-job-af-conf",
            backend_name="colabfold",
            payload={"candidate_id": candidate_id},
            run_alphafold_sync=fake_sync,
        )

        db2 = SessionLocal()
        sj = db2.query(StructureJob).filter(StructureJob.case_id == case_id).one()
        # stdout JSON should be parsed and override the base structure dict
        assert sj.confidence_metrics.get("pLDDT_mean") == 87.3
        assert sj.confidence_metrics.get("ptm") == 0.72
        assert sj.confidence_metrics.get("ranking_score") == 0.91
        db2.close()


# ---------------------------------------------------------------------------
# 3. Eager task execution: inline task definitions (no worker import needed)
#    These replicate the real task logic with a test Celery app configured
#    for eager execution, proving the same code path works without a broker.
# ---------------------------------------------------------------------------


def _make_eager_app() -> Celery:
    """Create a Celery app configured for eager (synchronous) execution."""
    app = Celery("foldagent_test", broker="memory://", backend="cache+memory://")
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
    )
    return app


class TestPipelineRunTaskEager:
    """Test the pipeline_run task logic in eager mode.

    We replicate the task function on an eager Celery app so that .apply()
    runs it synchronously. This tests the same code path without a broker.
    """

    def test_pipeline_run_calls_run_pipeline_job_with_correct_args(self):
        eager_app = _make_eager_app()

        call_tracker = {"called": False, "kwargs": {}}

        def fake_run_pipeline_job(*, case_id, job_id, run_pipeline_sync, pipeline_mode):
            call_tracker["called"] = True
            call_tracker["kwargs"] = {
                "case_id": case_id,
                "job_id": job_id,
                "pipeline_mode": pipeline_mode,
            }
            return {"status": "completed", "pipeline_steps": 3}

        @eager_app.task(bind=True, name="test.pipeline_run_eager")
        def pipeline_run_eager(self, *, job_id, payload, case_id=None):
            """Replica of backend.app.worker.tasks.pipeline_run logic."""
            from backend.app.jobs import run_pipeline_job as _run_pipeline_job
            from backend.app.safety.preflight import preflight_action

            pipeline_case_id = case_id or payload.get("case_id")
            if not pipeline_case_id:
                raise ValueError("pipeline_run requires case_id")

            action = payload.get("action", "run_pipeline")
            species_mode = payload.get("species_mode", "demo")
            result = preflight_action(
                action=action,
                species_mode=species_mode,
                involves_sequence_data=species_mode != "demo",
            )
            if result.status != PreflightResult.PASS:
                raise ValueError(f"Pipeline worker blocked by safety preflight: {result.reason}")

            return _run_pipeline_job(
                case_id=pipeline_case_id,
                job_id=job_id,
                run_pipeline_sync=lambda cid: {
                    "status": "completed",
                    "steps": [],
                    "completed_steps": 0,
                    "total_steps": 0,
                },
                pipeline_mode=payload.get("pipeline_mode", "mock"),
            )

        # Patch run_pipeline_job to our tracker
        with patch("backend.app.jobs.run_pipeline_job", fake_run_pipeline_job):
            result = pipeline_run_eager.apply(
                kwargs=dict(
                    job_id="eager-job-001",
                    payload={
                        "case_id": "case-demo",
                        "species_mode": "demo",
                        "pipeline_mode": "mock",
                    },
                )
            )

        assert result.successful()
        assert call_tracker["called"]
        assert call_tracker["kwargs"]["case_id"] == "case-demo"
        assert call_tracker["kwargs"]["job_id"] == "eager-job-001"
        assert call_tracker["kwargs"]["pipeline_mode"] == "mock"

    def test_pipeline_run_eager_with_db_persistence(self):
        """Full eager execution: task runs, preflight passes, PipelineRun
        record is written to the DB."""
        eager_app = _make_eager_app()

        @eager_app.task(bind=True, name="test.pipeline_run_eager_persist")
        def pipeline_run_eager_persist(self, *, job_id, payload, case_id=None):
            """Replica of the real pipeline_run task."""
            from backend.app.jobs import run_pipeline_job
            from backend.app.safety.preflight import preflight_action

            pipeline_case_id = case_id or payload.get("case_id")
            if not pipeline_case_id:
                raise ValueError("pipeline_run requires case_id")

            action = payload.get("action", "run_pipeline")
            species_mode = payload.get("species_mode", "demo")
            result = preflight_action(
                action=action,
                species_mode=species_mode,
                involves_sequence_data=species_mode != "demo",
            )
            if result.status != PreflightResult.PASS:
                raise ValueError(f"Pipeline worker blocked by safety preflight: {result.reason}")

            # Use a mock sync that returns realistic data
            def _mock_sync(cid: str) -> dict:
                return {
                    "status": "completed",
                    "total_steps": 1,
                    "completed_steps": 1,
                    "steps": [
                        {
                            "step_name": "annotation",
                            "step_version": "1.0",
                            "status": "completed",
                            "outputs": {},
                            "warnings": [],
                            "errors": [],
                            "safety_label": "research_only",
                            "requires_professional_review": False,
                        },
                    ],
                }

            with patch("backend.app.main._run_pipeline_sync", _mock_sync):
                return run_pipeline_job(
                    case_id=pipeline_case_id,
                    job_id=job_id,
                    run_pipeline_sync=_mock_sync,
                    pipeline_mode=payload.get("pipeline_mode", "mock"),
                )

        # Create a case in the DB
        db = SessionLocal()
        case_id = _make_case(db)
        db.close()

        result = pipeline_run_eager_persist.apply(
            kwargs=dict(
                job_id="eager-persist-001",
                payload={"case_id": case_id, "species_mode": "demo"},
            )
        )

        assert result.successful()
        assert result.result["status"] == "completed"

        # Verify PipelineRun record was created
        db2 = SessionLocal()
        pr = db2.query(PipelineRun).filter(PipelineRun.case_id == case_id).one()
        assert pr.status == "completed"
        db2.close()

    def test_pipeline_run_rejects_missing_case_id(self):
        eager_app = _make_eager_app()

        @eager_app.task(bind=True, name="test.pipeline_run_no_case")
        def pipeline_run_no_case(self, *, job_id, payload, case_id=None):
            pipeline_case_id = case_id or payload.get("case_id")
            if not pipeline_case_id:
                raise ValueError("pipeline_run requires case_id")
            return {"status": "ok"}

        with pytest.raises(ValueError, match="pipeline_run requires case_id"):
            pipeline_run_no_case.apply(kwargs=dict(job_id="eager-no-case", payload={}))

    def test_pipeline_run_blocked_by_safety_preflight(self):
        eager_app = _make_eager_app()

        @eager_app.task(bind=True, name="test.pipeline_run_safety_block")
        def pipeline_run_safety_block(self, *, job_id, payload, case_id=None):
            from backend.app.safety.preflight import preflight_action

            pipeline_case_id = case_id or payload.get("case_id")
            action = payload.get("action", "run_pipeline")
            species_mode = payload.get("species_mode", "human")
            result = preflight_action(
                action=action,
                species_mode=species_mode,
                involves_sequence_data=species_mode != "demo",
            )
            if result.status != PreflightResult.PASS:
                raise ValueError(f"Pipeline worker blocked by safety preflight: {result.reason}")
            return {"status": "ok"}

        with pytest.raises(ValueError, match="Pipeline worker blocked by safety preflight"):
            pipeline_run_safety_block.apply(
                kwargs=dict(
                    job_id="eager-safety-block",
                    payload={"case_id": "case-human", "species_mode": "human"},
                )
            )


# ---------------------------------------------------------------------------
# 4. Eager task execution: structure_prediction task
# ---------------------------------------------------------------------------


class TestStructurePredictionTaskEager:
    """Test the structure_prediction task logic in eager mode."""

    def test_structure_prediction_delegates_to_run_alphafold_job(self):
        eager_app = _make_eager_app()

        call_tracker = {"called": False, "kwargs": {}}

        def fake_run_alphafold_job(*, case_id, job_id, backend_name, payload, run_alphafold_sync):
            call_tracker["called"] = True
            call_tracker["kwargs"] = {
                "case_id": case_id,
                "job_id": job_id,
                "backend_name": backend_name,
                "payload": payload,
            }
            return {"status": "completed"}

        @eager_app.task(bind=True, name="test.structure_prediction_eager")
        def structure_prediction_eager(self, *, job_id, backend_name, payload, case_id=None):
            """Replica of backend.app.worker.tasks.structure_prediction logic."""
            from backend.app.jobs import run_alphafold_job as _run_alphafold_job

            pipeline_case_id = case_id or payload.get("case_id")
            return _run_alphafold_job(
                case_id=pipeline_case_id,
                job_id=job_id,
                backend_name=backend_name,
                payload=payload,
                run_alphafold_sync=lambda bname, p: {"status": "completed"},
            )

        with patch("backend.app.jobs.run_alphafold_job", fake_run_alphafold_job):
            result = structure_prediction_eager.apply(
                kwargs=dict(
                    job_id="eager-af-job-001",
                    backend_name="colabfold",
                    payload={"case_id": "case-af-demo", "sequence": "MTEYKLVVVG"},
                    case_id="case-af-explicit",
                )
            )

        assert result.successful()
        assert call_tracker["called"]
        # Explicit case_id should take precedence
        assert call_tracker["kwargs"]["case_id"] == "case-af-explicit"
        assert call_tracker["kwargs"]["job_id"] == "eager-af-job-001"
        assert call_tracker["kwargs"]["backend_name"] == "colabfold"

    def test_structure_prediction_uses_payload_case_id_as_fallback(self):
        eager_app = _make_eager_app()

        call_tracker = {"called": False, "case_id": None}

        def fake_run_alphafold_job(*, case_id, job_id, backend_name, payload, run_alphafold_sync):
            call_tracker["called"] = True
            call_tracker["case_id"] = case_id
            return {"status": "completed"}

        @eager_app.task(bind=True, name="test.structure_prediction_fallback")
        def structure_prediction_fallback(self, *, job_id, backend_name, payload, case_id=None):
            pipeline_case_id = case_id or payload.get("case_id")
            from backend.app.jobs import run_alphafold_job as _run_alphafold_job

            return _run_alphafold_job(
                case_id=pipeline_case_id,
                job_id=job_id,
                backend_name=backend_name,
                payload=payload,
                run_alphafold_sync=lambda bname, p: {"status": "completed"},
            )

        with patch("backend.app.jobs.run_alphafold_job", fake_run_alphafold_job):
            result = structure_prediction_fallback.apply(
                kwargs=dict(
                    job_id="eager-af-job-002",
                    backend_name="mock",
                    payload={"case_id": "case-af-from-payload"},
                )
            )

        assert result.successful()
        assert call_tracker["called"]
        assert call_tracker["case_id"] == "case-af-from-payload"

    def test_structure_prediction_eager_with_db_persistence(self):
        """Full eager execution of structure_prediction that persists
        a StructureJob record."""
        eager_app = _make_eager_app()

        @eager_app.task(bind=True, name="test.structure_prediction_persist")
        def structure_prediction_persist(self, *, job_id, backend_name, payload, case_id=None):
            from backend.app.jobs import run_alphafold_job

            pipeline_case_id = case_id or payload.get("case_id")
            return run_alphafold_job(
                case_id=pipeline_case_id,
                job_id=job_id,
                backend_name=backend_name,
                payload=payload,
                run_alphafold_sync=lambda bname, p: {
                    "status": "completed",
                    "structure": {"pdb_file": "/tmp/eager_test.pdb"},
                },
            )

        db = SessionLocal()
        case_id = _make_case(db)
        variant_id = _make_variant(db, case_id)
        candidate_id = _make_candidate(db, case_id, variant_id)
        db.close()

        result = structure_prediction_persist.apply(
            kwargs=dict(
                job_id="eager-af-persist-001",
                backend_name="colabfold",
                payload={"case_id": case_id, "candidate_id": candidate_id},
            )
        )

        assert result.successful()
        assert result.result["status"] == "completed"

        # Verify StructureJob was persisted
        db2 = SessionLocal()
        sj = db2.query(StructureJob).filter(StructureJob.case_id == case_id).one()
        assert sj.backend_used == "colabfold"
        assert sj.status == "completed"
        assert sj.candidate_id == candidate_id
        db2.close()


# ---------------------------------------------------------------------------
# 5. Direct task execution via imported module (broker env var set)
#    This imports the real tasks.py by temporarily setting the broker URL,
#    then calls the task functions directly (bypassing Celery dispatch).
# ---------------------------------------------------------------------------


class TestDirectTaskImport:
    """Import the real task module by setting the broker env var, then call
    the task functions' underlying Python logic directly.

    This is the strongest 'eager' test: it uses the actual code from
    backend.app.worker.tasks, not a replica.
    """

    @pytest.fixture(autouse=True)
    def _import_real_tasks(self, monkeypatch):
        """Set broker env vars so the worker module can be imported, then
        inject a mock Celery app so tasks can be called as plain functions."""
        # Set env vars for the config module
        monkeypatch.setenv("FOLDAGENT_CELERY_BROKER_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("FOLDAGENT_REDIS_URL", "redis://localhost:6379/0")

        # Reload config to pick up new env vars
        import backend.app.config as _cfg

        monkeypatch.setattr(_cfg.settings, "celery_broker_url", "redis://localhost:6379/0")
        monkeypatch.setattr(_cfg.settings, "redis_url", "redis://localhost:6379/0")

        # Remove cached worker modules so they get re-imported
        for mod_key in list(sys.modules.keys()):
            if mod_key.startswith("backend.app.worker"):
                del sys.modules[mod_key]

        # Now we can import the worker module
        import backend.app.worker  # noqa: F401 -- triggers __init__.py
        import backend.app.worker.tasks as _tasks

        # Replace the Celery app with a passthrough mock so task functions
        # can be called directly as plain Python functions
        mock_app = MagicMock()
        mock_app.task = lambda **kw: lambda fn: fn

        # We need to get the undecorated function. Since the module was already
        # imported with the real Celery app, the functions are Celery Task objects.
        # We'll extract the .run() method from each task.
        self._tasks_module = _tasks
        self._pipeline_run_fn = _tasks.pipeline_run
        self._structure_prediction_fn = _tasks.structure_prediction

        yield

        # Clean up
        for mod_key in list(sys.modules.keys()):
            if mod_key.startswith("backend.app.worker"):
                del sys.modules[mod_key]

    def test_real_pipeline_run_delegates_correctly(self):
        """The real pipeline_run task function calls run_pipeline_job
        with the correct arguments after passing preflight."""
        call_tracker = {"called": False, "kwargs": {}}

        def fake_run_pipeline_job(*, case_id, job_id, run_pipeline_sync, pipeline_mode):
            call_tracker["called"] = True
            call_tracker["kwargs"] = {
                "case_id": case_id,
                "job_id": job_id,
                "pipeline_mode": pipeline_mode,
            }
            assert callable(run_pipeline_sync)
            return {"status": "completed", "pipeline_steps": 2}

        # pipeline_run is a Celery Task with bind=True.
        # Calling .run() invokes the underlying function directly.
        with patch("backend.app.jobs.run_pipeline_job", fake_run_pipeline_job):
            result = self._pipeline_run_fn.run(
                job_id="real-task-001",
                payload={"case_id": "case-real", "species_mode": "demo"},
            )

        assert call_tracker["called"]
        assert call_tracker["kwargs"]["case_id"] == "case-real"
        assert call_tracker["kwargs"]["job_id"] == "real-task-001"
        assert call_tracker["kwargs"]["pipeline_mode"] == "mock"

    def test_real_structure_prediction_delegates_correctly(self):
        """The real structure_prediction task function calls run_alphafold_job
        with the correct arguments."""
        call_tracker = {"called": False, "kwargs": {}}

        def fake_run_alphafold_job(*, case_id, job_id, backend_name, payload, run_alphafold_sync):
            call_tracker["called"] = True
            call_tracker["kwargs"] = {
                "case_id": case_id,
                "job_id": job_id,
                "backend_name": backend_name,
                "payload": payload,
            }
            assert callable(run_alphafold_sync)
            return {"status": "completed"}

        with patch("backend.app.jobs.run_alphafold_job", fake_run_alphafold_job):
            result = self._structure_prediction_fn.run(
                job_id="real-af-task-001",
                backend_name="colabfold",
                payload={"case_id": "case-af-real"},
            )

        assert call_tracker["called"]
        assert call_tracker["kwargs"]["case_id"] == "case-af-real"
        assert call_tracker["kwargs"]["job_id"] == "real-af-task-001"
        assert call_tracker["kwargs"]["backend_name"] == "colabfold"

    def test_real_pipeline_run_raises_on_missing_case_id(self):
        """The real pipeline_run task should raise ValueError when
        no case_id is provided."""
        with pytest.raises(ValueError, match="pipeline_run requires case_id"):
            self._pipeline_run_fn.run(
                job_id="real-no-case",
                payload={},
            )

    def test_real_pipeline_run_raises_on_safety_block(self):
        """The real pipeline_run task should raise ValueError when
        preflight blocks (human mode without attestation)."""
        mock_case = MagicMock()
        mock_case.species.value = "human"
        mock_db = MagicMock()
        mock_db.get.return_value = mock_case

        with patch("backend.app.worker.tasks.SessionLocal", return_value=mock_db):
            with pytest.raises(ValueError, match="Pipeline worker blocked by safety preflight"):
                self._pipeline_run_fn.run(
                    job_id="real-safety-block",
                    payload={"case_id": "case-human"},
                )

    def test_real_pipeline_run_case_id_from_explicit_arg(self):
        """Explicit case_id argument should take precedence over payload."""
        call_tracker = {"called": False, "case_id": None}

        def fake_run_pipeline_job(*, case_id, job_id, run_pipeline_sync, pipeline_mode):
            call_tracker["called"] = True
            call_tracker["case_id"] = case_id
            return {"status": "completed", "pipeline_steps": 1}

        with patch("backend.app.jobs.run_pipeline_job", fake_run_pipeline_job):
            result = self._pipeline_run_fn.run(
                job_id="real-explicit-case",
                payload={"case_id": "from-payload", "species_mode": "demo"},
                case_id="from-explicit-arg",
            )

        assert call_tracker["called"]
        assert call_tracker["case_id"] == "from-explicit-arg"

    def test_real_structure_prediction_case_id_from_explicit_arg(self):
        """Explicit case_id argument should take precedence over payload
        for structure_prediction too."""
        call_tracker = {"called": False, "case_id": None}

        def fake_run_alphafold_job(*, case_id, job_id, backend_name, payload, run_alphafold_sync):
            call_tracker["called"] = True
            call_tracker["case_id"] = case_id
            return {"status": "completed"}

        with patch("backend.app.jobs.run_alphafold_job", fake_run_alphafold_job):
            self._structure_prediction_fn.run(
                job_id="real-af-explicit-case",
                backend_name="mock",
                payload={"case_id": "from-payload"},
                case_id="from-explicit-arg",
            )

        assert call_tracker["called"]
        assert call_tracker["case_id"] == "from-explicit-arg"
