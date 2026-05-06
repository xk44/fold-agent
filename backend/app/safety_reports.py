"""FoldAgent Safety Report Enhancements (Phase 7)

Provides insufficient-evidence flagging, false-positive risk assessment,
source citations, and professional attestation gating for case reports.

Research coordination artifacts only — not medical/veterinary advice.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Evidence level
# ---------------------------------------------------------------------------


class EvidenceLevel(str, enum.Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"
    insufficient = "insufficient"


@dataclass
class EvidenceAssessment:
    level: EvidenceLevel
    flags: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def assess_evidence_level(case_id: str, db: Session) -> EvidenceAssessment:
    """Evaluate evidence quality for a case and return an EvidenceAssessment.

    Checks candidate count, binding predictions, structure predictions,
    RNA expression data, and sample coverage.
    """
    from backend.app.models import CandidateAntigen, Sample, StructureJob, StructureJobStatusEnum

    flags: list[str] = []
    recommendations: list[str] = []

    candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
    samples = db.query(Sample).filter(Sample.case_id == case_id).all()

    candidate_count = len(candidates)

    # --- Candidate count ---
    if candidate_count == 0:
        flags.append("No candidate antigens identified")
        recommendations.append(
            "Run variant calling and antigen prediction pipeline to generate candidate antigens."
        )
    elif candidate_count < 3:
        flags.append("Fewer than 3 candidate antigens identified")
        recommendations.append(
            "Consider expanding variant calling parameters or reviewing filtering thresholds."
        )

    # --- Binding predictions ---
    has_binding = any(c.prediction_scores and len(c.prediction_scores) > 0 for c in candidates)
    if candidates and not has_binding:
        flags.append("No binding affinity data available")
        recommendations.append(
            "Run MHC binding prediction tools (e.g. NetMHCpan) on candidate peptides."
        )

    # --- Structure predictions ---
    completed_structure_jobs = (
        db.query(StructureJob)
        .filter(
            StructureJob.case_id == case_id,
            StructureJob.status == StructureJobStatusEnum.completed,
        )
        .count()
    )
    if completed_structure_jobs == 0:
        flags.append("No completed structure predictions available")
        recommendations.append(
            "Submit candidate peptide-MHC complexes to AlphaFold or equivalent structure prediction."
        )

    # --- RNA expression ---
    rna_samples = [s for s in samples if s.sample_type.value == "rna"]
    has_rna_expression = any(
        c.expression_evidence and len(c.expression_evidence) > 0 for c in candidates
    )
    if not rna_samples:
        flags.append("No RNA sample registered for this case")
        recommendations.append(
            "Register an RNA-seq sample to enable expression-based candidate filtering."
        )
    elif not has_rna_expression:
        flags.append("RNA sample present but no expression data linked to candidates")
        recommendations.append(
            "Process RNA-seq data and link expression evidence to candidate antigens."
        )

    # --- Sample count ---
    if not samples:
        flags.append("No samples registered for this case")
        recommendations.append(
            "Register at least tumor and normal samples to enable somatic variant calling."
        )
    else:
        sample_types = {s.sample_type.value for s in samples}
        if "tumor" not in sample_types:
            flags.append("No tumor sample registered")
            recommendations.append("Register a tumor sample for somatic variant calling.")
        if "normal" not in sample_types:
            flags.append("No matched normal sample registered")
            recommendations.append(
                "Register a matched normal sample to improve somatic variant specificity."
            )

    # --- Derive level ---
    if candidate_count == 0 or not samples:
        level = EvidenceLevel.insufficient
    elif len(flags) >= 4:
        level = EvidenceLevel.weak
    elif len(flags) >= 2:
        level = EvidenceLevel.moderate
    else:
        level = EvidenceLevel.strong

    return EvidenceAssessment(level=level, flags=flags, recommendations=recommendations)


# ---------------------------------------------------------------------------
# False-positive risk
# ---------------------------------------------------------------------------


class FalsePositiveRisk(str, enum.Enum):
    low = "low"
    moderate = "moderate"
    high = "high"


@dataclass
class CandidateFPWarning:
    candidate_id: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class FPAssessment:
    risk: FalsePositiveRisk
    overall_warnings: list[str] = field(default_factory=list)
    per_candidate: list[CandidateFPWarning] = field(default_factory=list)


def assess_false_positive_risk(candidates: list, db: Session) -> FPAssessment:
    """Evaluate false-positive risk across a list of CandidateAntigen objects.

    Considers candidate-to-variant ratio, missing expression data, and
    low-confidence binding predictions.
    """
    from backend.app.models import Variant

    overall_warnings: list[str] = []
    per_candidate: list[CandidateFPWarning] = []

    if not candidates:
        return FPAssessment(
            risk=FalsePositiveRisk.low,
            overall_warnings=["No candidates to evaluate."],
            per_candidate=[],
        )

    # Determine case from first candidate
    case_id = candidates[0].case_id
    variant_count = db.query(Variant).filter(Variant.case_id == case_id).count()
    candidate_count = len(candidates)

    # High ratio of candidates to variants suggests aggressive filtering or pipeline issues
    if variant_count > 0:
        ratio = candidate_count / variant_count
        if ratio > 0.5:
            overall_warnings.append(
                f"High candidate-to-variant ratio ({candidate_count}/{variant_count}): "
                "many variants are being promoted — review filtering thresholds."
            )
    elif candidate_count > 0:
        overall_warnings.append(
            "Candidates exist but no variants are registered — data integrity concern."
        )

    risk_score = 0

    for cand in candidates:
        cand_warnings: list[str] = []

        # Missing expression evidence
        if not cand.expression_evidence:
            cand_warnings.append("No expression data — candidate may not be tumour-expressed.")
            risk_score += 1

        # Low or missing binding confidence
        if not cand.prediction_scores:
            cand_warnings.append("No binding prediction scores — immunogenicity uncharacterised.")
            risk_score += 1
        else:
            # Look for low confidence indicators
            scores = cand.prediction_scores
            affinity = scores.get("binding_affinity") or scores.get("affinity_nm")
            rank = scores.get("rank") or scores.get("percentile_rank")
            if affinity is not None:
                try:
                    if float(affinity) > 500:
                        cand_warnings.append(
                            f"Binding affinity {affinity} nM exceeds 500 nM threshold — weak binder."
                        )
                        risk_score += 1
                except (TypeError, ValueError):
                    pass
            if rank is not None:
                try:
                    if float(rank) > 2.0:
                        cand_warnings.append(
                            f"Binding rank {rank}% exceeds 2% — low predicted presentation."
                        )
                        risk_score += 1
                except (TypeError, ValueError):
                    pass

        # Uncertainty flags set on candidate
        if cand.uncertainty_flags:
            flagged = [k for k, v in cand.uncertainty_flags.items() if v]
            if flagged:
                cand_warnings.append(f"Uncertainty flags set: {', '.join(flagged)}.")
                risk_score += 1

        if cand_warnings:
            per_candidate.append(CandidateFPWarning(candidate_id=cand.id, warnings=cand_warnings))

    # Derive risk level
    if risk_score == 0:
        risk = FalsePositiveRisk.low
    elif risk_score <= candidate_count:
        risk = FalsePositiveRisk.moderate
    else:
        risk = FalsePositiveRisk.high

    if overall_warnings or per_candidate:
        pass  # already set

    return FPAssessment(
        risk=risk,
        overall_warnings=overall_warnings,
        per_candidate=per_candidate,
    )


# ---------------------------------------------------------------------------
# Source citations
# ---------------------------------------------------------------------------


@dataclass
class Citation:
    source: str
    description: str
    url: str | None = None
    accessed_date: str = ""


_CITATION_TEMPLATES: dict[str, Citation] = {
    "netmhcpan": Citation(
        source="NetMHCpan 4.1",
        description=(
            "Peptide-MHC class I binding prediction. Reynisson B et al. (2020) Nucleic Acids Res."
        ),
        url="https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/",
    ),
    "netmhcpan_4": Citation(
        source="NetMHCpan 4.1",
        description=(
            "Peptide-MHC class I binding prediction. Reynisson B et al. (2020) Nucleic Acids Res."
        ),
        url="https://services.healthtech.dtu.dk/services/NetMHCpan-4.1/",
    ),
    "alphafold": Citation(
        source="AlphaFold2",
        description=("Protein structure prediction. Jumper J et al. (2021) Nature."),
        url="https://alphafold.ebi.ac.uk/",
    ),
    "alphafold2": Citation(
        source="AlphaFold2",
        description=("Protein structure prediction. Jumper J et al. (2021) Nature."),
        url="https://alphafold.ebi.ac.uk/",
    ),
    "alphafold3": Citation(
        source="AlphaFold3",
        description=("Protein structure prediction with ligands. Abramson J et al. (2024) Nature."),
        url="https://alphafoldserver.com/",
    ),
    "vep": Citation(
        source="Ensembl VEP",
        description=("Variant Effect Predictor annotation. McLaren W et al. (2016) Genome Biol."),
        url="https://www.ensembl.org/Tools/VEP",
    ),
    "ensembl_vep": Citation(
        source="Ensembl VEP",
        description=("Variant Effect Predictor annotation. McLaren W et al. (2016) Genome Biol."),
        url="https://www.ensembl.org/Tools/VEP",
    ),
    "mutect2": Citation(
        source="GATK Mutect2",
        description=("Somatic SNV and indel calling. Benjamin D et al. (2019) bioRxiv."),
        url="https://gatk.broadinstitute.org/hc/en-us/articles/360037593851",
    ),
    "strelka2": Citation(
        source="Strelka2",
        description=(
            "Small variant calling for germline and somatic samples. "
            "Kim S et al. (2018) Nat Methods."
        ),
        url="https://github.com/Illumina/strelka",
    ),
    "grch38": Citation(
        source="GRCh38 / hg38",
        description="Human reference genome assembly GRCh38 (Genome Reference Consortium).",
        url="https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.26/",
    ),
    "grch37": Citation(
        source="GRCh37 / hg19",
        description="Human reference genome assembly GRCh37 (Genome Reference Consortium).",
        url="https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13/",
    ),
    "canfam4": Citation(
        source="CanFam4",
        description="Dog reference genome assembly CanFam4.",
        url="https://www.ncbi.nlm.nih.gov/assembly/GCF_011100685.1/",
    ),
    "mock": Citation(
        source="FoldAgent Mock Pipeline",
        description=(
            "Internal research mock pipeline for demonstration and testing. "
            "Not a validated clinical tool."
        ),
        url=None,
    ),
}


def _accessed_today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def build_report_citations(case_id: str, db: Session) -> list[Citation]:
    """Generate source citations for tools and references used in a case.

    Inspects variant caller_source, annotation_source, candidate prediction_scores,
    structure job backend_used, and case species to determine which citations apply.
    """
    from backend.app.models import CandidateAntigen, Case, StructureJob, Variant

    case = db.get(Case, case_id)
    today = _accessed_today()
    seen: set[str] = set()
    citations: list[Citation] = []

    def _add(key: str) -> None:
        key_lower = key.lower()
        for template_key, cit in _CITATION_TEMPLATES.items():
            if template_key in key_lower and template_key not in seen:
                seen.add(template_key)
                citations.append(
                    Citation(
                        source=cit.source,
                        description=cit.description,
                        url=cit.url,
                        accessed_date=today,
                    )
                )
                return
        # Fallback: unknown tool — create a generic entry
        if key_lower not in seen:
            seen.add(key_lower)
            citations.append(
                Citation(
                    source=key,
                    description=f"Tool or reference used in case {case_id}.",
                    url=None,
                    accessed_date=today,
                )
            )

    # Variant callers and annotation sources
    variants = db.query(Variant).filter(Variant.case_id == case_id).all()
    for v in variants:
        if v.caller_source:
            _add(v.caller_source)
        if v.annotation_source:
            _add(v.annotation_source)

    # Binding prediction tools from candidate prediction_scores
    candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
    for c in candidates:
        if c.prediction_scores:
            tool = c.prediction_scores.get("tool") or c.prediction_scores.get("predictor")
            if tool:
                _add(tool)

    # Structure prediction backends
    structure_jobs = db.query(StructureJob).filter(StructureJob.case_id == case_id).all()
    for sj in structure_jobs:
        if sj.backend_used:
            _add(sj.backend_used)

    # Reference genome from case species if no explicit reference found
    if case is not None:
        ref_keys = [k for k in seen if any(g in k for g in ("grch", "canfam", "hg38", "hg19"))]
        if not ref_keys:
            species = case.species.value
            if species == "human":
                _add("grch38")
            elif species == "dog":
                _add("canfam4")

    # If no citations resolved, add mock pipeline as baseline
    if not citations:
        _add("mock")

    return citations


# ---------------------------------------------------------------------------
# Professional attestation
# ---------------------------------------------------------------------------


class AttestationType(str, enum.Enum):
    veterinary_review = "veterinary_review"
    medical_review = "medical_review"
    research_only = "research_only"


@dataclass
class ProfessionalAttestation:
    type: AttestationType
    attester_name: str
    credentials: str
    attestation_text: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# In-memory store for attestations (keyed by case_id).
# In production this would be persisted to the database.
_attestation_store: dict[str, dict] = {}


def check_attestation_required(case_id: str, db: Session) -> bool:
    """Return True if a professional attestation is required before report export.

    Attestation is required when:
    - Evidence level is strong or moderate, AND
    - At least one report has been generated for the case.
    """
    from backend.app.models import Report

    assessment = assess_evidence_level(case_id, db)
    if assessment.level not in (EvidenceLevel.strong, EvidenceLevel.moderate):
        return False

    report_count = db.query(Report).filter(Report.case_id == case_id).count()
    return report_count > 0


def record_attestation(
    case_id: str,
    attestation: ProfessionalAttestation,
    db: Session,
) -> dict:
    """Record a professional attestation for a case.

    Stores the attestation and creates an audit log entry.
    Returns a dict with attestation details and audit confirmation.
    """
    from backend.app.safety.audit import log_action

    record = {
        "case_id": case_id,
        "type": attestation.type.value,
        "attester_name": attestation.attester_name,
        "credentials": attestation.credentials,
        "attestation_text": attestation.attestation_text,
        "timestamp": attestation.timestamp,
    }
    _attestation_store[case_id] = record

    log_action(
        db,
        case_id=case_id,
        actor=attestation.attester_name,
        action="attestation.recorded",
        inputs={
            "type": attestation.type.value,
            "credentials": attestation.credentials,
        },
        outputs={"attestation_recorded": True},
        details=record,
    )
    db.commit()

    return {
        "status": "recorded",
        "case_id": case_id,
        "attestation": record,
    }


def get_attestation(case_id: str) -> dict | None:
    """Retrieve the stored attestation for a case, or None if not recorded."""
    return _attestation_store.get(case_id)
