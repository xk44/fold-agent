"""Structure gallery and AlphaFold backend comparison helpers.

Provides rendering functions for the structure prediction gallery
and backend comparison views in the Streamlit dashboard.
"""

from __future__ import annotations

from typing import Any

from frontend.app.structure_viewer import (
    list_structure_artifacts,
    select_structure_artifact,
    viewer_format_for_artifact,
)


BACKEND_INFO = {
    "mock": {
        "name": "Mock Backend",
        "mode": "mock",
        "description": "Synthetic structure outputs for testing and demo cases.",
        "gpu_required": False,
        "cloud": False,
        "privacy_risk": "none",
    },
    "colabfold": {
        "name": "ColabFold",
        "mode": "local",
        "description": "Fast MSA-based structure prediction via MMseqs2 + AlphaFold2.",
        "gpu_required": True,
        "cloud": False,
        "privacy_risk": "none",
    },
    "local_colabfold": {
        "name": "LocalColabFold",
        "mode": "local",
        "description": "Fully local ColabFold installation with pre-downloaded databases.",
        "gpu_required": True,
        "cloud": False,
        "privacy_risk": "none",
    },
    "alphafold2_local": {
        "name": "AlphaFold 2 (Local)",
        "mode": "local",
        "description": "Full AlphaFold 2 pipeline running locally.",
        "gpu_required": True,
        "cloud": False,
        "privacy_risk": "none",
    },
    "alphafold3_local": {
        "name": "AlphaFold 3 (Local)",
        "mode": "local",
        "description": "AlphaFold 3 with multimer and ligand support.",
        "gpu_required": True,
        "cloud": False,
        "privacy_risk": "none",
    },
    "alphafold_server": {
        "name": "AlphaFold Server",
        "mode": "cloud",
        "description": "Google DeepMind hosted service. Sends sequence data externally.",
        "gpu_required": False,
        "cloud": True,
        "privacy_risk": "high",
    },
    "alphafold_db": {
        "name": "AlphaFold DB Lookup",
        "mode": "cloud",
        "description": "Retrieves pre-computed structures by UniProt accession.",
        "gpu_required": False,
        "cloud": True,
        "privacy_risk": "low",
    },
}


def build_backend_comparison_rows() -> list[dict]:
    rows = []
    for key, info in BACKEND_INFO.items():
        rows.append({
            "Backend": info["name"],
            "Mode": info["mode"],
            "GPU": "Yes" if info["gpu_required"] else "No",
            "Cloud": "Yes" if info["cloud"] else "No",
            "Privacy Risk": info["privacy_risk"].title(),
            "key": key,
        })
    return rows


def render_structure_gallery(
    st: Any,
    structure_jobs: list[dict],
    artifacts: list[dict],
) -> None:
    st.subheader("Structure Gallery")

    if not structure_jobs:
        st.info("No structure predictions yet. Run AlphaFold from the Pipeline section.")
        return

    for job in structure_jobs:
        status_icon = {"queued": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(
            job.get("status", ""), "❓"
        )
        with st.expander(f"{status_icon} Job {job['id'][:8]} — {job.get('backend_used', 'unknown')}"):
            cols = st.columns(3)
            cols[0].metric("Status", job.get("status", "unknown"))
            cols[1].metric("Backend", job.get("backend_used", "—"))

            confidence = job.get("confidence_metrics") or {}
            if confidence:
                plddt = confidence.get("mean_plddt") or confidence.get("plddt_mean")
                if plddt is not None:
                    cols[2].metric("Mean pLDDT", f"{plddt:.1f}")

            if job.get("input_hash"):
                st.caption(f"Input hash: `{job['input_hash'][:16]}...`")

            job_artifacts = [a for a in artifacts if a.get("execution_run_id") == job.get("id")]
            structure_arts = list_structure_artifacts(job_artifacts)
            if structure_arts:
                st.write(f"**{len(structure_arts)} structure file(s)**")
                for art in structure_arts:
                    st.write(f"- `{art.get('filename', 'unknown')}` ({art.get('format', '?')})")


def render_backend_comparison(st: Any, backend_statuses: list[dict] | None = None) -> None:
    st.subheader("AlphaFold Backend Comparison")

    rows = build_backend_comparison_rows()
    st.table([{k: v for k, v in r.items() if k != "key"} for r in rows])

    st.warning(
        "Cloud backends (AlphaFold Server) send sequence data to external servers. "
        "Review the provider's privacy policy before use. "
        "Local backends keep all data on your machine."
    )

    if backend_statuses:
        st.subheader("Backend Health")
        for status in backend_statuses:
            name = status.get("name", "unknown")
            ok = status.get("validation_ok", False)
            icon = "✅" if ok else "❌"
            reason = status.get("validation_reason", "")
            st.write(f"{icon} **{name}**: {reason or 'Ready'}")
