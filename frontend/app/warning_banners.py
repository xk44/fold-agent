"""Persistent warning banners for FoldAgent dashboard.

Renders research-use and privacy disclaimers, plus case-specific
evidence and attestation warnings.
"""

from __future__ import annotations

from typing import Any


def render_warning_banners(st: Any) -> None:
    """Render persistent research-use and privacy banners."""
    st.warning(
        "⚠️ This software is for research and educational purposes only. "
        "It does not provide medical advice, diagnosis, or treatment recommendations."
    )
    st.info(
        "🔒 All data is processed locally. No data is sent to external servers "
        "unless you explicitly choose a cloud backend."
    )


def render_case_warnings(
    api_base: str,
    case_id: str,
    http_get: Any,
    st: Any,
) -> None:
    """Render case-specific evidence and attestation warnings."""
    # Evidence level warning
    try:
        ev_data = http_get(f"{api_base}/cases/{case_id}/evidence").json()
        evidence_level = ev_data.get("evidence_level") or ev_data.get("level")
        if evidence_level and str(evidence_level).lower() in ("insufficient", "weak", "low"):
            st.warning(
                f"⚠️ Evidence level for this case is **{evidence_level}**. "
                "Additional data collection is recommended before drawing conclusions."
            )
    except Exception:
        pass

    # Attestation status info
    try:
        att_data = http_get(f"{api_base}/cases/{case_id}/attestation").json()
        attested = att_data.get("attested") or att_data.get("attestation_recorded")
        if not attested:
            st.info(
                "ℹ️ Attestation has not yet been recorded for this case. "
                "Record an attestation to confirm expert review of the research context."
            )
    except Exception:
        pass
