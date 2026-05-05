# NeoVax TypeScript Client

Hand-written TypeScript client for the NeoVax-Agent FastAPI backend.
Uses the native `fetch` API — no runtime dependencies.

> **Research coordination tool only. Not medical or veterinary advice.**

## Requirements

- Node 18+ (or any runtime with `fetch`)
- TypeScript 5.x (dev dependency only — for building/type-checking)

## Install

Copy `neovax-client.ts` into your project or build it first:

```bash
npm install          # installs typescript dev dep
npm run build        # compiles to dist/
```

Then import:

```typescript
// from source (e.g. with ts-node / Bun / Deno)
import { NeoVaxClient } from "./neovax-client";

// from compiled dist
import { NeoVaxClient } from "./dist/neovax-client";
```

## Quick start

```typescript
import { NeoVaxClient } from "./neovax-client";

const client = new NeoVaxClient("http://localhost:8000");

// Health check
const health = await client.health();
console.log(health); // { status: "ok", mode: "demo", ... }

// Create a demo case (synthetic data, no real patient info)
const demoCase = await client.createDemoCase();
console.log(demoCase.id);

// Create a real dog case
const dogCase = await client.createCase("dog", {
  diagnosisSummary: "Osteosarcoma, right distal radius",
  supervisingProfessional: "Dr. Jane Smith DVM DACVIM",
});

// Add a sample
const sample = await client.addSample(
  dogCase.id,
  "tumor_dna",
  "/data/sequencing/tumor_R1.fastq.gz",
  { sourceLab: "Acme Genomics" },
);

// Run pipeline dry-run to validate steps
const dry = await client.dryRunPipeline(["align", "variant_call", "annotate"]);
console.log(dry.valid);

// Trigger a pipeline run
const run = await client.runPipeline(dogCase.id);
console.log(run.status); // "running" | "completed" | "failed"

// Poll pipeline status
const status = await client.getPipelineStatus(dogCase.id);
console.log(`${status.completed_steps}/${status.total_steps} steps done`);

// Get candidates
const candidates = await client.getCandidates(dogCase.id);
console.log(`${candidates.length} candidates`);

// Evidence assessment
const evidence = await client.getEvidence(dogCase.id);
console.log(evidence.level); // "strong" | "moderate" | "weak" | "insufficient"
console.log(evidence.flags); // string[]

// False-positive risk
const fp = await client.getFalsePositiveRisk(dogCase.id);

// AlphaFold prediction (mock backend — no GPU, no external upload)
const backends = await client.listBackends();
const pred = await client.predict("MKTAYIAKQRQISFVKSHFSRQ", "mock");
console.log(pred.backend_name, pred.confidence);

// Reports
const html = await client.getReportHtml(dogCase.id);
const md = await client.getReportMarkdown(dogCase.id);
console.log(md.content.slice(0, 200));

// Safety preflight
const check = await client.preflight("export.sequence", "dog", {
  involvesSequenceData: true,
});
if (check.status !== "pass") {
  console.error("Blocked:", check.reason);
}
```

## Error handling

All methods throw `ApiError` on non-2xx responses:

```typescript
try {
  const c = await client.getCase("nonexistent-id");
} catch (err) {
  if (err instanceof Error && err.name === "ApiError") {
    // err.message: "NeoVax API error 404: Case not found"
  }
}
```

## Type reference

| Type                      | Description                                                    |
| ------------------------- | -------------------------------------------------------------- |
| `Case`                    | Core case record (species, consent_status, review_status, ...) |
| `Sample`                  | Sequencing sample attached to a case                           |
| `Variant`                 | Somatic variant called by the pipeline                         |
| `Candidate`               | Neoantigen candidate derived from a variant                    |
| `StructureJob`            | AlphaFold structure prediction job                             |
| `PipelineRunRead`         | Pipeline execution record with step progress                   |
| `EvidenceAssessment`      | Evidence level + flags + recommendations                       |
| `AlphaFoldPrediction`     | Structure prediction result                                    |
| `SafetyPreflightResponse` | Safety gate check result                                       |

## Notes

- All dates are ISO 8601 strings (use `new Date(value)` to parse).
- `species` must be `"demo"`, `"dog"`, or `"human"`. Human mode requires IRB
  oversight and restricts sequence-level exports.
- Cloud AlphaFold backends (`alphafold_server`) send sequence data to Google
  DeepMind. Use `"mock"` or local backends for privacy-sensitive data.
- This client does not handle authentication — add an `Authorization` header
  wrapper if your deployment requires it.
