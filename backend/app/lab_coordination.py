"""FoldAgent Lab Coordination Module (Phase 10)

Licensed lab outreach, sequencing provider checklists, cost/timeline tracking,
contact logs, and professional collaboration utilities.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

import structlog
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.models import Base

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LabContact(Base):
    __tablename__ = "lab_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cases.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(200))
    organization: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class CostEntry(Base):
    __tablename__ = "cost_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    category: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(50), default="estimated")
    date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class TimelineEntry(Base):
    __tablename__ = "timeline_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class DocumentRequest(Base):
    __tablename__ = "document_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    document_type: Mapped[str] = mapped_column(String(200))
    requested_from: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

SEQUENCING_PROVIDER_CHECKLIST = [
    "Confirm species-appropriate reference genome availability",
    "Confirm tumor/normal matched pair sequencing capability",
    "Confirm whole-exome or whole-genome sequencing (WES/WGS) availability",
    "Request sample handling and chain-of-custody documentation",
    "Confirm data format output (FASTQ, BAM, VCF)",
    "Confirm turnaround time and pricing",
    "Confirm data security and privacy handling procedures",
    "Request information on quality control metrics provided",
]

RNA_MANUFACTURING_CHECKLIST = [
    "Confirm GMP or research-grade mRNA synthesis capability",
    "Confirm ability to accept custom sequence specifications",
    "Request quality control and purity documentation procedures",
    "Confirm regulatory compliance status for research use",
    "DO NOT request dosing, formulation, or administration instructions",
    "DO NOT request LNP encapsulation protocols",
    "Confirm chain-of-custody and storage requirements",
]

UNIVERSITY_OUTREACH_TEMPLATE = """Subject: Research Collaboration Inquiry — Personalized Cancer Vaccine Computational Pipeline

Dear [Researcher Name],

I am writing to inquire about potential research collaboration on a computational biology project focused on personalized cancer vaccine candidate identification.

Our project, FoldAgent, is an open-source research coordination platform that assists with:
- Somatic variant calling from tumor/normal sequencing data
- Neoantigen candidate ranking using established prediction tools
- Protein structure analysis via AlphaFold backends
- Transparent, auditable reporting for expert review

We are looking for collaborators with expertise in [specific area].

This is a research coordination tool only — it does not produce administerable treatments or provide medical advice. All outputs require professional expert review.

I would welcome the opportunity to discuss how our project might support your research goals.

Best regards,
[Your Name]
"""

SECURE_HANDOFF_CHECKLIST = [
    "Verify recipient identity and authorization",
    "Use encrypted file transfer (SFTP, institutional secure share, or equivalent)",
    "DO NOT send sensitive genomic data via unencrypted email",
    "Include data-use agreement or MTA reference",
    "Log the transfer in the audit trail",
    "Confirm receipt and integrity (checksums)",
    "Remove local copies if retention policy requires it",
]

EMAIL_PRIVACY_WARNING = (
    "WARNING: Do not send sensitive genomic data, patient/animal identifiers, "
    "or sequencing files via unencrypted email. Use institutional secure file "
    "transfer services or encrypted channels."
)

LAB_OUTREACH_EMAIL_TEMPLATE = """Subject: Research Inquiry — {service_type} for Personalized Cancer Vaccine Research

Dear {contact_name},

I am reaching out regarding {service_type} services for a research project involving personalized cancer vaccine candidate identification.

Case summary:
- Species: {species}
- Case ID: {case_id}
- Diagnosis: {diagnosis_summary}

We are seeking:
{service_description}

This inquiry is for research coordination purposes only. All clinical decisions require licensed professional oversight.

Please let me know if you would be able to discuss this further.

Best regards,
{sender_name}

---
Generated by FoldAgent — Research coordination platform
This is NOT a medical or veterinary treatment request.
"""


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def create_lab_contact(db: Session, *, case_id: str | None, name: str, role: str, **kwargs) -> LabContact:
    contact = LabContact(id=str(uuid4()), case_id=case_id, name=name, role=role, **kwargs)
    db.add(contact)
    db.flush()
    return contact


def list_lab_contacts(db: Session, case_id: str | None = None) -> list[LabContact]:
    query = db.query(LabContact)
    if case_id:
        query = query.filter(LabContact.case_id == case_id)
    return query.order_by(LabContact.created_at.desc()).all()


def create_cost_entry(db: Session, *, case_id: str, category: str, description: str, **kwargs) -> CostEntry:
    entry = CostEntry(id=str(uuid4()), case_id=case_id, category=category, description=description, **kwargs)
    db.add(entry)
    db.flush()
    return entry


def list_cost_entries(db: Session, case_id: str) -> list[CostEntry]:
    return db.query(CostEntry).filter(CostEntry.case_id == case_id).order_by(CostEntry.created_at.desc()).all()


def get_cost_summary(db: Session, case_id: str) -> dict:
    entries = list_cost_entries(db, case_id)
    total = sum(e.amount_cents for e in entries)
    by_category: dict[str, int] = {}
    for e in entries:
        by_category[e.category] = by_category.get(e.category, 0) + e.amount_cents
    return {
        "case_id": case_id,
        "total_cents": total,
        "total_display": f"${total / 100:.2f}",
        "entry_count": len(entries),
        "by_category": {k: f"${v / 100:.2f}" for k, v in by_category.items()},
    }


def create_timeline_entry(db: Session, *, case_id: str, title: str, **kwargs) -> TimelineEntry:
    entry = TimelineEntry(id=str(uuid4()), case_id=case_id, title=title, **kwargs)
    db.add(entry)
    db.flush()
    return entry


def list_timeline_entries(db: Session, case_id: str) -> list[TimelineEntry]:
    return db.query(TimelineEntry).filter(TimelineEntry.case_id == case_id).order_by(TimelineEntry.due_date.asc().nullslast()).all()


def create_document_request(db: Session, *, case_id: str, document_type: str, **kwargs) -> DocumentRequest:
    entry = DocumentRequest(id=str(uuid4()), case_id=case_id, document_type=document_type, **kwargs)
    db.add(entry)
    db.flush()
    return entry


def list_document_requests(db: Session, case_id: str) -> list[DocumentRequest]:
    return db.query(DocumentRequest).filter(DocumentRequest.case_id == case_id).order_by(DocumentRequest.created_at.desc()).all()


def generate_outreach_email(
    *,
    service_type: str,
    contact_name: str = "[Contact Name]",
    species: str = "demo",
    case_id: str = "",
    diagnosis_summary: str = "",
    service_description: str = "",
    sender_name: str = "[Your Name]",
) -> str:
    return LAB_OUTREACH_EMAIL_TEMPLATE.format(
        service_type=service_type,
        contact_name=contact_name,
        species=species,
        case_id=case_id,
        diagnosis_summary=diagnosis_summary,
        service_description=service_description,
        sender_name=sender_name,
    )


def get_case_summary_packet(db: Session, case_id: str) -> dict:
    from backend.app.models import Case, Sample, Variant, CandidateAntigen, Report
    case = db.get(Case, case_id)
    if case is None:
        return {"error": "Case not found"}
    return {
        "case_id": case_id,
        "species": case.species.value,
        "diagnosis_summary": case.diagnosis_summary,
        "consent_status": case.consent_status,
        "sample_count": db.query(Sample).filter(Sample.case_id == case_id).count(),
        "variant_count": db.query(Variant).filter(Variant.case_id == case_id).count(),
        "candidate_count": db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).count(),
        "report_count": db.query(Report).filter(Report.case_id == case_id).count(),
        "privacy_warning": EMAIL_PRIVACY_WARNING,
        "generated_at": datetime.now(UTC).isoformat(),
        "disclaimer": "Research coordination summary only — not a treatment plan.",
    }
