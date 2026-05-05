"""FoldAgent SQLAlchemy Models

Core data model for the local-first research coordination platform.
All entities include audit trail fields and safety gate tracking.
"""

import enum
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Enum,
    Float,
    Boolean,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SpeciesEnum(str, enum.Enum):
    """Species mode for a case."""

    demo = "demo"
    dog = "dog"
    human = "human"


class SampleTypeEnum(str, enum.Enum):
    """Sample type classification."""

    tumor = "tumor"
    normal = "normal"
    rna = "rna"
    other = "other"


class ReviewStatusEnum(str, enum.Enum):
    """Expert review status."""

    unreviewed = "unreviewed"
    needs_data = "needs_data"
    expert_rejected = "expert_rejected"
    expert_accepted = "expert_accepted_for_further_research"


class RedactionLevelEnum(str, enum.Enum):
    """Redaction level for case data privacy.

    - ``full``: all data visible (default)
    - ``deidentify``: PII fields replaced with placeholders, identifiers scrambled
    - ``anonymous``: only aggregate / statistical data retained
    - ``deleted``: data marked as permanently deleted (soft-delete marker)
    """

    full = "full"
    deidentify = "deidentify"
    anonymous = "anonymous"
    deleted = "deleted"


class PipelineStatusEnum(str, enum.Enum):
    """Pipeline run status."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StructureJobStatusEnum(str, enum.Enum):
    """AlphaFold structure job status."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class BackgroundJobStatusEnum(str, enum.Enum):
    """Background job lifecycle status."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class AgentFrameworkEnum(str, enum.Enum):
    """Agent framework types."""

    claude_code = "claude_code"
    openclaw = "openclaw"
    hermes = "hermes"
    other = "other"


# --- Case ---

class Case(Base):
    """Research case. Top-level entity linking all other records."""

    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    species: Mapped[SpeciesEnum] = mapped_column(Enum(SpeciesEnum), default=SpeciesEnum.demo)
    diagnosis_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supervising_professional: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(50), default="pending")
    review_status: Mapped[str] = mapped_column(String(50), default="unreviewed")
    redaction_level: Mapped[str] = mapped_column(String(50), default="full")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    subjects: Mapped[list["Subject"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    samples: Mapped[list["Sample"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    variants: Mapped[list["Variant"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    candidates: Mapped[list["CandidateAntigen"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    structure_jobs: Mapped[list["StructureJob"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    tasks: Mapped[list["CaseTask"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    agent_tasks: Mapped[list["AgentTask"]] = relationship(back_populates="case")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="case", cascade="all, delete-orphan")


# --- Subject ---

class Subject(Base):
    """Subject (human or animal) metadata for a case."""

    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    anonymized_display_name: Mapped[str] = mapped_column(String(200))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    privacy_flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    redaction_level: Mapped[str] = mapped_column(String(50), default="full")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="subjects")
    samples: Mapped[list["Sample"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


# --- Sample ---

class Sample(Base):
    """Sequencing sample metadata registration."""

    __tablename__ = "samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    subject_id: Mapped[Optional[str]] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    sample_type: Mapped[SampleTypeEnum] = mapped_column(Enum(SampleTypeEnum))
    file_paths: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_lab: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    custody_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="samples")
    subject: Mapped[Optional["Subject"]] = relationship(back_populates="samples")
    variants: Mapped[list["Variant"]] = relationship(cascade="all, delete-orphan")


# --- Variant ---

class Variant(Base):
    """Called and annotated variant."""

    __tablename__ = "variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    sample_id: Mapped[Optional[str]] = mapped_column(ForeignKey("samples.id"), nullable=True)
    genomic_coordinates: Mapped[str] = mapped_column(String(500))
    gene: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    protein_change: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    caller_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    quality_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    annotation_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    expert_review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_parsed_execution_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    review_status: Mapped[ReviewStatusEnum] = mapped_column(
        Enum(ReviewStatusEnum), default=ReviewStatusEnum.unreviewed
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="variants")
    sample: Mapped[Optional["Sample"]] = relationship(back_populates="variants")
    candidates: Mapped[list["CandidateAntigen"]] = relationship(back_populates="variant", cascade="all, delete-orphan")


# --- CandidateAntigen ---

class CandidateAntigen(Base):
    """Candidate neoantigen for review."""

    __tablename__ = "candidate_antigens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"))
    peptide_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mhc_context: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    prediction_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expression_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    structure_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    uncertainty_flags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expert_review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_parsed_execution_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    review_status: Mapped[ReviewStatusEnum] = mapped_column(
        Enum(ReviewStatusEnum), default=ReviewStatusEnum.unreviewed
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="candidates")
    variant: Mapped["Variant"] = relationship(back_populates="candidates")
    structure_jobs: Mapped[list["StructureJob"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


# --- StructureJob ---

class StructureJob(Base):
    """AlphaFold structure prediction job."""

    __tablename__ = "structure_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidate_antigens.id"))
    backend_used: Mapped[str] = mapped_column(String(100))
    input_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    output_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    visualization_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[StructureJobStatusEnum] = mapped_column(
        Enum(StructureJobStatusEnum), default=StructureJobStatusEnum.queued
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="structure_jobs")
    candidate: Mapped["CandidateAntigen"] = relationship(back_populates="structure_jobs")


# --- PipelineRun ---

class PipelineRun(Base):
    """Mock or real bioinformatics pipeline execution state."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    status: Mapped[PipelineStatusEnum] = mapped_column(Enum(PipelineStatusEnum), default=PipelineStatusEnum.pending)
    current_step: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    step_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    case: Mapped["Case"] = relationship(back_populates="pipeline_runs")


# --- ExecutionRun ---

class ExecutionRun(Base):
    """Execution history for shell wrappers and future real adapters."""

    __tablename__ = "execution_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    runner_kind: Mapped[str] = mapped_column(String(100))
    runner_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    command: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stdout: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stderr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parse_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    parse_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    return_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped[Optional["Case"]] = relationship()


# --- Artifact ---

class Artifact(Base):
    """Persistent artifact registry for saved files."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    execution_run_id: Mapped[Optional[str]] = mapped_column(ForeignKey("execution_runs.id"), nullable=True)
    report_id: Mapped[Optional[str]] = mapped_column(ForeignKey("reports.id"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(1000))
    filename: Mapped[str] = mapped_column(String(300))
    format: Mapped[str] = mapped_column(String(50))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped[Optional["Case"]] = relationship()
    execution_run: Mapped[Optional["ExecutionRun"]] = relationship()
    report: Mapped[Optional["Report"]] = relationship()


# --- CaseTask ---

class CaseTask(Base):
    """Coordination tasks attached to a case."""

    __tablename__ = "case_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(50), default="todo")
    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    case: Mapped["Case"] = relationship(back_populates="tasks")


# --- Report ---

class Report(Base):
    """Generated report (candidate review, ethics package, etc.)."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    report_type: Mapped[str] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    generated_by: Mapped[str] = mapped_column(String(200))
    redaction_level: Mapped[str] = mapped_column(String(50), default="full")
    export_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    safety_label: Mapped[str] = mapped_column(
        String(200), default="Research candidate only — not administerable"
    )

    case: Mapped["Case"] = relationship(back_populates="reports")


# --- AgentTask ---

class AgentTask(Base):
    """Agent (Claude/OpenClaw/Hermes) task record."""

    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    framework: Mapped[AgentFrameworkEnum] = mapped_column(Enum(AgentFrameworkEnum))
    skill_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    logs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    artifacts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    case: Mapped[Optional["Case"]] = relationship(back_populates="agent_tasks")


# --- BackgroundJob ---

class BackgroundJob(Base):
    """Persisted background job with lifecycle state for async execution."""

    __tablename__ = "background_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[BackgroundJobStatusEnum] = mapped_column(
        Enum(BackgroundJobStatusEnum), default=BackgroundJobStatusEnum.pending
    )
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    case: Mapped[Optional["Case"]] = relationship()


# --- AuditLog ---

class AuditLog(Base):
    """Append-only audit log for all actions."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(200))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    inputs_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    outputs_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    safety_gate_result: Mapped[str] = mapped_column(String(50))  # pass / block / requires_approval
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    case: Mapped[Optional["Case"]] = relationship(back_populates="audit_logs")