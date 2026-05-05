"""Pydantic schemas for the NeoVax API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.config import SpeciesMode
from backend.app.models import AgentFrameworkEnum, ReviewStatusEnum, SampleTypeEnum


class CaseCreate(BaseModel):
    species: SpeciesMode
    diagnosis_summary: str | None = None
    supervising_professional: str | None = None


class CaseUpdate(BaseModel):
    diagnosis_summary: str | None = None
    supervising_professional: str | None = None
    consent_status: str | None = None
    review_status: str | None = None

    @field_validator("consent_status", "review_status", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Field may not be null")
        return value


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    species: SpeciesMode
    diagnosis_summary: str | None
    supervising_professional: str | None
    consent_status: str
    review_status: str
    redaction_level: str = "full"
    created_at: datetime
    updated_at: datetime


class SampleCreate(BaseModel):
    subject_id: str | None = None
    sample_type: SampleTypeEnum
    file_paths: dict[str, str] | None = None
    checksum: str | None = None
    source_lab: str | None = None
    custody_metadata: dict[str, str] | None = None


class SampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None
    subject_id: str | None
    sample_type: SampleTypeEnum
    file_paths: dict[str, str] | None
    checksum: str | None
    source_lab: str | None
    custody_metadata: dict[str, str] | None
    created_at: datetime


class SubjectCreate(BaseModel):
    anonymized_display_name: str
    metadata_json: dict | None = None
    privacy_flags: dict | None = None


class SubjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    anonymized_display_name: str
    metadata_json: dict | None
    privacy_flags: dict | None
    redaction_level: str = "full"
    created_at: datetime


class CaseTaskCreate(BaseModel):
    title: str
    status: str = "todo"
    owner: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class CaseTaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    owner: str | None = None
    due_date: datetime | None = None
    notes: str | None = None


class CaseTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    title: str
    status: str
    owner: str | None
    due_date: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AgentTaskCreate(BaseModel):
    framework: AgentFrameworkEnum
    skill_name: str
    status: str = "pending"
    logs: dict | None = None
    artifacts: dict | None = None


class AgentTaskUpdate(BaseModel):
    framework: AgentFrameworkEnum | None = None
    skill_name: str | None = None
    status: str | None = None
    logs: dict | None = None
    artifacts: dict | None = None


class AgentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None
    framework: AgentFrameworkEnum
    skill_name: str
    status: str
    logs: dict | None
    artifacts: dict | None
    created_at: datetime


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    sample_id: str | None
    genomic_coordinates: str
    gene: str | None
    transcript: str | None
    protein_change: str | None
    caller_source: str | None
    quality_metrics: dict | None
    annotation_source: str | None
    expert_review_notes: str | None
    last_parsed_execution_id: str | None
    review_status: str
    created_at: datetime


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    variant_id: str
    peptide_metadata: dict | None
    mhc_context: str | None
    prediction_scores: dict | None
    expression_evidence: dict | None
    structure_evidence: dict | None
    uncertainty_flags: dict | None
    expert_review_notes: str | None
    last_parsed_execution_id: str | None
    review_status: str
    created_at: datetime


class VariantCreate(BaseModel):
    sample_id: str | None = None
    genomic_coordinates: str
    gene: str | None = None
    transcript: str | None = None
    protein_change: str | None = None
    caller_source: str | None = None
    quality_metrics: dict | None = None
    annotation_source: str | None = None


class CandidateCreate(BaseModel):
    variant_id: str
    peptide_metadata: dict | None = None
    mhc_context: str | None = None
    prediction_scores: dict | None = None
    expression_evidence: dict | None = None
    structure_evidence: dict | None = None
    uncertainty_flags: dict | None = None


class ReviewUpdate(BaseModel):
    review_status: ReviewStatusEnum
    expert_review_notes: str | None = None


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None
    actor: str
    action: str
    timestamp: datetime
    inputs_hash: str | None
    outputs_hash: str | None
    safety_gate_result: str
    details: dict | None


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    report_type: str
    generated_at: datetime
    generated_by: str
    redaction_level: str
    export_path: str | None
    content_json: dict | None
    safety_label: str
    content_text: str | None = None


class StructureJobCreate(BaseModel):
    candidate_id: str
    backend_used: str
    input_hash: str | None = None
    output_path: str | None = None
    confidence_metrics: dict | None = None
    visualization_path: str | None = None
    status: str = "queued"


class StructureJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    candidate_id: str
    backend_used: str
    input_hash: str | None
    output_path: str | None
    confidence_metrics: dict | None
    visualization_path: str | None
    status: str
    created_at: datetime


class ReportExport(BaseModel):
    report_id: str
    format: Literal["markdown", "json"]
    content_text: str | None = None
    content_json: dict | None = None
    safety_label: str


class PipelineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    status: str
    current_step: str | None
    completed_steps: int
    total_steps: int
    step_results: dict | None
    steps: list[dict] = []
    started_at: datetime
    finished_at: datetime | None


class CaseBundleRead(BaseModel):
    case: CaseRead
    subjects: list[SubjectRead]
    samples: list[SampleRead]
    variants: list[VariantRead]
    candidates: list[CandidateRead]
    tasks: list[CaseTaskRead]
    agent_tasks: list[AgentTaskRead]
    reports: list[ReportRead]
    latest_pipeline_run: PipelineRunRead | None = None
    audit_log: list[AuditLogRead]
    safety_label: str


class CaseBundleExport(BaseModel):
    case_id: str
    format: Literal["markdown", "json"]
    content_text: str | None = None
    content_json: dict | None = None
    safety_label: str


class SavedArtifact(BaseModel):
    id: str
    path: str
    filename: str
    download_url: str
    format: Literal["markdown", "json", "binary"]
    mime_type: str
    file_size: int
    content_hash: str | None = None
    saved_at: datetime
    artifact_type: str
    case_id: str | None = None
    report_id: str | None = None


class ExecutionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None
    runner_kind: str
    runner_name: str
    status: str
    command: dict | None
    stdout: str | None
    stderr: str | None
    parse_status: str | None = None
    parse_error: str | None = None
    timed_out: bool
    return_code: int | None
    created_at: datetime
    artifacts: list[SavedArtifact] = []


class UnifiedRunRead(BaseModel):
    id: str
    case_id: str
    run_kind: str
    name: str
    status: str
    created_at: datetime
    details: dict | None = None
    artifacts: list[SavedArtifact] = []


class SafetyPreflightRequest(BaseModel):
    action: str
    species_mode: SpeciesMode
    content: str | None = None
    is_expert_mode: bool = False
    is_export: bool = False
    involves_external_upload: bool = False
    involves_sequence_data: bool = False


class SafetyPreflightResponse(BaseModel):
    status: str
    allowed: bool
    blocked: bool
    needs_approval: bool
    reason: str | None = None
    blocked_patterns: list[str] = []


class ErrorResponse(BaseModel):
    detail: str


class AlphaFoldValidationErrorResponse(BaseModel):
    detail: str
    backend_name: str
    validation_ok: Literal[False]
    validation_reason: str
