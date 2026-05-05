/**
 * NeoVax-Agent TypeScript API Client
 *
 * Research coordination tool only — not medical or veterinary advice.
 * All outputs require review by a licensed physician or veterinary oncologist.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SpeciesMode = "demo" | "dog" | "human";

export interface Case {
  id: string;
  species: SpeciesMode;
  diagnosis_summary: string | null;
  supervising_professional: string | null;
  consent_status: string;
  review_status: string;
  redaction_level: string;
  created_at: string;
  updated_at: string;
}

export interface Sample {
  id: string;
  case_id: string | null;
  subject_id: string | null;
  sample_type: string;
  file_paths: Record<string, string> | null;
  checksum: string | null;
  source_lab: string | null;
  custody_metadata: Record<string, string> | null;
  created_at: string;
}

export interface Variant {
  id: string;
  case_id: string;
  sample_id: string | null;
  genomic_coordinates: string;
  gene: string | null;
  transcript: string | null;
  protein_change: string | null;
  caller_source: string | null;
  quality_metrics: Record<string, unknown> | null;
  annotation_source: string | null;
  expert_review_notes: string | null;
  last_parsed_execution_id: string | null;
  review_status: string;
  created_at: string;
}

export interface Candidate {
  id: string;
  case_id: string;
  variant_id: string;
  peptide_metadata: Record<string, unknown> | null;
  mhc_context: string | null;
  prediction_scores: Record<string, unknown> | null;
  expression_evidence: Record<string, unknown> | null;
  structure_evidence: Record<string, unknown> | null;
  uncertainty_flags: Record<string, unknown> | null;
  expert_review_notes: string | null;
  last_parsed_execution_id: string | null;
  review_status: string;
  created_at: string;
}

export interface StructureJob {
  id: string;
  case_id: string;
  candidate_id: string;
  backend_used: string;
  input_hash: string | null;
  output_path: string | null;
  confidence_metrics: Record<string, unknown> | null;
  visualization_path: string | null;
  status: string;
  created_at: string;
}

export interface PipelineRunRead {
  id: string;
  case_id: string;
  status: string;
  current_step: string | null;
  completed_steps: number;
  total_steps: number;
  step_results: Record<string, unknown> | null;
  steps: Record<string, unknown>[];
  started_at: string;
  finished_at: string | null;
}

export interface EvidenceAssessment {
  level: "strong" | "moderate" | "weak" | "insufficient";
  flags: string[];
  recommendations: string[];
}

export interface AlphaFoldPrediction {
  backend_name: string;
  pdb_data: string | null;
  confidence: number | null;
  duration_seconds: number | null;
  cached: boolean;
}

export interface SafetyPreflightResponse {
  status: string;
  blocked_patterns: string[];
  reason: string | null;
}

export interface DryRunResult {
  valid: boolean;
  steps?: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface NeoVaxError {
  status: number;
  detail: string;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`NeoVax API error ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function checkResponse(res: Response): Promise<void> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      // ignore parse error; use statusText
    }
    throw new ApiError(res.status, detail);
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class NeoVaxClient {
  private readonly base: string;

  /**
   * @param baseUrl  Base URL of the NeoVax-Agent FastAPI server,
   *                 e.g. "http://localhost:8000". Trailing slash is stripped.
   */
  constructor(baseUrl: string) {
    this.base = baseUrl.replace(/\/$/, "");
  }

  private url(path: string): string {
    return `${this.base}${path}`;
  }

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(this.url(path), {
      headers: { Accept: "application/json" },
    });
    await checkResponse(res);
    return res.json() as Promise<T>;
  }

  private async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(this.url(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    await checkResponse(res);
    return res.json() as Promise<T>;
  }

  // -------------------------------------------------------------------------
  // Health
  // -------------------------------------------------------------------------

  async health(): Promise<Record<string, unknown>> {
    return this.get("/health");
  }

  // -------------------------------------------------------------------------
  // Cases
  // -------------------------------------------------------------------------

  /**
   * Create a new case.
   * @param species  "demo" | "dog" | "human"
   * @param opts     Optional case fields (diagnosis_summary, supervising_professional)
   */
  async createCase(
    species: SpeciesMode,
    opts?: { diagnosisSummary?: string; supervisingProfessional?: string },
  ): Promise<Case> {
    return this.post<Case>("/cases", {
      species,
      diagnosis_summary: opts?.diagnosisSummary ?? null,
      supervising_professional: opts?.supervisingProfessional ?? null,
    });
  }

  async getCase(caseId: string): Promise<Case> {
    return this.get<Case>(`/cases/${caseId}`);
  }

  async listCases(): Promise<Case[]> {
    return this.get<Case[]>("/cases");
  }

  // -------------------------------------------------------------------------
  // Samples
  // -------------------------------------------------------------------------

  /**
   * Add a sample to a case.
   * @param caseId      Case UUID
   * @param sampleType  e.g. "tumor_dna", "normal_dna", "tumor_rna"
   * @param filePath    Path key to register (stored in file_paths)
   * @param opts        Optional: subjectId, sourcelab, checksum
   */
  async addSample(
    caseId: string,
    sampleType: string,
    filePath: string,
    opts?: { subjectId?: string; sourceLab?: string; checksum?: string },
  ): Promise<Sample> {
    return this.post<Sample>(`/cases/${caseId}/samples`, {
      sample_type: sampleType,
      file_paths: { primary: filePath },
      subject_id: opts?.subjectId ?? null,
      source_lab: opts?.sourceLab ?? null,
      checksum: opts?.checksum ?? null,
    });
  }

  async listSamples(caseId: string): Promise<Sample[]> {
    return this.get<Sample[]>(`/cases/${caseId}/samples`);
  }

  // -------------------------------------------------------------------------
  // Pipeline
  // -------------------------------------------------------------------------

  /**
   * Get the most recent pipeline run status for a case.
   */
  async getPipelineStatus(caseId: string): Promise<PipelineRunRead> {
    return this.get<PipelineRunRead>(`/cases/${caseId}/pipeline/status`);
  }

  async getPipelineHistory(caseId: string): Promise<PipelineRunRead[]> {
    return this.get<PipelineRunRead[]>(`/cases/${caseId}/pipeline/history`);
  }

  /**
   * Dry-run the pipeline to validate a set of steps without executing them.
   */
  async dryRunPipeline(
    steps: string[],
    opts?: Record<string, unknown>,
  ): Promise<DryRunResult> {
    return this.post<DryRunResult>("/pipeline/dry-run", { steps, ...opts });
  }

  /**
   * Trigger a full pipeline run for a case.
   */
  async runPipeline(
    caseId: string,
    opts?: Record<string, unknown>,
  ): Promise<PipelineRunRead> {
    return this.post<PipelineRunRead>(
      `/cases/${caseId}/pipeline/run`,
      opts ?? {},
    );
  }

  // -------------------------------------------------------------------------
  // Candidates
  // -------------------------------------------------------------------------

  async getCandidates(caseId: string): Promise<Candidate[]> {
    return this.get<Candidate[]>(`/cases/${caseId}/candidates`);
  }

  async getVariants(caseId: string): Promise<Variant[]> {
    return this.get<Variant[]>(`/cases/${caseId}/variants`);
  }

  // -------------------------------------------------------------------------
  // Structure jobs
  // -------------------------------------------------------------------------

  async listStructureJobs(caseId: string): Promise<StructureJob[]> {
    return this.get<StructureJob[]>(`/cases/${caseId}/structure-jobs`);
  }

  async getStructureJob(jobId: string): Promise<StructureJob> {
    return this.get<StructureJob>(`/structure-jobs/${jobId}`);
  }

  // -------------------------------------------------------------------------
  // AlphaFold (v2 abstraction layer)
  // -------------------------------------------------------------------------

  /**
   * List available AlphaFold backends and their availability status.
   */
  async listBackends(): Promise<Record<string, unknown>[]> {
    return this.get<Record<string, unknown>[]>("/alphafold/v2/backends");
  }

  /**
   * Run a structure prediction via the Phase-6 backend abstraction layer.
   * @param sequence    Amino-acid sequence string
   * @param backend     Backend name, e.g. "mock", "colabfold", "alphafold_server"
   * @param opts        allow_cloud, allow_fallback, options
   */
  async predict(
    sequence: string,
    backend: string,
    opts?: {
      allowCloud?: boolean;
      allowFallback?: boolean;
      options?: Record<string, unknown>;
    },
  ): Promise<AlphaFoldPrediction> {
    return this.post<AlphaFoldPrediction>("/alphafold/v2/predict", {
      sequence,
      backend,
      allow_cloud: opts?.allowCloud ?? false,
      allow_fallback: opts?.allowFallback ?? false,
      options: opts?.options ?? {},
    });
  }

  // -------------------------------------------------------------------------
  // Reports
  // -------------------------------------------------------------------------

  /**
   * Fetch the styled HTML report for a case.
   * Returns raw HTML string.
   */
  async getReportHtml(caseId: string): Promise<string> {
    const res = await fetch(this.url(`/cases/${caseId}/report/html`), {
      headers: { Accept: "text/html" },
    });
    await checkResponse(res);
    return res.text();
  }

  /**
   * Fetch the Markdown report for a case.
   * Returns `{ case_id, format, content }`.
   */
  async getReportMarkdown(
    caseId: string,
  ): Promise<{ case_id: string; format: string; content: string }> {
    return this.get(`/cases/${caseId}/report/markdown`);
  }

  async listReports(caseId: string): Promise<Record<string, unknown>[]> {
    return this.get(`/cases/${caseId}/reports`);
  }

  // -------------------------------------------------------------------------
  // Safety
  // -------------------------------------------------------------------------

  /**
   * Get evidence-level assessment for a case.
   */
  async getEvidence(caseId: string): Promise<EvidenceAssessment> {
    return this.get<EvidenceAssessment>(`/cases/${caseId}/evidence`);
  }

  /**
   * Get false-positive risk assessment for all candidates in a case.
   */
  async getFalsePositiveRisk(caseId: string): Promise<Record<string, unknown>> {
    return this.get(`/cases/${caseId}/false-positive-risk`);
  }

  /**
   * Run a safety preflight check.
   * @param action       Action string, e.g. "export.sequence"
   * @param speciesMode  "demo" | "dog" | "human"
   * @param opts         Optional preflight fields
   */
  async preflight(
    action: string,
    speciesMode: SpeciesMode,
    opts?: {
      content?: string;
      isExpertMode?: boolean;
      isExport?: boolean;
      involvesExternalUpload?: boolean;
      involvesSequenceData?: boolean;
    },
  ): Promise<SafetyPreflightResponse> {
    return this.post<SafetyPreflightResponse>("/safety/preflight", {
      action,
      species_mode: speciesMode,
      content: opts?.content ?? null,
      is_expert_mode: opts?.isExpertMode ?? false,
      is_export: opts?.isExport ?? false,
      involves_external_upload: opts?.involvesExternalUpload ?? false,
      involves_sequence_data: opts?.involvesSequenceData ?? false,
    });
  }

  /**
   * Check whether cloud upload is permitted under the current server config.
   */
  async cloudUploadCheck(): Promise<Record<string, unknown>> {
    return this.get("/privacy/cloud-upload-check");
  }

  // -------------------------------------------------------------------------
  // Demo
  // -------------------------------------------------------------------------

  /**
   * Create a complete demo case with synthetic data.
   * Safe to call without real patient data.
   */
  async createDemoCase(): Promise<Case> {
    const result =
      await this.post<Record<string, unknown>>("/demo/create-case");
    // The demo endpoint returns a richer dict; extract the case sub-object if present.
    const caseObj = (result.case ?? result) as Case;
    return caseObj;
  }

  async getDemoStatus(): Promise<Record<string, unknown>> {
    return this.get("/demo/status");
  }
}
