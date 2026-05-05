"""OpenAPI 3.1 spec export with agent-friendly extensions.

Adds ``x-safety-level`` and ``x-agent-description`` to every endpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Safety-level classification rules
# ---------------------------------------------------------------------------

# Paths that are always "dangerous" regardless of method
_DANGEROUS_PATH_FRAGMENTS: tuple[str, ...] = (
    "/delete",
    "/export",
    "/bundle/export",
    "/bundle/save",
    "/audit/export",
    "/reports/{report_id}/export",
    "/reports/{report_id}/save",
    "/alphafold/backends/{backend_name}/run",
    "/alphafold/v2/predict",
    "/cases/{case_id}/pipeline/run",
    "/cases/{case_id}/pipeline/run-async",
    "/privacy/cloud-upload-check",
    "/privacy/retention/expired",
)

# Paths where POST creates data (requires-review)
_CREATES_DATA_PATH_FRAGMENTS: tuple[str, ...] = (
    "/cases",
    "/subjects",
    "/samples",
    "/variants",
    "/candidates",
    "/structure-jobs",
    "/agent/tasks",
    "/cases/{case_id}/agent-tasks",
    "/cases/{case_id}/tasks",
    "/cases/{case_id}/reports/",
    "/cases/{case_id}/redact",
    "/cases/{case_id}/subjects/{subject_id}/redact",
    "/cases/{case_id}/attestation",
    "/cases/{case_id}/lab/",
    "/safety/preflight",
    "/safety/mrna-gate",
    "/pipeline/adapters/{adapter_name}/run",
    "/agent/dry-run",
)

# Agent-friendly descriptions by path+method (exact or prefix match)
_AGENT_DESCRIPTIONS: dict[str, str] = {
    "GET /health": "Check API and database health. Always safe to call.",
    "GET /version": "Retrieve version, mode, and backend configuration.",
    "GET /cases": "List all cases. Read-only.",
    "POST /cases": "Create a new case. Requires species, diagnosis_summary.",
    "GET /cases/{case_id}": "Fetch a single case by ID.",
    "PATCH /cases/{case_id}": "Update case fields such as review_status or consent_status.",
    "DELETE /cases/{case_id}": "Permanently delete a case. Requires approval.",
    "POST /cases/{case_id}/redact": "Redact PII from a case. Irreversible.",
    "GET /cases/{case_id}/samples": "List samples for a case.",
    "POST /cases/{case_id}/samples": "Upload a new sample to a case.",
    "GET /cases/{case_id}/variants": "List variants for a case.",
    "POST /cases/{case_id}/variants": "Add a variant to a case.",
    "GET /cases/{case_id}/candidates": "List neoantigen candidates for a case.",
    "POST /cases/{case_id}/candidates": "Add a neoantigen candidate to a case.",
    "GET /cases/{case_id}/reports": "List reports for a case.",
    "POST /cases/{case_id}/reports/candidate-review": "Generate a candidate review report. Research-only.",
    "POST /cases/{case_id}/reports/ethics-package": "Generate an ethics package report. Research-only.",
    "GET /reports/{report_id}/export": "Export a report to markdown or JSON. Downloads file.",
    "GET /cases/{case_id}/bundle/export": "Export full case bundle as ZIP. Downloads file.",
    "POST /cases/{case_id}/pipeline/run": "Run the analysis pipeline for a case.",
    "POST /cases/{case_id}/pipeline/run-async": "Queue pipeline run as background job.",
    "GET /cases/{case_id}/pipeline/status": "Get current pipeline status for a case.",
    "GET /cases/{case_id}/pipeline/history": "List all pipeline runs for a case.",
    "POST /alphafold/backends/{backend_name}/run": "Run AlphaFold structure prediction. May call external service.",
    "POST /alphafold/v2/predict": "Run AlphaFold v2 prediction with caching.",
    "GET /alphafold/backends": "List available AlphaFold backends and their status.",
    "GET /agent/skills": "List available agent skills.",
    "GET /agent/events": "Server-sent event stream for agent activity.",
    "POST /agent/tasks": "Create an agent task.",
    "GET /agent/tasks": "List agent tasks.",
    "POST /agent/tasks/dry-run": "Dry-run an agent task without executing.",
    "POST /safety/preflight": "Run safety preflight check for an action.",
    "POST /safety/mrna-gate": "Run mRNA safety gate check.",
    "GET /audit/{case_id}": "List audit log entries for a case.",
    "GET /audit/export": "Export full audit log. Dangerous — contains all activity.",
    "GET /jobs": "List background jobs.",
    "GET /jobs/{job_id}": "Get a background job by ID.",
    "POST /jobs/{job_id}/cancel": "Cancel a running background job.",
    "POST /jobs/{job_id}/retry": "Retry a failed background job.",
    "GET /pipeline/adapters": "List pipeline adapter statuses.",
    "POST /pipeline/adapters/{adapter_name}/run": "Execute a pipeline adapter.",
    "POST /pipeline/adapters/{adapter_name}/dry-run": "Dry-run a pipeline adapter without executing.",
    "GET /cases/{case_id}/evidence": "Get evidence level assessment for a case.",
    "GET /cases/{case_id}/false-positive-risk": "Get false-positive risk assessment.",
    "GET /cases/{case_id}/report/citations": "Get report citations for a case.",
    "POST /cases/{case_id}/attestation": "Record professional attestation for a case.",
    "GET /cases/{case_id}/attestation": "Get attestation records for a case.",
    "GET /cases/{case_id}/privacy": "Get privacy summary for a case.",
    "GET /openapi-export": "Get enhanced OpenAPI spec with agent extensions.",
    "POST /agent/dry-run": "Dry-run a named action without executing it.",
    "GET /agent/approval-required": "List all actions requiring explicit approval.",
    "GET /agent/approval-required/{action}": "Check if a specific action requires approval.",
    "GET /agent/error-catalog": "List all agent error types and their meanings.",
}


def _classify_safety_level(method: str, path: str) -> str:
    """Return 'safe', 'requires-review', or 'dangerous'."""
    upper = method.upper()

    # DELETE is always dangerous
    if upper == "DELETE":
        return "dangerous"

    # Check dangerous path fragments
    for frag in _DANGEROUS_PATH_FRAGMENTS:
        if frag in path:
            return "dangerous"

    # GET/HEAD/OPTIONS are safe (read-only)
    if upper in {"GET", "HEAD", "OPTIONS"}:
        return "safe"

    # POST that matches creates-data patterns requires review
    if upper in {"POST", "PUT", "PATCH"}:
        for frag in _CREATES_DATA_PATH_FRAGMENTS:
            if path == frag or path.startswith(frag.rstrip("}")):
                return "requires-review"
        return "requires-review"

    return "safe"


def _agent_description(method: str, path: str) -> str:
    key = f"{method.upper()} {path}"
    if key in _AGENT_DESCRIPTIONS:
        return _AGENT_DESCRIPTIONS[key]
    # Generic fallback
    upper = method.upper()
    if upper == "GET":
        return f"Read {path}."
    if upper == "POST":
        return f"Create or execute action at {path}."
    if upper == "PATCH":
        return f"Update resource at {path}."
    if upper == "DELETE":
        return f"Delete resource at {path}. Requires approval."
    return f"{upper} {path}."


def export_openapi_spec() -> dict:
    """Generate the OpenAPI spec from the FastAPI app with agent extensions.

    Adds ``x-safety-level`` and ``x-agent-description`` to every operation.
    """
    # Import here to avoid circular imports at module load time
    from backend.app.main import app  # noqa: PLC0415

    spec: dict = app.openapi()

    paths: dict = spec.get("paths", {})
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
                if not isinstance(operation, dict):
                    continue
                safety = _classify_safety_level(method, path)
                operation["x-safety-level"] = safety
                operation["x-agent-description"] = _agent_description(method, path)

    return spec
