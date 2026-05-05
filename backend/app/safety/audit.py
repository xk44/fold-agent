"""NeoVax-Agent Audit Logging

Append-only, tamper-evident audit log system.
Every action (user, system, or agent) must be recorded here.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

import structlog

from backend.app.event_stream import publish_event

logger = structlog.get_logger()


class SafetyGateResult:
    PASS = "pass"
    BLOCK = "block"
    REQUIRES_APPROVAL = "requires_approval"


def compute_hash(data: dict | str | None) -> Optional[str]:
    """Compute SHA-256 hash of data for audit integrity."""
    if data is None:
        return None
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def log_action(
    db_session,
    *,
    case_id: Optional[str],
    actor: str,
    action: str,
    inputs: Optional[dict] = None,
    outputs: Optional[dict] = None,
    safety_gate_result: str = SafetyGateResult.PASS,
    details: Optional[dict] = None,
) -> str:
    """Log an action to the audit trail."""
    from backend.app.models import AuditLog

    log_id = str(uuid4())
    timestamp = datetime.now(UTC)

    entry = AuditLog(
        id=log_id,
        case_id=case_id,
        actor=actor,
        action=action,
        timestamp=timestamp,
        inputs_hash=compute_hash(inputs),
        outputs_hash=compute_hash(outputs),
        safety_gate_result=safety_gate_result,
        details=details,
    )

    db_session.add(entry)
    db_session.flush()

    publish_event(
        action,
        {
            "log_id": log_id,
            "case_id": case_id,
            "actor": actor,
            "action": action,
            "timestamp": timestamp.isoformat(),
            "safety_gate_result": safety_gate_result,
            "details": details,
        },
    )

    logger.info(
        "audit_log_entry",
        log_id=log_id,
        case_id=case_id,
        actor=actor,
        action=action,
        safety_gate=safety_gate_result,
    )

    return log_id
