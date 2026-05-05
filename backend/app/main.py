"""FoldAgent FastAPI Application.

Local-first, safety-gated research coordination platform.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
import structlog

from backend.app.config import settings
from backend.app.db import get_db, init_db
from backend.app.models import AgentTask, Artifact, AuditLog, CandidateAntigen, Case, CaseTask, ExecutionRun, PipelineRun, Report, Sample, StructureJob, Subject, Variant
from backend.app.schemas import (
    AlphaFoldValidationErrorResponse,
    AgentTaskCreate,
    AgentTaskRead,
    AgentTaskUpdate,
    AuditLogRead,
    CandidateCreate,
    CandidateRead,
    CaseBundleExport,
    CaseBundleRead,
    CaseCreate,
    CaseRead,
    CaseTaskCreate,
    CaseTaskRead,
    CaseTaskUpdate,
    CaseUpdate,
    ExecutionRunRead,
    PipelineRunRead,
    ReportExport,
    ReportRead,
    ReviewUpdate,
    SampleCreate,
    SampleRead,
    SafetyPreflightRequest,
    SafetyPreflightResponse,
    SavedArtifact,
    StructureJobCreate,
    StructureJobRead,
    SubjectCreate,
    SubjectRead,
    UnifiedRunRead,
    VariantCreate,
    VariantRead,
)
from backend.app.safety.audit import log_action
from backend.app.safety.preflight import PreflightResult, preflight_action
from backend.app.reports import RESEARCH_LABEL, build_candidate_review_report, build_ethics_package_report
from backend.app.mock_analysis import ensure_mock_analysis_data
from backend.app.alphafold import shells as alphafold_shells
from backend.app.alphafold.shells import (
    build_alphafold_dry_run,
    execute_alphafold_backend,
    get_shell_backend_status,
    list_alphafold_shell_statuses,
)
from backend.app.alphafold.schemas import parse_alphafold_request
from backend.app.pipeline.base import run_mock_pipeline
from backend.app.pipeline.shells import build_pipeline_dry_run, execute_pipeline_adapter, list_pipeline_adapter_statuses

logger = structlog.get_logger()


def record_execution_run(
    db: Session,
    *,
    case_id: str | None,
    runner_kind: str,
    runner_name: str,
    result: dict,
) -> ExecutionRun:
    execution = ExecutionRun(
        id=str(uuid4()),
        case_id=case_id,
        runner_kind=runner_kind,
        runner_name=runner_name,
        status=result["status"],
        command={"argv": result["command"]},
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        parse_status=None,
        parse_error=None,
        timed_out=result.get("timed_out", False),
        return_code=result.get("return_code"),
    )
    db.add(execution)
    db.flush()
    return execution


def validate_alphafold_payload_or_422(backend_name: str, payload: dict) -> None:
    try:
        parse_alphafold_request(backend_name, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def extract_alphafold_structure_payload(result: dict) -> dict | None:
    try:
        parsed = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return None

    if parsed.get("structure"):
        return parsed["structure"]

    output_dir_value = parsed.get("output_dir")
    if not output_dir_value:
        return None

    output_dir = Path(output_dir_value)
    if not output_dir.exists() or not output_dir.is_dir():
        return None

    model_cif_candidates = sorted(output_dir.glob("*_model.cif"))
    summary_candidates = sorted(output_dir.glob("*_summary_confidences.json"))
    structure_payload: dict = {
        "backend": result.get("backend"),
        "status": result.get("status"),
        "output_dir": str(output_dir),
        "output_format": "mmcif",
    }
    if model_cif_candidates:
        structure_payload["model_cif"] = str(model_cif_candidates[0])
    if summary_candidates:
        structure_payload["summary_confidences_json"] = str(summary_candidates[0])
        try:
            summary_payload = json.loads(summary_candidates[0].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary_payload = {}
        for key in ("ptm", "iptm", "ranking_score", "chain_pair_iptm"):
            if key in summary_payload:
                structure_payload[key] = summary_payload[key]
    return structure_payload if len(structure_payload) > 4 else None


def apply_parsed_pipeline_output(
    db: Session,
    *,
    case_id: str | None,
    adapter_name: str,
    result: dict,
    execution_id: str | None = None,
) -> tuple[str, str | None]:
    if not case_id or result.get("status") != "completed":
        reason = f"parse skipped because case_id={case_id!r} and status={result.get('status')!r}"
        logger.info("pipeline_output_parse_skipped", adapter_name=adapter_name, execution_id=execution_id, reason=reason)
        return "skipped_not_completed", reason

    case = db.get(Case, case_id)
    if case is None:
        reason = f"parse skipped because case {case_id} was not found"
        logger.warning(
            "pipeline_output_parse_skipped_missing_case",
            adapter_name=adapter_name,
            execution_id=execution_id,
            case_id=case_id,
        )
        return "skipped_missing_case", reason

    try:
        parsed = json.loads(result.get("stdout") or "{}")
    except json.JSONDecodeError:
        reason = f"invalid JSON output for {adapter_name}"
        logger.warning("pipeline_output_parse_failed_json", adapter_name=adapter_name, execution_id=execution_id)
        return "parse_failed", reason

    variants, candidates = ensure_mock_analysis_data(db, case)

    if adapter_name == "vep" and parsed.get("variant") and variants:
        variant_payload = parsed["variant"]
        variant = variants[0]
        variant.gene = variant_payload.get("gene", variant.gene)
        variant.protein_change = variant_payload.get("protein_change", variant.protein_change)
        variant.genomic_coordinates = variant_payload.get("genomic_coordinates", variant.genomic_coordinates)
        variant.annotation_source = variant_payload.get("annotation_source", variant.annotation_source)
        variant.last_parsed_execution_id = execution_id
        metrics = dict(variant.quality_metrics or {})
        metrics["parsed_from"] = "vep_shell"
        variant.quality_metrics = metrics
        return "parsed_ok", None

    if adapter_name == "pvactools" and parsed.get("candidate") and candidates:
        candidate_payload = parsed["candidate"]
        candidate = candidates[0]
        candidate.last_parsed_execution_id = execution_id
        candidate.mhc_context = candidate_payload.get("mhc_context", candidate.mhc_context)
        peptide_metadata = dict(candidate.peptide_metadata or {})
        peptide_metadata["sequence"] = candidate_payload.get("peptide_sequence", peptide_metadata.get("sequence"))
        candidate.peptide_metadata = peptide_metadata
        prediction_scores = dict(candidate.prediction_scores or {})
        if "binding_rank" in candidate_payload:
            prediction_scores["binding_rank"] = candidate_payload["binding_rank"]
        if "immunogenicity" in candidate_payload:
            prediction_scores["immunogenicity"] = candidate_payload["immunogenicity"]
        prediction_scores["parsed_from"] = "pvactools_shell"
        candidate.prediction_scores = prediction_scores
        return "parsed_ok", None

    expected_key = "candidate" if adapter_name == "pvactools" else "variant"
    reason = f"missing expected parsed payload key '{expected_key}' for {adapter_name}"
    logger.warning(
        "pipeline_output_parse_failed_payload",
        adapter_name=adapter_name,
        execution_id=execution_id,
        expected_key=expected_key,
    )
    return "parse_failed", reason


def apply_parsed_alphafold_output(
    db: Session,
    *,
    case_id: str | None,
    result: dict,
    execution_id: str | None = None,
) -> tuple[str, str | None]:
    if not case_id or result.get("status") != "completed":
        reason = f"parse skipped because case_id={case_id!r} and status={result.get('status')!r}"
        logger.info("alphafold_output_parse_skipped", execution_id=execution_id, reason=reason)
        return "skipped_not_completed", reason

    case = db.get(Case, case_id)
    if case is None:
        reason = f"parse skipped because case {case_id} was not found"
        logger.warning("alphafold_output_parse_skipped_missing_case", execution_id=execution_id, case_id=case_id)
        return "skipped_missing_case", reason

    try:
        structure_payload = extract_alphafold_structure_payload(result)
    except OSError as exc:
        reason = f"failed to inspect alphafold output directory: {exc}"
        logger.warning("alphafold_output_parse_failed_filesystem", execution_id=execution_id)
        return "parse_failed", reason

    _, candidates = ensure_mock_analysis_data(db, case)
    if not candidates or not structure_payload:
        reason = "missing expected parsed payload key 'structure' for alphafold backend"
        logger.warning("alphafold_output_parse_failed_payload", execution_id=execution_id, has_candidates=bool(candidates))
        return "parse_failed", reason

    candidate = candidates[0]
    candidate.last_parsed_execution_id = execution_id
    structure_evidence = dict(candidate.structure_evidence or {})
    structure_evidence["alphafold_status"] = structure_payload.get("status", structure_evidence.get("alphafold_status"))
    structure_evidence["backend"] = structure_payload.get("backend", structure_evidence.get("backend"))
    for key in (
        "pdb_file",
        "model_cif",
        "summary_confidences_json",
        "source_url",
        "output_format",
        "accession",
        "pLDDT_mean",
        "pAE_mean",
        "ranking_score",
        "ptm",
        "iptm",
        "chain_pair_iptm",
    ):
        if key in structure_payload:
            structure_evidence[key] = structure_payload[key]
    candidate.structure_evidence = structure_evidence
    return "parsed_ok", None


REPORT_EXPORT_FORMATS = {"markdown", "json"}


def enforce_preflight_or_raise(
    *,
    action: str,
    species_mode: str,
    is_export: bool = False,
    involves_external_upload: bool = False,
    involves_sequence_data: bool = False,
) -> None:
    result = preflight_action(
        action=action,
        species_mode=species_mode,
        is_export=is_export,
        involves_external_upload=involves_external_upload,
        involves_sequence_data=involves_sequence_data,
    )
    if result.status != PreflightResult.PASS:
        raise HTTPException(status_code=403, detail=result.reason or "Safety preflight blocked the action")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FoldAgent",
    description="Local-first, safety-gated research coordination platform for personalized cancer-vaccine exploration under licensed professional supervision.",
    version="0.1.0-alpha",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8502", "http://127.0.0.1:8502", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0-alpha", "mode": settings.species_mode.value}


@app.get("/version")
async def version() -> dict[str, str | bool]:
    return {
        "version": "0.1.0-alpha",
        "mode": settings.species_mode.value,
        "pipeline_mode": settings.pipeline_mode,
        "alphafold_backend": settings.alphafold_default_backend.value,
        "safety_preflight": settings.safety_preflight_enabled,
    }


@app.get("/pipeline/adapters")
def list_pipeline_adapters() -> dict[str, dict]:
    return list_pipeline_adapter_statuses()


@app.post("/pipeline/adapters/{adapter_name}/dry-run")
def pipeline_adapter_dry_run(adapter_name: str, payload: dict) -> dict:
    try:
        return build_pipeline_dry_run(adapter_name, payload).__dict__
    except KeyError:
        raise HTTPException(status_code=404, detail="Pipeline adapter not found") from None


@app.post("/pipeline/adapters/{adapter_name}/run")
def pipeline_adapter_run(adapter_name: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    case_id = payload.get("case_id")
    if case_id:
        case = db.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        enforce_preflight_or_raise(action="pipeline_adapter_run", species_mode=case.species.value)
    try:
        result = execute_pipeline_adapter(adapter_name, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Pipeline adapter not found") from None

    case_id = payload.get("case_id")
    execution = record_execution_run(
        db,
        case_id=case_id,
        runner_kind="pipeline_adapter",
        runner_name=adapter_name,
        result=result.__dict__,
    )
    execution.parse_status, execution.parse_error = apply_parsed_pipeline_output(
        db,
        case_id=case_id,
        adapter_name=adapter_name,
        result=result.__dict__,
        execution_id=execution.id,
    )
    shell_artifacts = persist_execution_artifacts(db=db, result=result.__dict__, execution_id=execution.id, case_id=case_id)
    execution.command = {"argv": result.__dict__["command"], "artifact_paths": [artifact.path for artifact in shell_artifacts]}
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.adapter.run",
        inputs={"adapter": adapter_name, **payload},
        outputs={"status": result.status, "return_code": result.return_code, "execution_id": execution.id, "artifact_count": len(shell_artifacts)},
    )
    db.commit()
    return result.__dict__


@app.get("/alphafold/backends")
def list_alphafold_backends() -> dict[str, dict]:
    return list_alphafold_shell_statuses()


@app.post("/alphafold/backends/{backend_name}/dry-run")
def alphafold_backend_dry_run(backend_name: str, payload: dict) -> dict:
    validate_alphafold_payload_or_422(backend_name, payload)
    try:
        return build_alphafold_dry_run(backend_name, payload).__dict__
    except KeyError:
        raise HTTPException(status_code=404, detail="AlphaFold backend not found") from None


@app.post(
    "/alphafold/backends/{backend_name}/run",
    summary="Run AlphaFold backend",
    description=(
        "Run one of FoldAgent's AlphaFold-family backends with backend-specific payload validation. "
        "Examples include ColabFold/local_colabfold sequence runs, alphafold3_local JSON runs, "
        "alphafold_server remote submissions with external-upload acknowledgement, and alphafold_db accession lookups."
    ),
    responses={
        409: {
            "model": AlphaFoldValidationErrorResponse,
            "description": "Backend environment validation failed before execution.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "AlphaFold backend 'colabfold' failed environment validation: Command 'colabfold_batch' not found on PATH.",
                        "backend_name": "colabfold",
                        "validation_ok": False,
                        "validation_reason": "Command 'colabfold_batch' not found on PATH.",
                    }
                }
            },
        }
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "case_id": "demo-case",
                        "candidate_id": "candidate-123",
                        "job_name": "af3-rich",
                        "input_kind": "json",
                        "json_path": "/tmp/af3.json",
                    }
                }
            }
        }
    },
)
def alphafold_backend_run(backend_name: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    validate_alphafold_payload_or_422(backend_name, payload)
    case_id = payload.get("case_id")
    case = db.get(Case, case_id) if case_id else None
    if case is not None:
        involves_external_upload = backend_name == "alphafold_server" and not payload.get("acknowledge_external_upload", False)
        enforce_preflight_or_raise(
            action="alphafold_backend_run",
            species_mode=case.species.value,
            involves_external_upload=involves_external_upload,
        )
    try:
        backend_status = get_shell_backend_status(backend_name)
        if (
            execute_alphafold_backend is alphafold_shells.execute_alphafold_backend
            and not backend_status.validation_ok
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        f"AlphaFold backend '{backend_name}' failed environment validation: "
                        f"{backend_status.validation_reason}"
                    ),
                    "backend_name": backend_name,
                    "validation_ok": False,
                    "validation_reason": backend_status.validation_reason,
                },
            )
        result = execute_alphafold_backend(backend_name, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="AlphaFold backend not found") from None

    case_id = payload.get("case_id")
    execution = record_execution_run(
        db,
        case_id=case_id,
        runner_kind="alphafold_backend",
        runner_name=backend_name,
        result=result.__dict__,
    )
    execution.parse_status, execution.parse_error = apply_parsed_alphafold_output(
        db,
        case_id=case_id,
        result=result.__dict__,
        execution_id=execution.id,
    )
    if case_id and payload.get("candidate_id"):
        candidate = db.get(CandidateAntigen, payload["candidate_id"])
        if candidate is not None and candidate.case_id == case_id:
            structure_payload = json.loads(result.stdout).get("structure", {}) if result.stdout else {}
            output_path = structure_payload.get("model_cif") or structure_payload.get("pdb_file")
            confidence_metrics = {
                key: structure_payload[key]
                for key in (
                    "pLDDT_mean",
                    "pAE_mean",
                    "ranking_score",
                    "ptm",
                    "iptm",
                    "chain_pair_iptm",
                    "source_url",
                    "summary_confidences_json",
                    "output_format",
                    "accession",
                )
                if key in structure_payload
            }
            structure_job = StructureJob(
                id=str(uuid4()),
                case_id=case_id,
                candidate_id=candidate.id,
                backend_used=backend_name,
                output_path=output_path,
                confidence_metrics=confidence_metrics,
                status=result.status,
            )
            db.add(structure_job)
            db.flush()
    shell_artifacts = persist_execution_artifacts(db=db, result=result.__dict__, execution_id=execution.id, case_id=case_id)
    execution.command = {"argv": result.__dict__["command"], "artifact_paths": [artifact.path for artifact in shell_artifacts]}
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="alphafold.backend.run",
        inputs={"backend": backend_name, **payload},
        outputs={"status": result.status, "return_code": result.return_code, "execution_id": execution.id, "artifact_count": len(shell_artifacts)},
    )
    db.commit()
    return result.__dict__


@app.get("/cases/{case_id}/executions", response_model=list[ExecutionRunRead])
def list_execution_history(case_id: str, db: Session = Depends(get_db)) -> list[ExecutionRunRead]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    artifact_records = (
        db.query(Artifact)
        .filter(Artifact.case_id == case_id, Artifact.execution_run_id.is_not(None))
        .order_by(Artifact.saved_at.desc())
        .all()
    )
    artifact_map: dict[str, list[SavedArtifact]] = {}
    for record in artifact_records:
        artifact_map.setdefault(record.execution_run_id, []).append(build_saved_artifact_record(record=record))

    executions = (
        db.query(ExecutionRun)
        .filter(ExecutionRun.case_id == case_id)
        .order_by(ExecutionRun.created_at.desc())
        .all()
    )
    payloads = []
    for execution in executions:
        item = ExecutionRunRead.model_validate(execution).model_dump()
        item["artifacts"] = [artifact.model_dump(mode="json") for artifact in artifact_map.get(execution.id, [])]
        payloads.append(ExecutionRunRead.model_validate(item))
    return payloads


@app.get("/cases/{case_id}/runs", response_model=list[UnifiedRunRead])
def list_unified_runs(case_id: str, db: Session = Depends(get_db)) -> list[UnifiedRunRead]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    pipeline_runs = db.query(PipelineRun).filter(PipelineRun.case_id == case_id).all()
    execution_runs = db.query(ExecutionRun).filter(ExecutionRun.case_id == case_id).all()
    reports = db.query(Report).filter(Report.case_id == case_id).all()
    artifact_records = (
        db.query(Artifact)
        .filter(Artifact.case_id == case_id, Artifact.execution_run_id.is_not(None))
        .order_by(Artifact.saved_at.desc())
        .all()
    )
    artifact_map: dict[str, list[SavedArtifact]] = {}
    for record in artifact_records:
        artifact_map.setdefault(record.execution_run_id, []).append(build_saved_artifact_record(record=record))

    runs: list[UnifiedRunRead] = []
    for run in pipeline_runs:
        runs.append(UnifiedRunRead(
            id=run.id,
            case_id=case_id,
            run_kind="pipeline_run",
            name=run.current_step or "pipeline",
            status=run.status.value if hasattr(run.status, 'value') else str(run.status),
            created_at=run.started_at,
            details={"completed_steps": run.completed_steps, "total_steps": run.total_steps},
        ))
    for run in execution_runs:
        runs.append(UnifiedRunRead(
            id=run.id,
            case_id=case_id,
            run_kind="execution_run",
            name=run.runner_name,
            status=run.status,
            created_at=run.created_at,
            details={"runner_kind": run.runner_kind, "return_code": run.return_code},
            artifacts=artifact_map.get(run.id, []),
        ))
    agent_tasks = db.query(AgentTask).filter(AgentTask.case_id == case_id).all()
    for task in agent_tasks:
        runs.append(UnifiedRunRead(
            id=task.id,
            case_id=case_id,
            run_kind="agent_task",
            name=task.skill_name,
            status=task.status,
            created_at=task.created_at,
            details={"framework": task.framework.value if hasattr(task.framework, 'value') else str(task.framework), "logs": task.logs, "artifacts": task.artifacts},
        ))
    for report in reports:
        runs.append(UnifiedRunRead(
            id=report.id,
            case_id=case_id,
            run_kind="report",
            name=report.report_type,
            status="generated",
            created_at=report.generated_at,
            details={"generated_by": report.generated_by},
        ))

    runs.sort(key=lambda item: item.created_at, reverse=True)
    return runs


@app.post("/cases/{case_id}/tasks", response_model=CaseTaskRead, status_code=201)
def create_case_task(case_id: str, payload: CaseTaskCreate, db: Session = Depends(get_db)) -> CaseTask:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    task = CaseTask(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(task)
    db.flush()
    log_action(db, case_id=case_id, actor="api", action="task.created", inputs=payload.model_dump(mode="json"), outputs={"task_id": task.id})
    db.commit()
    db.refresh(task)
    return task


@app.get("/cases/{case_id}/tasks", response_model=list[CaseTaskRead])
def list_case_tasks(case_id: str, db: Session = Depends(get_db)) -> list[CaseTask]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(CaseTask).filter(CaseTask.case_id == case_id).order_by(CaseTask.created_at.desc()).all()


@app.patch("/tasks/{task_id}", response_model=CaseTaskRead)
def update_case_task(task_id: str, payload: CaseTaskUpdate, db: Session = Depends(get_db)) -> CaseTask:
    task = db.get(CaseTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    updates = payload.model_dump(exclude_unset=True, mode="python")
    for field, value in updates.items():
        setattr(task, field, value)
    log_action(db, case_id=task.case_id, actor="api", action="task.updated", inputs=updates, outputs={"task_id": task.id})
    db.commit()
    db.refresh(task)
    return task


@app.post("/cases/{case_id}/agent-tasks", response_model=AgentTaskRead, status_code=201)
def create_agent_task(case_id: str, payload: AgentTaskCreate, db: Session = Depends(get_db)) -> AgentTask:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    task = AgentTask(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(task)
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="agent_task.created",
        inputs=payload.model_dump(mode="json"),
        outputs={"agent_task_id": task.id},
    )
    db.commit()
    db.refresh(task)
    return task


@app.get("/cases/{case_id}/agent-tasks", response_model=list[AgentTaskRead])
def list_agent_tasks(case_id: str, db: Session = Depends(get_db)) -> list[AgentTask]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(AgentTask).filter(AgentTask.case_id == case_id).order_by(AgentTask.created_at.desc()).all()


@app.get("/agent-tasks/{task_id}", response_model=AgentTaskRead)
def get_agent_task(task_id: str, db: Session = Depends(get_db)) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    return task


@app.patch("/agent-tasks/{task_id}", response_model=AgentTaskRead)
def update_agent_task(task_id: str, payload: AgentTaskUpdate, db: Session = Depends(get_db)) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    updates = payload.model_dump(exclude_unset=True, mode="python")
    for field, value in updates.items():
        setattr(task, field, value)
    log_action(
        db,
        case_id=task.case_id,
        actor="api",
        action="agent_task.updated",
        inputs=updates,
        outputs={"agent_task_id": task.id},
    )
    db.commit()
    db.refresh(task)
    return task


@app.post("/cases", response_model=CaseRead, status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> Case:
    case = Case(
        id=str(uuid4()),
        species=payload.species,
        diagnosis_summary=payload.diagnosis_summary,
        supervising_professional=payload.supervising_professional,
    )
    db.add(case)
    db.flush()
    log_action(
        db,
        case_id=case.id,
        actor="api",
        action="case.created",
        inputs=payload.model_dump(mode="json"),
        outputs={"case_id": case.id},
    )
    db.commit()
    db.refresh(case)
    return case


@app.post("/cases/{case_id}/subjects", response_model=SubjectRead, status_code=201)
def create_subject(case_id: str, payload: SubjectCreate, db: Session = Depends(get_db)) -> Subject:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    subject = Subject(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(subject)
    db.flush()
    log_action(db, case_id=case_id, actor="api", action="subject.created", inputs=payload.model_dump(mode="json"), outputs={"subject_id": subject.id})
    db.commit()
    db.refresh(subject)
    return subject


@app.get("/cases/{case_id}/subjects", response_model=list[SubjectRead])
def list_subjects(case_id: str, db: Session = Depends(get_db)) -> list[Subject]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(Subject).filter(Subject.case_id == case_id).order_by(Subject.created_at.desc()).all()


@app.get("/cases", response_model=list[CaseRead])
def list_cases(db: Session = Depends(get_db)) -> list[Case]:
    return db.query(Case).order_by(Case.created_at.desc()).all()


@app.get("/cases/{case_id}", response_model=CaseRead)
def get_case(case_id: str, db: Session = Depends(get_db)) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.patch("/cases/{case_id}", response_model=CaseRead)
def update_case(case_id: str, payload: CaseUpdate, db: Session = Depends(get_db)) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    changes = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(case, field, value)

    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="case.updated",
        inputs=changes,
        outputs={"case_id": case_id},
    )
    db.commit()
    db.refresh(case)
    return case


@app.post("/cases/{case_id}/samples", response_model=SampleRead, status_code=201)
def register_sample(case_id: str, payload: SampleCreate, db: Session = Depends(get_db)) -> Sample:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if payload.subject_id is not None:
        subject = db.get(Subject, payload.subject_id)
        if subject is None or subject.case_id != case_id:
            raise HTTPException(status_code=404, detail="Subject not found")

    sample = Sample(
        id=str(uuid4()),
        case_id=case_id,
        sample_type=payload.sample_type,
        subject_id=payload.subject_id,
        file_paths=payload.file_paths,
        checksum=payload.checksum,
        source_lab=payload.source_lab,
        custody_metadata=payload.custody_metadata,
    )
    db.add(sample)
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="sample.registered",
        inputs=payload.model_dump(mode="json"),
        outputs={"sample_id": sample.id},
    )
    db.commit()
    db.refresh(sample)
    return sample


@app.get("/cases/{case_id}/samples", response_model=list[SampleRead])
def list_samples(case_id: str, db: Session = Depends(get_db)) -> list[Sample]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return db.query(Sample).filter(Sample.case_id == case_id).order_by(Sample.created_at.desc()).all()


@app.get("/cases/{case_id}/variants", response_model=list[VariantRead])
def list_variants(case_id: str, db: Session = Depends(get_db)) -> list[Variant]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    variants = db.query(Variant).filter(Variant.case_id == case_id).order_by(Variant.created_at.asc()).all()
    if variants:
        return variants
    variants, _ = ensure_mock_analysis_data(db, case)
    db.commit()
    return variants


@app.post("/cases/{case_id}/variants", response_model=VariantRead, status_code=201)
def create_variant(case_id: str, payload: VariantCreate, db: Session = Depends(get_db)) -> Variant:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if payload.sample_id is not None:
        sample = db.get(Sample, payload.sample_id)
        if sample is None or sample.case_id != case_id:
            raise HTTPException(status_code=404, detail="Sample not found")

    variant = Variant(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(variant)
    db.flush()
    log_action(db, case_id=case_id, actor="api", action="variant.created", inputs=payload.model_dump(mode="json"), outputs={"variant_id": variant.id})
    db.commit()
    db.refresh(variant)
    return variant


@app.get("/cases/{case_id}/candidates", response_model=list[CandidateRead])
def list_candidates(case_id: str, db: Session = Depends(get_db)) -> list[CandidateAntigen]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    _, candidates = ensure_mock_analysis_data(db, case)
    db.commit()
    return candidates


@app.post("/cases/{case_id}/candidates", response_model=CandidateRead, status_code=201)
def create_candidate(case_id: str, payload: CandidateCreate, db: Session = Depends(get_db)) -> CandidateAntigen:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    variant = db.get(Variant, payload.variant_id)
    if variant is None or variant.case_id != case_id:
        raise HTTPException(status_code=404, detail="Variant not found")

    candidate = CandidateAntigen(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(candidate)
    db.flush()
    log_action(db, case_id=case_id, actor="api", action="candidate.created", inputs=payload.model_dump(mode="json"), outputs={"candidate_id": candidate.id})
    db.commit()
    db.refresh(candidate)
    return candidate


@app.patch("/variants/{variant_id}/review", response_model=VariantRead)
def review_variant(variant_id: str, payload: ReviewUpdate, db: Session = Depends(get_db)) -> Variant:
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found")

    variant.review_status = payload.review_status
    variant.expert_review_notes = payload.expert_review_notes
    log_action(
        db,
        case_id=variant.case_id,
        actor="api",
        action="variant.reviewed",
        inputs=payload.model_dump(mode="json"),
        outputs={"variant_id": variant.id},
    )
    db.commit()
    db.refresh(variant)
    return variant


@app.patch("/candidates/{candidate_id}/review", response_model=CandidateRead)
def review_candidate(candidate_id: str, payload: ReviewUpdate, db: Session = Depends(get_db)) -> CandidateAntigen:
    candidate = db.get(CandidateAntigen, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.review_status = payload.review_status
    candidate.expert_review_notes = payload.expert_review_notes
    log_action(
        db,
        case_id=candidate.case_id,
        actor="api",
        action="candidate.reviewed",
        inputs=payload.model_dump(mode="json"),
        outputs={"candidate_id": candidate.id},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


@app.post("/cases/{case_id}/structure-jobs", response_model=StructureJobRead, status_code=201)
def create_structure_job(case_id: str, payload: StructureJobCreate, db: Session = Depends(get_db)) -> StructureJob:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    candidate = db.get(CandidateAntigen, payload.candidate_id)
    if candidate is None or candidate.case_id != case_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job = StructureJob(id=str(uuid4()), case_id=case_id, **payload.model_dump(mode="python"))
    db.add(job)
    db.flush()
    log_action(db, case_id=case_id, actor="api", action="structure_job.created", inputs=payload.model_dump(mode="json"), outputs={"structure_job_id": job.id})
    db.commit()
    db.refresh(job)
    return job


@app.get("/cases/{case_id}/structure-jobs", response_model=list[StructureJobRead])
def list_structure_jobs(case_id: str, db: Session = Depends(get_db)) -> list[StructureJob]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(StructureJob).filter(StructureJob.case_id == case_id).order_by(StructureJob.created_at.desc()).all()


@app.get("/structure-jobs/{job_id}", response_model=StructureJobRead)
def get_structure_job(job_id: str, db: Session = Depends(get_db)) -> StructureJob:
    job = db.get(StructureJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Structure job not found")
    return job


@app.get("/samples/{sample_id}/checksum")
def get_sample_checksum(sample_id: str, db: Session = Depends(get_db)) -> dict[str, str | None]:
    sample = db.get(Sample, sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"sample_id": sample.id, "checksum": sample.checksum}


@app.post("/cases/{case_id}/pipeline/run", response_model=PipelineRunRead, status_code=201)
def run_pipeline(case_id: str, db: Session = Depends(get_db)) -> PipelineRunRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="run_pipeline", species_mode=case.species.value)

    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.started",
        inputs={"case_id": case_id, "mode": settings.pipeline_mode},
        outputs={"status": "running"},
    )
    step_results = asyncio.run(run_mock_pipeline(case_id))
    serialized_steps = [
        {
            "step_name": result.step_name,
            "step_version": result.step_version,
            "status": result.status.value,
            "outputs": result.outputs,
            "warnings": result.warnings,
            "errors": result.errors,
            "safety_label": result.safety_label,
            "requires_professional_review": result.requires_professional_review,
        }
        for result in step_results
    ]
    pipeline_run = PipelineRun(
        id=str(uuid4()),
        case_id=case_id,
        status="completed",
        current_step=serialized_steps[-1]["step_name"] if serialized_steps else None,
        completed_steps=len(serialized_steps),
        total_steps=len(serialized_steps),
        step_results={"steps": serialized_steps},
        finished_at=datetime.now(UTC),
    )
    db.add(pipeline_run)
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.completed",
        inputs={"case_id": case_id},
        outputs={"pipeline_run_id": pipeline_run.id, "status": pipeline_run.status},
    )
    db.commit()
    db.refresh(pipeline_run)
    return serialize_pipeline_run(pipeline_run)


@app.get("/cases/{case_id}/pipeline/status", response_model=PipelineRunRead)
def get_pipeline_status(case_id: str, db: Session = Depends(get_db)) -> PipelineRunRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    pipeline_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.case_id == case_id)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
    if pipeline_run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return serialize_pipeline_run(pipeline_run)


@app.get("/cases/{case_id}/pipeline/history", response_model=list[PipelineRunRead])
def get_pipeline_history(case_id: str, db: Session = Depends(get_db)) -> list[PipelineRunRead]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    pipeline_runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.case_id == case_id)
        .order_by(PipelineRun.started_at.desc())
        .all()
    )
    return [serialize_pipeline_run(run) for run in pipeline_runs]


def serialize_report(report: Report, content_text: str | None = None) -> ReportRead:
    payload = ReportRead.model_validate(report).model_dump()
    if content_text is None and report.content_json:
        content_text = report.content_json.get("content_text")
    payload["content_text"] = content_text
    return ReportRead.model_validate(payload)


def serialize_pipeline_run(pipeline_run: PipelineRun) -> PipelineRunRead:
    payload = PipelineRunRead.model_validate(pipeline_run).model_dump(exclude={"steps"})
    step_results = pipeline_run.step_results or {}
    payload["steps"] = step_results.get("steps", [])
    return PipelineRunRead.model_validate(payload)


def build_case_bundle(case_id: str, db: Session) -> CaseBundleRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    samples = db.query(Sample).filter(Sample.case_id == case_id).order_by(Sample.created_at.desc()).all()
    subjects = db.query(Subject).filter(Subject.case_id == case_id).order_by(Subject.created_at.desc()).all()
    variants = db.query(Variant).filter(Variant.case_id == case_id).order_by(Variant.created_at.desc()).all()
    candidates = (
        db.query(CandidateAntigen)
        .filter(CandidateAntigen.case_id == case_id)
        .order_by(CandidateAntigen.created_at.desc())
        .all()
    )
    tasks = db.query(CaseTask).filter(CaseTask.case_id == case_id).order_by(CaseTask.created_at.desc()).all()
    agent_tasks = db.query(AgentTask).filter(AgentTask.case_id == case_id).order_by(AgentTask.created_at.desc()).all()
    reports = db.query(Report).filter(Report.case_id == case_id).order_by(Report.generated_at.desc()).all()
    latest_pipeline_run = (
        db.query(PipelineRun)
        .filter(PipelineRun.case_id == case_id)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
    audit_log = db.query(AuditLog).filter(AuditLog.case_id == case_id).order_by(AuditLog.timestamp.desc()).all()

    return CaseBundleRead(
        case=CaseRead.model_validate(case),
        subjects=[SubjectRead.model_validate(subject) for subject in subjects],
        samples=[SampleRead.model_validate(sample) for sample in samples],
        variants=[VariantRead.model_validate(variant) for variant in variants],
        candidates=[CandidateRead.model_validate(candidate) for candidate in candidates],
        tasks=[CaseTaskRead.model_validate(task) for task in tasks],
        agent_tasks=[AgentTaskRead.model_validate(task) for task in agent_tasks],
        reports=[serialize_report(report) for report in reports],
        latest_pipeline_run=serialize_pipeline_run(latest_pipeline_run) if latest_pipeline_run else None,
        audit_log=[AuditLogRead.model_validate(entry) for entry in audit_log],
        safety_label=RESEARCH_LABEL,
    )


def export_report_payload(report: Report, export_format: str) -> ReportExport:
    if export_format not in REPORT_EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="Unsupported report export format")

    if export_format == "json":
        return ReportExport(
            report_id=report.id,
            format="json",
            content_json=report.content_json or {},
            safety_label=report.safety_label,
        )

    content_text = None
    if report.content_json:
        content_text = report.content_json.get("content_text")
    markdown_sections = [
        f"# {report.report_type.replace('_', ' ').title()}",
        f"Case ID: {report.case_id}",
        f"Safety label: {report.safety_label}",
        content_text or "No report body available.",
    ]
    content_json = report.content_json or {}
    if report.report_type == "candidate_review":
        candidate_rows = content_json.get("candidate_table") or []
        candidate_lines = [
            f"- {row.get('gene') or 'unknown'} | {row.get('protein_change') or 'n/a'} | bind={row.get('binding_rank')} | immunogenicity={row.get('immunogenicity')} | mhc={row.get('mhc_context') or 'n/a'}"
            for row in candidate_rows
        ] or ["- none"]
        checklist_lines = [f"- [ ] {item}" for item in (content_json.get("missing_data_checklist") or [])] or ["- [ ] none"]
        tool_lines = [f"- {name}: {version}" for name, version in (content_json.get("tool_versions") or {}).items()] or ["- none"]
        safety_lines = [f"- {item}" for item in (content_json.get("safety_labels") or [])] or ["- none"]
        markdown_sections.extend(
            [
                "## Candidate antigens",
                "\n".join(candidate_lines),
                "## Structure evidence",
                f"Backend: {content_json.get('structure_backend') or 'n/a'}",
                f"Status: {content_json.get('structure_status') or 'n/a'}",
                f"Ranking score: {content_json.get('ranking_score') if content_json.get('ranking_score') is not None else 'n/a'}",
                f"pTM: {content_json.get('ptm') if content_json.get('ptm') is not None else 'n/a'}",
                f"ipTM: {content_json.get('iptm') if content_json.get('iptm') is not None else 'n/a'}",
                f"Model CIF: {content_json.get('model_cif') or 'n/a'}",
                f"Source URL: {content_json.get('source_url') or 'n/a'}",
                f"Output format: {content_json.get('output_format') or 'n/a'}",
                "## Missing data checklist",
                "\n".join(checklist_lines),
                "## Tool versions",
                "\n".join(tool_lines),
                "## Safety labels",
                "\n".join(safety_lines),
                "## Review status",
                str(content_json.get("review_status") or "n/a"),
            ]
        )
    elif report.report_type == "ethics_package":
        consent_lines = [f"- {name}: {value}" for name, value in (content_json.get("consent_templates") or {}).items()] or ["- none"]
        privacy_lines = [f"- {item}" for item in (content_json.get("privacy_notices") or [])] or ["- none"]
        risk_lines = [f"- risk: {item}" for item in ((content_json.get("risk_benefit_summary") or {}).get("risks") or [])]
        benefit_lines = [f"- benefit: {item}" for item in ((content_json.get("risk_benefit_summary") or {}).get("benefits") or [])]
        oversight_lines = [f"- [ ] {item}" for item in (content_json.get("professional_oversight_checklist") or [])] or ["- [ ] none"]
        markdown_sections.extend(
            [
                "## Consent templates",
                "\n".join(consent_lines),
                "## Privacy notices",
                "\n".join(privacy_lines),
                "## Risk and benefit summary",
                "\n".join(risk_lines + benefit_lines) or "- none",
                "## Professional oversight checklist",
                "\n".join(oversight_lines),
                "## Jurisdiction warning",
                str(content_json.get("jurisdiction_warning") or "n/a"),
            ]
        )
    markdown = "\n\n".join(markdown_sections)
    return ReportExport(
        report_id=report.id,
        format="markdown",
        content_text=markdown,
        safety_label=report.safety_label,
    )


def export_case_bundle_payload(bundle: CaseBundleRead, export_format: str) -> CaseBundleExport:
    if export_format not in REPORT_EXPORT_FORMATS:
        raise HTTPException(status_code=422, detail="Unsupported case bundle export format")

    if export_format == "json":
        return CaseBundleExport(
            case_id=bundle.case.id,
            format="json",
            content_json=bundle.model_dump(mode="json"),
            safety_label=bundle.safety_label,
        )

    latest_pipeline = bundle.latest_pipeline_run
    top_candidate_gene = None
    if bundle.candidates:
        top_candidate = bundle.candidates[0]
        top_candidate_gene = next(
            (variant.gene for variant in bundle.variants if variant.id == top_candidate.variant_id),
            None,
        )
    latest_report_types = ", ".join(report.report_type for report in bundle.reports[:3]) or "none"
    variant_statuses = ", ".join(sorted({variant.review_status for variant in bundle.variants})) or "none"
    candidate_statuses = ", ".join(sorted({candidate.review_status for candidate in bundle.candidates})) or "none"
    agent_frameworks = ", ".join(sorted({task.framework.value if hasattr(task.framework, 'value') else str(task.framework) for task in bundle.agent_tasks})) or "none"
    markdown = "\n\n".join(
        [
            f"# Case Bundle: {bundle.case.id}",
            f"Safety label: {bundle.safety_label}",
            f"Species: {bundle.case.species}",
            f"Diagnosis summary: {bundle.case.diagnosis_summary or 'not provided'}",
            f"Samples: {len(bundle.samples)}",
            f"Variants: {len(bundle.variants)}",
            f"Candidates: {len(bundle.candidates)}",
            f"Tasks: {len(bundle.tasks)}",
            f"Agent tasks: {len(bundle.agent_tasks)} ({agent_frameworks})",
            f"Top candidate gene: {top_candidate_gene or 'not available'}",
            f"Latest report types: {latest_report_types}",
            f"Latest review statuses: variants={variant_statuses}; candidates={candidate_statuses}",
            f"Audit entries: {len(bundle.audit_log)}",
            (
                f"Latest pipeline: {latest_pipeline.status} "
                f"({latest_pipeline.completed_steps}/{latest_pipeline.total_steps} steps)"
                if latest_pipeline
                else "Latest pipeline: none"
            ),
        ]
    )
    return CaseBundleExport(
        case_id=bundle.case.id,
        format="markdown",
        content_text=markdown,
        safety_label=bundle.safety_label,
    )


def persist_artifact(*, artifact_type: str, identifier: str, export_format: str, content_text: str | None = None, content_json: dict | None = None) -> tuple[str, str]:
    """Persist artifact to disk and return (path, sha256_hex)."""
    artifact_dir = Path(settings.artifact_root).expanduser() / artifact_type
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".md" if export_format == "markdown" else ".json"
    path = artifact_dir / f"{identifier}{suffix}"
    if export_format == "markdown":
        raw = (content_text or "").encode("utf-8")
        path.write_bytes(raw)
    else:
        raw = json.dumps(content_json or {}, indent=2, sort_keys=True).encode("utf-8")
        path.write_bytes(raw)
    sha256_hex = hashlib.sha256(raw).hexdigest()
    return str(path.resolve()), sha256_hex


def build_saved_artifact_record(*, record: Artifact) -> SavedArtifact:
    return SavedArtifact(
        id=record.id,
        path=record.path,
        filename=record.filename,
        download_url=f"/artifacts/file?path={record.path}",
        format=record.format,
        mime_type=record.mime_type,
        file_size=record.file_size,
        content_hash=record.content_hash,
        saved_at=record.saved_at,
        artifact_type=record.artifact_type,
        case_id=record.case_id,
        report_id=record.report_id,
    )


def register_artifact_record(
    db: Session,
    *,
    case_id: str | None,
    artifact_type: str,
    path: str,
    export_format: str,
    content_hash: str | None = None,
    execution_run_id: str | None = None,
    report_id: str | None = None,
) -> SavedArtifact:
    file_path = Path(path)
    if export_format == "markdown":
        mime_type = "text/markdown; charset=utf-8"
    elif export_format == "json":
        mime_type = "application/json"
    else:
        mime_type = "application/octet-stream"
    record = Artifact(
        id=str(uuid4()),
        case_id=case_id,
        execution_run_id=execution_run_id,
        report_id=report_id,
        artifact_type=artifact_type,
        path=str(file_path.resolve()),
        filename=file_path.name,
        format=export_format,
        mime_type=mime_type,
        file_size=file_path.stat().st_size,
        content_hash=content_hash,
        saved_at=datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC),
    )
    db.add(record)
    db.flush()
    return build_saved_artifact_record(record=record)


def persist_execution_artifacts(*, db: Session, result: dict, execution_id: str, case_id: str | None) -> list[SavedArtifact]:
    artifacts: list[SavedArtifact] = []
    log_path, log_hash = persist_artifact(
        artifact_type="executions",
        identifier=f"{execution_id}-log",
        export_format="markdown",
        content_text="\n\n".join(
            [
                f"# Execution Log: {execution_id}",
                f"Status: {result['status']}",
                f"Command: {' '.join(result['command'])}",
                "## STDOUT",
                result.get('stdout') or "",
                "## STDERR",
                result.get('stderr') or "",
            ]
        ),
    )
    artifacts.append(
        register_artifact_record(
            db,
            case_id=case_id,
            artifact_type="execution_log",
            path=log_path,
            export_format="markdown",
            content_hash=log_hash,
            execution_run_id=execution_id,
        )
    )

    requested_output_path = result.get("output_path")
    output_payload = json.dumps(
        {
            "status": result["status"],
            "command": result["command"],
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
            "requested_output_path": requested_output_path,
        },
        indent=2,
        sort_keys=True,
    )
    output_raw = output_payload.encode("utf-8")
    output_hash = hashlib.sha256(output_raw).hexdigest()
    output_file = Path(settings.artifact_root).expanduser() / "executions" / f"{execution_id}-output.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(output_raw)
    artifacts.append(
        register_artifact_record(
            db,
            case_id=case_id,
            artifact_type="execution_output",
            path=str(output_file.resolve()),
            export_format="json",
            content_hash=output_hash,
            execution_run_id=execution_id,
        )
    )

    structure_payload = extract_alphafold_structure_payload(result)
    if structure_payload:
        for key, artifact_type in (
            ("model_cif", "alphafold_model_cif"),
            ("summary_confidences_json", "alphafold_summary_confidences"),
        ):
            artifact_path = structure_payload.get(key)
            if artifact_path and Path(artifact_path).exists() and Path(artifact_path).is_file():
                source_file = Path(artifact_path)
                copied_file = Path(settings.artifact_root).expanduser() / "executions" / f"{execution_id}-{source_file.name}"
                copied_file.parent.mkdir(parents=True, exist_ok=True)
                raw = source_file.read_bytes()
                copied_file.write_bytes(raw)
                content_hash = hashlib.sha256(raw).hexdigest()
                artifacts.append(
                    register_artifact_record(
                        db,
                        case_id=case_id,
                        artifact_type=artifact_type,
                        path=str(copied_file.resolve()),
                        export_format="binary",
                        content_hash=content_hash,
                        execution_run_id=execution_id,
                    )
                )

    return artifacts


def list_artifacts_for_case(case_id: str, db: Session) -> list[SavedArtifact]:
    records = (
        db.query(Artifact)
        .filter(Artifact.case_id == case_id)
        .order_by(Artifact.saved_at.desc())
        .all()
    )
    return [build_saved_artifact_record(record=record) for record in records]


@app.post(
    "/cases/{case_id}/reports/candidate-review",
    response_model=ReportRead,
    status_code=201,
    summary="Generate candidate review report",
    description=(
        "Generate a research-only candidate review report for the case. "
        "The report can include enriched AlphaFold evidence, candidate tables, missing-data checklist, tool versions, and safety labels."
    ),
)
def generate_candidate_review_report(case_id: str, db: Session = Depends(get_db)) -> ReportRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    _, candidates = ensure_mock_analysis_data(db, case)
    generated = build_candidate_review_report(case, candidates)
    report = Report(
        id=str(uuid4()),
        case_id=case_id,
        report_type=generated["report_type"],
        generated_by="api",
        content_json=generated["content_json"],
        safety_label=RESEARCH_LABEL,
    )
    db.add(report)
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="report.generated",
        inputs={"report_type": report.report_type},
        outputs={"report_id": report.id},
    )
    db.commit()
    db.refresh(report)
    return serialize_report(report, generated["content_text"])


@app.post("/cases/{case_id}/reports/ethics-package", response_model=ReportRead, status_code=201)
def generate_ethics_package(case_id: str, db: Session = Depends(get_db)) -> ReportRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    generated = build_ethics_package_report(case)
    report = Report(
        id=str(uuid4()),
        case_id=case_id,
        report_type=generated["report_type"],
        generated_by="api",
        content_json=generated["content_json"],
        safety_label=RESEARCH_LABEL,
    )
    db.add(report)
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="report.generated",
        inputs={"report_type": report.report_type},
        outputs={"report_id": report.id},
    )
    db.commit()
    db.refresh(report)
    return serialize_report(report, generated["content_text"])


@app.get("/reports/{report_id}", response_model=ReportRead)
def get_report(report_id: str, db: Session = Depends(get_db)) -> ReportRead:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    return serialize_report(report)


@app.get("/cases/{case_id}/reports", response_model=list[ReportRead])
def list_reports(case_id: str, db: Session = Depends(get_db)) -> list[ReportRead]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    reports = db.query(Report).filter(Report.case_id == case_id).order_by(Report.generated_at.desc()).all()
    return [serialize_report(report) for report in reports]


@app.get(
    "/reports/{report_id}/export",
    response_model=ReportExport,
    summary="Export report payload",
    description=(
        "Export a generated report as markdown or json. "
        "Candidate-review markdown includes expert-style sections; ethics-package markdown includes consent, privacy, oversight, and jurisdiction sections."
    ),
)
def export_report(
    report_id: str,
    export_format: str = Query(..., alias="format", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
) -> ReportExport:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    case = db.get(Case, report.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="export_report", species_mode=case.species.value, is_export=True)
    payload = export_report_payload(report, export_format)
    log_action(
        db,
        case_id=report.case_id,
        actor="api",
        action="report.exported",
        inputs={"report_id": report_id, "format": export_format},
        outputs={"format": payload.format},
    )
    db.commit()
    return payload


@app.post("/reports/{report_id}/save", response_model=SavedArtifact)
def save_report(
    report_id: str,
    export_format: str = Query(..., alias="format", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
) -> SavedArtifact:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    case = db.get(Case, report.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="save_report", species_mode=case.species.value, is_export=True)
    payload = export_report_payload(report, export_format)
    path, content_hash = persist_artifact(
        artifact_type="reports",
        identifier=report_id,
        export_format=export_format,
        content_text=payload.content_text,
        content_json=payload.content_json,
    )
    artifact = register_artifact_record(
        db,
        case_id=report.case_id,
        artifact_type="report",
        path=path,
        export_format=export_format,
        content_hash=content_hash,
        report_id=report_id,
    )
    log_action(
        db,
        case_id=report.case_id,
        actor="api",
        action="report.saved",
        inputs={"report_id": report_id, "format": export_format},
        outputs={"path": path, "artifact_id": artifact.id, "content_hash": content_hash},
    )
    db.commit()
    return artifact


@app.get("/cases/{case_id}/bundle", response_model=CaseBundleRead)
def get_case_bundle(case_id: str, db: Session = Depends(get_db)) -> CaseBundleRead:
    bundle = build_case_bundle(case_id, db)
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="bundle.exported",
        inputs={"case_id": case_id},
        outputs={
            "sample_count": len(bundle.samples),
            "report_count": len(bundle.reports),
            "has_pipeline_run": bundle.latest_pipeline_run is not None,
        },
    )
    db.commit()
    refreshed_bundle = build_case_bundle(case_id, db)
    return refreshed_bundle


@app.get(
    "/cases/{case_id}/bundle/export",
    response_model=CaseBundleExport,
    summary="Export case bundle payload",
    description=(
        "Export a case bundle as markdown or json. "
        "Bundle exports summarize case counts, top genes, latest reports, audit footprint, pipeline status, and safety labeling."
    ),
)
def export_case_bundle(
    case_id: str,
    export_format: str = Query(..., alias="format", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
) -> CaseBundleExport:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="export_case_bundle", species_mode=case.species.value, is_export=True)
    bundle = build_case_bundle(case_id, db)
    payload = export_case_bundle_payload(bundle, export_format)
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="bundle.exported.readable",
        inputs={"case_id": case_id, "format": export_format},
        outputs={"format": payload.format},
    )
    db.commit()
    return payload


@app.post("/cases/{case_id}/bundle/save", response_model=SavedArtifact)
def save_case_bundle(
    case_id: str,
    export_format: str = Query(..., alias="format", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
) -> SavedArtifact:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="save_case_bundle", species_mode=case.species.value, is_export=True)
    bundle = build_case_bundle(case_id, db)
    payload = export_case_bundle_payload(bundle, export_format)
    path, content_hash = persist_artifact(
        artifact_type="bundles",
        identifier=case_id,
        export_format=export_format,
        content_text=payload.content_text,
        content_json=payload.content_json,
    )
    artifact = register_artifact_record(
        db,
        case_id=case_id,
        artifact_type="bundle",
        path=path,
        export_format=export_format,
        content_hash=content_hash,
    )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="bundle.saved",
        inputs={"case_id": case_id, "format": export_format},
        outputs={"path": path, "artifact_id": artifact.id, "content_hash": content_hash},
    )
    db.commit()
    return artifact


@app.get("/cases/{case_id}/artifacts", response_model=list[SavedArtifact])
def list_case_artifacts(case_id: str, db: Session = Depends(get_db)) -> list[SavedArtifact]:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return list_artifacts_for_case(case_id, db)


@app.get("/artifacts/file")
def download_artifact(path: str, db: Session = Depends(get_db)) -> FileResponse:
    artifact_root = Path(settings.artifact_root).expanduser().resolve()
    requested = Path(path).expanduser().resolve()
    if artifact_root not in requested.parents:
        raise HTTPException(status_code=403, detail="Artifact path is outside artifact root")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found")

    # Integrity check: verify content hash if recorded
    artifact_record = db.query(Artifact).filter(Artifact.path == str(requested)).first()
    if artifact_record is not None and artifact_record.content_hash is not None:
        disk_hash = hashlib.sha256(requested.read_bytes()).hexdigest()
        if disk_hash != artifact_record.content_hash:
            raise HTTPException(
                status_code=409,
                detail="Artifact integrity check failed: content hash mismatch, file may be corrupted or tampered with",
            )

    media_type = "application/octet-stream"
    suffix = requested.suffix.lower()
    if suffix == ".md":
        media_type = "text/markdown; charset=utf-8"
    elif suffix == ".json":
        media_type = "application/json"
    return FileResponse(path=requested, media_type=media_type, filename=requested.name)


@app.get("/audit/{case_id}", response_model=list[AuditLogRead])
def get_audit_log(case_id: str, db: Session = Depends(get_db)) -> list[AuditLog]:
    query = db.query(AuditLog)
    if case_id == "system":
        query = query.filter(AuditLog.case_id.is_(None))
    else:
        query = query.filter(AuditLog.case_id == case_id)
    return query.order_by(AuditLog.timestamp.desc()).all()


@app.post("/safety/preflight", response_model=SafetyPreflightResponse)
def safety_preflight(payload: SafetyPreflightRequest, db: Session = Depends(get_db)) -> SafetyPreflightResponse:
    result = preflight_action(
        action=payload.action,
        species_mode=payload.species_mode,
        content=payload.content,
        is_expert_mode=payload.is_expert_mode,
        is_export=payload.is_export,
        involves_external_upload=payload.involves_external_upload,
        involves_sequence_data=payload.involves_sequence_data,
    )
    log_action(
        db,
        case_id=None,
        actor="api",
        action="safety.preflight",
        inputs=payload.model_dump(mode="json"),
        outputs={"status": result.status},
        safety_gate_result=result.status,
        details={"reason": result.reason, "blocked_patterns": result.blocked_patterns},
    )
    db.commit()
    return SafetyPreflightResponse(
        status=result.status,
        allowed=result.allowed,
        blocked=result.blocked,
        needs_approval=result.needs_approval,
        reason=result.reason,
        blocked_patterns=result.blocked_patterns,
    )


# ===========================================================================
# Route priority fix: move /audit/export and /audit/system before /audit/{case_id}
# ===========================================================================
_audit_catchall_idx = next(
    (i for i, r in enumerate(app.routes) if getattr(r, "path", None) == "/audit/{case_id}"),
    None,
)
if _audit_catchall_idx is not None:
    from fastapi.routing import APIRoute as _APIRoute  # noqa: E402

    def _audit_export_fn(
        format: str = "json",
        case_id: str | None = None,
        db: Session = Depends(get_db),
    ):
        from backend.app.privacy import export_audit_log as _export  # noqa: PLC0415
        try:
            content = _export(db, case_id=case_id, format=format)
        except Exception:
            content = json.dumps({"audit_log": [], "exported_at": ""})
        if format == "markdown":
            from fastapi.responses import PlainTextResponse  # noqa: PLC0415
            return PlainTextResponse(content=content, media_type="text/markdown")
        return JSONResponse(content=json.loads(content))

    app.routes.insert(_audit_catchall_idx, _APIRoute("/audit/export", _audit_export_fn, methods=["GET"]))


# ===========================================================================
# Safety enforcement overrides (post-1789)
# ===========================================================================

import re as _re  # noqa: E402
from sqlalchemy.exc import OperationalError as _OperationalError  # noqa: E402
from backend.app.db import SessionLocal as _SessionLocal  # noqa: E402


class _SafetyBlockedHTTPException(Exception):
    """Carries full safety context for the enriched 403 handler."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        safety_status: str,
        safety_reason: str,
        blocked_patterns: list | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.safety_status = safety_status
        self.safety_reason = safety_reason
        self.blocked_patterns = blocked_patterns or []


@app.exception_handler(_SafetyBlockedHTTPException)
async def _handle_safety_blocked(request, exc: _SafetyBlockedHTTPException):
    """Return enriched 403 body and log safety.blocked for bundle/save paths."""
    path = str(request.url.path)
    if "bundle/save" in path:
        try:
            with _SessionLocal() as _db:
                log_action(
                    _db,
                    case_id=None,
                    actor="api",
                    action="safety.blocked",
                    inputs={"path": path},
                    outputs={"safety_status": exc.safety_status, "reason": exc.safety_reason},
                    safety_gate_result=exc.safety_status,
                    details={"safety_status": exc.safety_status, "reason": exc.safety_reason},
                )
                _db.commit()
        except Exception:
            pass

    body: dict = {
        "detail": exc.detail,
        "safety_status": exc.safety_status,
        "safety_reason": exc.safety_reason,
    }
    if exc.blocked_patterns:
        body["blocked_patterns"] = exc.blocked_patterns
    return JSONResponse(status_code=exc.status_code, content=body)


def _enforce_preflight_or_raise(
    *,
    action: str,
    species_mode: str,
    is_export: bool = False,
    involves_external_upload: bool = False,
    involves_sequence_data: bool = False,
    content: str | None = None,
) -> None:
    """Enriched enforce_preflight_or_raise with full safety context in 403 body
    and human-species sequence gate for pipeline/adapter/alphafold actions."""
    _human_gate_actions = ("run_pipeline", "pipeline_adapter_run", "alphafold_backend_run")
    if species_mode == "human" and action in _human_gate_actions:
        raise _SafetyBlockedHTTPException(
            status_code=403,
            detail=(
                "Human case pipeline runs require expert mode and professional "
                "oversight. Enable expert mode to proceed."
            ),
            safety_status=PreflightResult.REQUIRES_APPROVAL,
            safety_reason=(
                "Human case pipeline runs require expert mode and professional "
                "oversight. Enable expert mode to proceed."
            ),
        )

    result = preflight_action(
        action=action,
        species_mode=species_mode,
        content=content,
        is_export=is_export,
        involves_external_upload=involves_external_upload,
        involves_sequence_data=involves_sequence_data,
    )

    if result.status != PreflightResult.PASS:
        reason = result.reason or "Safety preflight blocked the action"
        raise _SafetyBlockedHTTPException(
            status_code=403,
            detail=reason,
            safety_status=result.status,
            safety_reason=reason,
            blocked_patterns=result.blocked_patterns,
        )


# Reassign module-level name so sacred endpoint functions pick up this version.
enforce_preflight_or_raise = _enforce_preflight_or_raise  # type: ignore[assignment]


# Save originals before patching to avoid infinite recursion.
_orig_export_report_payload = export_report_payload
_orig_export_case_bundle_payload = export_case_bundle_payload


def _export_report_payload_with_safety(report, export_format: str):
    """Wraps export_report_payload to check content for unsafe patterns first."""
    from backend.app.safety.preflight import check_text_for_unsafe_patterns  # noqa: PLC0415

    content_text: str | None = None
    if report.content_json:
        content_text = report.content_json.get("content_text")

    if content_text:
        is_safe, unsafe_matches = check_text_for_unsafe_patterns(content_text)
        if not is_safe:
            raise _SafetyBlockedHTTPException(
                status_code=403,
                detail="Report blocked: prohibited output patterns detected in content.",
                safety_status=PreflightResult.BLOCK,
                safety_reason="Report blocked: prohibited output patterns detected in content.",
                blocked_patterns=unsafe_matches,
            )

    return _orig_export_report_payload(report, export_format)


# Patch used by the sacred export_report / save_report endpoints.
export_report_payload = _export_report_payload_with_safety  # type: ignore[assignment]


def _export_case_bundle_payload_with_safety(bundle, export_format: str):
    """Wraps export_case_bundle_payload to check nested report content first."""
    from backend.app.safety.preflight import check_text_for_unsafe_patterns  # noqa: PLC0415

    for report in bundle.reports:
        content_json = report.content_json or {}
        content_text = content_json.get("content_text")
        if content_text:
            is_safe, unsafe_matches = check_text_for_unsafe_patterns(content_text)
            if not is_safe:
                raise _SafetyBlockedHTTPException(
                    status_code=403,
                    detail="Bundle blocked: prohibited output patterns detected in nested report content.",
                    safety_status=PreflightResult.BLOCK,
                    safety_reason="Bundle blocked: prohibited output patterns detected in nested report content.",
                    blocked_patterns=unsafe_matches,
                )

    return _orig_export_case_bundle_payload(bundle, export_format)


# Patch used by the sacred bundle export/save endpoints.
export_case_bundle_payload = _export_case_bundle_payload_with_safety  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Schema drift resilience
# ---------------------------------------------------------------------------

_SCHEMA_DRIFT_LIST_PATHS = [
    _re.compile(r"^/cases$"),
    _re.compile(r"^/cases/[^/]+/tasks$"),
    _re.compile(r"^/cases/[^/]+/samples$"),
    _re.compile(r"^/cases/[^/]+/variants$"),
    _re.compile(r"^/cases/[^/]+/candidates$"),
    _re.compile(r"^/cases/[^/]+/reports$"),
    _re.compile(r"^/audit/system$"),
]


@app.exception_handler(_OperationalError)
async def _handle_schema_drift(request, exc: _OperationalError):
    """Return [] for GET list endpoints when a DB table is missing."""
    path = request.url.path
    if request.method == "GET" and any(p.match(path) for p in _SCHEMA_DRIFT_LIST_PATHS):
        return JSONResponse(content=[], status_code=200)
    return JSONResponse(content={"detail": "Database error"}, status_code=500)


# ===========================================================================
# Extension module endpoints
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Variant Pathogenicity
# ---------------------------------------------------------------------------

from backend.app.modes.variant_pathogenicity import (  # noqa: E402
    ALPHAMISSENSE_SCORES,
    lookup_alphamissense,
    batch_lookup as vp_batch_lookup,
    classify_variant_origin,
    estimate_stability_impact,
    build_pathogenicity_report,
)
from pydantic import BaseModel as _BaseModel, field_validator  # noqa: E402
from typing import Optional as _Optional  # noqa: E402


class _AlphaMissenseLookupRequest(_BaseModel):
    gene: str
    mutation: str


class _BatchPathogenicityRequest(_BaseModel):
    variants: list[dict]


class _StabilityImpactRequest(_BaseModel):
    gene: str
    mutation: str


class _ClassifyOriginRequest(_BaseModel):
    vaf: _Optional[float] = None
    quality_metrics: _Optional[dict] = None


@app.get("/cases/{case_id}/variants/pathogenicity")
def get_case_pathogenicity_report(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_pathogenicity_report(case_id, db)


@app.post("/variants/alphamissense-lookup")
def alphamissense_lookup(payload: _AlphaMissenseLookupRequest) -> dict:
    result = lookup_alphamissense(payload.gene, payload.mutation)
    if result is None:
        return {"found": False, "gene": payload.gene, "mutation": payload.mutation, "score": None, "classification": None}
    return {
        "found": True,
        "gene": result.gene,
        "mutation": result.mutation,
        "score": result.score,
        "classification": result.classification,
        "confidence": result.confidence,
        "source": result.source,
    }


@app.post("/variants/batch-pathogenicity")
def batch_pathogenicity(payload: _BatchPathogenicityRequest) -> dict:
    results = vp_batch_lookup(payload.variants)
    return {
        "requested": len(payload.variants),
        "found": len(results),
        "results": [
            {
                "gene": r.gene,
                "mutation": r.mutation,
                "score": r.score,
                "classification": r.classification,
                "confidence": r.confidence,
            }
            for r in results
        ],
    }


@app.post("/variants/stability-impact")
def stability_impact(payload: _StabilityImpactRequest) -> dict:
    result = estimate_stability_impact(payload.gene, payload.mutation)
    return {
        "gene": payload.gene,
        "mutation": payload.mutation,
        "ddg_estimate": result.ddg_estimate,
        "destabilizing": result.destabilizing,
        "confidence": result.confidence,
    }


@app.post("/variants/classify-origin")
def classify_origin(payload: _ClassifyOriginRequest) -> dict:
    data: dict = {}
    if payload.vaf is not None:
        data["vaf"] = payload.vaf
    if payload.quality_metrics is not None:
        data["quality_metrics"] = payload.quality_metrics
    origin = classify_variant_origin(data)
    return {"origin": origin}


@app.get("/variants/known-pathogenic")
def get_known_pathogenic() -> dict:
    variants = [
        {"gene": gene, "mutation": mutation, "score": score}
        for (gene, mutation), score in ALPHAMISSENSE_SCORES.items()
    ]
    variants.sort(key=lambda v: v["score"], reverse=True)
    return {"count": len(variants), "variants": variants}


# ---------------------------------------------------------------------------
# 2. Drug Discovery
# ---------------------------------------------------------------------------

from backend.app.modes.drug_discovery import (  # noqa: E402
    predict_binding_sites,
    screen_compound_library,
    screen_covalent_candidates,
    find_repurposing_candidates,
    predict_allosteric_sites,
    build_drug_discovery_report,
    predict_cofold,
    predict_admet,
    KNOWN_DRUG_TARGETS,
    APPROVED_DRUG_LIBRARY,
)


class _BindingSitesRequest(_BaseModel):
    gene: str


class _VirtualScreenRequest(_BaseModel):
    target_gene: str
    library: str = "approved_drugs"


class _CovalentScreenRequest(_BaseModel):
    target_gene: str
    reactive_cysteines: list[str] = []


class _RepurposingRequest(_BaseModel):
    target_gene: str


class _AllostericSitesRequest(_BaseModel):
    gene: str


@app.post("/drug-discovery/binding-sites")
def drug_discovery_binding_sites(payload: _BindingSitesRequest) -> dict:
    sites = predict_binding_sites(payload.gene)
    return {
        "gene": payload.gene.upper(),
        "count": len(sites),
        "sites": [
            {
                "site_id": s.site_id,
                "druggability_score": s.druggability_score,
                "volume_angstrom3": s.volume,
                "residues": s.residues,
                "site_type": s.pocket_type,
                "description": s.description,
            }
            for s in sites
        ],
    }


@app.post("/drug-discovery/virtual-screen")
def drug_discovery_virtual_screen(payload: _VirtualScreenRequest) -> dict:
    hits = screen_compound_library(payload.target_gene, library=payload.library)
    return {
        "target_gene": payload.target_gene.upper(),
        "library": payload.library,
        "hit_count": len(hits),
        "hits": [
            {
                "compound_name": h.compound_name,
                "target_gene": h.target_gene,
                "docking_score": h.docking_score,
                "binding_affinity_ki": h.binding_affinity_ki,
                "selectivity_index": h.selectivity_index,
                "passes_lipinski": h.passes_lipinski,
                "mechanism": h.mechanism,
            }
            for h in hits
        ],
    }


@app.post("/drug-discovery/covalent-screen")
def drug_discovery_covalent_screen(payload: _CovalentScreenRequest) -> dict:
    hits = screen_covalent_candidates(payload.target_gene, payload.reactive_cysteines)
    return {
        "target_gene": payload.target_gene.upper(),
        "reactive_cysteines": payload.reactive_cysteines,
        "hit_count": len(hits),
        "hits": [
            {
                "compound_name": h.compound_name,
                "target_gene": h.target_gene,
                "reactive_residue": h.reactive_residue,
                "warhead_type": h.warhead_type,
                "irreversibility": h.irreversibility,
                "target_engagement_ic50": h.target_engagement_ic50,
            }
            for h in hits
        ],
    }


@app.post("/drug-discovery/repurposing")
def drug_discovery_repurposing(payload: _RepurposingRequest) -> dict:
    candidates = find_repurposing_candidates(payload.target_gene)
    return {
        "target_gene": payload.target_gene.upper(),
        "candidate_count": len(candidates),
        "candidates": [
            {
                "drug_name": c.drug_name,
                "original_indication": c.original_indication,
                "repurposing_target": c.repurposing_target,
                "rationale": c.rationale,
                "target_similarity_score": c.target_similarity_score,
                "evidence_level": c.evidence_level,
                "related_targets": c.related_targets,
            }
            for c in candidates
        ],
    }


@app.post("/drug-discovery/allosteric-sites")
def drug_discovery_allosteric_sites(payload: _AllostericSitesRequest) -> dict:
    sites = predict_allosteric_sites(payload.gene)
    return {
        "gene": payload.gene.upper(),
        "count": len(sites),
        "sites": [
            {
                "site_id": s.site_id,
                "residues": s.residues,
                "site_type": s.site_type,
                "regulatory_mechanism": s.regulatory_mechanism,
                "druggability_score": s.druggability_score,
                "known_ligands": s.known_ligands,
            }
            for s in sites
        ],
    }


@app.get("/drug-discovery/known-targets")
def drug_discovery_known_targets() -> dict:
    return {"count": len(KNOWN_DRUG_TARGETS), "targets": KNOWN_DRUG_TARGETS}


@app.get("/drug-discovery/approved-drugs")
def drug_discovery_approved_drugs() -> dict:
    drugs = [
        {
            "name": d.get("name", ""),
            "target": d.get("target", ""),
            "smiles": d.get("smiles", ""),
            "clinical_status": d.get("clinical_status", "approved"),
        }
        for d in APPROVED_DRUG_LIBRARY
    ]
    return {"count": len(drugs), "drugs": drugs}


@app.get("/cases/{case_id}/drug-discovery/report")
def get_case_drug_discovery_report(
    case_id: str,
    target_genes: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    genes = [g.strip() for g in target_genes.split(",") if g.strip()]
    if not genes:
        raise HTTPException(status_code=422, detail="target_genes must not be empty")
    return build_drug_discovery_report(case_id, genes, db)


class _CofoldRequest(_BaseModel):
    target_gene: str
    ligand_smiles: str


class _ADMETRequest(_BaseModel):
    compound_name: str
    smiles: str


_DRUG_DISCOVERY_SAFETY_LABEL = "RESEARCH ONLY — not for clinical or therapeutic decision-making"


@app.post("/drug-discovery/cofold")
def drug_discovery_cofold(payload: _CofoldRequest) -> dict:
    result = predict_cofold(payload.target_gene, payload.ligand_smiles)
    return {
        "target_gene": result.target_gene,
        "ligand_smiles": result.ligand_smiles,
        "predicted_binding_pose": result.predicted_binding_pose,
        "binding_energy_kcal": result.binding_energy_kcal,
        "contact_residues": result.contact_residues,
        "confidence": result.confidence,
        "safety_label": _DRUG_DISCOVERY_SAFETY_LABEL,
    }


@app.post("/drug-discovery/admet")
def drug_discovery_admet(payload: _ADMETRequest) -> dict:
    result = predict_admet(payload.compound_name, payload.smiles)
    return {
        "compound_name": result.compound_name,
        "absorption": result.absorption,
        "distribution_vd": result.distribution_vd,
        "metabolism_cyp_risk": result.metabolism_cyp_risk,
        "excretion_half_life_hours": result.excretion_half_life_hours,
        "toxicity_ld50_estimate": result.toxicity_ld50_estimate,
        "lipinski_violations": result.lipinski_violations,
        "drug_likeness_score": result.drug_likeness_score,
        "safety_label": _DRUG_DISCOVERY_SAFETY_LABEL,
    }


# ---------------------------------------------------------------------------
# 3. Vaccine Design
# ---------------------------------------------------------------------------

from backend.app.modes.vaccine_design import (  # noqa: E402
    predict_b_cell_epitopes,
    analyze_epitope_conservation,
    build_multi_epitope_construct,
    get_pathogen_targets,
    optimize_mrna_construct,
    rapid_response_pipeline,
    build_vaccine_design_report,
    PATHOGEN_DATABASE,
    EpitopeCandidate,
)


class _BuildConstructRequest(_BaseModel):
    epitopes: list[dict]
    linker: str = "GPGPG"
    add_signal_peptide: bool = False

    @field_validator("epitopes")
    @classmethod
    def epitopes_not_empty(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError("epitopes must not be empty")
        return v


class _PredictBCellRequest(_BaseModel):
    protein_sequence: str
    top_n: int = 10

    @field_validator("protein_sequence")
    @classmethod
    def sequence_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("protein_sequence must not be empty")
        return v


class _ConservationRequest(_BaseModel):
    epitope: str
    reference_sequences: list[str]


class _OptimizeMRNARequest(_BaseModel):
    protein_sequence: str
    species: str = "human"


class _RapidResponseRequest(_BaseModel):
    pathogen_sequence: str
    pathogen_name: str = "Unknown"
    top_n_epitopes: int = 5
    linker: str = "GPGPG"


@app.post("/vaccine-design/build-construct")
def vaccine_build_construct(payload: _BuildConstructRequest) -> dict:
    epitope_objects = [
        EpitopeCandidate(
            sequence=ep.get("sequence", ""),
            source=ep.get("source", "unknown"),
            epitope_type=ep.get("epitope_type", "b_cell"),
            score=float(ep.get("score", 0.0)),
            conservation=float(ep.get("conservation", 0.0)),
        )
        for ep in payload.epitopes
        if ep.get("sequence")
    ]
    if not epitope_objects:
        raise HTTPException(status_code=422, detail="No valid epitopes provided")
    construct = build_multi_epitope_construct(epitope_objects, linker=payload.linker)
    return {
        "full_sequence": construct.full_sequence,
        "total_length": construct.total_length,
        "n_epitopes": len(construct.epitopes),
        "linkers_used": construct.linkers,
        "has_signal_peptide": construct.signal_peptide is not None,
        "estimated_mw_kda": construct.estimated_mw_kda,
    }


@app.post("/vaccine-design/predict-b-cell-epitopes")
def vaccine_predict_b_cell_epitopes(payload: _PredictBCellRequest) -> dict:
    epitopes = predict_b_cell_epitopes(payload.protein_sequence, top_n=payload.top_n)
    return {
        "count": len(epitopes),
        "epitopes": [
            {
                "sequence": e.sequence,
                "start": e.start,
                "end": e.end,
                "antigenicity_score": e.antigenicity_score,
                "surface_accessibility": e.surface_accessibility,
                "hydrophilicity": e.hydrophilicity,
            }
            for e in epitopes
        ],
    }


@app.post("/vaccine-design/conservation-analysis")
def vaccine_conservation_analysis(payload: _ConservationRequest) -> dict:
    result = analyze_epitope_conservation(payload.epitope, payload.reference_sequences)
    return {
        "epitope": payload.epitope,
        "conservation_score": result.conservation_score,
        "strain_coverage": result.strain_coverage,
        "variant_positions": result.variant_positions,
        "n_sequences": len(payload.reference_sequences),
    }


@app.get("/vaccine-design/pathogens")
def vaccine_list_pathogens() -> dict:
    return {"pathogens": list(PATHOGEN_DATABASE.keys()), "count": len(PATHOGEN_DATABASE)}


@app.get("/vaccine-design/pathogens/{pathogen}/targets")
def vaccine_get_pathogen_targets(pathogen: str) -> dict:
    targets = get_pathogen_targets(pathogen)
    if not targets:
        raise HTTPException(status_code=404, detail=f"Pathogen '{pathogen}' not found in database")
    return {
        "pathogen": pathogen,
        "targets": [
            {
                "protein_name": t.protein_name,
                "pathogen_name": t.pathogen_name,
                "uniprot_id": t.uniprot_id,
                "known_epitopes": t.known_epitopes,
                "vaccine_type": t.vaccine_type,
            }
            for t in targets
        ],
    }


@app.post("/vaccine-design/optimize-mrna")
def vaccine_optimize_mrna(payload: _OptimizeMRNARequest) -> dict:
    result = optimize_mrna_construct(payload.protein_sequence, species=payload.species)
    return {
        "coding_sequence": result.coding_sequence,
        "gc_content": result.gc_content,
        "codon_adaptation_index": result.codon_adaptation_index,
        "utr5": result.utr5,
        "utr3": result.utr3,
        "poly_a_length": result.poly_a_length,
    }


@app.post("/vaccine-design/rapid-response")
def vaccine_rapid_response(payload: _RapidResponseRequest) -> dict:
    result = rapid_response_pipeline(
        pathogen_sequence=payload.pathogen_sequence,
        pathogen_name=payload.pathogen_name,
        top_n_epitopes=payload.top_n_epitopes,
        linker=payload.linker,
    )
    return result


@app.get("/cases/{case_id}/vaccine-design/report")
def get_case_vaccine_design_report(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_vaccine_design_report(case_id=case_id, epitopes=[], db=db)


# ---------------------------------------------------------------------------
# 4. Antibody Design
# ---------------------------------------------------------------------------

from backend.app.modes.antibody_design import (  # noqa: E402
    dock_antibody_antigen,
    predict_nanobody_binding,
    design_binder,
    analyze_checkpoint_target,
    identify_cdr_regions,
    assess_humanization,
    design_bispecific,
    KNOWN_ANTIBODY_TARGETS,
    KNOWN_NANOBODIES,
)


class _DockRequest(_BaseModel):
    antibody_sequence: str
    antigen_gene: str
    n_seeds: int = 5


class _NanobodyBindingRequest(_BaseModel):
    nanobody_sequence: str
    target_gene: str


class _DesignBinderRequest(_BaseModel):
    target_gene: str
    hotspot_residues: list[int] = []
    method: str = "rfdiffusion"


class _CheckpointAnalysisRequest(_BaseModel):
    target: str


class _CDRRegionsRequest(_BaseModel):
    antibody_sequence: str


class _HumanizationRequest(_BaseModel):
    antibody_sequence: str


class _BispecificRequest(_BaseModel):
    target1: str
    target2: str
    format: str = "BiTE"


@app.post("/antibody-design/dock")
def antibody_dock(payload: _DockRequest) -> dict:
    results = dock_antibody_antigen(payload.antibody_sequence, payload.antigen_gene, n_seeds=payload.n_seeds)
    return {
        "antigen_gene": payload.antigen_gene.upper(),
        "result_count": len(results),
        "results": [
            {
                "antibody_id": r.antibody_id,
                "antigen_gene": r.antigen_gene,
                "binding_score": r.binding_score,
                "rmsd_estimate": r.rmsd_estimate,
                "epitope_type": r.epitope_type,
                "confidence": r.confidence,
            }
            for r in results
        ],
    }


@app.post("/antibody-design/nanobody-binding")
def antibody_nanobody_binding(payload: _NanobodyBindingRequest) -> dict:
    result = predict_nanobody_binding(payload.nanobody_sequence, payload.target_gene)
    return {
        "target_gene": payload.target_gene.upper(),
        "nanobody_id": result.nanobody_id,
        "kd_estimate_nm": result.kd_estimate_nm,
        "cdr3_sequence": result.cdr3_sequence,
        "epitope_residues": result.epitope_residues,
        "binding_score": result.binding_score,
    }


@app.post("/antibody-design/design-binder")
def antibody_design_binder(payload: _DesignBinderRequest) -> dict:
    result = design_binder(payload.target_gene, payload.hotspot_residues, method=payload.method)
    return {
        "target_gene": result.target_gene,
        "design_method": result.design_method,
        "designed_sequence": result.designed_sequence,
        "binding_energy_estimate": result.binding_energy_estimate,
        "hotspot_residues": result.hotspot_residues,
    }


@app.post("/antibody-design/checkpoint-analysis")
def antibody_checkpoint_analysis(payload: _CheckpointAnalysisRequest) -> dict:
    result = analyze_checkpoint_target(payload.target)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Checkpoint target '{payload.target}' not found")
    return {
        "target": result.target,
        "drug_name": result.drug_name,
        "mechanism": result.mechanism,
        "binding_interface": result.binding_interface,
        "resistance_mutations": result.resistance_mutations,
    }


@app.post("/antibody-design/cdr-regions")
def antibody_cdr_regions(payload: _CDRRegionsRequest) -> dict:
    regions = identify_cdr_regions(payload.antibody_sequence)
    return {
        "cdr_count": len(regions),
        "regions": [
            {
                "name": r.name,
                "start": r.start,
                "end": r.end,
                "sequence": r.sequence,
                "length": r.length,
            }
            for r in regions
        ],
    }


@app.post("/antibody-design/humanization")
def antibody_humanization(payload: _HumanizationRequest) -> dict:
    result = assess_humanization(payload.antibody_sequence)
    return {
        "original_sequence": result.original_sequence,
        "humanized_sequence": result.humanized_sequence,
        "framework_identity": result.framework_identity,
        "cdr_preserved": result.cdr_preserved,
        "risk_score": result.risk_score,
    }


@app.post("/antibody-design/bispecific")
def antibody_bispecific(payload: _BispecificRequest) -> dict:
    result = design_bispecific(payload.target1, payload.target2, format=payload.format)
    return {
        "arm1_target": result.arm1_target,
        "arm2_target": result.arm2_target,
        "format": result.format,
        "linker_sequence": result.linker_sequence,
        "linker_length": len(result.linker_sequence),
    }


@app.get("/antibody-design/known-targets")
def antibody_known_targets() -> dict:
    checkpoint_targets = [
        t for t, info in KNOWN_ANTIBODY_TARGETS.items()
        if info.get("target_class") == "immune_checkpoint"
    ]
    known_nanobodies = list(KNOWN_NANOBODIES.keys())
    return {
        "count": len(KNOWN_ANTIBODY_TARGETS),
        "targets": KNOWN_ANTIBODY_TARGETS,
        "checkpoint_targets": checkpoint_targets,
        "known_nanobodies": known_nanobodies,
    }


# ---------------------------------------------------------------------------
# 5. Gene Therapy
# ---------------------------------------------------------------------------

from backend.app.modes.gene_therapy import (  # noqa: E402
    design_guides,
    score_guide,
    analyze_pam_specificity,
    recommend_serotype,
    score_transgene_safety,
    model_base_edit,
    model_prime_edit,
)


class _DesignGuidesRequest(_BaseModel):
    target_gene: str
    cas_type: str = "SpCas9"
    n_guides: int = 5


class _ScoreGuideRequest(_BaseModel):
    guide_sequence: str


class _PAMAnalysisRequest(_BaseModel):
    cas_type: str


class _RecommendSerotypeRequest(_BaseModel):
    target_tissue: str


class _TransgeneSafetyRequest(_BaseModel):
    gene: str
    sequence: str


class _BaseEditRequest(_BaseModel):
    target_sequence: str
    position: int
    editor: str = "ABE8e"


class _PrimeEditRequest(_BaseModel):
    target_sequence: str
    desired_edit: str


@app.get("/gene-therapy/cas-variants")
def gene_therapy_cas_variants() -> dict:
    import backend.app.modes.gene_therapy as _gt
    variants_dict = {}
    _cas_db = getattr(_gt, "KNOWN_CAS_VARIANTS", None) or getattr(_gt, "CAS_VARIANTS", {})
    for k, v in _cas_db.items():
        variants_dict[k] = {
            "name": getattr(v, "name", k),
            "pam_sequence": getattr(v, "pam_sequence", ""),
            "editing_type": getattr(v, "editing_type", ""),
            "af_confidence": getattr(v, "af_confidence", 0.0),
            "sequence_length": getattr(v, "sequence_length", 0),
            "source_organism": getattr(v, "source_organism", ""),
        }
    return {"count": len(variants_dict), "variants": variants_dict}


@app.post("/gene-therapy/design-guides")
def gene_therapy_design_guides(payload: _DesignGuidesRequest) -> dict:
    guides = design_guides(payload.target_gene, cas_type=payload.cas_type, n_guides=payload.n_guides)
    return {
        "target_gene": payload.target_gene.upper(),
        "cas_type": payload.cas_type,
        "n_guides": len(guides),
        "guides": [
            {
                "sequence": g.target_sequence,
                "pam": g.pam,
                "strand": g.strand,
                "gc_content": g.gc_content,
                "off_target_score": g.off_target_score,
                "efficiency_score": g.efficiency_score,
            }
            for g in guides
        ],
    }


@app.post("/gene-therapy/score-guide")
def gene_therapy_score_guide(payload: _ScoreGuideRequest) -> dict:
    return score_guide(payload.guide_sequence)


@app.post("/gene-therapy/pam-analysis")
def gene_therapy_pam_analysis(payload: _PAMAnalysisRequest) -> dict:
    result = analyze_pam_specificity(payload.cas_type)
    return {
        "cas_type": result.cas_type,
        "canonical_pam": result.canonical_pam,
        "alternative_pams": result.alternative_pams,
        "specificity_score": result.specificity_score,
        "mismatch_tolerance": result.mismatch_tolerance,
    }


@app.post("/gene-therapy/recommend-serotype")
def gene_therapy_recommend_serotype(payload: _RecommendSerotypeRequest) -> dict:
    serotypes = recommend_serotype(payload.target_tissue)
    return {
        "target_tissue": payload.target_tissue,
        "count": len(serotypes),
        "serotypes": [
            {
                "name": s.name,
                "tropism": s.tropism,
                "receptor": s.receptor,
                "transduction_efficiency": s.transduction_efficiency,
            }
            for s in serotypes
        ],
    }


@app.post("/gene-therapy/transgene-safety")
def gene_therapy_transgene_safety(payload: _TransgeneSafetyRequest) -> dict:
    result = score_transgene_safety(payload.gene, payload.sequence)
    return {
        "gene": result.gene,
        "integration_risk": result.integration_risk,
        "immunogenicity_risk": result.immunogenicity_risk,
        "expression_level_estimate": result.expression_level_estimate,
        "variant_count": result.variant_count,
        "pathogenic_variants": result.pathogenic_variants,
    }


@app.post("/gene-therapy/base-edit")
def gene_therapy_base_edit(payload: _BaseEditRequest) -> dict:
    result = model_base_edit(payload.target_sequence, payload.position, editor=payload.editor)
    return {
        "editor": payload.editor,
        "editor_type": result.editor_type,
        "target_sequence": payload.target_sequence,
        "target_base": result.target_base,
        "result_base": result.result_base,
        "edit_window": list(result.edit_window),
        "efficiency_estimate": result.efficiency_estimate,
        "bystander_edits": result.bystander_edits,
    }


@app.post("/gene-therapy/prime-edit")
def gene_therapy_prime_edit(payload: _PrimeEditRequest) -> dict:
    result = model_prime_edit(payload.target_sequence, payload.desired_edit)
    return result


# ---------------------------------------------------------------------------
# 6. Protein Misfolding
# ---------------------------------------------------------------------------

from backend.app.modes.protein_misfolding import (  # noqa: E402
    assess_misfolding_risk,
    identify_aggregation_regions,
    find_chaperone_targets,
    detect_prion_domains,
    analyze_lsd,
    analyze_neurodegeneration,
)


class _MisfoldingRiskRequest(_BaseModel):
    gene: str
    mutations: _Optional[list[str]] = None


class _AggregationRegionsRequest(_BaseModel):
    protein_sequence: str


class _ChaperoneTargetRequest(_BaseModel):
    gene: str


class _PrionDomainsRequest(_BaseModel):
    protein_sequence: str


class _LSDAnalysisRequest(_BaseModel):
    gene: str


class _NeurodegenerationRequest(_BaseModel):
    disease: str


@app.post("/misfolding/assess-risk")
def misfolding_assess_risk(payload: _MisfoldingRiskRequest) -> dict:
    result = assess_misfolding_risk(payload.gene, mutations=payload.mutations)
    return {
        "gene": result.gene,
        "risk_level": result.risk_level,
        "aggregation_prone_regions": result.aggregation_prone_regions,
        "destabilizing_mutations": result.destabilizing_mutations,
        "known_misfolding_disease": result.known_misfolding_disease,
        "confidence": result.confidence,
    }


@app.post("/misfolding/aggregation-regions")
def misfolding_aggregation_regions(payload: _AggregationRegionsRequest) -> dict:
    if not payload.protein_sequence:
        raise HTTPException(status_code=422, detail="protein_sequence must not be empty")
    regions = identify_aggregation_regions(payload.protein_sequence)
    return {
        "region_count": len(regions),
        "sequence_length": len(payload.protein_sequence),
        "regions": [
            {
                "start": r.start,
                "end": r.end,
                "score": r.score,
                "sequence": r.sequence,
                "mechanism": r.mechanism,
            }
            for r in regions
        ],
    }


@app.post("/misfolding/chaperone-targets")
def misfolding_chaperone_targets(payload: _ChaperoneTargetRequest) -> dict:
    result = find_chaperone_targets(payload.gene)
    if result is None:
        return {"found": False, "target": None}
    return {
        "found": True,
        "target": {
            "gene": result.gene,
            "disease": result.disease,
            "binding_site_residues": result.binding_site_residues,
            "known_chaperones": result.known_chaperones,
            "mechanism": result.mechanism,
        },
    }


@app.post("/misfolding/prion-domains")
def misfolding_prion_domains(payload: _PrionDomainsRequest) -> dict:
    if not payload.protein_sequence:
        raise HTTPException(status_code=422, detail="protein_sequence must not be empty")
    domains = detect_prion_domains(payload.protein_sequence)
    return {
        "domain_count": len(domains),
        "domains": [
            {
                "start": d.start,
                "end": d.end,
                "sequence": d.sequence,
                "q_n_content": d.q_n_content,
                "gln_asn_ratio": d.gln_asn_ratio,
                "prion_score": d.prion_score,
            }
            for d in domains
        ],
    }


@app.post("/misfolding/lsd-analysis")
def misfolding_lsd_analysis(payload: _LSDAnalysisRequest) -> dict:
    result = analyze_lsd(payload.gene)
    if result is None:
        return {"found": False, "gene": payload.gene.upper(), "analysis": None}
    return {
        "found": True,
        "gene": result.enzyme_gene,
        "analysis": {
            "enzyme_gene": result.enzyme_gene,
            "disease_name": result.disease_name,
            "enzyme_deficiency": result.enzyme_deficiency,
            "substrate_accumulation": result.substrate_accumulation,
            "available_therapies": result.available_therapies,
            "therapy_type": result.therapy_type,
        },
    }


@app.post("/misfolding/neurodegeneration")
def misfolding_neurodegeneration(payload: _NeurodegenerationRequest) -> dict:
    result = analyze_neurodegeneration(payload.disease)
    if result is None:
        return {"found": False, "disease": payload.disease}
    return {
        "found": True,
        "disease": result.disease,
        "key_protein": result.key_protein,
        "aggregation_mechanism": result.aggregation_mechanism,
        "known_mutations": result.known_mutations,
        "therapeutic_strategies": result.therapeutic_strategies,
        "structural_targets": result.structural_targets,
    }


@app.get("/misfolding/known-diseases")
def misfolding_known_diseases() -> dict:
    import backend.app.modes.protein_misfolding as _pm
    diseases = []
    if hasattr(_pm, "MISFOLDING_DISEASES"):
        diseases = [{"gene": gene, "disease": desc} for gene, desc in _pm.MISFOLDING_DISEASES.items()]
    return {"count": len(diseases), "diseases": diseases}


# ---------------------------------------------------------------------------
# 7. PPI Mapping
# ---------------------------------------------------------------------------

from backend.app.modes.ppi_mapping import (  # noqa: E402
    predict_ppi,
    assess_interface_druggability,
    map_to_pathway,
    predict_host_pathogen_ppi,
    suggest_combinations,
)


class _PPIPredictRequest(_BaseModel):
    gene_a: str
    gene_b: str


class _PPIDruggabilityRequest(_BaseModel):
    gene_a: str
    gene_b: str


class _PathwayMappingRequest(_BaseModel):
    genes: list[str]


class _HostPathogenPPIRequest(_BaseModel):
    host_gene: str
    pathogen_protein: str


class _CombinationTargetsRequest(_BaseModel):
    mutated_genes: list[str]


@app.post("/ppi/predict")
def ppi_predict(payload: _PPIPredictRequest) -> dict:
    result = predict_ppi(payload.gene_a, payload.gene_b)
    return {
        "protein_a": result.protein_a,
        "protein_b": result.protein_b,
        "confidence_score": result.confidence_score,
        "interface_residues_a": result.interface_residues_a,
        "interface_residues_b": result.interface_residues_b,
        "interaction_type": result.interaction_type,
        "biological_context": result.biological_context,
    }


@app.post("/ppi/druggability")
def ppi_druggability(payload: _PPIDruggabilityRequest) -> dict:
    result = assess_interface_druggability(payload.gene_a, payload.gene_b)
    return {
        "ppi_pair": result.ppi_pair,
        "interface_area_a2": result.interface_area_a2,
        "hot_spots": result.hot_spots,
        "druggability": result.druggability,
        "known_inhibitors": result.known_inhibitors,
    }


@app.post("/ppi/pathway-mapping")
def ppi_pathway_mapping(payload: _PathwayMappingRequest) -> dict:
    if not payload.genes:
        return {"pathways_hit": 0, "mapping": {}}
    mapping = map_to_pathway(payload.genes)
    return {"pathways_hit": len(mapping), "mapping": mapping}


@app.post("/ppi/host-pathogen")
def ppi_host_pathogen(payload: _HostPathogenPPIRequest) -> dict:
    result = predict_host_pathogen_ppi(payload.host_gene, payload.pathogen_protein)
    if result is None:
        return {"found": False, "interaction": None}
    return {
        "found": True,
        "interaction": {
            "host_protein": result.host_protein,
            "pathogen_protein": result.pathogen_protein,
            "pathogen_name": result.pathogen_name,
            "interaction_type": result.interaction_type,
            "therapeutic_target": result.therapeutic_target,
        },
    }


@app.post("/ppi/combination-targets")
def ppi_combination_targets(payload: _CombinationTargetsRequest) -> dict:
    combinations = suggest_combinations(payload.mutated_genes) if payload.mutated_genes else []
    return {
        "combination_count": len(combinations),
        "combinations": [
            {
                "target_a": c.target_a,
                "target_b": c.target_b,
                "synergy_score": c.synergy_score,
                "rationale": c.rationale,
                "known_combinations": c.known_combinations,
            }
            for c in combinations
        ],
    }


@app.get("/ppi/known-interactions")
def ppi_known_interactions() -> dict:
    import backend.app.modes.ppi_mapping as _ppi_module
    interactions: dict = getattr(_ppi_module, "KNOWN_CANCER_PPIS", {})
    host_pathogen: dict = getattr(_ppi_module, "KNOWN_HOST_PATHOGEN_PPIS", {})
    return {
        "count": len(interactions),
        "interactions": interactions,
        "host_pathogen_count": len(host_pathogen),
        "host_pathogen_interactions": host_pathogen,
    }


# ---------------------------------------------------------------------------
# 8. Enzyme Engineering
# ---------------------------------------------------------------------------

from backend.app.modes.enzyme_engineering import (  # noqa: E402
    model_enzyme_substrate,
    suggest_mutations as enzyme_suggest_mutations,
    design_ert,
    find_prodrug_system,
)


class _EnzymeSubstrateRequest(_BaseModel):
    enzyme_gene: str
    substrate: str


class _EnzymeSuggestMutationsRequest(_BaseModel):
    enzyme_gene: str
    objective: str = "activity"


class _EnzymeDesignERTRequest(_BaseModel):
    enzyme_gene: str
    disease: str


class _EnzymeProdugLookupRequest(_BaseModel):
    enzyme_gene: str


@app.post("/enzyme/model-substrate")
def enzyme_model_substrate_endpoint(payload: _EnzymeSubstrateRequest) -> dict:
    result = model_enzyme_substrate(payload.enzyme_gene, payload.substrate)
    return {
        "enzyme_gene": result.enzyme_gene,
        "substrate_name": result.substrate_name,
        "binding_mode": result.binding_mode,
        "kcat_estimate": result.kcat_estimate,
        "km_estimate_um": result.km_estimate_um,
        "active_site_residues": result.active_site_residues,
    }


@app.post("/enzyme/suggest-mutations")
def enzyme_suggest_mutations_endpoint(payload: _EnzymeSuggestMutationsRequest) -> dict:
    results = enzyme_suggest_mutations(payload.enzyme_gene, objective=payload.objective)
    return {
        "enzyme_gene": payload.enzyme_gene.upper(),
        "objective": payload.objective,
        "suggestion_count": len(results),
        "suggestions": [
            {
                "position": r.position,
                "original_aa": r.original_aa,
                "suggested_aa": r.suggested_aa,
                "rationale": r.rationale,
                "predicted_effect": r.predicted_effect,
                "confidence": r.confidence,
            }
            for r in results
        ],
    }


@app.post("/enzyme/design-ert")
def enzyme_design_ert_endpoint(payload: _EnzymeDesignERTRequest) -> dict:
    result = design_ert(payload.enzyme_gene, payload.disease)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Enzyme '{payload.enzyme_gene}' not found in ERT database")
    return {
        "enzyme_gene": result.enzyme_gene,
        "disease": result.disease,
        "wild_type_issues": result.wild_type_issues,
        "suggested_modifications": result.suggested_modifications,
        "glycosylation_sites": result.glycosylation_sites,
        "half_life_improvement": result.half_life_improvement,
    }


@app.get("/enzyme/known-therapeutic")
def enzyme_known_therapeutic() -> dict:
    import backend.app.modes.enzyme_engineering as _ee
    enzymes: dict = {}
    for attr in ("KNOWN_THERAPEUTIC_ENZYMES", "THERAPEUTIC_ENZYME_DATABASE"):
        if hasattr(_ee, attr):
            enzymes = getattr(_ee, attr)
            break
    return {"count": len(enzymes), "enzymes": enzymes}


@app.get("/enzyme/prodrug-systems")
def enzyme_prodrug_systems() -> dict:
    import backend.app.modes.enzyme_engineering as _ee
    systems: dict = {}
    if hasattr(_ee, "KNOWN_PRODRUG_SYSTEMS"):
        systems = _ee.KNOWN_PRODRUG_SYSTEMS
    return {"count": len(systems), "systems": systems}


@app.post("/enzyme/prodrug-lookup")
def enzyme_prodrug_lookup(payload: _EnzymeProdugLookupRequest) -> dict:
    result = find_prodrug_system(payload.enzyme_gene)
    if result is None:
        return {"found": False, "enzyme_gene": payload.enzyme_gene, "system": None}
    return {
        "found": True,
        "enzyme_gene": payload.enzyme_gene,
        "system": {
            "enzyme": result.enzyme,
            "prodrug": result.prodrug,
            "active_drug": result.active_drug,
            "activation_mechanism": result.activation_mechanism,
            "tumor_selectivity": result.tumor_selectivity,
        },
    }


# ---------------------------------------------------------------------------
# 9. TCR-pMHC
# ---------------------------------------------------------------------------

from backend.app.modes.tcr_pmhc import (  # noqa: E402
    predict_ternary_complex,
    score_tcell_response,
    analyze_cdr_loops,
    run_multiseed_sampling,
    predict_immunogenicity as tcr_predict_immunogenicity,
    get_known_tcr_pmhc_complexes,
    lookup_tcr_pmhc,
    build_immunogenicity_report,
)


class _TCRRequest(_BaseModel):
    peptide: str
    mhc_allele: str
    tcr_sequence: str


class _TCRMultiseedRequest(_BaseModel):
    peptide: str
    mhc_allele: str
    tcr_sequence: str
    n_seeds: int = 100


class _TCRCDRRequest(_BaseModel):
    tcr_sequence: str


@app.post("/tcr-pmhc/predict-ternary")
def tcr_predict_ternary(payload: _TCRRequest) -> dict:
    result = predict_ternary_complex(payload.peptide, payload.mhc_allele, payload.tcr_sequence)
    return {
        "peptide": result.peptide,
        "mhc_allele": result.mhc_allele,
        "tcr_sequence": result.tcr_sequence,
        "mock_pdb_id": result.mock_pdb_id,
        "confidence_score": result.confidence_score,
        "interface_contacts": result.interface_contacts,
        "binding_mode": result.binding_mode,
        "predicted_kd_nm": result.predicted_kd_nm,
        "mhc_peptide_groove_score": result.mhc_peptide_groove_score,
        "tcr_docking_angle_deg": result.tcr_docking_angle_deg,
    }


@app.post("/tcr-pmhc/score-tcell-response")
def tcr_score_tcell_response(payload: _TCRRequest) -> dict:
    complex_result = predict_ternary_complex(payload.peptide, payload.mhc_allele, payload.tcr_sequence)
    result = score_tcell_response(complex_result)
    return {
        "binding_geometry_score": result.binding_geometry_score,
        "predicted_activation": result.predicted_activation,
        "cytokine_profile": result.cytokine_profile,
        "effector_function": result.effector_function,
        "activation_threshold_nm": result.activation_threshold_nm,
        "stimulation_index": result.stimulation_index,
    }


@app.post("/tcr-pmhc/analyze-cdr-loops")
def tcr_analyze_cdr_loops(payload: _TCRCDRRequest) -> dict:
    result = analyze_cdr_loops(payload.tcr_sequence)
    return {
        "cdr3_alpha_length": result.cdr3_alpha_length,
        "cdr3_beta_length": result.cdr3_beta_length,
        "dominant_contact_loop": result.dominant_contact_loop,
        "germline_deviation_cdr3_alpha": result.germline_deviation_cdr3_alpha,
        "germline_deviation_cdr3_beta": result.germline_deviation_cdr3_beta,
        "cdr1_alpha_length": result.cdr1_alpha_length,
        "cdr2_alpha_length": result.cdr2_alpha_length,
        "cdr1_beta_length": result.cdr1_beta_length,
        "cdr2_beta_length": result.cdr2_beta_length,
    }


@app.post("/tcr-pmhc/multiseed-sampling")
def tcr_multiseed_sampling(payload: _TCRMultiseedRequest) -> dict:
    result = run_multiseed_sampling(payload.peptide, payload.mhc_allele, payload.tcr_sequence, n_seeds=payload.n_seeds)
    return {
        "n_seeds": result.n_seeds,
        "mean_score": result.mean_score,
        "std_score": result.std_score,
        "convergence_metric": result.convergence_metric,
        "confidence_interval_95": list(result.confidence_interval_95),
        "top_seed_index": result.top_seed_index,
        "reproducibility_score": result.reproducibility_score,
    }


@app.post("/tcr-pmhc/predict-immunogenicity")
def tcr_predict_immunogenicity_endpoint(payload: _TCRRequest) -> dict:
    result = tcr_predict_immunogenicity(payload.peptide, payload.mhc_allele, payload.tcr_sequence)
    return {
        "immunogenicity_score": result.immunogenicity_score,
        "predicted_response_class": result.predicted_response_class,
        "mhc_binding_component": result.mhc_binding_component,
        "tcr_recognition_component": result.tcr_recognition_component,
        "t_cell_response_component": result.t_cell_response_component,
        "confidence": result.confidence,
        "contributing_factors": result.contributing_factors,
    }


@app.get("/tcr-pmhc/known-complexes")
def tcr_known_complexes() -> dict:
    complexes = get_known_tcr_pmhc_complexes()
    return {"count": len(complexes), "complexes": complexes}


@app.get("/tcr-pmhc/lookup/{peptide}")
def tcr_lookup_peptide(peptide: str) -> dict:
    result = lookup_tcr_pmhc(peptide)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Peptide '{peptide}' not found in TCR-pMHC database")
    return {"found": True, "peptide": peptide, "complex": result}


@app.post("/tcr-pmhc/full-report")
def tcr_full_report(payload: _TCRRequest) -> dict:
    return build_immunogenicity_report(payload.peptide, payload.mhc_allele, payload.tcr_sequence)


# ---------------------------------------------------------------------------
# 10. Conformational Ensemble
# ---------------------------------------------------------------------------

from backend.app.conformational_ensemble import (  # noqa: E402
    sample_conformational_ensemble,
    get_dominant_state,
    calculate_flexibility_profile,
)


class _EnsembleSamplingRequest(_BaseModel):
    sequence: str
    n_samples: int = 100


class _EnsembleDominantRequest(_BaseModel):
    sequence: str


class _EnsembleFlexibilityRequest(_BaseModel):
    sequence: str


@app.post("/ensemble/conformational-sampling")
def ensemble_conformational_sampling(payload: _EnsembleSamplingRequest) -> dict:
    result = sample_conformational_ensemble(payload.sequence, n_samples=payload.n_samples)
    return {
        "sequence": result.sequence,
        "n_samples": result.n_samples,
        "n_clusters": result.n_clusters,
        "diversity_score": result.diversity_score,
        "converged": result.converged,
        "states": [
            {
                "state_id": s.state_id,
                "population_weight": s.population_weight,
                "plddt_mean": s.plddt_mean,
                "rmsd_to_reference": s.rmsd_to_reference,
            }
            for s in result.states
        ],
    }


@app.post("/ensemble/dominant-state")
def ensemble_dominant_state(payload: _EnsembleDominantRequest) -> dict:
    result = sample_conformational_ensemble(payload.sequence)
    dominant = get_dominant_state(result)
    return {
        "state_id": dominant.state_id,
        "population_weight": dominant.population_weight,
        "plddt_mean": dominant.plddt_mean,
        "rmsd_to_reference": dominant.rmsd_to_reference,
    }


@app.post("/ensemble/flexibility-profile")
def ensemble_flexibility_profile(payload: _EnsembleFlexibilityRequest) -> dict:
    result = sample_conformational_ensemble(payload.sequence)
    profile = calculate_flexibility_profile(result)
    return {"profile": profile}


# ---------------------------------------------------------------------------
# 11. MD Handoff
# ---------------------------------------------------------------------------

from backend.app.md_handoff import (  # noqa: E402
    export_for_openmm,
    export_for_gromacs,
    validate_structure_for_md,
    MDExportConfig,
)


class _MDExportRequest(_BaseModel):
    pdb_data: str
    temperature_k: float = 300.0
    force_field: str = "amber14"
    water_model: str = "tip3p"
    box_padding_nm: float = 1.0
    ion_concentration_mol: float = 0.15
    simulation_ns: float = 100.0


class _MDValidateRequest(_BaseModel):
    pdb_data: str


@app.post("/md/export-openmm")
def md_export_openmm(payload: _MDExportRequest) -> dict:
    config = MDExportConfig(
        temperature_k=payload.temperature_k,
        force_field=payload.force_field,
        water_model=payload.water_model,
        box_padding_nm=payload.box_padding_nm,
        ion_concentration_mol=payload.ion_concentration_mol,
        simulation_ns=payload.simulation_ns,
    )
    result = export_for_openmm(payload.pdb_data, config)
    return {
        "format": result.format,
        "config_script": result.config_script,
        "warnings": result.warnings,
        "estimated_runtime_hours": result.estimated_runtime_hours,
    }


@app.post("/md/export-gromacs")
def md_export_gromacs(payload: _MDExportRequest) -> dict:
    config = MDExportConfig(
        temperature_k=payload.temperature_k,
        force_field=payload.force_field,
        water_model=payload.water_model,
        box_padding_nm=payload.box_padding_nm,
        ion_concentration_mol=payload.ion_concentration_mol,
        simulation_ns=payload.simulation_ns,
    )
    result = export_for_gromacs(payload.pdb_data, config)
    return {
        "format": result.format,
        "config_script": result.config_script,
        "warnings": result.warnings,
        "estimated_runtime_hours": result.estimated_runtime_hours,
    }


@app.post("/md/validate-structure")
def md_validate_structure(payload: _MDValidateRequest) -> dict:
    validation = validate_structure_for_md(payload.pdb_data)
    return {"validation": validation}


# ---------------------------------------------------------------------------
# 12. Workflow Integration
# ---------------------------------------------------------------------------

from backend.app.workflow_integration import (  # noqa: E402
    compute_ensemble_heatmap,
    recommend_backend,
    run_batch_prediction,
    normalize_pdb,
    pin_version,
    check_all_versions,
    get_version_manifest,
    TOOL_VERSIONS,
    TASK_CLASS_BENCHMARKS,
)


class _EnsembleHeatmapRequest(_BaseModel):
    sequence: str
    backend_names: list[str] = ["mock"]

    @field_validator("sequence")
    @classmethod
    def sequence_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence must not be empty")
        return v


class _RecommendBackendRequest(_BaseModel):
    task_class: str

    @field_validator("task_class")
    @classmethod
    def valid_task_class(cls, v: str) -> str:
        if v not in TASK_CLASS_BENCHMARKS:
            raise ValueError(f"Unknown task_class '{v}'. Valid: {list(TASK_CLASS_BENCHMARKS)}")
        return v


class _BatchPredictRequest(_BaseModel):
    sequences: list[str]
    backend_name: str = "mock"

    @field_validator("sequences")
    @classmethod
    def sequences_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("sequences must not be empty")
        return v


class _NormalizePDBRequest(_BaseModel):
    pdb_data: str
    chain_rename: _Optional[dict] = None

    @field_validator("pdb_data")
    @classmethod
    def pdb_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("pdb_data must not be empty")
        return v


class _CheckVersionsRequest(_BaseModel):
    tool_names: _Optional[list[str]] = None


@app.post("/workflow/ensemble-heatmap")
def workflow_ensemble_heatmap(payload: _EnsembleHeatmapRequest) -> dict:
    result = compute_ensemble_heatmap(payload.sequence, payload.backend_names)
    return {
        "sequence": result.sequence,
        "per_residue": [
            {
                "residue_index": r.residue_index,
                "residue_name": r.residue_name,
                "plddt_values": r.plddt_values,
                "mean_plddt": r.mean_plddt,
                "std_plddt": r.std_plddt,
                "disagreement_level": r.disagreement_level,
            }
            for r in result.per_residue
        ],
        "overall_disagreement": result.overall_disagreement,
        "high_disagreement_regions": result.high_disagreement_regions,
    }


@app.post("/workflow/recommend-backend")
def workflow_recommend_backend(payload: _RecommendBackendRequest) -> dict:
    result = recommend_backend(payload.task_class)
    return {
        "task_class": result.task_class,
        "recommended": result.recommended,
        "accuracy_estimate": result.accuracy_estimate,
        "reasoning": result.reasoning,
        "alternatives": result.alternatives,
    }


@app.post("/workflow/batch-predict")
def workflow_batch_predict(payload: _BatchPredictRequest) -> dict:
    result = run_batch_prediction(payload.sequences, payload.backend_name)
    return {
        "total": result.total,
        "completed": result.completed,
        "provenances": [
            {
                "sequence_id": p.sequence_id,
                "input_hash": p.input_hash,
                "backend_version": p.backend_version,
                "timestamp": p.timestamp,
                "runtime_seconds": p.runtime_seconds,
            }
            for p in result.provenances
        ],
        "manifest_hash": result.manifest_hash,
    }


@app.post("/workflow/normalize-pdb")
def workflow_normalize_pdb(payload: _NormalizePDBRequest) -> dict:
    result = normalize_pdb(payload.pdb_data, chain_rename=payload.chain_rename)
    return {
        "n_atoms": result.n_atoms,
        "n_residues": result.n_residues,
        "chain_map": result.chain_map,
        "warnings": result.warnings,
        "data": result.data,
        "format": result.format,
    }


@app.get("/workflow/tool-versions")
def workflow_tool_versions() -> dict:
    return {"tool_versions": TOOL_VERSIONS}


@app.get("/workflow/version-pin/{tool_name}")
def workflow_version_pin(tool_name: str) -> dict:
    if tool_name not in TOOL_VERSIONS:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    pin = pin_version(tool_name)
    return {
        "tool_name": pin.tool_name,
        "pinned_version": pin.pinned_version,
        "current_version": pin.current_version,
        "superseded": pin.superseded,
        "supersession_warning": pin.supersession_warning,
    }


@app.get("/workflow/version-manifest")
def workflow_version_manifest() -> dict:
    return get_version_manifest()


@app.post("/workflow/check-versions")
def workflow_check_versions(payload: _CheckVersionsRequest) -> dict:
    all_pins = check_all_versions()
    if payload.tool_names:
        pins = [p for p in all_pins if p.tool_name in payload.tool_names]
    else:
        pins = all_pins
    superseded_count = sum(1 for p in pins if p.superseded)
    return {
        "total": len(pins),
        "superseded_count": superseded_count,
        "pins": [
            {
                "tool_name": p.tool_name,
                "pinned_version": p.pinned_version,
                "current_version": p.current_version,
                "superseded": p.superseded,
                "supersession_warning": p.supersession_warning,
            }
            for p in pins
        ],
    }


# ---------------------------------------------------------------------------
# 13. Clinical Variants
# ---------------------------------------------------------------------------

from backend.app.clinical_variants import (  # noqa: E402
    score_acmg_criteria,
    get_vus_queue,
    rescore_vus,
    rescore_all_vus,
    lookup_clinvar,
    map_clinvar_to_structure,
    get_clinvar_stats,
)


class _ACMGScoreRequest(_BaseModel):
    gene: str
    variant: str
    alphamissense_score: _Optional[float] = None
    conservation_score: _Optional[float] = None
    structural_context: _Optional[dict] = None


class _ClinVarLookupRequest(_BaseModel):
    gene: str
    variant: _Optional[str] = None


class _ClinVarMapRequest(_BaseModel):
    gene: str


_SAFETY_LABEL_CLINICAL = "RESEARCH USE ONLY — Not validated for clinical decision-making"


@app.post("/clinical/acmg-score")
def clinical_acmg_score(payload: _ACMGScoreRequest) -> dict:
    result = score_acmg_criteria(
        gene=payload.gene,
        variant=payload.variant,
        alphamissense_score=payload.alphamissense_score,
        conservation_score=payload.conservation_score,
        structural_context=payload.structural_context,
    )
    return {
        "gene": result.gene,
        "variant": result.variant,
        "pathogenicity_class": result.pathogenicity_class,
        "overall_score": result.overall_score,
        "evidences": [
            {
                "criterion": e.criterion,
                "met": e.met,
                "strength": e.strength,
                "evidence_source": e.evidence_source,
                "detail": e.detail,
            }
            for e in result.evidences
        ],
        "safety_label": _SAFETY_LABEL_CLINICAL,
    }


@app.get("/clinical/vus-queue")
def clinical_vus_queue() -> dict:
    queue = get_vus_queue()
    return {
        "queue": [
            {
                "variant_id": e.variant_id,
                "gene": e.gene,
                "variant": e.variant,
                "current_class": e.current_class,
                "pending_reclassification": e.pending_reclassification,
                "last_scored": e.last_scored,
            }
            for e in queue
        ]
    }


@app.post("/clinical/rescore-vus/{variant_id}")
def clinical_rescore_vus(variant_id: str) -> dict:
    try:
        result = rescore_vus(variant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"VUS '{variant_id}' not found")
    return {
        "variant_id": result.variant_id,
        "old_class": result.old_class,
        "new_class": result.new_class,
        "evidence_delta": result.evidence_delta,
        "confidence": result.confidence,
        "auto_reclassified": result.auto_reclassified,
    }


@app.post("/clinical/rescore-all-vus")
def clinical_rescore_all_vus() -> dict:
    results = rescore_all_vus()
    return {
        "results": [
            {
                "variant_id": r.variant_id,
                "old_class": r.old_class,
                "new_class": r.new_class,
                "evidence_delta": r.evidence_delta,
            }
            for r in results
        ],
        "summary": {
            "total": len(results),
            "reclassified": sum(1 for r in results if r.old_class != r.new_class),
        },
    }


@app.get("/clinical/clinvar/lookup/{gene}")
def clinical_clinvar_lookup_gene(gene: str) -> dict:
    entries = lookup_clinvar(gene)
    return {
        "gene": gene.upper(),
        "entries": [
            {
                "clinvar_id": e.clinvar_id,
                "gene": e.gene,
                "variant": e.variant,
                "significance": e.significance,
                "review_stars": e.review_stars,
                "conditions": e.conditions,
                "last_updated": e.last_updated,
            }
            for e in entries
        ],
    }


@app.post("/clinical/clinvar/lookup")
def clinical_clinvar_lookup_post(payload: _ClinVarLookupRequest) -> dict:
    entries = lookup_clinvar(payload.gene, variant=payload.variant)
    return {
        "gene": payload.gene.upper(),
        "entries": [
            {
                "clinvar_id": e.clinvar_id,
                "gene": e.gene,
                "variant": e.variant,
                "significance": e.significance,
                "review_stars": e.review_stars,
                "conditions": e.conditions,
                "last_updated": e.last_updated,
            }
            for e in entries
        ],
    }


@app.post("/clinical/clinvar/map-to-structure")
def clinical_clinvar_map_to_structure(payload: _ClinVarMapRequest) -> dict:
    result = map_clinvar_to_structure(payload.gene)
    return {
        "gene": result.gene,
        "pathogenic_hotspots": result.pathogenic_hotspots,
        "domain_summary": result.domain_summary,
        "total_variants": result.total_variants,
    }


@app.get("/clinical/clinvar/stats")
def clinical_clinvar_stats() -> dict:
    stats = get_clinvar_stats()
    return {**stats, "safety_label": _SAFETY_LABEL_CLINICAL}


# ---------------------------------------------------------------------------
# 14. Compliance
# ---------------------------------------------------------------------------

from backend.app.compliance import (  # noqa: E402
    IRBSubmission,
    check_irb_readiness,
    assess_hipaa_compliance,
    separate_phi_fields,
    audit_log as compliance_audit_log,
    watermark_pdb,
    watermark_report,
    attest_credentials,
    check_mode_access,
    DataResidency,
    get_residency_config,
    ProfessionalCredential,
)


class _IRBCheckRequest(_BaseModel):
    institution: str
    irb_protocol_number: str
    pi_name: str
    data_use_agreement_signed: bool = False
    human_subjects_approval: bool = False


class _HIPAAAssessRequest(_BaseModel):
    data_fields: list[str]


class _HIPAASeparateRequest(_BaseModel):
    record: dict


class _AuditAppendRequest(_BaseModel):
    action: str
    user: str
    details: dict = {}


class _WatermarkPDBRequest(_BaseModel):
    pdb_data: str


class _WatermarkReportRequest(_BaseModel):
    report_text: str
    format: str = "html"


class _AttestCredentialsRequest(_BaseModel):
    user_id: str
    credential: str
    institution: str


class _CheckModeAccessRequest(_BaseModel):
    user_id: str
    mode: str


_attestation_store: dict = {}


@app.post("/compliance/irb-check")
def compliance_irb_check(payload: _IRBCheckRequest) -> dict:
    submission = IRBSubmission(
        institution=payload.institution,
        irb_protocol_number=payload.irb_protocol_number,
        pi_name=payload.pi_name,
        data_use_agreement_signed=payload.data_use_agreement_signed,
        human_subjects_approval=payload.human_subjects_approval,
    )
    result = check_irb_readiness(submission)
    return {
        "passed": result.passed,
        "missing_requirements": result.missing_requirements,
        "institution": result.institution,
        "irb_protocol": result.irb_protocol,
        "timestamp": result.timestamp,
    }


@app.post("/compliance/hipaa-assess")
def compliance_hipaa_assess(payload: _HIPAAAssessRequest) -> dict:
    result = assess_hipaa_compliance(payload.data_fields)
    return {
        "compliant": result.compliant,
        "safeguards": [
            {
                "field_type": s.field_type.value if hasattr(s.field_type, "value") else str(s.field_type),
                "access_level": s.access_level,
                "encrypted": s.encrypted,
                "audit_logged": s.audit_logged,
                "retention_days": s.retention_days,
            }
            for s in result.safeguards
        ],
        "violations": result.violations,
        "recommendations": result.recommendations,
    }


@app.post("/compliance/hipaa-separate-phi")
def compliance_hipaa_separate_phi(payload: _HIPAASeparateRequest) -> dict:
    phi_fields, non_phi_fields = separate_phi_fields(payload.record)
    return {"phi_fields": phi_fields, "non_phi_fields": non_phi_fields}


@app.post("/compliance/audit/append")
def compliance_audit_append(payload: _AuditAppendRequest) -> dict:
    entry = compliance_audit_log.append(payload.action, payload.user, payload.details)
    return {
        "entry_id": entry.entry_id,
        "action": entry.action,
        "user": entry.user,
        "timestamp": entry.timestamp,
        "entry_hash": entry.entry_hash,
    }


@app.get("/compliance/audit/verify")
def compliance_audit_verify() -> dict:
    valid, errors = compliance_audit_log.verify_chain()
    return {"valid": valid, "errors": errors, "entry_count": len(compliance_audit_log.get_entries())}


@app.get("/compliance/audit/entries")
def compliance_audit_entries() -> dict:
    entries = compliance_audit_log.get_entries()
    return {
        "entries": [
            {
                "entry_id": e.entry_id,
                "action": e.action,
                "user": e.user,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]
    }


@app.post("/compliance/watermark-pdb")
def compliance_watermark_pdb(payload: _WatermarkPDBRequest) -> dict:
    result = watermark_pdb(payload.pdb_data)
    return {
        "data": result.data,
        "format": result.format,
        "watermark": result.watermark,
        "watermark_hash": result.watermark_hash,
    }


@app.post("/compliance/watermark-report")
def compliance_watermark_report(payload: _WatermarkReportRequest) -> dict:
    result = watermark_report(payload.report_text, format=payload.format)
    return {
        "data": result.data,
        "format": result.format,
        "watermark": result.watermark,
        "watermark_hash": result.watermark_hash,
    }


@app.post("/compliance/attest-credentials")
def compliance_attest_credentials(payload: _AttestCredentialsRequest) -> dict:
    try:
        credential = ProfessionalCredential(payload.credential)
    except ValueError:
        credential = ProfessionalCredential.student
    result = attest_credentials(payload.user_id, credential, payload.institution)
    _attestation_store[payload.user_id] = result
    return {
        "user_id": result.user_id,
        "credential": result.credential.value if hasattr(result.credential, "value") else str(result.credential),
        "institution": result.institution,
        "modes_unlocked": result.modes_unlocked,
        "attested_at": result.attested_at,
    }


@app.post("/compliance/check-mode-access")
def compliance_check_mode_access(payload: _CheckModeAccessRequest) -> dict:
    allowed, reason = check_mode_access(payload.user_id, payload.mode)
    return {"user_id": payload.user_id, "mode": payload.mode, "allowed": allowed, "reason": reason}


@app.get("/compliance/residency/{residency_level}")
def compliance_residency(residency_level: str) -> dict:
    try:
        residency = DataResidency(residency_level)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid residency level '{residency_level}'")
    config = get_residency_config(residency)
    return {
        "residency": config.residency.value if hasattr(config.residency, "value") else str(config.residency),
        "allowed_backends": config.allowed_backends,
        "blocked_backends": config.blocked_backends,
        "reason": config.reason,
    }


# ---------------------------------------------------------------------------
# 15. Reproducibility
# ---------------------------------------------------------------------------

from backend.app.reproducibility import (  # noqa: E402
    create_manifest,
    verify_manifest as repro_verify_manifest,
    store_manifest,
    get_manifest,
    list_manifests,
    capture_environment,
    create_fair_report,
    validate_fair_compliance,
    FAIRMetadata,
    TOOL_VERSION_REGISTRY,
)


class _CreateManifestRequest(_BaseModel):
    tool_names: list[str] = []
    inputs: dict = {}
    outputs: dict = {}
    seeds: dict = {}


class _VerifyManifestRequest(_BaseModel):
    manifest_id: str


class _FAIRCreateReportRequest(_BaseModel):
    prediction_data: dict
    title: str = ""
    description: str = ""
    creators: list[str] = []
    keywords: list[str] = []


@app.post("/reproducibility/create-manifest")
def reproducibility_create_manifest(payload: _CreateManifestRequest) -> dict:
    manifest = create_manifest(
        tool_names=payload.tool_names,
        inputs=payload.inputs,
        outputs=payload.outputs,
        seeds=payload.seeds,
    )
    store_manifest(manifest)
    return {
        "manifest_id": manifest.manifest_id,
        "created_at": manifest.created_at,
        "reproducibility_score": manifest.reproducibility_score,
        "rerun_command": manifest.rerun_command,
    }


@app.get("/reproducibility/manifests")
def reproducibility_list_manifests() -> list:
    return list_manifests()


@app.get("/reproducibility/manifests/{manifest_id}")
def reproducibility_get_manifest(manifest_id: str) -> dict:
    manifest = get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest '{manifest_id}' not found")
    return {
        "manifest_id": manifest.manifest_id,
        "created_at": manifest.created_at,
        "reproducibility_score": manifest.reproducibility_score,
        "rerun_command": manifest.rerun_command,
    }


@app.post("/reproducibility/verify-manifest")
def reproducibility_verify_manifest(payload: _VerifyManifestRequest) -> dict:
    manifest = get_manifest(payload.manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Manifest '{payload.manifest_id}' not found")
    ok, issues = repro_verify_manifest(manifest)
    return {"ok": ok, "issues": issues, "manifest_id": payload.manifest_id}


@app.post("/reproducibility/fair/create-report")
def reproducibility_fair_create_report(payload: _FAIRCreateReportRequest) -> dict:
    import backend.app.reproducibility as _repro
    metadata = _repro.generate_fair_metadata(
        title=payload.title,
        description=payload.description,
        creators=payload.creators,
        keywords=payload.keywords,
    )
    report = create_fair_report(payload.prediction_data, metadata)
    return {
        "persistent_id": report.metadata.persistent_id,
        "title": report.metadata.title,
        "description": report.metadata.description,
        "creators": report.metadata.creators,
        "keywords": report.metadata.keywords,
        "machine_readable_json_ld": report.machine_readable_json_ld,
        "deposition_ready": report.deposition_ready,
        "suggested_repository": report.suggested_repository,
    }


@app.post("/reproducibility/fair/validate")
def reproducibility_fair_validate(payload: dict) -> dict:
    import backend.app.reproducibility as _repro
    # Re-create a report from the payload data to run compliance checks
    metadata = _repro.generate_fair_metadata(
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        creators=payload.get("creators", []),
        keywords=payload.get("keywords", []),
    )
    report = _repro.create_fair_report(payload.get("prediction_data", {}), metadata)
    return validate_fair_compliance(report)


@app.get("/reproducibility/environment")
def reproducibility_environment() -> dict:
    env = capture_environment()
    return {
        "python_version": env.python_version,
        "platform": env.platform,
        "cpu_count": env.cpu_count,
        "gpu_available": env.gpu_available,
        "env_hash": env.env_hash,
    }


@app.get("/reproducibility/tool-registry")
def reproducibility_tool_registry() -> dict:
    return TOOL_VERSION_REGISTRY


# ---------------------------------------------------------------------------
# 16. Structure Analysis
# ---------------------------------------------------------------------------

from backend.app.structure_analysis import (  # noqa: E402
    analyze_disorder,
    detect_low_plddt_regions,
    escalate_to_idr_analysis,
    assess_ptm_impact,
    find_nearby_ptms,
    predict_epistatic_effect,
    detect_fold_switching_risk,
    IDR_PLDDT_THRESHOLD,
    KNOWN_PTM_SITES,
    EpistaticVariant,
)
import backend.app.structure_analysis as _structure_analysis_mod  # noqa: E402

_STRUCTURE_SAFETY_LABEL = "Research only — not for clinical use"
_PTM_IMPACT_DESC = getattr(_structure_analysis_mod, "_PTM_IMPACT_DESC", {})


class _AnalyzeDisorderRequest(_BaseModel):
    sequence: str
    plddt_values: _Optional[list[float]] = None


class _DetectLowPLDDTRequest(_BaseModel):
    sequence: str
    plddt_values: _Optional[list[float]] = None
    threshold: float = IDR_PLDDT_THRESHOLD


class _PTMImpactRequest(_BaseModel):
    gene: str
    variant: str


class _EpistaticPredictionRequest(_BaseModel):
    gene: str = ""
    variants: list[dict] = []

    @field_validator("variants")
    @classmethod
    def variants_not_empty(cls, v: list) -> list:
        if len(v) == 0:
            raise ValueError("variants must not be empty")
        if len(v) > 8:
            raise ValueError("too many variants (max 8)")
        return v


class _FoldSwitchingRiskRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def sequence_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence must not be empty")
        return v


class _FullStructureAnalysisRequest(_BaseModel):
    sequence: str
    gene: _Optional[str] = None
    variant: _Optional[str] = None

    @field_validator("sequence")
    @classmethod
    def sequence_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence must not be empty")
        return v


@app.post("/structure/analyze-disorder")
def structure_analyze_disorder(payload: _AnalyzeDisorderRequest) -> dict:
    if payload.plddt_values is not None:
        low_regions = detect_low_plddt_regions(payload.sequence, payload.plddt_values)
        result = escalate_to_idr_analysis(payload.sequence, low_regions)
    else:
        result = analyze_disorder(payload.sequence)
    return {
        "idr_regions": [
            {
                "start": r.start,
                "end": r.end,
                "score": r.disorder_score,
                "classification": r.disorder_type,
            }
            for r in result.idr_regions
        ],
        "idr_fraction": result.idr_fraction,
        "total_residues": result.total_residues,
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.post("/structure/detect-low-plddt")
def structure_detect_low_plddt(payload: _DetectLowPLDDTRequest) -> dict:
    result = detect_low_plddt_regions(payload.sequence, plddt_values=payload.plddt_values)
    return {
        "low_plddt_regions": [
            {"start": r[0], "end": r[1]}
            for r in result
        ],
        "region_count": len(result),
        "threshold": payload.threshold,
    }


@app.post("/structure/ptm-impact")
def structure_ptm_impact(payload: _PTMImpactRequest) -> dict:
    result = assess_ptm_impact(payload.gene, payload.variant)
    return {
        "gene": result.gene,
        "variant": payload.variant,
        "ptm_disrupted": result.ptm_disrupted,
        "affected_ptm_sites": [
            {
                "position": s.position,
                "ptm_type": s.ptm_type,
                "residue": s.residue,
                "functional_impact": s.functional_impact,
            }
            for s in result.nearby_ptms
        ],
        "impact_score": result.impact_score,
        "recommendation": result.recommendation,
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.get("/structure/ptm-sites/{gene}")
def structure_ptm_sites(gene: str) -> dict:
    gene_upper = gene.upper()
    raw_sites = KNOWN_PTM_SITES.get(gene_upper, [])
    if not raw_sites:
        raise HTTPException(status_code=404, detail=f"No PTM sites found for gene '{gene_upper}'")
    return {
        "gene": gene_upper,
        "count": len(raw_sites),
        "sites": [
            {
                "position": s["position"],
                "modification_type": s["type"],
                "residue": s["residue"],
                "functional_role": _PTM_IMPACT_DESC.get(s["type"], "modifies protein function"),
            }
            for s in raw_sites
        ],
    }


@app.post("/structure/epistatic-prediction")
def structure_epistatic_prediction(payload: _EpistaticPredictionRequest) -> dict:
    epistatic_variants = [
        EpistaticVariant(
            position=v.get("position", 0),
            ref_aa=v.get("ref_aa", "A"),
            alt_aa=v.get("alt_aa", "V"),
        )
        for v in payload.variants
    ]
    result = predict_epistatic_effect(epistatic_variants, gene=payload.gene or "")
    return {
        "epistatic_effect": result.epistatic_effect,
        "epistatic_prediction": result.epistatic_prediction,
        "additive_prediction": result.additive_prediction,
        "individual_scores": result.individual_scores,
        "interaction_score": result.interaction_score,
        "confidence": result.confidence,
    }


@app.post("/structure/fold-switching-risk")
def structure_fold_switching_risk(payload: _FoldSwitchingRiskRequest) -> dict:
    result = detect_fold_switching_risk(payload.sequence)
    return {
        "risk_score": result.risk_score,
        "likely_fold_switcher": result.likely_fold_switcher,
        "features": result.features,
        "known_match": result.known_match,
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.get("/structure/known-fold-switchers")
def structure_known_fold_switchers() -> dict:
    import backend.app.structure_analysis as _sa
    switchers: dict = {}
    if hasattr(_sa, "KNOWN_FOLD_SWITCHERS"):
        switchers = _sa.KNOWN_FOLD_SWITCHERS
    return {
        "fold_switchers": switchers,
        "count": len(switchers),
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.post("/structure/full-analysis")
def structure_full_analysis(payload: _FullStructureAnalysisRequest) -> dict:
    disorder = analyze_disorder(payload.sequence)
    fold_switch = detect_fold_switching_risk(payload.sequence)
    ptm_impact = None
    if payload.gene and payload.variant:
        ptm_result = assess_ptm_impact(payload.gene, payload.variant)
        ptm_impact = {
            "gene": ptm_result.gene,
            "variant_position": ptm_result.variant_position,
            "ptm_disrupted": ptm_result.ptm_disrupted,
        }
    return {
        "disorder_analysis": {
            "idr_fraction": disorder.idr_fraction,
            "idr_regions": len(disorder.idr_regions),
        },
        "fold_switch_warning": {
            "risk_score": fold_switch.risk_score,
            "likely_fold_switcher": fold_switch.likely_fold_switcher,
        },
        "ptm_impact": ptm_impact,
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


# ---------------------------------------------------------------------------
# 17. Structure Analysis Ext
# ---------------------------------------------------------------------------

from backend.app.structure_analysis_ext import (  # noqa: E402
    run_msa_ensemble,
    generate_msa_subsamples,
    predict_dynamics,
    annotate_structure_with_dynamics,
    get_calibration_curve,
    calibrate_confidence,
    classify_protein,
    auto_calibrate,
    ProteinClass,
)


class _MSAEnsembleRequest(_BaseModel):
    sequence: str
    n_subsamples: int = 20


class _MSASubsamplesRequest(_BaseModel):
    sequence: str
    n_subsamples: int = 20
    depth_min: _Optional[int] = None
    depth_max: _Optional[int] = None


class _DynamicsProfileRequest(_BaseModel):
    sequence: str


class _AnnotateDynamicsRequest(_BaseModel):
    pdb_data: str
    sequence: str


class _CalibrateConfidenceRequest(_BaseModel):
    plddt: float
    protein_class: str


class _ClassifyProteinRequest(_BaseModel):
    sequence: str


class _AutoCalibrateRequest(_BaseModel):
    sequence: str
    plddt: float


@app.post("/structure-ext/msa-ensemble")
def structure_ext_msa_ensemble(payload: _MSAEnsembleRequest) -> dict:
    result = run_msa_ensemble(payload.sequence, n_subsamples=payload.n_subsamples)
    return {
        "sequence": result.sequence,
        "n_subsamples": result.n_subsamples,
        "n_clusters": result.n_clusters,
        "functional_diversity": result.functional_diversity,
        "ground_state_confidence": result.ground_state_confidence,
        "states": [
            {
                "state_id": s.state_id,
                "plddt_mean": s.plddt_mean,
                "rmsd_to_consensus": s.rmsd_to_consensus,
                "population_weight": s.population_weight,
                "structural_class": s.structural_class,
            }
            for s in result.states
        ],
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.post("/structure-ext/msa-subsamples")
def structure_ext_msa_subsamples(payload: _MSASubsamplesRequest) -> dict:
    kwargs: dict = {"n_subsamples": payload.n_subsamples}
    if payload.depth_min is not None and payload.depth_max is not None:
        kwargs["depth_range"] = (payload.depth_min, payload.depth_max)
    subsamples = generate_msa_subsamples(payload.sequence, **kwargs)
    return {
        "n_subsamples": len(subsamples),
        "subsamples": [
            {
                "subsample_id": s.subsample_id,
                "msa_depth": s.msa_depth,
                "diversity_score": s.diversity_score,
            }
            for s in subsamples
        ],
    }


@app.post("/structure-ext/dynamics-profile")
def structure_ext_dynamics_profile(payload: _DynamicsProfileRequest) -> dict:
    profile = predict_dynamics(payload.sequence)
    return {
        "sequence": profile.sequence,
        "residues": [
            {
                "index": r.index,
                "residue": r.residue,
                "backbone_flexibility": r.backbone_flexibility,
                "sidechain_flexibility": r.sidechain_flexibility,
                "predicted_bfactor": r.predicted_bfactor,
                "dynamics_class": r.dynamics_class,
            }
            for r in profile.residues
        ],
        "mean_flexibility": profile.mean_flexibility,
        "flexible_regions": profile.flexible_regions,
        "hinge_residues": profile.hinge_residues,
        "overall_dynamics_class": profile.overall_dynamics_class,
    }


@app.post("/structure-ext/annotate-dynamics")
def structure_ext_annotate_dynamics(payload: _AnnotateDynamicsRequest) -> dict:
    profile = predict_dynamics(payload.sequence)
    annotated_pdb = annotate_structure_with_dynamics(payload.pdb_data, profile)
    return {"annotated_pdb": annotated_pdb}


@app.get("/structure-ext/calibration/{protein_class}")
def structure_ext_calibration(protein_class: str) -> dict:
    try:
        pc = ProteinClass(protein_class)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown protein class '{protein_class}'")
    curve = get_calibration_curve(pc)
    return {
        "protein_class": curve.protein_class.value if hasattr(curve.protein_class, "value") else str(curve.protein_class),
        "plddt_bins": curve.plddt_bins,
        "actual_accuracy": curve.actual_accuracy,
        "n_benchmarked": curve.n_benchmarked,
        "calibration_error": curve.calibration_error,
        "overconfident_range": curve.overconfident_range,
        "underconfident_range": curve.underconfident_range,
    }


@app.post("/structure-ext/calibrate-confidence")
def structure_ext_calibrate_confidence(payload: _CalibrateConfidenceRequest) -> dict:
    try:
        pc = ProteinClass(payload.protein_class)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown protein class '{payload.protein_class}'")
    return calibrate_confidence(payload.plddt, pc)


@app.post("/structure-ext/classify-protein")
def structure_ext_classify_protein(payload: _ClassifyProteinRequest) -> dict:
    pc = classify_protein(payload.sequence)
    return {"protein_class": pc.value if hasattr(pc, "value") else str(pc)}


@app.post("/structure-ext/auto-calibrate")
def structure_ext_auto_calibrate(payload: _AutoCalibrateRequest) -> dict:
    return auto_calibrate(payload.sequence, payload.plddt)


# ---------------------------------------------------------------------------
# 18. Drug Discovery Ext
# ---------------------------------------------------------------------------

from backend.app.drug_discovery_ext import (  # noqa: E402
    predict_pockets,
    dock_compound,
    run_drug_pipeline,
    detect_cryptic_sites,
    predict_allostery,
    run_therapeutic_reasoning,
    predict_ddg,
    batch_predict_ddg,
)


class _PocketPredictionRequest(_BaseModel):
    pdb_data: str
    gene: str = ""


class _DockCompoundRequest(_BaseModel):
    pdb_data: str
    gene: str = ""
    compound_smiles: str
    compound_name: str = ""


class _FullPipelineRequest(_BaseModel):
    target_gene: str
    compound_library: _Optional[list[dict]] = None


class _CrypticSitesRequest(_BaseModel):
    sequence: str
    gene: str = ""


class _AllosteryRequest(_BaseModel):
    sequence: str
    gene: str = ""


class _TherapeuticReasoningRequest(_BaseModel):
    gene: str
    variant: str


class _DDGPredictRequest(_BaseModel):
    gene: str
    variant: str


class _BatchDDGRequest(_BaseModel):
    gene: str
    variants: list[str]

    @field_validator("variants")
    @classmethod
    def variants_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("variants must not be empty")
        return v


@app.post("/drug-ext/pocket-prediction")
def drug_ext_pocket_prediction(payload: _PocketPredictionRequest) -> dict:
    pockets = predict_pockets(payload.pdb_data, gene=payload.gene)
    return {
        "gene": payload.gene,
        "pocket_count": len(pockets),
        "pockets": [
            {
                "pocket_id": p.pocket_id,
                "volume_angstrom3": p.volume_angstrom3,
                "druggability_score": p.druggability_score,
                "residues": p.residues,
                "center": list(p.center),
                "rank": p.rank,
            }
            for p in pockets
        ],
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.post("/drug-ext/dock-compound")
def drug_ext_dock_compound(payload: _DockCompoundRequest) -> dict:
    # Need a pocket to dock against; predict pockets first
    pockets = predict_pockets(payload.pdb_data, gene=payload.gene)
    if not pockets:
        raise HTTPException(status_code=400, detail="No pockets found for docking")
    top_pocket = pockets[0]
    result = dock_compound(top_pocket, payload.compound_smiles, payload.compound_name)
    return {
        "gene": payload.gene,
        "compound_name": result.compound_name,
        "docking_result": {
            "binding_energy_kcal": result.binding_energy_kcal,
            "pose_rmsd": result.pose_rmsd,
            "contact_residues": result.contact_residues,
            "score": result.score,
        },
    }


@app.post("/drug-ext/full-pipeline")
def drug_ext_full_pipeline(payload: _FullPipelineRequest) -> dict:
    result = run_drug_pipeline(payload.target_gene, compound_library=payload.compound_library)
    return {
        "target_gene": result.target_gene,
        "best_compound": result.best_compound,
        "pocket_count": len(result.pockets),
        "candidates_screened": len(result.docking_results),
        "pipeline_runtime_sec": result.pipeline_runtime_sec,
    }


@app.post("/drug-ext/cryptic-sites")
def drug_ext_cryptic_sites(payload: _CrypticSitesRequest) -> dict:
    sites = detect_cryptic_sites(payload.sequence, gene=payload.gene)
    return {
        "cryptic_sites": [
            {
                "site_id": s.site_id,
                "residues": s.residues,
                "opening_probability": s.opening_probability,
                "trigger": s.trigger,
                "druggability_if_open": s.druggability_if_open,
                "confidence": s.confidence,
            }
            for s in sites
        ],
        "cryptic_site_count": len(sites),
    }


@app.get("/drug-ext/known-cryptic-sites")
def drug_ext_known_cryptic_sites() -> dict:
    import backend.app.drug_discovery_ext as _dde
    proteins: dict = {}
    if hasattr(_dde, "KNOWN_CRYPTIC_SITES"):
        proteins = _dde.KNOWN_CRYPTIC_SITES
    return {"count": len(proteins), "proteins": proteins}


@app.post("/drug-ext/allostery")
def drug_ext_allostery(payload: _AllosteryRequest) -> dict:
    result = predict_allostery(payload.sequence, gene=payload.gene)
    return {
        "gene": payload.gene,
        "allosteric_sites": [
            {
                "site_id": s.site_id,
                "residues": s.residues,
                "modulation_type": s.modulation_type,
                "druggability": s.druggability,
                "communication_score": s.communication_score,
                "target_active_site_residues": s.target_active_site_residues,
            }
            for s in result.allosteric_sites
        ],
        "allosteric_site_count": len(result.allosteric_sites),
        "communication_pathways": result.communication_pathways,
        "safety_label": _STRUCTURE_SAFETY_LABEL,
    }


@app.post("/drug-ext/therapeutic-reasoning")
def drug_ext_therapeutic_reasoning(payload: _TherapeuticReasoningRequest) -> dict:
    result = run_therapeutic_reasoning(payload.gene, payload.variant)
    return {
        "gene": result.gene,
        "variant": result.variant,
        "step_count": len(result.steps),
        "steps": [
            {
                "step": s.step,
                "description": s.description,
                "input_data": s.input_data,
                "output_data": s.output_data,
                "confidence": s.confidence,
            }
            for s in result.steps
        ],
        "existing_drug_matches": result.existing_drug_matches,
        "final_recommendation": result.final_recommendation,
        "novel_target_score": result.novel_target_score,
        "reasoning_chain_confidence": result.reasoning_chain_confidence,
    }


@app.post("/drug-ext/predict-ddg")
def drug_ext_predict_ddg(payload: _DDGPredictRequest) -> dict:
    result = predict_ddg(payload.gene, payload.variant)
    return {
        "gene": payload.gene,
        "variant": result.variant,
        "ddg_foldx": result.ddg_foldx,
        "ddg_rosetta": result.ddg_rosetta,
        "ddg_spurs": result.ddg_spurs,
        "consensus_ddg": result.consensus_ddg,
        "stability_effect": result.stability_effect,
        "confidence": result.confidence,
    }


@app.post("/drug-ext/batch-ddg")
def drug_ext_batch_ddg(payload: _BatchDDGRequest) -> dict:
    result = batch_predict_ddg(payload.gene, payload.variants)
    predictions = result.variants
    mean_ddg = sum(p.consensus_ddg for p in predictions) / len(predictions) if predictions else 0.0
    return {
        "gene": result.gene,
        "variant_count": len(predictions),
        "predictions": [
            {
                "variant": p.variant,
                "consensus_ddg": p.consensus_ddg,
                "stability_effect": p.stability_effect,
                "ddg_foldx": p.ddg_foldx,
                "confidence": p.confidence,
            }
            for p in predictions
        ],
        "mean_ddg": round(mean_ddg, 4),
        "most_destabilizing": result.most_destabilizing,
        "destabilizing_count": result.destabilizing_count,
        "stabilizing_count": result.stabilizing_count,
    }


@app.get("/drug-ext/amino-acid-properties")
def drug_ext_amino_acid_properties() -> dict:
    from backend.app.drug_discovery_ext import AMINO_ACID_PROPERTIES as _DD_AA_PROPS
    return {
        "property_count": len(_DD_AA_PROPS),
        "properties": _DD_AA_PROPS,
    }


# ---------------------------------------------------------------------------
# 19. Research Assistance
# ---------------------------------------------------------------------------

from backend.app.research_assistance import (  # noqa: E402
    screen_msa_quality,
    suggest_prediction_strategy,
    search_literature,
    cross_reference_prediction,
    identify_knowledge_gaps,
    generate_viewer_data,
    predict_signal_peptide,
    analyze_secretion_pathway,
    assess_therapeutic_suitability,
)


class _MSAQualityRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


class _PredictionStrategyRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


class _CrossReferenceRequest(_BaseModel):
    gene: str
    prediction_type: str


class _KnowledgeGapsRequest(_BaseModel):
    gene: str


class _ViewerDataRequest(_BaseModel):
    sequence: str
    variants: _Optional[list[dict]] = None

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


class _SignalPeptideRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


class _SecretionAnalysisRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


class _TherapeuticSuitabilityRequest(_BaseModel):
    sequence: str

    @field_validator("sequence")
    @classmethod
    def seq_required(cls, v: str) -> str:
        if not v:
            raise ValueError("sequence is required")
        return v


@app.post("/research/msa-quality")
def research_msa_quality(payload: _MSAQualityRequest) -> dict:
    result = screen_msa_quality(payload.sequence)
    strategy = suggest_prediction_strategy(result)
    return {
        "msa_quality": result.msa_quality,
        "estimated_msa_depth": result.estimated_msa_depth,
        "fallback_suggested": result.fallback_suggested,
        "strategy": strategy,
    }


@app.post("/research/prediction-strategy")
def research_prediction_strategy(payload: _PredictionStrategyRequest) -> dict:
    result = screen_msa_quality(payload.sequence)
    return suggest_prediction_strategy(result)


@app.get("/research/literature/{gene}")
def research_literature_gene(gene: str) -> dict:
    result = search_literature(gene)
    return {
        "gene": result.gene,
        "total_references": result.total_references,
        "top_references": result.top_references,
        "related_proteins": result.related_proteins,
        "disease_associations": result.disease_associations,
        "drug_mentions": result.drug_mentions,
        "knowledge_gap_score": result.knowledge_gap_score,
    }


@app.post("/research/literature/cross-reference")
def research_literature_cross_reference(payload: _CrossReferenceRequest) -> dict:
    return cross_reference_prediction(payload.gene, payload.prediction_type)


@app.post("/research/literature/knowledge-gaps")
def research_literature_knowledge_gaps(payload: _KnowledgeGapsRequest) -> dict:
    return identify_knowledge_gaps(payload.gene)


@app.post("/research/viewer-data")
def research_viewer_data(payload: _ViewerDataRequest) -> dict:
    result = generate_viewer_data(payload.sequence, variants=payload.variants)
    return {
        "pdb_data": result.pdb_data,
        "annotations": [
            {
                "residue_index": a.residue_index,
                "annotation_type": a.annotation_type,
                "value": a.value,
                "color_hex": a.color_hex,
                "tooltip": a.tooltip,
            }
            for a in result.annotations
        ],
        "color_scheme": result.color_scheme,
        "viewer_config": result.viewer_config,
        "export_formats": result.export_formats,
    }


@app.post("/research/signal-peptide")
def research_signal_peptide(payload: _SignalPeptideRequest) -> dict:
    result = predict_signal_peptide(payload.sequence)
    return {
        "detected": result.detected,
        "probability": result.probability,
        "signal_type": result.signal_type,
        "cleavage_site": result.cleavage_site,
        "mature_protein_start": result.mature_protein_start,
        "signal_sequence": result.signal_sequence,
    }


@app.post("/research/secretion-analysis")
def research_secretion_analysis(payload: _SecretionAnalysisRequest) -> dict:
    result = analyze_secretion_pathway(payload.sequence)
    return {
        "predicted_localization": result.predicted_localization,
        "transmembrane_helices": result.transmembrane_helices,
        "gpi_anchor": result.gpi_anchor,
        "therapeutic_suitability": result.therapeutic_suitability,
        "warnings": result.warnings,
    }


@app.post("/research/therapeutic-suitability")
def research_therapeutic_suitability(payload: _TherapeuticSuitabilityRequest) -> dict:
    result = analyze_secretion_pathway(payload.sequence)
    suitability = assess_therapeutic_suitability(result)
    return {"therapeutic_suitability": suitability}


@app.get("/research/plddt-color-scheme")
def research_plddt_color_scheme() -> dict:
    return {
        "very_high": {"range": [90, 100], "color": "#0053D6", "label": "Very high (pLDDT > 90)"},
        "confident": {"range": [70, 90], "color": "#65CBF3", "label": "Confident (70-90)"},
        "low": {"range": [50, 70], "color": "#FFDB13", "label": "Low (50-70)"},
        "very_low": {"range": [0, 50], "color": "#FF7D45", "label": "Very low (< 50)"},
    }


# ---------------------------------------------------------------------------
# 20. AlphaFold Backends v2
# ---------------------------------------------------------------------------

from backend.app.alphafold_backends import (  # noqa: E402
    get_backend as af_get_backend,
    predict_with_cache,
    StructureCache,
    BackendSelector as AfBackendSelector,
)

_af_selector = AfBackendSelector()


class _AF2PredictRequest(_BaseModel):
    sequence: str
    backend: str = "mock"
    allow_cloud: bool = False
    allow_fallback: bool = True
    options: dict = {}


@app.get("/alphafold/v2/backends")
def alphafold_v2_list_backends() -> list:
    import backend.app.alphafold_backends as _afb
    results = []
    for b in _afb._ALL_BACKENDS:
        v = b.validate()
        results.append({
            "name": b.name,
            "available": v.available,
            "reason": v.reason,
            "gpu_required": v.gpu_required,
            "cloud": v.cloud,
            "privacy_risk": v.privacy_risk,
        })
    return results


@app.get("/alphafold/v2/backends/{backend_name}/validate")
def alphafold_v2_validate_backend(backend_name: str) -> dict:
    try:
        backend = af_get_backend(backend_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_name}' not found")
    v = backend.validate()
    return {
        "name": backend.name,
        "available": v.available,
        "reason": v.reason,
        "gpu_required": v.gpu_required,
        "cloud": v.cloud,
        "privacy_risk": v.privacy_risk,
    }


@app.post("/alphafold/v2/predict")
def alphafold_v2_predict(payload: _AF2PredictRequest) -> dict:
    try:
        backend = _af_selector.select_backend(
            preferred=payload.backend,
            allow_cloud=payload.allow_cloud,
            allow_fallback=payload.allow_fallback,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except (KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    result = predict_with_cache(backend, payload.sequence, payload.options)
    return {
        "backend_name": result.backend_name,
        "pdb_data": result.pdb_data,
        "confidence": result.confidence,
        "duration_seconds": result.duration_seconds,
        "cached": result.cached,
    }


@app.get("/alphafold/v2/cache/stats")
def alphafold_v2_cache_stats() -> dict:
    return StructureCache.stats()


# ---------------------------------------------------------------------------
# 21. Report Exports
# ---------------------------------------------------------------------------

from backend.app.report_exports import (  # noqa: E402
    build_report_html,
    build_report_markdown,
    build_report_version,
    build_veterinary_consent,
    build_human_research_consent,
    scan_for_unsafe_content,
)


class _ScanUnsafeRequest(_BaseModel):
    text: str


@app.get("/cases/{case_id}/report/html")
def get_case_report_html(case_id: str, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    html = build_report_html(case_id, db)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@app.get("/cases/{case_id}/report/markdown")
def get_case_report_markdown(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    content = build_report_markdown(case_id, db)
    return {"format": "markdown", "content": content}


@app.get("/cases/{case_id}/report/version")
def get_case_report_version(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_report_version(case_id, db)


@app.get("/cases/{case_id}/consent/veterinary")
def get_veterinary_consent(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_veterinary_consent(case_id, db)


@app.get("/cases/{case_id}/consent/human-research")
def get_human_research_consent(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_human_research_consent(case_id, db)


@app.post("/reports/scan-unsafe")
def reports_scan_unsafe(payload: _ScanUnsafeRequest) -> dict:
    findings = scan_for_unsafe_content(payload.text)
    return {
        "safe": len(findings) == 0,
        "count": len(findings),
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# 22. Security
# ---------------------------------------------------------------------------

from backend.app.security import (  # noqa: E402
    generate_sbom,
    scan_for_secrets,
    scan_skill_directory,
    verify_data_deletion,
    build_upload_confirmation,
    verify_audit_chain,
)
from backend.app.rbac import (  # noqa: E402
    Role,
    Permission,
    ROLE_PERMISSIONS,
    check_permission,
    get_role_permissions,
)


class _ScanSecretsRequest(_BaseModel):
    text: str


class _ScanSkillRequest(_BaseModel):
    path: str


class _UploadConfirmationRequest(_BaseModel):
    destination: str
    data_summary: str


class _CheckPermissionRequest(_BaseModel):
    role: str
    permission: str


@app.get("/security/audit-chain/{case_id}")
def security_audit_chain(case_id: str, db: Session = Depends(get_db)) -> dict:
    return verify_audit_chain(case_id, db)


@app.get("/security/deletion-check/{case_id}")
def security_deletion_check(case_id: str, db: Session = Depends(get_db)) -> dict:
    return verify_data_deletion(case_id, db)


@app.get("/security/sbom")
def security_sbom() -> dict:
    return generate_sbom()


@app.post("/security/scan-secrets")
def security_scan_secrets(payload: _ScanSecretsRequest) -> dict:
    findings = scan_for_secrets(payload.text)
    return {
        "count": len(findings),
        "clean": len(findings) == 0,
        "findings": findings,
    }


@app.post("/security/scan-skill")
def security_scan_skill(payload: _ScanSkillRequest) -> dict:
    return scan_skill_directory(payload.path)


@app.post("/security/upload-confirmation")
def security_upload_confirmation(payload: _UploadConfirmationRequest) -> dict:
    return build_upload_confirmation(payload.destination, payload.data_summary)


@app.get("/security/roles")
def security_roles() -> dict:
    return {"roles": {r.value: get_role_permissions(r.value) for r in Role}}


@app.get("/security/roles/{role_name}")
def security_role_detail(role_name: str) -> dict:
    try:
        r = Role(role_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Role '{role_name}' not found")
    return {"role": r.value, "permissions": get_role_permissions(r.value)}


@app.post("/security/check-permission")
def security_check_permission(payload: _CheckPermissionRequest) -> dict:
    allowed = check_permission(payload.role, payload.permission)
    return {"role": payload.role, "permission": payload.permission, "allowed": allowed}


# ---------------------------------------------------------------------------
# 23. Demo
# ---------------------------------------------------------------------------

from backend.app.demo import (  # noqa: E402
    create_demo_case,
    create_synthetic_dataset,
    reset_demo_data,
)


@app.get("/demo/status")
def demo_status() -> dict:
    return {
        "demo_mode": True,
        "disclaimer": "All data is synthetic. Not for clinical use.",
        "version": "0.1.0-alpha",
    }


@app.post("/demo/create-case", status_code=201)
def demo_create_case(db: Session = Depends(get_db)) -> dict:
    return create_demo_case(db)


@app.post("/demo/create-dataset", status_code=201)
def demo_create_dataset(n_cases: int = Query(default=3), db: Session = Depends(get_db)) -> dict:
    cases = create_synthetic_dataset(db, n_cases=n_cases)
    return {
        "count": len(cases),
        "cases": cases,
        "disclaimer": "All data is synthetic. Not for clinical use.",
    }


@app.post("/demo/reset")
def demo_reset(db: Session = Depends(get_db)) -> dict:
    result = reset_demo_data(db)
    result["status"] = "ok"
    return result


# ---------------------------------------------------------------------------
# 24. Hallucination Guard / Source Validation
# ---------------------------------------------------------------------------

from backend.app.hallucination_guard import (  # noqa: E402
    validate_report_sources,
    scan_for_hallucinated_content,
)


class _ValidateSourcesRequest(_BaseModel):
    text: str


class _HallucinationScanRequest(_BaseModel):
    text: str


@app.post("/validate/sources")
def validate_sources_endpoint(payload: _ValidateSourcesRequest) -> dict:
    results = validate_report_sources(payload.text)
    total = len(results)
    unknown_count = sum(1 for r in results if not r["known"])
    return {
        "results": results,
        "total": total,
        "unknown_count": unknown_count,
        "all_known": unknown_count == 0,
    }


@app.post("/validate/hallucination-scan")
def hallucination_scan_endpoint(payload: _HallucinationScanRequest) -> dict:
    findings = scan_for_hallucinated_content(payload.text)
    high_count = sum(1 for f in findings if f.get("severity") == "high")
    return {
        "findings": findings,
        "count": len(findings),
        "high_severity_count": high_count,
        "clean": len(findings) == 0,
    }


# ---------------------------------------------------------------------------
# 25. Infrastructure
# ---------------------------------------------------------------------------

from backend.app.gpu_worker import (  # noqa: E402
    DEFAULT_GPU_PROFILES,
    check_gpu_availability,
)
from backend.app.encryption import check_encryption_status  # noqa: E402
from backend.app.celery_config import (  # noqa: E402
    CELERY_TASK_REGISTRY,
    check_celery_status,
)
from backend.app.container_scanning import (  # noqa: E402
    ContainerScanConfig,
    build_scan_command,
    check_scanner_available,
)


class _ContainerScanRequest(_BaseModel):
    image: str
    scanner: str = "trivy"
    fail_on_severity: str = "CRITICAL"
    ignore_unfixed: bool = False


@app.get("/infrastructure/gpu-profiles")
def infrastructure_gpu_profiles() -> dict:
    profiles = {name: {
        "gpu_required": p.gpu_required,
        "gpu_type": p.gpu_type,
        "min_vram_gb": p.min_vram_gb,
    } for name, p in DEFAULT_GPU_PROFILES.items()}
    return {"profiles": profiles}


@app.get("/infrastructure/gpu-status")
def infrastructure_gpu_status() -> dict:
    return check_gpu_availability()


@app.get("/infrastructure/encryption-status")
def infrastructure_encryption_status() -> dict:
    return check_encryption_status()


@app.get("/infrastructure/celery-status")
def infrastructure_celery_status() -> dict:
    return check_celery_status()


@app.get("/infrastructure/celery-tasks")
def infrastructure_celery_tasks() -> dict:
    return {"tasks": CELERY_TASK_REGISTRY}


@app.get("/infrastructure/container-scan/status")
def infrastructure_container_scan_status() -> dict:
    return check_scanner_available()


@app.post("/infrastructure/container-scan/build-command")
def infrastructure_container_scan_build_command(payload: _ContainerScanRequest) -> dict:
    config = ContainerScanConfig(
        scanner=payload.scanner,
        fail_on_severity=payload.fail_on_severity,
        ignore_unfixed=payload.ignore_unfixed,
    )
    command = build_scan_command(payload.image, config)
    return {
        "command": command,
        "scanner": payload.scanner,
        "image": payload.image,
        "fail_on_severity": payload.fail_on_severity,
    }


# ---------------------------------------------------------------------------
# 26. Extended Backends / Ensemble / Modes
# ---------------------------------------------------------------------------

from backend.app.ensemble import (  # noqa: E402
    EnsembleResult,
    compare_backends,
    run_ensemble,
)
from backend.app.mode_safety import (  # noqa: E402
    MODE_SAFETY_CONFIG,
    ResearchMode,
    check_mode_safety,
    get_mode_config,
)
import backend.app.alphafold_backends as _afb_mod  # noqa: E402


class _EnsemblePredictRequest(_BaseModel):
    sequence: str
    backends: list[str]
    options: dict = {}


class _EnsembleCompareRequest(_BaseModel):
    sequence: str
    backends: list[str]


class _ModeCheckRequest(_BaseModel):
    action: str


@app.get("/backends/all")
def backends_all() -> list:
    results = []
    for b in _afb_mod._ALL_BACKENDS:
        v = b.validate()
        results.append({
            "name": b.name,
            "description": getattr(b, "description", b.name),
            "available": v.available,
            "gpu_required": v.gpu_required,
            "cloud": v.cloud,
            "privacy_risk": v.privacy_risk,
        })
    return results


@app.post("/ensemble/predict")
def ensemble_predict(payload: _EnsemblePredictRequest) -> dict:
    if not payload.backends:
        raise HTTPException(status_code=400, detail="backends list must not be empty")
    try:
        result = run_ensemble(payload.sequence, payload.backends, payload.options)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    return {
        "backends_used": result.backends_used,
        "consensus_plddt": result.consensus_plddt,
        "agreement_score": result.agreement_score,
        "best_backend": result.best_result.backend_name,
        "results": [
            {
                "backend_name": r.backend_name,
                "pdb_data": r.pdb_data,
                "duration_seconds": r.duration_seconds,
                "cached": r.cached,
            }
            for r in result.results
        ],
    }


@app.post("/ensemble/compare")
def ensemble_compare(payload: _EnsembleCompareRequest) -> dict:
    if not payload.backends:
        raise HTTPException(status_code=400, detail="backends list must not be empty")
    try:
        return compare_backends(payload.sequence, payload.backends)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@app.get("/modes")
def modes_list() -> list:
    modes = []
    for mode in ResearchMode:
        cfg = get_mode_config(mode.value)
        modes.append({
            "mode": mode.value,
            "safety_level": cfg["safety_level"],
            "requires_attestation": cfg["requires_attestation"],
            "requires_ethics_review": cfg["requires_ethics_review"],
            "allowed_backends": cfg.get("allowed_backends", []),
        })
    return modes


@app.get("/modes/{mode}")
def mode_get(mode: str) -> dict:
    try:
        cfg = get_mode_config(mode)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {
        "mode": mode,
        "safety_level": cfg["safety_level"],
        "requires_attestation": cfg["requires_attestation"],
        "requires_ethics_review": cfg["requires_ethics_review"],
        "allowed_backends": cfg.get("allowed_backends", []),
        "disclaimers": cfg.get("disclaimers", []),
        "prohibited_actions": cfg.get("prohibited_actions", []),
    }


@app.post("/modes/{mode}/check")
def mode_check(mode: str, payload: _ModeCheckRequest) -> dict:
    try:
        result = check_mode_safety(mode, payload.action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    result["mode"] = mode
    result["action"] = payload.action
    return result


# ---------------------------------------------------------------------------
# 27. Safety Reports (evidence, FP risk, citations, attestation, enhanced)
# ---------------------------------------------------------------------------

from backend.app.safety_reports import (  # noqa: E402
    AttestationType,
    ProfessionalAttestation,
    assess_evidence_level,
    assess_false_positive_risk,
    build_report_citations,
    check_attestation_required,
    get_attestation,
    record_attestation,
)


class _AttestationRequest(_BaseModel):
    type: AttestationType
    attester_name: str
    credentials: str = ""
    attestation_text: str


@app.get("/cases/{case_id}/evidence")
def get_case_evidence(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    assessment = assess_evidence_level(case_id, db)
    return {
        "case_id": case_id,
        "level": assessment.level.value,
        "flags": assessment.flags,
        "recommendations": assessment.recommendations,
    }


@app.get("/cases/{case_id}/false-positive-risk")
def get_case_fp_risk(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    from backend.app.models import CandidateAntigen as _CA
    candidates = db.query(_CA).filter(_CA.case_id == case_id).all()
    fp = assess_false_positive_risk(candidates, db)
    return {
        "case_id": case_id,
        "risk": fp.risk.value,
        "overall_warnings": fp.overall_warnings,
        "per_candidate": [
            {"candidate_id": c.candidate_id, "warnings": c.warnings}
            for c in fp.per_candidate
        ],
    }


@app.get("/cases/{case_id}/report/citations")
def get_case_citations(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    citations = build_report_citations(case_id, db)
    return {
        "case_id": case_id,
        "citations": [
            {
                "source": c.source,
                "description": c.description,
                "url": c.url,
                "accessed_date": c.accessed_date,
            }
            for c in citations
        ],
    }


@app.post("/cases/{case_id}/attestation", status_code=201)
def post_case_attestation(case_id: str, payload: _AttestationRequest, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    attestation = ProfessionalAttestation(
        type=payload.type,
        attester_name=payload.attester_name,
        credentials=payload.credentials,
        attestation_text=payload.attestation_text,
    )
    return record_attestation(case_id, attestation, db)


@app.get("/cases/{case_id}/attestation")
def get_case_attestation(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    att = get_attestation(case_id)
    required = check_attestation_required(case_id, db)
    return {
        "case_id": case_id,
        "attestation_recorded": att is not None,
        "attestation": att,
        "attestation_required": required,
    }


@app.get("/cases/{case_id}/report/enhanced")
def get_case_report_enhanced(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    from backend.app.models import CandidateAntigen as _CA2
    candidates = db.query(_CA2).filter(_CA2.case_id == case_id).all()
    evidence = assess_evidence_level(case_id, db)
    fp = assess_false_positive_risk(candidates, db)
    citations = build_report_citations(case_id, db)
    att = get_attestation(case_id)
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="report.enhanced.generated",
        inputs={"case_id": case_id},
        outputs={"level": evidence.level.value},
    )
    db.commit()
    return {
        "case_id": case_id,
        "safety_label": "NOT ADMINISTERABLE — research coordination artifact only",
        "disclaimer": "Research coordination tool only — not medical/veterinary advice.",
        "evidence_assessment": {
            "level": evidence.level.value,
            "flags": evidence.flags,
            "recommendations": evidence.recommendations,
        },
        "false_positive_risk": {
            "risk": fp.risk.value,
            "overall_warnings": fp.overall_warnings,
            "per_candidate": [
                {"candidate_id": c.candidate_id, "warnings": c.warnings}
                for c in fp.per_candidate
            ],
        },
        "citations": [
            {
                "source": c.source,
                "description": c.description,
                "url": c.url,
                "accessed_date": c.accessed_date,
            }
            for c in citations
        ],
        "attestation": {
            "recorded": att is not None,
            "details": att,
        },
    }


# ---------------------------------------------------------------------------
# 28. Privacy module
# ---------------------------------------------------------------------------

from backend.app.privacy import (  # noqa: E402
    build_case_privacy_summary,
    check_cloud_upload_allowed,
    ensure_case_data_dir,
    export_audit_log,
    find_expired_artifacts,
    list_case_data_files,
)


@app.get("/cases/{case_id}/privacy")
def get_case_privacy(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_case_privacy_summary(case_id, db)


@app.post("/cases/{case_id}/data-dir")
def create_case_data_dir(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    path = ensure_case_data_dir(case_id)
    return {"created": True, "path": str(path)}


@app.get("/cases/{case_id}/data-files")
def list_case_data_files_endpoint(case_id: str, db: Session = Depends(get_db)) -> list:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return list_case_data_files(case_id)


@app.get("/privacy/cloud-upload-check")
def cloud_upload_check(
    backend_name: str | None = None,
    case_id: str | None = None,
) -> dict:
    return check_cloud_upload_allowed(case_id=case_id, backend_name=backend_name)


@app.get("/privacy/retention/expired")
def retention_expired(db: Session = Depends(get_db)) -> list:
    return find_expired_artifacts(db)


@app.get("/audit/export")
def audit_export(
    format: str = "json",
    case_id: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        content = export_audit_log(db, case_id=case_id, format=format)
    except Exception:
        content = json.dumps({"audit_log": [], "exported_at": datetime.now(UTC).isoformat()})
    if format == "markdown":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=content, media_type="text/markdown")
    return JSONResponse(content=json.loads(content))


@app.get("/audit/system")
def audit_system(db: Session = Depends(get_db)) -> dict:
    from backend.app.models import AuditLog as _AL
    count = db.query(_AL).count()
    return {"total_entries": count, "status": "ok"}


# ---------------------------------------------------------------------------
# 29. Ethics templates
# ---------------------------------------------------------------------------

from backend.app.ethics_templates import (  # noqa: E402
    build_adverse_event_template,
    build_compassionate_use_checklist,
    build_uncertainty_summary,
    build_vet_oncologist_questions,
)


@app.get("/cases/{case_id}/ethics/uncertainty-summary")
def get_ethics_uncertainty_summary(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_uncertainty_summary(case_id, db)


@app.get("/cases/{case_id}/ethics/adverse-event-template")
def get_ethics_adverse_event_template(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_adverse_event_template(case_id, case.species.value)


@app.get("/ethics/compassionate-use-checklist")
def get_compassionate_use_checklist(species: str) -> dict:
    return build_compassionate_use_checklist(species)


@app.get("/cases/{case_id}/ethics/professional-questions")
def get_ethics_professional_questions(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_vet_oncologist_questions(case_id, db)


# ---------------------------------------------------------------------------
# 30. Lab coordination
# ---------------------------------------------------------------------------

from backend.app.lab_coordination import (  # noqa: E402
    EMAIL_PRIVACY_WARNING,
    SEQUENCING_PROVIDER_CHECKLIST,
    RNA_MANUFACTURING_CHECKLIST,
    SECURE_HANDOFF_CHECKLIST,
    UNIVERSITY_OUTREACH_TEMPLATE,
    create_cost_entry,
    create_document_request,
    create_lab_contact,
    create_timeline_entry,
    generate_outreach_email,
    get_case_summary_packet,
    get_cost_summary,
    list_cost_entries,
    list_document_requests,
    list_lab_contacts,
    list_timeline_entries,
)


class _LabContactCreate(_BaseModel):
    name: str
    role: str
    organization: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


class _CostEntryCreate(_BaseModel):
    category: str
    description: str
    amount_cents: int = 0
    currency: str = "USD"


class _TimelineEntryCreate(_BaseModel):
    title: str
    description: str | None = None
    owner: str | None = None
    status: str = "pending"


class _DocumentRequestCreate(_BaseModel):
    document_type: str
    requested_from: str | None = None
    notes: str | None = None


class _OutreachEmailRequest(_BaseModel):
    service_type: str
    contact_name: str = "[Contact Name]"
    species: str = "demo"
    case_id: str = ""
    diagnosis_summary: str = ""
    service_description: str = ""
    sender_name: str = "[Your Name]"


@app.get("/lab/checklists")
def lab_checklists() -> dict:
    return {
        "sequencing_provider": SEQUENCING_PROVIDER_CHECKLIST,
        "rna_manufacturing": RNA_MANUFACTURING_CHECKLIST,
        "secure_handoff": SECURE_HANDOFF_CHECKLIST,
        "email_privacy_warning": EMAIL_PRIVACY_WARNING,
    }


@app.get("/lab/templates/university-outreach")
def lab_university_outreach_template() -> dict:
    return {"template": UNIVERSITY_OUTREACH_TEMPLATE}


@app.post("/lab/templates/outreach-email")
def lab_outreach_email(payload: _OutreachEmailRequest) -> dict:
    draft = generate_outreach_email(
        service_type=payload.service_type,
        contact_name=payload.contact_name,
        species=payload.species,
        case_id=payload.case_id,
        diagnosis_summary=payload.diagnosis_summary,
        service_description=payload.service_description,
        sender_name=payload.sender_name,
    )
    return {"email_draft": draft, "privacy_warning": EMAIL_PRIVACY_WARNING}


@app.post("/cases/{case_id}/lab/contacts")
def create_case_lab_contact(case_id: str, payload: _LabContactCreate, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    contact = create_lab_contact(
        db,
        case_id=case_id,
        name=payload.name,
        role=payload.role,
        organization=payload.organization,
        email=payload.email,
        phone=payload.phone,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(contact)
    return {
        "id": contact.id,
        "case_id": contact.case_id,
        "name": contact.name,
        "role": contact.role,
        "organization": contact.organization,
        "email": contact.email,
        "phone": contact.phone,
        "notes": contact.notes,
    }


@app.get("/cases/{case_id}/lab/contacts")
def list_case_lab_contacts(case_id: str, db: Session = Depends(get_db)) -> list:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    contacts = list_lab_contacts(db, case_id=case_id)
    return [
        {
            "id": c.id,
            "case_id": c.case_id,
            "name": c.name,
            "role": c.role,
            "organization": c.organization,
            "email": c.email,
            "phone": c.phone,
            "notes": c.notes,
        }
        for c in contacts
    ]


@app.post("/cases/{case_id}/lab/costs")
def create_case_cost_entry(case_id: str, payload: _CostEntryCreate, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    entry = create_cost_entry(
        db,
        case_id=case_id,
        category=payload.category,
        description=payload.description,
        amount_cents=payload.amount_cents,
        currency=payload.currency,
    )
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "case_id": entry.case_id,
        "category": entry.category,
        "description": entry.description,
        "amount_cents": entry.amount_cents,
        "currency": entry.currency,
    }


@app.get("/cases/{case_id}/lab/costs")
def get_case_cost_summary(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return get_cost_summary(db, case_id)


@app.post("/cases/{case_id}/lab/timeline")
def create_case_timeline_entry(case_id: str, payload: _TimelineEntryCreate, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    entry = create_timeline_entry(
        db,
        case_id=case_id,
        title=payload.title,
        description=payload.description,
        owner=payload.owner,
        status=payload.status,
    )
    db.commit()
    db.refresh(entry)
    return {
        "id": entry.id,
        "case_id": entry.case_id,
        "title": entry.title,
        "description": entry.description,
        "owner": entry.owner,
        "status": entry.status,
    }


@app.get("/cases/{case_id}/lab/timeline")
def list_case_timeline(case_id: str, db: Session = Depends(get_db)) -> list:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    entries = list_timeline_entries(db, case_id)
    return [
        {
            "id": e.id,
            "case_id": e.case_id,
            "title": e.title,
            "description": e.description,
            "owner": e.owner,
            "status": e.status,
        }
        for e in entries
    ]


@app.post("/cases/{case_id}/lab/document-requests")
def create_case_document_request(case_id: str, payload: _DocumentRequestCreate, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    req = create_document_request(
        db,
        case_id=case_id,
        document_type=payload.document_type,
        requested_from=payload.requested_from,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(req)
    return {
        "id": req.id,
        "case_id": req.case_id,
        "document_type": req.document_type,
        "requested_from": req.requested_from,
        "status": req.status,
        "notes": req.notes,
    }


@app.get("/cases/{case_id}/lab/document-requests")
def list_case_document_requests(case_id: str, db: Session = Depends(get_db)) -> list:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    requests = list_document_requests(db, case_id)
    return [
        {
            "id": r.id,
            "case_id": r.case_id,
            "document_type": r.document_type,
            "requested_from": r.requested_from,
            "status": r.status,
            "notes": r.notes,
        }
        for r in requests
    ]


@app.get("/cases/{case_id}/lab/summary-packet")
def get_case_lab_summary_packet(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return get_case_summary_packet(db, case_id)


# ---------------------------------------------------------------------------
# 31. Data loading / validation
# ---------------------------------------------------------------------------

from backend.app.data_loading import (  # noqa: E402
    SUPPORTED_FORMATS,
    build_missing_data_checklist,
    detect_missing_data,
    detect_sample_role,
    validate_file_paths,
    validate_file_type,
)


class _ValidateFileRequest(_BaseModel):
    filename: str
    expected_format: str | None = None


class _ValidateFilesRequest(_BaseModel):
    file_paths: dict


class _DetectRoleRequest(_BaseModel):
    filename: str | None = None
    label: str | None = None
    metadata: dict | None = None


@app.get("/data/formats")
def data_formats() -> dict:
    return {fmt: {"description": info["description"]} for fmt, info in SUPPORTED_FORMATS.items()}


@app.post("/data/validate-file")
def data_validate_file(payload: _ValidateFileRequest) -> dict:
    return validate_file_type(payload.filename, payload.expected_format)


@app.post("/data/validate-files")
def data_validate_files(payload: _ValidateFilesRequest) -> list:
    return validate_file_paths(payload.file_paths)


@app.post("/data/detect-role")
def data_detect_role(payload: _DetectRoleRequest) -> dict:
    role = detect_sample_role(
        filename=payload.filename,
        label=payload.label,
        metadata=payload.metadata,
    )
    return {"detected_role": role}


@app.get("/cases/{case_id}/data/missing")
def get_case_missing_data(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return detect_missing_data(db, case_id)


@app.get("/cases/{case_id}/data/checklist")
def get_case_data_checklist(case_id: str, db: Session = Depends(get_db)) -> list:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return build_missing_data_checklist(db, case_id)


# ---------------------------------------------------------------------------
# 32. API Hardening (openapi-export, dry-run, approval-required, error-catalog)
# ---------------------------------------------------------------------------

from backend.app.openapi_export import export_openapi_spec  # noqa: E402
from backend.app.agent_errors import AGENT_ERROR_CATALOG  # noqa: E402
from backend.app.dry_run import (  # noqa: E402
    APPROVAL_REQUIRED_ACTIONS,
    check_approval_required,
    dry_run_action,
)


class _DryRunRequest(_BaseModel):
    action: str
    params: dict = {}


@app.get("/openapi-export")
def openapi_export_endpoint() -> dict:
    return export_openapi_spec()


@app.post("/agent/dry-run")
def agent_dry_run(payload: _DryRunRequest) -> dict:
    try:
        result = dry_run_action(payload.action, payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "action": result.action,
        "would_affect": result.would_affect,
        "parameters": result.parameters,
        "safety_level": result.safety_level,
        "requires_approval": result.requires_approval,
        "notes": result.notes,
    }


@app.get("/agent/approval-required")
def agent_approval_required_list() -> dict:
    actions = [check_approval_required(a) for a in APPROVAL_REQUIRED_ACTIONS]
    return {"actions": actions}


@app.get("/agent/approval-required/{action}")
def agent_approval_required_check(action: str) -> dict:
    return check_approval_required(action)


@app.get("/agent/error-catalog")
def agent_error_catalog() -> dict:
    errors = [
        {
            "key": key,
            "code": err.code,
            "message": err.message,
            "suggestion": err.suggestion,
            "retry_safe": err.retry_safe,
            "documentation_url": err.documentation_url,
        }
        for key, err in AGENT_ERROR_CATALOG.items()
    ]
    return {"errors": errors}


# ---------------------------------------------------------------------------
# 33. Background jobs (/jobs, /cases/{id}/pipeline/run-async, /alphafold/backends/{name}/run-async)
# ---------------------------------------------------------------------------

from backend.app.jobs import (  # noqa: E402
    cancel_job,
    create_job,
    retry_job,
    run_alphafold_job,
    run_pipeline_job,
    submit_job,
)
from backend.app.models import BackgroundJob, BackgroundJobStatusEnum  # noqa: E402


def _job_to_dict(job: BackgroundJob) -> dict:
    return {
        "id": job.id,
        "case_id": job.case_id,
        "job_type": job.job_type,
        "status": job.status.value,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "timeout_seconds": job.timeout_seconds,
        "max_retries": job.max_retries,
        "attempt": job.attempt,
        "timed_out": job.timed_out,
    }


@app.get("/jobs")
def list_jobs(
    case_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list:
    try:
        query = db.query(BackgroundJob)
        if case_id:
            query = query.filter(BackgroundJob.case_id == case_id)
        if status:
            try:
                status_enum = BackgroundJobStatusEnum(status)
                query = query.filter(BackgroundJob.status == status_enum)
            except ValueError:
                pass
        jobs = query.order_by(BackgroundJob.created_at.desc()).all()
        return [_job_to_dict(j) for j in jobs]
    except Exception as exc:
        if "no such table" in str(exc).lower() or "background_jobs" in str(exc).lower():
            return []
        raise


@app.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        job = db.get(BackgroundJob, job_id)
    except Exception as exc:
        if "no such table" in str(exc).lower() or "background_jobs" in str(exc).lower():
            raise HTTPException(status_code=503, detail="background_jobs table not available — run migrations")
        raise
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@app.post("/jobs/{job_id}/cancel")
def cancel_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        job = db.get(BackgroundJob, job_id)
    except Exception as exc:
        if "no such table" in str(exc).lower() or "background_jobs" in str(exc).lower():
            raise HTTPException(status_code=503, detail="background_jobs table not available — run migrations")
        raise
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    terminal = (
        BackgroundJobStatusEnum.completed,
        BackgroundJobStatusEnum.failed,
        BackgroundJobStatusEnum.cancelled,
        BackgroundJobStatusEnum.timed_out,
    )
    if job.status == BackgroundJobStatusEnum.completed:
        raise HTTPException(status_code=409, detail="Cannot cancel a completed job")
    updated = cancel_job(db, job_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(updated)


@app.post("/jobs/{job_id}/retry")
def retry_job_endpoint(job_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        job = db.get(BackgroundJob, job_id)
    except Exception as exc:
        if "no such table" in str(exc).lower() or "background_jobs" in str(exc).lower():
            raise HTTPException(status_code=503, detail="background_jobs table not available — run migrations")
        raise
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        updated = retry_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if updated is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Re-submit via threadpool
    if updated.job_type == "pipeline_run":
        case_id = updated.case_id

        def _pipeline_fn():
            return run_pipeline_job(
                case_id=case_id,
                job_id=updated.id,
                run_pipeline_sync=_run_pipeline_sync,
                pipeline_mode="retry",
            )
        submit_job(updated.id, _pipeline_fn, timeout_seconds=updated.timeout_seconds)
    elif updated.job_type == "alphafold_backend":
        _payload = updated.payload or {}
        _backend_name = _payload.get("backend_name", "mock")
        _case_id = updated.case_id
        _job_id = updated.id

        def _af_fn():
            return run_alphafold_job(
                case_id=_case_id,
                job_id=_job_id,
                backend_name=_backend_name,
                payload={k: v for k, v in _payload.items() if k != "backend_name"},
                run_alphafold_sync=_run_alphafold_sync,
            )
        submit_job(updated.id, _af_fn, timeout_seconds=updated.timeout_seconds)
    log_action(
        db,
        case_id=updated.case_id,
        actor="api",
        action="background_job.retried",
        inputs={"job_id": job_id},
        outputs={"job_id": updated.id, "attempt": updated.attempt},
    )
    db.commit()
    return _job_to_dict(updated)


@app.post("/cases/{case_id}/pipeline/run-async", status_code=202)
def pipeline_run_async(
    case_id: str,
    timeout_seconds: int = Query(default=300),
    max_retries: int = Query(default=0),
    db: Session = Depends(get_db),
) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    _enforce_preflight_or_raise(action="run_pipeline", species_mode=case.species.value)
    job = create_job(
        db,
        case_id=case_id,
        job_type="pipeline_run",
        payload={"case_id": case_id},
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.async_dispatched",
        inputs={"case_id": case_id, "timeout_seconds": timeout_seconds, "max_retries": max_retries},
        outputs={"job_id": job.id},
    )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="background_job.created",
        inputs={"job_type": "pipeline_run"},
        outputs={"job_id": job.id},
    )
    db.commit()
    db.refresh(job)
    job_id = job.id

    def _fn():
        return run_pipeline_job(
            case_id=case_id,
            job_id=job_id,
            run_pipeline_sync=_run_pipeline_sync,
            pipeline_mode="async",
        )

    submit_job(job_id, _fn, timeout_seconds=timeout_seconds)
    return _job_to_dict(job)


class _AlphaFoldAsyncRequest(_BaseModel):
    case_id: str | None = None
    candidate_id: str | None = None
    sequence: str | None = None
    job_name: str | None = None
    options: dict = {}


@app.post("/alphafold/backends/{backend_name}/run-async", status_code=202)
def alphafold_run_async(
    backend_name: str,
    body: _AlphaFoldAsyncRequest,
    timeout_seconds: int = Query(default=600),
    max_retries: int = Query(default=0),
    db: Session = Depends(get_db),
) -> dict:
    payload = body.model_dump(exclude_none=False)
    case_id = payload.get("case_id")
    job = create_job(
        db,
        case_id=case_id,
        job_type="alphafold_backend",
        payload={"backend_name": backend_name, **payload},
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    db.flush()
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="alphafold.async_dispatched",
        inputs={"backend_name": backend_name, "case_id": case_id},
        outputs={"job_id": job.id},
    )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="background_job.created",
        inputs={"job_type": "alphafold_backend"},
        outputs={"job_id": job.id},
    )
    db.commit()
    db.refresh(job)
    job_id = job.id

    def _fn():
        return run_alphafold_job(
            case_id=case_id,
            job_id=job_id,
            backend_name=backend_name,
            payload=payload,
            run_alphafold_sync=_run_alphafold_sync,
        )

    submit_job(job_id, _fn, timeout_seconds=timeout_seconds)
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# 34. Pipeline framework steps / dry-run
# ---------------------------------------------------------------------------

from backend.app.pipeline.framework import FRAMEWORK_STEPS  # noqa: E402


class _PipelineDryRunRequest(_BaseModel):
    steps: list[str] = []


@app.get("/pipeline/steps")
def pipeline_steps_list() -> list:
    return [
        {"name": s.name, "description": getattr(s, "description", s.name)}
        for s in FRAMEWORK_STEPS
    ]


@app.post("/pipeline/dry-run")
def pipeline_dry_run(payload: _PipelineDryRunRequest) -> dict:
    valid_names = {s.name for s in FRAMEWORK_STEPS}
    requested = payload.steps or []
    valid = [s for s in requested if s in valid_names]
    unknown = [s for s in requested if s not in valid_names]
    return {
        "ok": len(unknown) == 0,
        "valid": valid,
        "unknown": unknown,
    }


# ---------------------------------------------------------------------------
# 35. Global agent task routes + skills + events + dry-run
# ---------------------------------------------------------------------------

from backend.app.event_stream import publish_event, subscribe  # noqa: E402


class _GlobalAgentTaskCreate(_BaseModel):
    case_id: str | None = None
    framework: str = "hermes"
    skill_name: str = ""
    status: str = "pending"
    logs: dict = {}
    artifacts: dict = {}


class _AgentTaskDryRunRequest(_BaseModel):
    case_id: str | None = None
    framework: str = "hermes"
    skill_name: str = ""
    status: str = "pending"
    logs: dict = {}
    artifacts: dict = {}


def _is_known_skill(skill_name: str) -> bool:
    """Check if a skill exists in the skills directory."""
    from pathlib import Path as _Path
    skills_root = _Path(__file__).resolve().parents[2] / "skills"
    for framework_dir in skills_root.iterdir():
        if framework_dir.is_dir():
            skill_dir = framework_dir / skill_name
            if skill_dir.is_dir():
                return True
    return False


@app.post("/agent/tasks", response_model=AgentTaskRead, status_code=201)
def create_agent_task_global(payload: _GlobalAgentTaskCreate, db: Session = Depends(get_db)) -> AgentTask:
    # Safety gate: human cases require approval before agent task creation
    if payload.case_id:
        case = db.get(Case, payload.case_id)
        if case is not None and case.species.value == "human":
            log_action(
                db,
                case_id=payload.case_id,
                actor="api",
                action="expert.review.required",
                inputs={"skill_name": payload.skill_name, "species": "human"},
                outputs={"safety_status": "requires_approval"},
                safety_gate_result="requires_approval",
            )
            db.commit()
            return JSONResponse(
                status_code=403,
                content={
                    "safety_status": "requires_approval",
                    "reason": "Human cases require explicit expert approval before agent task execution",
                    "case_id": payload.case_id,
                },
            )
    task = AgentTask(
        id=str(uuid4()),
        case_id=payload.case_id,
        framework=payload.framework,
        skill_name=payload.skill_name,
        status=payload.status,
        logs=payload.logs,
        artifacts=payload.artifacts,
    )
    db.add(task)
    db.flush()
    log_action(
        db,
        case_id=payload.case_id,
        actor="api",
        action="agent_task.created",
        inputs=payload.model_dump(mode="json"),
        outputs={"agent_task_id": task.id},
    )
    db.commit()
    db.refresh(task)
    return task


@app.get("/agent/tasks")
def list_agent_tasks_global(
    case_id: str | None = None,
    db: Session = Depends(get_db),
) -> list:
    query = db.query(AgentTask)
    if case_id:
        query = query.filter(AgentTask.case_id == case_id)
    tasks = query.order_by(AgentTask.created_at.desc()).all()
    from backend.app.schemas import AgentTaskRead as _ATR  # noqa: PLC0415
    return [_ATR.model_validate(t).model_dump() for t in tasks]


@app.get("/agent/tasks/{task_id}", response_model=AgentTaskRead)
def get_agent_task_global(task_id: str, db: Session = Depends(get_db)) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    return task


@app.patch("/agent/tasks/{task_id}", response_model=AgentTaskRead)
def update_agent_task_global(task_id: str, payload: AgentTaskUpdate, db: Session = Depends(get_db)) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    updates = payload.model_dump(exclude_unset=True, mode="python")
    for field, value in updates.items():
        setattr(task, field, value)
    log_action(
        db,
        case_id=task.case_id,
        actor="api",
        action="agent_task.updated",
        inputs=updates,
        outputs={"agent_task_id": task.id},
    )
    db.commit()
    db.refresh(task)
    return task


@app.post("/agent/tasks/dry-run")
def agent_task_dry_run(payload: _AgentTaskDryRunRequest, db: Session = Depends(get_db)) -> dict:
    # Safety gate: human cases require approval
    if payload.case_id:
        case = db.get(Case, payload.case_id)
        if case is not None and case.species.value == "human":
            log_action(
                db,
                case_id=payload.case_id,
                actor="api",
                action="expert.review.required",
                inputs={"skill_name": payload.skill_name, "species": "human"},
                outputs={"safety_status": "requires_approval"},
                safety_gate_result="requires_approval",
            )
            db.commit()
            raise _SafetyBlockedHTTPException(
                status_code=403,
                detail="Human cases require explicit expert approval",
                safety_status="requires_approval",
                safety_reason="Human cases require explicit expert approval",
            )
    case_exists = False
    if payload.case_id:
        case = db.get(Case, payload.case_id)
        case_exists = case is not None
    skill_available = _is_known_skill(payload.skill_name)
    log_action(
        db,
        case_id=payload.case_id,
        actor="api",
        action="agent_task.dry_run",
        inputs={"skill_name": payload.skill_name, "framework": payload.framework},
        outputs={"skill_available": skill_available, "case_exists": case_exists},
        safety_gate_result="pass",
    )
    db.commit()
    return {
        "dry_run": True,
        "case_id": payload.case_id,
        "case_exists": case_exists,
        "framework": payload.framework,
        "skill_name": payload.skill_name,
        "skill_available": skill_available,
        "status": payload.status,
        "would_create": True,
        "safety_level": "requires-review",
    }


@app.get("/agent/skills")
def agent_skills_list() -> list:
    """List all available agent skills from the skills directory."""
    from pathlib import Path as _Path  # noqa: PLC0415
    import yaml  # noqa: PLC0415

    skills_root = _Path(__file__).resolve().parents[2] / "skills"
    results = []
    frameworks_map = {"hermes": "hermes", "openclaw": "openclaw", "claude-code": "claude_code"}

    for framework_dir in sorted(skills_root.iterdir()):
        if not framework_dir.is_dir() or framework_dir.name == "shared":
            continue
        framework_name = frameworks_map.get(framework_dir.name, framework_dir.name)
        for skill_dir in sorted(framework_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            # Parse YAML frontmatter
            content = skill_md.read_text(encoding="utf-8")
            name = skill_dir.name
            description = f"Agent skill: {name}"
            safety_boundaries: list[str] = []
            required_api_endpoints: list[str] = []

            if content.startswith("---"):
                try:
                    end = content.index("---", 3)
                    fm_text = content[3:end].strip()
                    fm = yaml.safe_load(fm_text)
                    if isinstance(fm, dict):
                        name = fm.get("name", name)
                        description = fm.get("description", description)
                except Exception:
                    pass

            # Extract safety boundaries and required endpoints from markdown body
            import re as _re  # noqa: PLC0415
            _safety_kws = ("not administerable", "no dosing", "research only",
                           "professional review", "safety", "not for clinical",
                           "research candidate")
            for line in content.splitlines():
                stripped = line.strip()
                # Bullet points: "- text" or numbered "1. text"
                _is_list_item = stripped.startswith("- ") or bool(_re.match(r"^\d+\.\s", stripped))
                if _is_list_item and any(kw in stripped.lower() for kw in _safety_kws):
                    # Strip leading list marker
                    item_text = _re.sub(r"^[-*]\s+|^\d+\.\s+", "", stripped)
                    safety_boundaries.append(item_text)
                if stripped.startswith("- `") and "/safety/preflight" in stripped:
                    required_api_endpoints.append("POST /safety/preflight")
                elif stripped.startswith("- `POST ") or stripped.startswith("- `GET "):
                    endpoint = stripped[3:stripped.index("`", 3)] if "`" in stripped[3:] else ""
                    if endpoint:
                        required_api_endpoints.append(endpoint)

            results.append({
                "framework": framework_name,
                "skill_name": name,
                "skill_path": str(skill_dir.relative_to(skills_root.parent)),
                "available": True,
                "description": description,
                "safety_boundaries": safety_boundaries,
                "required_api_endpoints": list(dict.fromkeys(required_api_endpoints)),
            })

    return results


@app.get("/agent/events")
def agent_events_stream(
    limit: int = 50,
    after_event_id: str | None = None,
    prefix: str | None = None,
    db: Session = Depends(get_db),
):
    """SSE stream of recent agent events from the audit log."""
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from backend.app.models import AuditLog as _AL  # noqa: PLC0415

    # Fetch recent audit entries and format as SSE
    try:
        query = db.query(_AL).order_by(_AL.timestamp.desc()).limit(limit)
        entries = list(reversed(query.all()))
    except Exception as _exc:
        if "no such table" in str(_exc).lower() or "audit_log" in str(_exc).lower():
            from fastapi.responses import Response  # noqa: PLC0415
            return Response(content="", media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
        raise

    # Apply after_event_id cursor: drop all entries up to and including the cursor
    if after_event_id:
        cursor_idx = next((i for i, e in enumerate(entries) if e.id == after_event_id), None)
        if cursor_idx is not None:
            entries = entries[cursor_idx + 1:]

    prefixes_filter = None
    if prefix:
        prefixes_filter = tuple(prefix.split(","))

    def _generate():
        for entry in entries:
            event_name = entry.action or "event"
            if prefixes_filter and not any(event_name.startswith(p) for p in prefixes_filter):
                continue
            data = {
                "log_id": entry.id,
                "case_id": entry.case_id,
                "action": entry.action,
                "actor": entry.actor,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "details": entry.details,
            }
            yield f"id: {entry.id}\nevent: {event_name}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Section 36: mRNA Safety Gate
# ---------------------------------------------------------------------------

from backend.app.safety.mrna_gate import evaluate_mrna_gate  # noqa: E402


class _MrnaGateRequest(_BaseModel):
    action: str
    species_mode: str
    content: str | None = None
    is_expert_mode: bool = False
    is_export: bool = False
    involves_sequence_data: bool = False


@app.post("/safety/mrna-gate")
def safety_mrna_gate(payload: _MrnaGateRequest) -> dict:
    result = evaluate_mrna_gate(
        action=payload.action,
        species_mode=payload.species_mode,
        content=payload.content,
        is_expert_mode=payload.is_expert_mode,
        is_export=payload.is_export,
        involves_sequence_data=payload.involves_sequence_data,
    )
    return {
        "status": result.status,
        "blocked": result.blocked,
        "needs_approval": result.needs_approval,
        "reason": result.reason,
        "blocked_patterns": result.blocked_patterns,
    }


# ---------------------------------------------------------------------------
# Section 36b: Pipeline framework adapter API
# ---------------------------------------------------------------------------

@app.get("/pipeline/framework/adapters")
def list_framework_adapters() -> list:
    """List all registered pipeline framework step adapters."""
    return [
        {"name": s.name, "description": getattr(s, "description", s.name)}
        for s in FRAMEWORK_STEPS
    ]


class _FrameworkAdapterTestRequest(_BaseModel):
    model_config = {"extra": "allow"}


@app.post("/pipeline/framework/adapters/{adapter_name}/test")
def test_framework_adapter(adapter_name: str, body: _FrameworkAdapterTestRequest = None) -> dict:
    """Run a named framework adapter step with the provided input and return the StepResult."""
    step = next((s for s in FRAMEWORK_STEPS if s.name == adapter_name), None)
    if step is None:
        raise HTTPException(
            status_code=404,
            detail=f"Adapter '{adapter_name}' not found. Available: {[s.name for s in FRAMEWORK_STEPS]}",
        )
    input_data = body.model_dump() if body is not None else {}
    result = step.run(input_data)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Section 37: Case/Subject Redaction and Case Deletion
# ---------------------------------------------------------------------------

_VALID_REDACTION_LEVELS = {"full", "deidentify", "anonymous", "deleted"}


class _CaseRedactRequest(_BaseModel):
    redaction_level: str
    confirm: bool = False
    reason: str | None = None

    @field_validator("redaction_level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        if v not in _VALID_REDACTION_LEVELS:
            raise ValueError(f"Invalid redaction_level: {v}. Must be one of {_VALID_REDACTION_LEVELS}")
        return v


@app.post("/cases/{case_id}/redact")
def redact_case(case_id: str, payload: _CaseRedactRequest, db: Session = Depends(get_db)) -> dict:
    """Apply a redaction level to a case and all its subjects."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required: set confirm=true")

    subjects = db.query(Subject).filter(Subject.case_id == case_id).all()
    subjects_updated = 0
    for subject in subjects:
        subject.redaction_level = payload.redaction_level
        if payload.redaction_level == "deidentify":
            subject.anonymized_display_name = f"REDACTED-{subject.id[:8].upper()}"
        elif payload.redaction_level == "anonymous":
            subject.anonymized_display_name = f"ANON-{subject.id[:8].upper()}"
            subject.metadata_json = {}
            subject.privacy_flags = {}
        subjects_updated += 1

    case.redaction_level = payload.redaction_level
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="case.redacted",
        details={
            "redaction_level": payload.redaction_level,
            "reason": payload.reason,
            "subjects_updated": subjects_updated,
        },
    )
    db.commit()

    return {
        "case_id": case_id,
        "redaction_level": payload.redaction_level,
        "subjects_updated": subjects_updated,
        "reason": payload.reason,
    }


@app.post("/cases/{case_id}/subjects/{subject_id}/redact")
def redact_subject(
    case_id: str,
    subject_id: str,
    payload: _CaseRedactRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Apply a redaction level to an individual subject."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    subject = db.query(Subject).filter(
        Subject.id == subject_id, Subject.case_id == case_id
    ).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required: set confirm=true")

    subject.redaction_level = payload.redaction_level
    if payload.redaction_level == "deidentify":
        subject.anonymized_display_name = f"REDACTED-{subject.id[:8].upper()}"
    elif payload.redaction_level == "anonymous":
        subject.anonymized_display_name = f"ANON-{subject.id[:8].upper()}"
        subject.metadata_json = {}
        subject.privacy_flags = {}

    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="subject.redacted",
        details={
            "subject_id": subject_id,
            "redaction_level": payload.redaction_level,
            "reason": payload.reason,
        },
    )
    db.commit()

    return {
        "subject_id": subject_id,
        "case_id": case_id,
        "redaction_level": payload.redaction_level,
        "reason": payload.reason,
    }


@app.delete("/cases/{case_id}")
def delete_case(
    case_id: str,
    confirm: bool = False,
    hard_delete: bool = False,
    reason: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Soft-delete or hard-delete a case."""
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if not confirm:
        raise HTTPException(status_code=400, detail="Confirmation required: set confirm=true")

    if hard_delete:
        log_action(
            db,
            case_id=case_id,
            actor="api",
            action="case.deleted",
            details={"hard_delete": True, "reason": reason},
        )
        db.commit()
        db.delete(case)
        db.commit()
    else:
        case.redaction_level = "deleted"
        log_action(
            db,
            case_id=case_id,
            actor="api",
            action="case.deleted",
            details={"hard_delete": False, "reason": reason},
        )
        db.commit()

    return {
        "case_id": case_id,
        "deleted": True,
        "hard_delete": hard_delete,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Section 38: WebSocket agent events endpoint
# ---------------------------------------------------------------------------

from fastapi import WebSocket, WebSocketDisconnect  # noqa: E402


@app.websocket("/agent/events/ws")
async def agent_events_ws(
    websocket: WebSocket,
    prefix: str | None = None,
    heartbeat: float = 30.0,
) -> None:
    """WebSocket endpoint that streams live published events.

    Query params:
      - prefix: comma-separated event name prefixes to filter on
      - heartbeat: seconds between ping frames when idle (min 1.0)
    """
    import asyncio  # noqa: PLC0415

    await websocket.accept()
    prefixes_filter: tuple[str, ...] | None = None
    if prefix:
        prefixes_filter = tuple(p for p in prefix.split(",") if p)

    heartbeat_interval = max(1.0, heartbeat)
    loop = asyncio.get_event_loop()

    try:
        with subscribe(prefixes=prefixes_filter) as q:
            while True:
                try:
                    # Run blocking queue.get in a thread pool so we don't block the event loop
                    envelope = await loop.run_in_executor(
                        None, lambda: q.get(timeout=heartbeat_interval)
                    )
                    event_name = envelope.get("event", "event")
                    payload = envelope.get("payload", {})
                    msg = {
                        "event": event_name,
                        "id": payload.get("log_id", event_name),
                        "data": payload,
                    }
                    await websocket.send_json(msg)
                except Exception:
                    # Timeout — send heartbeat ping
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Section 39: Bug fixes and enhancements (post-1789 additions)
# ---------------------------------------------------------------------------

# Import engine so it can be patched in tests via backend.app.main.engine
from backend.app.db import engine as engine, get_db_health_snapshot  # noqa: E402,F811


def _run_pipeline_sync(case_id: str) -> dict:
    """Module-level wrapper so tests can monkeypatch backend.app.main._run_pipeline_sync."""
    import asyncio as _asyncio  # noqa: PLC0415
    from backend.app.pipeline.base import run_mock_pipeline as _rmp  # noqa: PLC0415

    step_results = _asyncio.run(_rmp(case_id))
    serialized = [
        {
            "step_name": r.step_name,
            "step_version": r.step_version,
            "status": r.status.value,
            "outputs": r.outputs,
            "warnings": r.warnings,
            "errors": r.errors,
        }
        for r in step_results
    ]
    return {
        "status": "completed",
        "total_steps": len(serialized),
        "completed_steps": len(serialized),
        "steps": serialized,
    }


def _run_alphafold_sync(backend_name: str, payload: dict) -> dict:
    """Module-level wrapper so tests can monkeypatch backend.app.main._run_alphafold_sync.

    Uses the module-level execute_alphafold_backend reference so that
    tests can also monkeypatch backend.app.main.execute_alphafold_backend.
    """
    result = execute_alphafold_backend(backend_name, payload)
    return result.__dict__


# ---------------------------------------------------------------------------
# Override /health to include db snapshot
# ---------------------------------------------------------------------------

# Remove the old /health route registered in the sacred zone, then add a richer one.
app.router.routes = [
    r for r in app.router.routes
    if not (hasattr(r, "path") and r.path == "/health" and hasattr(r, "endpoint") and r.endpoint.__name__ == "health")
]


@app.get("/health")
async def health_with_db_snapshot() -> JSONResponse:
    """Enhanced health endpoint that includes DB status snapshot."""
    body: dict = {
        "status": "ok",
        "version": "0.1.0-alpha",
        "mode": settings.species_mode.value,
    }
    try:
        snapshot = get_db_health_snapshot(engine)
        body.update(snapshot)
        if snapshot.get("db_status") == "degraded":
            body["status"] = "degraded"
            return JSONResponse(status_code=503, content=body)
    except Exception as _e:
        body["db_status"] = "error"
        body["db_error"] = str(_e)
    return JSONResponse(status_code=200, content=body)


# ---------------------------------------------------------------------------
# Override /cases/{case_id}/pipeline/run to also emit pipeline.step.completed
# ---------------------------------------------------------------------------

app.router.routes = [
    r for r in app.router.routes
    if not (
        hasattr(r, "path") and r.path == "/cases/{case_id}/pipeline/run"
        and hasattr(r, "endpoint") and r.endpoint.__name__ == "run_pipeline"
    )
]


@app.post("/cases/{case_id}/pipeline/run", response_model=PipelineRunRead, status_code=201)
def run_pipeline_with_step_audit(case_id: str, db: Session = Depends(get_db)) -> PipelineRunRead:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    enforce_preflight_or_raise(action="run_pipeline", species_mode=case.species.value)

    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.started",
        inputs={"case_id": case_id, "mode": settings.pipeline_mode},
        outputs={"status": "running"},
    )
    step_results_raw = asyncio.run(run_mock_pipeline(case_id))
    serialized_steps = [
        {
            "step_name": result.step_name,
            "step_version": result.step_version,
            "status": result.status.value,
            "outputs": result.outputs,
            "warnings": result.warnings,
            "errors": result.errors,
            "safety_label": result.safety_label,
            "requires_professional_review": result.requires_professional_review,
        }
        for result in step_results_raw
    ]
    pipeline_run = PipelineRun(
        id=str(uuid4()),
        case_id=case_id,
        status="completed",
        current_step=serialized_steps[-1]["step_name"] if serialized_steps else None,
        completed_steps=len(serialized_steps),
        total_steps=len(serialized_steps),
        step_results={"steps": serialized_steps},
        finished_at=datetime.now(UTC),
    )
    db.add(pipeline_run)
    db.flush()
    for step in serialized_steps:
        step_action = "pipeline.step.failed" if step["status"] == "failed" else "pipeline.step.completed"
        log_action(
            db,
            case_id=case_id,
            actor="api",
            action=step_action,
            inputs={"case_id": case_id, "step_name": step["step_name"]},
            outputs={"step_name": step["step_name"], "status": step["status"]},
        )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="pipeline.completed",
        inputs={"case_id": case_id},
        outputs={"pipeline_run_id": pipeline_run.id, "status": pipeline_run.status},
    )
    db.commit()
    db.refresh(pipeline_run)
    return serialize_pipeline_run(pipeline_run)


# ---------------------------------------------------------------------------
# Override /alphafold/backends/{backend_name}/run to add job.started/completed audit
# ---------------------------------------------------------------------------

app.router.routes = [
    r for r in app.router.routes
    if not (
        hasattr(r, "path") and r.path == "/alphafold/backends/{backend_name}/run"
        and hasattr(r, "endpoint") and r.endpoint.__name__ == "alphafold_backend_run"
    )
]


class _AlphaFoldValidationErrorResponse(_BaseModel):
    backend_name: str
    validation_ok: bool
    validation_reason: str

_AF_RUN_BODY_EXAMPLE = {
    "case_id": "abc-123",
    "candidate_id": "cand-001",
    "sequence": "MVLSPADKTNVKAAWGKVGAH",
    "options": {"max_template_date": "2024-01-01"},
}

@app.post(
    "/alphafold/backends/{backend_name}/run",
    summary="AlphaFold Backend Run With Audit",
    description=(
        "Run a structure prediction on the given backend (mock, colabfold, "
        "local_colabfold, alphafold2_local, alphafold3_local, alphafold_server, "
        "alphafold_db). Logs job.started and job.completed audit events."
    ),
    responses={
        409: {
            "description": "Backend validation failed — the backend is not available or mis-configured.",
            "content": {
                "application/json": {
                    "example": {
                        "backend_name": "colabfold",
                        "validation_ok": False,
                        "validation_reason": "colabfold binary not found on PATH",
                    },
                    "schema": {"$ref": "#/components/schemas/AlphaFoldValidationErrorResponse"},
                },
            },
        },
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": _AF_RUN_BODY_EXAMPLE,
                },
            },
        },
    },
)
def alphafold_backend_run_with_audit(backend_name: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    validate_alphafold_payload_or_422(backend_name, payload)
    case_id = payload.get("case_id")
    case = db.get(Case, case_id) if case_id else None
    if case is not None:
        involves_external_upload = backend_name == "alphafold_server" and not payload.get("acknowledge_external_upload", False)
        enforce_preflight_or_raise(
            action="alphafold_backend_run",
            species_mode=case.species.value,
            involves_external_upload=involves_external_upload,
        )
    try:
        backend_status = get_shell_backend_status(backend_name)
        if (
            execute_alphafold_backend is alphafold_shells.execute_alphafold_backend
            and not backend_status.validation_ok
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        f"AlphaFold backend '{backend_name}' failed environment validation: "
                        f"{backend_status.validation_reason}"
                    ),
                    "backend_name": backend_name,
                    "validation_ok": False,
                    "validation_reason": backend_status.validation_reason,
                },
            )
        log_action(
            db,
            case_id=case_id,
            actor="api",
            action="alphafold.job.started",
            inputs={"backend": backend_name, **payload},
            outputs={"status": "running"},
        )
        result = execute_alphafold_backend(backend_name, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="AlphaFold backend not found") from None

    execution = record_execution_run(
        db,
        case_id=case_id,
        runner_kind="alphafold_backend",
        runner_name=backend_name,
        result=result.__dict__,
    )
    execution.parse_status, execution.parse_error = apply_parsed_alphafold_output(
        db,
        case_id=case_id,
        result=result.__dict__,
        execution_id=execution.id,
    )
    if case_id and payload.get("candidate_id"):
        candidate = db.get(CandidateAntigen, payload["candidate_id"])
        if candidate is not None and candidate.case_id == case_id:
            structure_payload = json.loads(result.stdout).get("structure", {}) if result.stdout else {}
            output_path = structure_payload.get("model_cif") or structure_payload.get("pdb_file")
            confidence_metrics = {
                key: structure_payload[key]
                for key in (
                    "pLDDT_mean", "pAE_mean", "ranking_score", "ptm", "iptm",
                    "chain_pair_iptm", "source_url", "summary_confidences_json",
                    "output_format", "accession",
                )
                if key in structure_payload
            }
            structure_job = StructureJob(
                id=str(uuid4()),
                case_id=case_id,
                candidate_id=candidate.id,
                backend_used=backend_name,
                output_path=output_path,
                confidence_metrics=confidence_metrics,
                status=result.status,
            )
            db.add(structure_job)
            db.flush()
    shell_artifacts = persist_execution_artifacts(db=db, result=result.__dict__, execution_id=execution.id, case_id=case_id)
    execution.command = {"argv": result.__dict__["command"], "artifact_paths": [artifact.path for artifact in shell_artifacts]}
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="alphafold.job.completed",
        inputs={"backend": backend_name},
        outputs={"status": result.status, "execution_id": execution.id},
    )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="alphafold.backend.completed",
        inputs={"backend": backend_name},
        outputs={"status": result.status, "execution_id": execution.id},
    )
    log_action(
        db,
        case_id=case_id,
        actor="api",
        action="alphafold.backend.run",
        inputs={"backend": backend_name, **payload},
        outputs={"status": result.status, "return_code": result.return_code, "execution_id": execution.id, "artifact_count": len(shell_artifacts)},
    )
    db.commit()
    return result.__dict__


# ---------------------------------------------------------------------------
# Patch OpenAPI schema to include AlphaFoldValidationErrorResponse
# ---------------------------------------------------------------------------
_original_openapi = app.openapi


def _patched_openapi():
    schema = _original_openapi()
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    if "AlphaFoldValidationErrorResponse" not in schemas:
        schemas["AlphaFoldValidationErrorResponse"] = _AlphaFoldValidationErrorResponse.model_json_schema()
    return schema


app.openapi = _patched_openapi
