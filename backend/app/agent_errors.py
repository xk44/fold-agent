"""Agent-safe error messages for NeoVax API.

Provides structured error types that help autonomous agents understand
what went wrong, whether retrying is safe, and how to fix the issue.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentError:
    """Structured error descriptor for agent consumers."""

    code: str
    message: str
    suggestion: str
    retry_safe: bool
    documentation_url: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

AGENT_ERROR_CATALOG: dict[str, AgentError] = {
    # 404 — resource not found
    "404_case_not_found": AgentError(
        code="CASE_NOT_FOUND",
        message="The requested case does not exist.",
        suggestion="Verify the case_id is correct. Use GET /cases to list available cases.",
        retry_safe=False,
        documentation_url=None,
    ),
    "404_not_found": AgentError(
        code="NOT_FOUND",
        message="The requested resource was not found.",
        suggestion="Verify the resource ID and endpoint path are correct.",
        retry_safe=False,
        documentation_url=None,
    ),
    # 400 — validation / bad request
    "400_validation_error": AgentError(
        code="VALIDATION_ERROR",
        message="The request body or parameters failed validation.",
        suggestion="Check required fields and data types. See the 422 response schema for details.",
        retry_safe=False,
        documentation_url=None,
    ),
    # 422 — missing or malformed field
    "422_missing_field": AgentError(
        code="MISSING_FIELD",
        message="One or more required fields are missing from the request.",
        suggestion="Include all required fields. Check the request schema at GET /api/openapi.json.",
        retry_safe=False,
        documentation_url=None,
    ),
    # 403 — safety blocked
    "403_safety_blocked": AgentError(
        code="SAFETY_BLOCKED",
        message="The action was blocked by the NeoVax safety preflight system.",
        suggestion=(
            "Review the blocked_patterns in the response. "
            "Obtain professional attestation or switch to demo/dog mode for non-human cases."
        ),
        retry_safe=False,
        documentation_url=None,
    ),
    # 409 — conflict
    "409_conflict": AgentError(
        code="CONFLICT",
        message="The request conflicts with the current state of the resource.",
        suggestion=(
            "Fetch the current resource state before retrying. "
            "For background jobs, check job status before cancelling or retrying."
        ),
        retry_safe=False,
        documentation_url=None,
    ),
    # 500 — internal server error
    "500_internal_error": AgentError(
        code="INTERNAL_ERROR",
        message="An unexpected server error occurred.",
        suggestion=(
            "Wait a moment and retry the request. "
            "If the error persists, check the server logs or contact support."
        ),
        retry_safe=True,
        documentation_url=None,
    ),
    # 503 — service unavailable (schema drift / DB issue)
    "503_service_unavailable": AgentError(
        code="SERVICE_UNAVAILABLE",
        message="The service is temporarily unavailable, likely due to database schema drift.",
        suggestion=(
            "Run database migrations (alembic upgrade head) and retry. "
            "Check GET /health for schema drift details."
        ),
        retry_safe=True,
        documentation_url=None,
    ),
}


def format_agent_error(status_code: int, error_type: str, detail: str | None = None) -> dict:
    """Return a structured agent-friendly error dict.

    Parameters
    ----------
    status_code:
        HTTP status code (e.g. 404, 403).
    error_type:
        Key in ``AGENT_ERROR_CATALOG`` or a freeform string used for the
        ``code`` field when no catalog entry exists.
    detail:
        Original error detail from the exception / response body.
    """
    catalog_key = f"{status_code}_{error_type}"
    # Also try exact match (caller may pass full key)
    entry = AGENT_ERROR_CATALOG.get(catalog_key) or AGENT_ERROR_CATALOG.get(error_type)

    if entry is None:
        # Fallback: derive from status code
        for key, err in AGENT_ERROR_CATALOG.items():
            if key.startswith(f"{status_code}_"):
                entry = err
                break

    if entry is None:
        entry = AgentError(
            code=error_type.upper(),
            message=detail or f"HTTP {status_code} error.",
            suggestion="Review the error detail and retry if appropriate.",
            retry_safe=status_code >= 500,
        )

    return {
        "error": True,
        "status_code": status_code,
        "code": entry.code,
        "message": entry.message,
        "detail": detail or entry.message,
        "suggestion": entry.suggestion,
        "retry_safe": entry.retry_safe,
        "documentation_url": entry.documentation_url,
    }
