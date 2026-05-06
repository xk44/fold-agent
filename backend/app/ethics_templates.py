"""Additional ethics and review template generators for FoldAgent.

All templates are research coordination artifacts only.
They do not constitute medical advice, veterinary advice, or treatment instructions.
No dosing, manufacturing, or injection information is included.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RESEARCH_COORDINATION_DISCLAIMER = (
    "Research coordination tool only — not medical/veterinary advice. "
    "Professional oversight, ethics board review, and jurisdiction-specific "
    "regulatory compliance are required before any real-world action."
)

_VETERINARY_SPECIES = {"dog", "cat", "horse", "rabbit", "demo"}
_CLINICAL_SPECIES = {"human"}


def _is_veterinary(species: str) -> bool:
    return species.lower() not in _CLINICAL_SPECIES


def build_uncertainty_summary(case_id: str, db: Session) -> dict:
    """Return a structured summary of uncertainty sources for a case.

    Does not fetch live data beyond confirming the case exists.
    The uncertainty sources are standardised across all cases; case_id is
    included for traceability only.
    """
    from backend.app.models import CandidateAntigen, Case, Sample

    case = db.get(Case, case_id)
    case_found = case is not None
    species = case.species.value if case_found else "unknown"

    candidates = (
        db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
        if case_found
        else []
    )
    samples = db.query(Sample).filter(Sample.case_id == case_id).all() if case_found else []

    has_rna = any(s.sample_type.value == "rna" for s in samples)
    candidate_count = len(candidates)

    uncertainty_sources = [
        {
            "name": "Variant calling confidence",
            "description": (
                "Variant calls are generated from mock/pipeline data. "
                "Real sequencing may yield different allele frequencies, strand biases, "
                "and somatic/germline classifications. All variant calls require "
                "orthogonal validation."
            ),
            "severity": "high",
            "mitigation": (
                "Submit raw FASTQ/BAM data to a validated clinical or research variant "
                "calling pipeline under professional supervision. Cross-check with "
                "matched normal sample if available."
            ),
        },
        {
            "name": "Prediction tool limitations",
            "description": (
                "Binding affinity, immunogenicity, and presentation scores are derived "
                "from computational predictors trained on limited species and allele data. "
                f"Candidate count in this case: {candidate_count}. "
                "Scores should be treated as prioritisation signals, not validated outcomes."
            ),
            "severity": "high",
            "mitigation": (
                "Have a qualified immunologist review all prediction scores. "
                "Validate top candidates with in-vitro or ex-vivo assays before "
                "any further research steps."
            ),
        },
        {
            "name": "Expression validation gaps",
            "description": (
                "Tumour-specific expression has "
                + (
                    "not been confirmed by RNA-seq in this case."
                    if not has_rna
                    else "RNA data present but mock/unvalidated."
                )
                + " Antigen candidates may not be expressed at levels relevant to immune recognition."
            ),
            "severity": "high" if not has_rna else "medium",
            "mitigation": (
                "Obtain validated RNA-seq data from matched tumour and normal tissue. "
                "Confirm differential expression with professional bioinformatics review."
            ),
        },
        {
            "name": "Structure prediction confidence",
            "description": (
                "3-D structure predictions (AlphaFold or equivalent) are computational "
                "models. pTM/ipTM scores and ranking scores indicate model confidence "
                "but do not substitute for experimental structural data."
            ),
            "severity": "medium",
            "mitigation": (
                "Treat structure models as hypothesis-generating only. "
                "Experimental structural biology (X-ray, cryo-EM) is required "
                "for high-confidence structural claims."
            ),
        },
        {
            "name": "MHC/HLA/DLA typing accuracy",
            "description": (
                "MHC context used for binding predictions may be imputed or mock. "
                "Inaccurate typing will propagate errors through all downstream "
                "binding and immunogenicity predictions."
            ),
            "severity": "high",
            "mitigation": (
                "Obtain validated MHC/HLA/DLA typing from an accredited laboratory "
                "before using binding predictions for any research decision."
            ),
        },
    ]

    return {
        "template_type": "uncertainty_summary",
        "case_id": case_id,
        "species": species,
        "candidate_count": candidate_count,
        "has_rna_sample": has_rna,
        "uncertainty_sources": uncertainty_sources,
        "overall_data_quality": "mock/research-only — not clinically validated",
        "disclaimer": RESEARCH_COORDINATION_DISCLAIMER,
        "warnings": [
            "All uncertainty ratings are indicative only.",
            "This summary does not replace professional scientific or clinical judgment.",
            "No dosing, formulation, injection, or manufacturing guidance is included.",
        ],
    }


def build_adverse_event_template(case_id: str, species: str) -> dict:
    """Return a fillable adverse-event report template.

    This is a TEMPLATE ONLY. It must be completed by a licensed professional
    and submitted through the appropriate regulatory/institutional channel.
    Species-appropriate language is used but no clinical instructions are included.
    """
    vet = _is_veterinary(species)
    subject_label = "animal patient" if vet else "patient"
    oversight_label = "attending veterinarian" if vet else "treating physician"
    regulatory_body = (
        "relevant veterinary regulatory authority and institutional IACUC/ethics committee"
        if vet
        else "relevant IRB, FDA MedWatch, or applicable national regulatory body"
    )
    professional_label = "veterinary oncologist" if vet else "medical oncologist"

    return {
        "template_type": "adverse_event_report",
        "template_status": "TEMPLATE ONLY — must be completed and submitted by a licensed professional",
        "case_id": case_id,
        "species": species,
        "sections": {
            "event_description": {
                "label": "Description of adverse event",
                "instructions": (
                    f"Describe the observed adverse event in the {subject_label}. "
                    "Include clinical signs, onset, and any relevant history. "
                    f"Complete in consultation with the {oversight_label}."
                ),
                "value": "[TO BE COMPLETED BY LICENSED PROFESSIONAL]",
            },
            "timeline": {
                "label": "Event timeline",
                "fields": {
                    "date_of_event": "[DATE]",
                    "date_first_observed": "[DATE]",
                    "date_reported_to_oversight": "[DATE]",
                    "date_of_resolution_or_ongoing": "[DATE or ONGOING]",
                },
            },
            "severity_classification": {
                "label": "Severity classification",
                "instructions": (
                    f"Grade severity according to applicable {species} oncology "
                    "adverse event criteria (e.g. VCOG-CTCAE for veterinary, "
                    "NCI-CTCAE for human). Grade must be assigned by the "
                    f"{oversight_label}."
                ),
                "grade": "[GRADE 1-5 — TO BE ASSIGNED BY LICENSED PROFESSIONAL]",
                "criteria_used": "[SPECIFY CRITERIA]",
            },
            "suspected_cause": {
                "label": "Suspected cause",
                "instructions": (
                    "Describe the suspected relationship to any research procedures, "
                    "experimental agents, or interventions. Causality assessment must "
                    f"be made by the {professional_label}."
                ),
                "value": "[TO BE COMPLETED BY LICENSED PROFESSIONAL]",
                "causal_assessment": "[UNRELATED / POSSIBLE / PROBABLE / DEFINITE — BY LICENSED PROFESSIONAL]",
            },
            "actions_taken": {
                "label": "Actions taken",
                "instructions": (
                    f"Document all actions taken by the {oversight_label}. "
                    "FoldAgent does not provide treatment or intervention instructions."
                ),
                "value": "[TO BE COMPLETED BY LICENSED PROFESSIONAL]",
            },
            "outcome": {
                "label": "Outcome",
                "options": [
                    "Recovered / Resolved",
                    "Recovering / Resolving",
                    "Not recovered / Not resolved",
                    "Recovered with sequelae",
                    "Fatal",
                    "Unknown",
                ],
                "value": "[SELECT OUTCOME — BY LICENSED PROFESSIONAL]",
            },
        },
        "reporting_contacts": {
            "institutional_oversight": "[INSERT INSTITUTIONAL IACUC / IRB / ETHICS COMMITTEE CONTACT]",
            "regulatory_body": regulatory_body,
            "principal_investigator": "[INSERT PI CONTACT]",
            "attending_professional": f"[INSERT {oversight_label.upper()} CONTACT]",
        },
        "disclaimer": RESEARCH_COORDINATION_DISCLAIMER,
        "warnings": [
            "THIS IS A TEMPLATE ONLY. FoldAgent does not generate final adverse event reports.",
            "All fields must be completed by a licensed professional.",
            "Do not use this template as a substitute for institutional reporting obligations.",
            "No dosing, injection, formulation, or manufacturing guidance is included.",
        ],
    }


def build_compassionate_use_checklist(species: str) -> dict:
    """Return a checklist for compassionate/experimental use review.

    FoldAgent cannot bypass, replace, or substitute for formal ethics approval.
    This checklist is a research coordination aid only.
    """
    vet = _is_veterinary(species)
    professional_label = "veterinary oncologist" if vet else "medical oncologist"
    oversight_body = (
        "IACUC / institutional veterinary ethics committee"
        if vet
        else "IRB / institutional review board"
    )
    regulatory_framework = (
        "applicable veterinary regulatory authority (e.g. USDA, VMD, state licensing board)"
        if vet
        else "applicable human-subject regulatory authority (e.g. FDA, EMA, national competent authority)"
    )
    informed_consent_note = (
        "Owner/guardian informed consent for experimental veterinary procedure"
        if vet
        else "Patient informed consent for experimental/compassionate use procedure"
    )

    checklist_items = [
        {
            "id": "cu_01",
            "category": "Eligibility",
            "item": "Confirm that standard-of-care options have been exhausted or are not applicable.",
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_02",
            "category": "Eligibility",
            "item": "Document medical/veterinary necessity and rationale for experimental approach.",
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_03",
            "category": "Ethics approval",
            "item": f"Submit protocol to {oversight_body} and obtain written approval.",
            "required_attestation": oversight_body,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_04",
            "category": "Ethics approval",
            "item": "Confirm approval covers the specific experimental modality being considered.",
            "required_attestation": oversight_body,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_05",
            "category": "Informed consent",
            "item": informed_consent_note,
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_06",
            "category": "Informed consent",
            "item": "Consent document explicitly addresses experimental/investigational nature and absence of guaranteed benefit.",
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_07",
            "category": "Regulatory",
            "item": f"Verify compliance with {regulatory_framework}.",
            "required_attestation": "qualified regulatory/legal counsel",
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_08",
            "category": "Regulatory",
            "item": "Confirm jurisdiction-specific requirements for compassionate/named-patient/expanded-access use.",
            "required_attestation": "qualified regulatory/legal counsel",
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_09",
            "category": "Data and privacy",
            "item": "Genomic data handling, storage, and sharing plan reviewed and approved.",
            "required_attestation": "data protection officer or equivalent",
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_10",
            "category": "Safety monitoring",
            "item": "Adverse event monitoring and reporting plan established before any experimental procedure.",
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_11",
            "category": "Research oversight",
            "item": "Principal investigator and supervising licensed professional identified and confirmed.",
            "required_attestation": "institutional research office",
            "status": "[ ] Incomplete",
        },
        {
            "id": "cu_12",
            "category": "FoldAgent scope",
            "item": (
                "Confirm that FoldAgent outputs are used as research coordination "
                "artifacts only, not as direct clinical instructions."
            ),
            "required_attestation": professional_label,
            "status": "[ ] Incomplete",
        },
    ]

    required_attestations = [
        {
            "role": professional_label,
            "attestation": (
                f"I confirm that I am a licensed {professional_label}, that I have reviewed "
                "the FoldAgent research outputs, and that any further steps will be taken "
                "under my professional supervision and in compliance with applicable regulations."
            ),
            "signature_placeholder": "[SIGNATURE / DATE]",
        },
        {
            "role": oversight_body,
            "attestation": (
                f"Ethics/oversight approval reference number: [INSERT REFERENCE]. "
                f"Approving body: {oversight_body}. Date of approval: [DATE]."
            ),
            "signature_placeholder": "[AUTHORIZED SIGNATORY / DATE]",
        },
    ]

    return {
        "template_type": "compassionate_use_checklist",
        "species": species,
        "is_veterinary": vet,
        "checklist_items": checklist_items,
        "regulatory_considerations": {
            "framework": regulatory_framework,
            "oversight_body": oversight_body,
            "note": (
                "Regulatory requirements vary by jurisdiction. "
                "This checklist does not constitute legal or regulatory advice. "
                "Consult qualified regulatory counsel."
            ),
        },
        "required_professional_attestations": required_attestations,
        "critical_warning": (
            "FoldAgent CANNOT bypass, substitute for, or satisfy ethics board approval. "
            "This checklist is a research coordination aid only. "
            "Formal approval from the appropriate ethics/regulatory body is mandatory."
        ),
        "disclaimer": RESEARCH_COORDINATION_DISCLAIMER,
        "warnings": [
            "This checklist does not constitute ethics approval.",
            "All items must be completed and attested by the specified licensed professionals.",
            "No dosing, injection, formulation, or manufacturing guidance is included.",
            "Jurisdiction-specific requirements may add additional mandatory items.",
        ],
    }


def build_vet_oncologist_questions(case_id: str, db: Session) -> dict:
    """Return pre-populated questions for a veterinary/oncology professional consultation.

    Questions are populated based on available case data. Species determines
    whether veterinary or clinical framing is used.
    """
    from backend.app.models import CandidateAntigen, Case, Sample

    case = db.get(Case, case_id)
    if case is None:
        species = "unknown"
        species_val = "unknown"
        candidate_count = 0
        sample_types: list[str] = []
        has_pipeline_run = False
    else:
        species_val = case.species.value
        candidates = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).all()
        samples = db.query(Sample).filter(Sample.case_id == case_id).all()
        candidate_count = len(candidates)
        sample_types = list({s.sample_type.value for s in samples})
        has_pipeline_run = True  # conservative — don't need to confirm

    vet = _is_veterinary(species_val)
    professional_label = "veterinary oncologist" if vet else "oncologist / treating physician"
    subject_label = "patient" if not vet else "animal patient"

    treatment_questions = [
        {
            "topic": "treatment_options",
            "question": (
                f"Based on the diagnosis summary and research candidate data for case {case_id}, "
                f"what standard-of-care treatment options are currently available for this {subject_label}?"
            ),
            "context": "FoldAgent has generated research candidate antigens. Professional assessment of treatment options is required independently of these computational outputs.",
            "for_professional": professional_label,
        },
        {
            "topic": "treatment_options",
            "question": (
                "Are there active clinical trials or research protocols this case may be eligible for, "
                "based on the species, diagnosis, and molecular profile?"
            ),
            "context": f"Candidate count in FoldAgent pipeline: {candidate_count}. Trial eligibility must be assessed by a licensed professional.",
            "for_professional": professional_label,
        },
    ]

    prognosis_questions = [
        {
            "topic": "prognosis",
            "question": (
                f"What is the expected prognosis for this {subject_label} given the available clinical information, "
                "independent of any experimental research coordination?"
            ),
            "context": "FoldAgent does not generate prognosis estimates. Professional clinical judgment is required.",
            "for_professional": professional_label,
        },
        {
            "topic": "prognosis",
            "question": (
                "How should the owner/guardian/family be counselled regarding the investigational nature "
                "of any research coordination outputs from FoldAgent?"
            ),
            "context": "Informed consent and prognostic counselling are the responsibility of the licensed professional.",
            "for_professional": professional_label,
        },
    ]

    sequencing_questions = [
        {
            "topic": "sequencing_results_interpretation",
            "question": (
                f"The pipeline has produced {candidate_count} candidate antigen(s) based on "
                f"{'mock/simulated' if not sample_types else ', '.join(sample_types)} data. "
                "Do these computational candidates align with your clinical assessment of the tumour biology?"
            ),
            "context": "All variant calls and prediction scores are research-only outputs requiring professional interpretation.",
            "for_professional": professional_label,
        },
        {
            "topic": "sequencing_results_interpretation",
            "question": (
                "What additional sequencing, pathology, or molecular testing would you recommend "
                "to validate or refute the candidate antigens identified by FoldAgent?"
            ),
            "context": "FoldAgent outputs should be treated as hypothesis-generating, not clinically validated.",
            "for_professional": professional_label,
        },
        {
            "topic": "sequencing_results_interpretation",
            "question": (
                "Are the MHC/HLA/DLA alleles used for binding predictions consistent with "
                "validated typing for this patient, or is laboratory typing required?"
            ),
            "context": "Accurate MHC typing is critical for binding prediction validity.",
            "for_professional": professional_label,
        },
    ]

    trial_questions = [
        {
            "topic": "clinical_trial_eligibility",
            "question": (
                f"Is this {subject_label} potentially eligible for any tumour-agnostic or "
                "species-specific immunotherapy research protocols?"
            ),
            "context": f"Species: {species_val}. Trial eligibility must be assessed by a licensed professional against current trial registries.",
            "for_professional": professional_label,
        },
        {
            "topic": "clinical_trial_eligibility",
            "question": (
                "What institutional or regulatory approvals would be required before this case "
                "could proceed from computational research coordination to any experimental procedure?"
            ),
            "context": "FoldAgent cannot authorise, replace, or expedite any regulatory or ethics approval process.",
            "for_professional": professional_label,
        },
    ]

    return {
        "template_type": "professional_consultation_questions",
        "case_id": case_id,
        "species": species_val,
        "is_veterinary": vet,
        "candidate_count": candidate_count,
        "sample_types_present": sample_types,
        "questions_by_topic": {
            "treatment_options": treatment_questions,
            "prognosis_discussion": prognosis_questions,
            "sequencing_results_interpretation": sequencing_questions,
            "clinical_trial_eligibility": trial_questions,
        },
        "instructions": (
            f"These questions are pre-populated from FoldAgent case data to facilitate "
            f"a structured consultation with a {professional_label}. "
            "They are starting points only — the professional should expand, modify, or "
            "discard questions as clinically appropriate."
        ),
        "disclaimer": RESEARCH_COORDINATION_DISCLAIMER,
        "warnings": [
            "These questions do not constitute a clinical consultation.",
            "FoldAgent does not provide medical or veterinary advice.",
            "No dosing, injection, formulation, or manufacturing guidance is included.",
            "All clinical decisions must be made by the licensed professional.",
        ],
    }
