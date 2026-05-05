"""FoldAgent Shared API Client

Python client for interacting with the FoldAgent API.
All agent skills (Claude Code, OpenClaw, Hermes) share this client.
"""

from typing import Optional
from urllib.parse import urljoin

import httpx


class AlphaFoldValidationError(Exception):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("detail") or "AlphaFold backend validation failed")


DEFAULT_BASE_URL = "http://localhost:8010"


class FoldAgentClient:
    """Client for the FoldAgent API with built-in safety checks."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, json: Optional[dict] = None, params: Optional[dict] = None) -> dict:
        response = self.client.post(path, json=json, params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _get(self, path: str, params: Optional[dict] = None):
        response = self.client.get(path, params=params, headers=self._headers())
        response.raise_for_status()
        return response

    # --- Health ---

    def health(self) -> dict:
        """Check API health."""
        return self._get("/health").json()

    def version(self) -> dict:
        """Get API version info."""
        return self._get("/version").json()

    # --- Safety Preflight ---

    def safety_preflight(self, action: str, content: Optional[str] = None, **kwargs) -> dict:
        """Run safety preflight check before an action.

        MUST be called before any write, export, or agent action.
        """
        payload = {"action": action, **kwargs}
        if content:
            payload["content"] = content
        response = self.client.post("/safety/preflight", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Cases ---

    def create_case(self, species: str, diagnosis_summary: str = "", **kwargs) -> dict:
        """Create a new research case."""
        payload = {"species": species, "diagnosis_summary": diagnosis_summary, **kwargs}
        response = self.client.post("/cases", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_case(self, case_id: str) -> dict:
        """Get case details."""
        response = self.client.get(f"/cases/{case_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def list_cases(self) -> list:
        """List all cases."""
        response = self.client.get("/cases", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def update_case(self, case_id: str, **kwargs) -> dict:
        """Update a case."""
        response = self.client.patch(f"/cases/{case_id}", json=kwargs, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def create_case_task(self, case_id: str, **kwargs) -> dict:
        """Create a coordination task for a case."""
        return self._post(f"/cases/{case_id}/tasks", json=kwargs)

    def list_case_tasks(self, case_id: str) -> list:
        """List tasks for a case."""
        return self._get(f"/cases/{case_id}/tasks").json()

    def update_case_task(self, task_id: str, **kwargs) -> dict:
        """Update a coordination task."""
        response = self.client.patch(f"/tasks/{task_id}", json=kwargs, headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Samples ---

    def register_sample(self, case_id: str, sample_type: str, **kwargs) -> dict:
        """Register a sample for a case."""
        payload = {"sample_type": sample_type, **kwargs}
        response = self.client.post(f"/cases/{case_id}/samples", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def list_samples(self, case_id: str) -> list:
        """List samples for a case."""
        response = self.client.get(f"/cases/{case_id}/samples", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_sample_checksum(self, sample_id: str) -> dict:
        """Get checksum metadata for a sample."""
        response = self.client.get(f"/samples/{sample_id}/checksum", headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Pipeline ---

    def run_pipeline(self, case_id: str) -> dict:
        """Start the bioinformatics pipeline for a case."""
        case = self.get_case(case_id)
        preflight = self.safety_preflight("run_pipeline", species_mode=case["species"])
        if preflight.get("status") == "block":
            raise PermissionError(f"Safety preflight blocked: {preflight.get('reason')}")
        response = self.client.post(f"/cases/{case_id}/pipeline/run", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def pipeline_status(self, case_id: str) -> dict:
        """Get pipeline status for a case."""
        response = self.client.get(f"/cases/{case_id}/pipeline/status", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def pipeline_history(self, case_id: str) -> list:
        """List pipeline runs for a case."""
        response = self.client.get(f"/cases/{case_id}/pipeline/history", headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Variants ---

    def list_variants(self, case_id: str) -> list:
        """List variants for a case."""
        response = self.client.get(f"/cases/{case_id}/variants", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def review_variant(self, variant_id: str, review_status: str, notes: str = "") -> dict:
        """Review a variant."""
        payload = {"review_status": review_status, "expert_review_notes": notes}
        response = self.client.patch(f"/variants/{variant_id}/review", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Candidates ---

    def list_candidates(self, case_id: str) -> list:
        """List candidate antigens for a case."""
        response = self.client.get(f"/cases/{case_id}/candidates", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def review_candidate(self, candidate_id: str, review_status: str, notes: str = "") -> dict:
        """Review a candidate antigen."""
        payload = {"review_status": review_status, "expert_review_notes": notes}
        response = self.client.patch(f"/candidates/{candidate_id}/review", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- AlphaFold ---

    def list_alphafold_backends(self) -> dict:
        """List available AlphaFold backends."""
        response = self.client.get("/alphafold/backends", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def submit_alphafold_job(self, sequence: str, backend: str = "mock", **kwargs) -> dict:
        """Submit an AlphaFold structure job through the current backend-run surface."""
        payload = {"sequence": sequence, **kwargs}
        return self.alphafold_backend_run(backend, payload)

    def get_alphafold_job(self, job_id: str) -> dict:
        """Get AlphaFold job detail via the structure-job detail route."""
        return self.get_structure_job(job_id)

    # --- Reports ---

    def get_report(self, report_id: str) -> dict:
        """Get a generated report."""
        response = self.client.get(f"/reports/{report_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def list_reports(self, case_id: str) -> list:
        """List reports for a case."""
        response = self.client.get(f"/cases/{case_id}/reports", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def export_report(self, report_id: str, format: str = "markdown") -> dict:
        """Export a report as markdown or json payload."""
        response = self.client.get(f"/reports/{report_id}/export", params={"format": format}, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def save_report(self, report_id: str, format: str = "markdown") -> dict:
        """Persist a report export to disk."""
        response = self.client.post(f"/reports/{report_id}/save", params={"format": format}, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_case_bundle(self, case_id: str) -> dict:
        """Get a full case bundle with reports, audit log, samples, and latest pipeline run."""
        response = self.client.get(f"/cases/{case_id}/bundle", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def export_case_bundle(self, case_id: str, format: str = "markdown") -> dict:
        """Export a case bundle as markdown or json payload."""
        response = self.client.get(f"/cases/{case_id}/bundle/export", params={"format": format}, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def save_case_bundle(self, case_id: str, format: str = "markdown") -> dict:
        """Persist a case bundle export to disk."""
        response = self.client.post(f"/cases/{case_id}/bundle/save", params={"format": format}, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def list_case_artifacts(self, case_id: str) -> list:
        """List saved artifacts for a case."""
        response = self.client.get(f"/cases/{case_id}/artifacts", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def download_artifact(self, path: str) -> bytes:
        """Download a saved artifact file."""
        response = self.client.get("/artifacts/file", params={"path": path}, headers=self._headers())
        response.raise_for_status()
        return response.content

    def list_pipeline_adapters(self) -> dict:
        """List bioinformatics shell adapter statuses."""
        return self._get("/pipeline/adapters").json()

    def pipeline_adapter_dry_run(self, adapter_name: str, payload: dict) -> dict:
        """Get a dry-run command manifest for a pipeline adapter."""
        return self._post(f"/pipeline/adapters/{adapter_name}/dry-run", json=payload)

    def pipeline_adapter_run(self, adapter_name: str, payload: dict) -> dict:
        """Execute or gracefully fail a pipeline adapter shell wrapper."""
        return self._post(f"/pipeline/adapters/{adapter_name}/run", json=payload)

    def list_alphafold_backends_status(self) -> dict:
        """List AlphaFold backend shell statuses."""
        return self._get("/alphafold/backends").json()

    def alphafold_backend_dry_run(self, backend_name: str, payload: dict) -> dict:
        """Get a dry-run command manifest for an AlphaFold backend."""
        return self._post(f"/alphafold/backends/{backend_name}/dry-run", json=payload)

    def alphafold_backend_run(self, backend_name: str, payload: dict) -> dict:
        """Execute or gracefully fail an AlphaFold backend shell wrapper."""
        response = self.client.post(
            f"/alphafold/backends/{backend_name}/run",
            json=payload,
            headers=self._headers(),
        )
        if response.status_code == 409:
            raise AlphaFoldValidationError(response.json())
        response.raise_for_status()
        return response.json()

    def list_execution_history(self, case_id: str) -> list:
        """List shell execution history for a case."""
        return self._get(f"/cases/{case_id}/executions").json()

    def list_structure_jobs(self, case_id: str) -> list:
        """List structure jobs for a case."""
        return self._get(f"/cases/{case_id}/structure-jobs").json()

    def get_structure_job(self, job_id: str) -> dict:
        """Get structure job detail."""
        return self._get(f"/structure-jobs/{job_id}").json()

    def generate_candidate_review_report(self, case_id: str) -> dict:
        """Generate a candidate-antigen review report."""
        preflight = self.safety_preflight("generate_report", report_type="candidate_review")
        if preflight.get("status") == "block":
            raise PermissionError(f"Safety preflight blocked: {preflight.get('reason')}")
        response = self.client.post(f"/cases/{case_id}/reports/candidate-review", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def generate_ethics_package(self, case_id: str) -> dict:
        """Generate an ethics/veterinary review package."""
        preflight = self.safety_preflight("generate_report", report_type="ethics_package")
        if preflight.get("status") == "block":
            raise PermissionError(f"Safety preflight blocked: {preflight.get('reason')}")
        response = self.client.post(f"/cases/{case_id}/reports/ethics-package", headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Agent Tasks ---

    def create_agent_task(self, case_id: str, framework: str, skill_name: str, **kwargs) -> dict:
        """Create an agent task."""
        payload = {"framework": framework, "skill_name": skill_name, **kwargs}
        response = self.client.post(f"/cases/{case_id}/agent-tasks", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_agent_task(self, task_id: str) -> dict:
        """Get agent task status."""
        response = self.client.get(f"/agent-tasks/{task_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def update_agent_task(self, task_id: str, **kwargs) -> dict:
        """Update an agent task via the current /agent/tasks route."""
        response = self.client.patch(f"/agent/tasks/{task_id}", json=kwargs, headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Background Jobs ---

    def list_background_jobs(self, case_id: Optional[str] = None, status: Optional[str] = None) -> list:
        """List background jobs, optionally filtered by case_id and/or status."""
        params: dict = {}
        if case_id is not None:
            params["case_id"] = case_id
        if status is not None:
            params["status"] = status
        response = self.client.get("/jobs", params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def get_background_job(self, job_id: str) -> dict:
        """Get background job status."""
        response = self.client.get(f"/jobs/{job_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def cancel_background_job(self, job_id: str) -> dict:
        """Cancel a background job."""
        response = self.client.post(f"/jobs/{job_id}/cancel", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def retry_background_job(self, job_id: str) -> dict:
        """Retry a failed background job."""
        response = self.client.post(f"/jobs/{job_id}/retry", headers=self._headers())
        response.raise_for_status()
        return response.json()

    # --- Audit ---

    def get_audit_log(self, case_id: str) -> list:
        """Get audit log for a case."""
        response = self.client.get(f"/audit/{case_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    def redact_case(self, case_id: str, redaction_level: str, confirm: bool = False, reason: Optional[str] = None) -> dict:
        """Apply a redaction level to a case and all its subjects."""
        payload = {"redaction_level": redaction_level, "confirm": confirm}
        if reason is not None:
            payload["reason"] = reason
        response = self.client.post(f"/cases/{case_id}/redact", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def redact_subject(self, case_id: str, subject_id: str, redaction_level: str, confirm: bool = False, reason: Optional[str] = None) -> dict:
        """Apply a redaction level to an individual subject."""
        payload = {"redaction_level": redaction_level, "confirm": confirm}
        if reason is not None:
            payload["reason"] = reason
        response = self.client.post(f"/cases/{case_id}/subjects/{subject_id}/redact", json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def delete_case(self, case_id: str, confirm: bool = False, hard_delete: bool = False, reason: Optional[str] = None) -> dict:
        """Soft-delete or hard-delete a case."""
        params = {"confirm": confirm, "hard_delete": hard_delete}
        if reason is not None:
            params["reason"] = reason
        response = self.client.delete(f"/cases/{case_id}", params=params, headers=self._headers())
        response.raise_for_status()
        return response.json()