"""NeoVax-Agent Privacy Module

Per-case data directories, file retention policies, cloud upload privacy gates,
and audit export utilities.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import AuditLog, Case, Sample

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Per-case data directories
# ---------------------------------------------------------------------------

CASE_DATA_SUBDIRS = ("uploads", "artifacts", "reports", "structures")


def case_data_root() -> Path:
    return Path(settings.artifact_root).expanduser().resolve() / "cases"


def case_data_dir(case_id: str) -> Path:
    return case_data_root() / case_id


def ensure_case_data_dir(case_id: str) -> Path:
    root = case_data_dir(case_id)
    for sub in CASE_DATA_SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    logger.info("case_data_dir_ensured", case_id=case_id, path=str(root))
    return root


def remove_case_data_dir(case_id: str) -> bool:
    root = case_data_dir(case_id)
    if root.exists():
        shutil.rmtree(root)
        logger.info("case_data_dir_removed", case_id=case_id, path=str(root))
        return True
    return False


def list_case_data_files(case_id: str) -> list[dict]:
    root = case_data_dir(case_id)
    if not root.exists():
        return []
    result = []
    for f in root.rglob("*"):
        if f.is_file():
            stat = f.stat()
            result.append({
                "path": str(f.relative_to(root)),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            })
    return result


# ---------------------------------------------------------------------------
# File retention policy
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 365


def get_retention_days() -> int:
    return DEFAULT_RETENTION_DAYS


def find_expired_artifacts(db: Session, *, retention_days: int | None = None) -> list[dict]:
    days = retention_days or get_retention_days()
    cutoff = datetime.now(UTC) - timedelta(days=days)
    from backend.app.models import Artifact
    expired = (
        db.query(Artifact)
        .filter(Artifact.saved_at < cutoff)
        .all()
    )
    return [
        {
            "artifact_id": a.id,
            "case_id": a.case_id,
            "path": a.path,
            "saved_at": a.saved_at.isoformat() if a.saved_at else None,
            "age_days": (datetime.now(UTC) - a.saved_at).days if a.saved_at else None,
        }
        for a in expired
    ]


# ---------------------------------------------------------------------------
# Cloud upload privacy gate
# ---------------------------------------------------------------------------


def check_cloud_upload_allowed(
    *,
    case_id: str | None = None,
    backend_name: str | None = None,
) -> dict:
    if not settings.cloud_upload_enabled:
        return {
            "allowed": False,
            "reason": "Cloud uploads are disabled by configuration (NEOVAX_CLOUD_UPLOAD_ENABLED=false).",
            "requires_confirmation": False,
        }

    requires_confirmation = settings.cloud_upload_confirmation_required
    warnings = []

    if backend_name and backend_name in ("alphafold_server", "alphafold_db"):
        warnings.append(
            f"Backend '{backend_name}' sends sequence data to an external server. "
            "Review the provider's data-use and privacy policies before proceeding."
        )

    return {
        "allowed": True,
        "requires_confirmation": requires_confirmation,
        "warnings": warnings,
        "case_id": case_id,
        "backend_name": backend_name,
    }


# ---------------------------------------------------------------------------
# Audit export
# ---------------------------------------------------------------------------


def export_audit_log(
    db: Session,
    *,
    case_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    format: str = "json",
) -> str:
    query = db.query(AuditLog).order_by(AuditLog.timestamp.asc())

    if case_id is not None:
        query = query.filter(AuditLog.case_id == case_id)
    if since is not None:
        query = query.filter(AuditLog.timestamp >= since)
    if until is not None:
        query = query.filter(AuditLog.timestamp <= until)

    entries = query.all()

    rows = [
        {
            "id": e.id,
            "case_id": e.case_id,
            "actor": e.actor,
            "action": e.action,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "inputs_hash": e.inputs_hash,
            "outputs_hash": e.outputs_hash,
            "safety_gate_result": e.safety_gate_result,
            "details": e.details,
        }
        for e in entries
    ]

    if format == "json":
        return json.dumps({"audit_log": rows, "exported_at": datetime.now(UTC).isoformat()}, indent=2)

    lines = [
        "# NeoVax-Agent Audit Log Export",
        f"Exported: {datetime.now(UTC).isoformat()}",
        f"Total entries: {len(rows)}",
        "",
    ]
    for r in rows:
        lines.append(f"- [{r['timestamp']}] {r['actor']}: {r['action']} (case={r['case_id']}, gate={r['safety_gate_result']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Privacy summary for a case
# ---------------------------------------------------------------------------


def build_case_privacy_summary(case_id: str, db: Session) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        return {"error": "Case not found"}

    samples = db.query(Sample).filter(Sample.case_id == case_id).all()
    data_files = list_case_data_files(case_id)

    return {
        "case_id": case_id,
        "redaction_level": case.redaction_level,
        "consent_status": case.consent_status,
        "cloud_upload_enabled": settings.cloud_upload_enabled,
        "encryption_at_rest": settings.encryption_at_rest_enabled,
        "data_directory": str(case_data_dir(case_id)),
        "data_directory_exists": case_data_dir(case_id).exists(),
        "file_count": len(data_files),
        "sample_count": len(samples),
        "retention_days": get_retention_days(),
    }
