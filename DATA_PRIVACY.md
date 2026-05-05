# FoldAgent Data Privacy Policy

## Local-First Default

FoldAgent is designed to be local-first. All data processing, storage, and
computation happens on the user's machine by default. No data leaves the local
system unless the user explicitly enables and confirms it.

## Core Privacy Principles

1. **No data leaves without explicit consent** -- Cloud services (AlphaFold
   Server, external APIs) are disabled by default. Enabling them requires
   informed acknowledgment of what data will be uploaded.

2. **No training on user data** -- FoldAgent does not train models on user
   data. No genomic data, case data, or derived data is used for model
   training or shared with third parties for that purpose.

3. **Encryption at rest** -- Users may optionally encrypt case data at rest
   using a local key. This feature is available but not default in MVP.

4. **Per-case data directories** -- Each case has its own data directory.
   Cases do not share data unless explicitly linked.

5. **Chain of custody** -- File provenance is tracked from upload through
   every pipeline step. Checksums are verified at each stage.

## Data Handling

### Data We Store

- Case metadata (diagnosis, species, mode)
- Sample metadata (type, source lab, checksums)
- Pipeline run manifests (tool versions, parameters, timing)
- Variant annotations (from VEP, pVACtools, etc.)
- Candidate antigen predictions
- AlphaFold structure jobs and outputs
- Audit logs
- Report exports

### Data We Do NOT Store

- Raw FASTQ files (metadata only)
- Raw BAM files (metadata only, until explicitly processed)
- Any data the user does not register in the system

### Data Retention

- Local data is retained until the user deletes it
- A data deletion workflow is available (post-MVP: automated)
- Audit logs are retained per configured policy
- No external backup unless explicitly configured

## External Uploads

When a user enables a cloud-connected feature (e.g., AlphaFold Server):

1. A confirmation dialog explains exactly what data will be uploaded
2. The user must acknowledge and confirm
3. The upload is logged in the audit trail
4. The user is reminded that external services have their own privacy policies
5. The system cannot proceed without confirmation

## Redaction

Reports can be exported with redaction levels:

- **Full**: All identifiers included
- **Anonymized**: Subject names and direct identifiers removed
- **Minimal**: Only aggregate statistics, no individual data

## Rights

- Users can export all data related to their cases
- Users can delete all data related to their cases
- Users can view the complete audit log for any case
- No data is shared with third parties without user action

## Children / Vulnerable Populations

Human mode requires physician/oncologist ownership and IRB/ethics review.
The system does not differentiate based on age or population vulnerability
beyond requiring appropriate professional oversight for all cases.

## Genomic Data Specifics

- Genomic data (FASTQ, BAM, VCF) is treated as sensitive health information
- Local storage only by default
- Checksum-based integrity verification at every step
- No genomic data appears in agent skill logs or WebSocket events by default
- Genomic data paths in reports are redacted unless explicitly included
