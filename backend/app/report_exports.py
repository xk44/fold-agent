"""FoldAgent Report Exports (Phase 9 + Phase 17)

Provides versioned HTML/Markdown report exports, veterinary and human research
consent draft templates, and unsafe-content scanning/sanitization.

All outputs are research coordination artifacts only.
No dosing, injection, manufacturing, or treatment protocol information is included.
These templates are NOT legal or medical advice and require professional review.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

RESEARCH_DISCLAIMER = (
    "RESEARCH COORDINATION TOOL ONLY — NOT MEDICAL OR VETERINARY ADVICE.\n"
    "All outputs require professional oversight, ethics board review, and "
    "jurisdiction-specific regulatory compliance before any real-world action.\n"
    "No dosing, injection, manufacturing, or treatment protocol information is included."
)

# ---------------------------------------------------------------------------
# Unsafe content patterns
# ---------------------------------------------------------------------------

UNSAFE_PATTERNS: list[dict] = [
    {
        "pattern": r"\b(\d+\s*(mg|ml|mcg|ug|μg|nmol|mmol|units?)\b[^.]*?(dose|inject|administ|infus))",
        "severity": "high",
        "recommendation": "Consult a licensed professional for any dosage information.",
    },
    {
        "pattern": r"\b(inject\w*\s+(into|through|subcutan|intraven|intramus|intraderm|intratumo))",
        "severity": "high",
        "recommendation": "Injection procedures must be performed by a licensed professional.",
    },
    {
        "pattern": r"\b(treatment\s+protocol\s*:)",
        "severity": "high",
        "recommendation": "Treatment protocols must be defined by a licensed professional.",
    },
    {
        "pattern": r"\b(administer\s+(\d+|the\s+dose|this\s+dose|a\s+dose))",
        "severity": "high",
        "recommendation": "Administration instructions must come from a licensed professional.",
    },
    {
        "pattern": r"\b(dose\s*[:=]\s*\d+)",
        "severity": "high",
        "recommendation": "Dosage specifications require licensed professional oversight.",
    },
    {
        "pattern": r"\b(inject\s+(the\s+)?(patient|animal|subject|subject|dog|cat))",
        "severity": "high",
        "recommendation": "Injection instructions must be provided by a licensed professional.",
    },
    {
        "pattern": r"\b(formulate\s+(the\s+)?(vaccine|peptide|antigen|compound|solution))",
        "severity": "moderate",
        "recommendation": "Formulation instructions require a licensed pharmaceutical/clinical professional.",
    },
    {
        "pattern": r"\b(manufacturing\s+(protocol|procedure|step|instruction|guide))",
        "severity": "moderate",
        "recommendation": "Manufacturing protocols are outside the scope of this research tool.",
    },
    {
        "pattern": r"\b(dilut\w+\s+to\s+\d+\s*(mg|ml|mcg|ug|μg|nmol|mM|nM))",
        "severity": "moderate",
        "recommendation": "Dilution instructions must be provided by a licensed professional.",
    },
    {
        "pattern": r"\b(sterile\s+(filter|preparation|technique|procedure)\s+.*?syringe)",
        "severity": "moderate",
        "recommendation": "Sterile preparation instructions require a licensed professional.",
    },
]

_COMPILED_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (re.compile(p["pattern"], re.IGNORECASE), p) for p in UNSAFE_PATTERNS
]

_REDACTION_PLACEHOLDER = "[REMOVED — consult qualified professional]"


def scan_for_unsafe_content(text: str) -> list[dict]:
    """Scan text for unsafe instruction patterns.

    Returns a list of matches with pattern, matched_text, severity, and recommendation.
    """
    results: list[dict] = []
    seen_spans: list[tuple[int, int]] = []

    for compiled, meta in _COMPILED_PATTERNS:
        for m in compiled.finditer(text):
            start, end = m.span()
            # deduplicate overlapping spans
            overlapping = any(not (end <= s or start >= e) for s, e in seen_spans)
            if not overlapping:
                seen_spans.append((start, end))
                results.append(
                    {
                        "pattern": meta["pattern"],
                        "matched_text": m.group(0),
                        "severity": meta["severity"],
                        "recommendation": meta["recommendation"],
                    }
                )

    return results


def sanitize_report_text(text: str) -> str:
    """Replace unsafe content matches with a redaction placeholder."""
    for compiled, _ in _COMPILED_PATTERNS:
        text = compiled.sub(_REDACTION_PLACEHOLDER, text)
    return text


# ---------------------------------------------------------------------------
# Version metadata
# ---------------------------------------------------------------------------


def build_report_version(case_id: str, db: "Session") -> dict:
    """Return versioned metadata for a case report."""
    from backend.app.models import Case, CandidateAntigen, Report

    case = db.get(Case, case_id)
    if case is None:
        return {
            "version": "0.0.0",
            "hash": None,
            "generated_at": datetime.now(UTC).isoformat(),
            "format": "html",
            "case_found": False,
        }

    candidate_count = db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).count()
    report_count = db.query(Report).filter(Report.case_id == case_id).count()
    generated_at = datetime.now(UTC).isoformat()

    version_src = f"{case_id}:{case.species.value}:{candidate_count}:{report_count}:{generated_at}"
    report_hash = hashlib.sha256(version_src.encode()).hexdigest()[:16]

    return {
        "version": f"1.{report_count}.{candidate_count}",
        "hash": report_hash,
        "generated_at": generated_at,
        "format": "html",
        "case_id": case_id,
        "species": case.species.value,
        "candidate_count": candidate_count,
        "report_count": report_count,
    }


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------


def build_report_html(case_id: str, db: "Session") -> str:
    """Build a styled HTML report for a case.

    Includes: case metadata, candidate summary table, evidence level, FP risk
    warnings, citations, safety disclaimers, and a version watermark.
    """
    from backend.app.models import Case, CandidateAntigen
    from backend.app.safety_reports import (
        assess_evidence_level,
        assess_false_positive_risk,
        build_report_citations,
    )

    case = db.get(Case, case_id)
    if case is None:
        return _html_not_found(case_id)

    candidates = (
        db.query(CandidateAntigen)
        .filter(CandidateAntigen.case_id == case_id)
        .order_by(CandidateAntigen.created_at.desc())
        .all()
    )

    evidence = assess_evidence_level(case_id, db)
    fp = assess_false_positive_risk(candidates, db)
    citations = build_report_citations(case_id, db)
    version_meta = build_report_version(case_id, db)

    created_str = case.created_at.strftime("%Y-%m-%d %H:%M UTC") if case.created_at else "unknown"
    generated_at = version_meta["generated_at"]
    report_hash = version_meta["hash"]
    version_str = version_meta["version"]

    # --- candidate table rows ---
    if candidates:
        cand_rows = "".join(
            f"<tr>"
            f"<td>{i + 1}</td>"
            f"<td>{_h(c.mhc_context or 'n/a')}</td>"
            f"<td>{_h(_score_summary(c.prediction_scores))}</td>"
            f"<td>{_h(_expr_summary(c.expression_evidence))}</td>"
            f"<td>{_h(c.review_status.value if c.review_status else 'unreviewed')}</td>"
            f"</tr>"
            for i, c in enumerate(candidates)
        )
        candidate_table = f"""
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th><th>MHC context</th><th>Binding score</th>
              <th>Expression</th><th>Review status</th>
            </tr>
          </thead>
          <tbody>{cand_rows}</tbody>
        </table>"""
    else:
        candidate_table = "<p class='empty'>No candidate antigens registered for this case.</p>"

    # --- evidence flags ---
    evidence_flag_html = ""
    if evidence.flags:
        items = "".join(f"<li>{_h(f)}</li>" for f in evidence.flags)
        evidence_flag_html = f"<ul class='flags'>{items}</ul>"

    # --- FP warnings ---
    fp_warning_html = ""
    if fp.overall_warnings:
        items = "".join(f"<li>{_h(w)}</li>" for w in fp.overall_warnings)
        fp_warning_html = f"<ul class='warnings'>{items}</ul>"

    # --- per-candidate FP ---
    per_cand_html = ""
    if fp.per_candidate:
        rows = "".join(
            f"<li><strong>Candidate {_h(pw.candidate_id[:8])}…</strong>: "
            + "; ".join(_h(w) for w in pw.warnings)
            + "</li>"
            for pw in fp.per_candidate
        )
        per_cand_html = f"<ul class='warnings'>{rows}</ul>"

    # --- citations ---
    if citations:
        cit_rows = "".join(
            f"<tr><td>{_h(c.source)}</td><td>{_h(c.description)}</td>"
            f"<td>{'<a href="' + _h(c.url) + '" target="_blank">' + _h(c.url) + '</a>' if c.url else 'n/a'}</td>"
            f"<td>{_h(c.accessed_date or '')}</td></tr>"
            for c in citations
        )
        citations_section = f"""
        <table class="data-table">
          <thead><tr><th>Source</th><th>Description</th><th>URL</th><th>Accessed</th></tr></thead>
          <tbody>{cit_rows}</tbody>
        </table>"""
    else:
        citations_section = "<p class='empty'>No citations available.</p>"

    evidence_cls = {
        "strong": "badge-green",
        "moderate": "badge-yellow",
        "weak": "badge-orange",
        "insufficient": "badge-red",
    }.get(evidence.level.value, "badge-grey")

    fp_cls = {
        "low": "badge-green",
        "moderate": "badge-yellow",
        "high": "badge-red",
    }.get(fp.risk.value, "badge-grey")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FoldAgent Case Report — {_h(case_id)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; color: #1a1a2e; }}
    h1, h2, h3 {{ color: #16213e; }}
    .disclaimer {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; margin: 1rem 0; }}
    .data-table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
    .data-table th {{ background: #16213e; color: white; padding: 0.5rem; text-align: left; }}
    .data-table td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; }}
    .data-table tr:nth-child(even) {{ background: #f9f9f9; }}
    .badge {{ padding: 2px 8px; border-radius: 3px; font-size: 0.8rem; font-weight: bold; }}
    .badge-green {{ background: #d4edda; color: #155724; }}
    .badge-yellow {{ background: #fff3cd; color: #856404; }}
    .badge-orange {{ background: #fde8d8; color: #7d4e00; }}
    .badge-red {{ background: #f8d7da; color: #721c24; }}
    .badge-grey {{ background: #e2e3e5; color: #383d41; }}
    .flags {{ color: #856404; }}
    .warnings {{ color: #721c24; }}
    .empty {{ color: #888; font-style: italic; }}
    .watermark {{ color: #aaa; font-size: 0.75rem; margin-top: 2rem; border-top: 1px solid #eee; padding-top: 0.5rem; }}
    .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }}
    .meta-item {{ background: #f4f4f8; padding: 0.5rem 0.75rem; border-radius: 4px; }}
    .meta-item label {{ font-size: 0.75rem; color: #666; display: block; }}
    .meta-item span {{ font-weight: 600; }}
  </style>
</head>
<body>
  <h1>FoldAgent Case Report</h1>

  <div class="disclaimer">
    <strong>RESEARCH ONLY.</strong> {_h(RESEARCH_DISCLAIMER)}
  </div>

  <h2>Case Metadata</h2>
  <div class="meta-grid">
    <div class="meta-item"><label>Case ID</label><span>{_h(case_id)}</span></div>
    <div class="meta-item"><label>Species</label><span>{_h(case.species.value)}</span></div>
    <div class="meta-item"><label>Created</label><span>{_h(created_str)}</span></div>
    <div class="meta-item"><label>Consent status</label><span>{_h(case.consent_status or "pending")}</span></div>
    <div class="meta-item"><label>Review status</label><span>{_h(case.review_status or "unreviewed")}</span></div>
    <div class="meta-item"><label>Diagnosis summary</label><span>{_h(case.diagnosis_summary or "n/a")}</span></div>
  </div>

  <h2>Candidate Antigens ({len(candidates)})</h2>
  {candidate_table}

  <h2>Evidence Assessment</h2>
  <p>Evidence level: <span class="badge {evidence_cls}">{_h(evidence.level.value.upper())}</span></p>
  {evidence_flag_html}
  {"<h3>Recommendations</h3><ul>" + "".join(f"<li>{_h(r)}</li>" for r in evidence.recommendations) + "</ul>" if evidence.recommendations else ""}

  <h2>False-Positive Risk</h2>
  <p>Overall risk: <span class="badge {fp_cls}">{_h(fp.risk.value.upper())}</span></p>
  {fp_warning_html}
  {per_cand_html}

  <h2>Source Citations</h2>
  {citations_section}

  <h2>Safety Disclaimers</h2>
  <div class="disclaimer">
    <ul>
      <li>This report is a <strong>research coordination artifact only</strong>. It is not a clinical or veterinary report.</li>
      <li>No dosing, injection, formulation, or manufacturing instructions are included.</li>
      <li>All candidate antigen predictions are computational estimates requiring expert validation.</li>
      <li>Ethics board review and professional oversight are mandatory before any real-world action.</li>
      <li>This system cannot authorise, replace, or expedite any regulatory approval process.</li>
    </ul>
  </div>

  <div class="watermark">
    Generated by FoldAgent &bull; Version {_h(version_str)} &bull;
    Hash <code>{_h(report_hash or "n/a")}</code> &bull;
    {_h(generated_at)}
  </div>
</body>
</html>"""

    return html


def _html_not_found(case_id: str) -> str:
    return (
        f"<!DOCTYPE html><html><body>"
        f"<h1>Case not found</h1>"
        f"<p>No case with ID <code>{_h(case_id)}</code> exists.</p>"
        f"</body></html>"
    )


def _h(value: str | None) -> str:
    """Minimal HTML escaping for untrusted strings."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _score_summary(scores: dict | None) -> str:
    if not scores:
        return "n/a"
    affinity = scores.get("binding_affinity") or scores.get("affinity_nm")
    rank = scores.get("rank") or scores.get("percentile_rank")
    parts = []
    if affinity is not None:
        parts.append(f"{affinity} nM")
    if rank is not None:
        parts.append(f"rank {rank}%")
    return ", ".join(parts) if parts else "present"


def _expr_summary(expr: dict | None) -> str:
    if not expr:
        return "absent"
    tpm = expr.get("tpm") or expr.get("TPM")
    if tpm is not None:
        return f"TPM {tpm}"
    return "present"


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def build_report_markdown(case_id: str, db: "Session") -> str:
    """Build a full Markdown report for a case.

    Includes the same sections as the HTML report. Sections are wrapped with
    <!-- EDITABLE: ... --> comment markers for user customisation.
    """
    from backend.app.models import Case, CandidateAntigen
    from backend.app.safety_reports import (
        assess_evidence_level,
        assess_false_positive_risk,
        build_report_citations,
    )

    case = db.get(Case, case_id)
    if case is None:
        return f"# Case Not Found\n\nNo case with ID `{case_id}` exists.\n"

    candidates = (
        db.query(CandidateAntigen)
        .filter(CandidateAntigen.case_id == case_id)
        .order_by(CandidateAntigen.created_at.desc())
        .all()
    )

    evidence = assess_evidence_level(case_id, db)
    fp = assess_false_positive_risk(candidates, db)
    citations = build_report_citations(case_id, db)
    version_meta = build_report_version(case_id, db)

    created_str = case.created_at.strftime("%Y-%m-%d %H:%M UTC") if case.created_at else "unknown"

    lines: list[str] = []

    lines += [
        "# FoldAgent Case Report",
        "",
        "> **RESEARCH ONLY.** " + RESEARCH_DISCLAIMER.replace("\n", " "),
        "",
    ]

    # --- Case metadata ---
    lines += [
        "<!-- EDITABLE: case-metadata -->",
        "## Case Metadata",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Case ID | `{case_id}` |",
        f"| Species | {case.species.value} |",
        f"| Created | {created_str} |",
        f"| Consent status | {case.consent_status or 'pending'} |",
        f"| Review status | {case.review_status or 'unreviewed'} |",
        f"| Diagnosis summary | {case.diagnosis_summary or 'n/a'} |",
        "<!-- /EDITABLE: case-metadata -->",
        "",
    ]

    # --- Candidate table ---
    lines += [
        "<!-- EDITABLE: candidate-summary -->",
        f"## Candidate Antigens ({len(candidates)})",
        "",
    ]
    if candidates:
        lines += [
            "| # | MHC context | Binding score | Expression | Review status |",
            "|---|---|---|---|---|",
        ]
        for i, c in enumerate(candidates):
            lines.append(
                f"| {i + 1} | {c.mhc_context or 'n/a'} | {_score_summary(c.prediction_scores)} "
                f"| {_expr_summary(c.expression_evidence)} | {c.review_status.value if c.review_status else 'unreviewed'} |"
            )
    else:
        lines.append("_No candidate antigens registered for this case._")
    lines += ["<!-- /EDITABLE: candidate-summary -->", ""]

    # --- Evidence ---
    lines += [
        "<!-- EDITABLE: evidence-assessment -->",
        "## Evidence Assessment",
        "",
        f"**Evidence level:** {evidence.level.value.upper()}",
        "",
    ]
    if evidence.flags:
        lines.append("**Flags:**")
        lines += [f"- {f}" for f in evidence.flags]
    if evidence.recommendations:
        lines.append("")
        lines.append("**Recommendations:**")
        lines += [f"- {r}" for r in evidence.recommendations]
    lines += ["<!-- /EDITABLE: evidence-assessment -->", ""]

    # --- FP risk ---
    lines += [
        "<!-- EDITABLE: fp-risk -->",
        "## False-Positive Risk",
        "",
        f"**Overall risk:** {fp.risk.value.upper()}",
        "",
    ]
    if fp.overall_warnings:
        lines.append("**Warnings:**")
        lines += [f"- {w}" for w in fp.overall_warnings]
    if fp.per_candidate:
        lines.append("")
        lines.append("**Per-candidate issues:**")
        for pw in fp.per_candidate:
            lines.append(f"- Candidate `{pw.candidate_id[:8]}…`: " + "; ".join(pw.warnings))
    lines += ["<!-- /EDITABLE: fp-risk -->", ""]

    # --- Citations ---
    lines += [
        "<!-- EDITABLE: citations -->",
        "## Source Citations",
        "",
    ]
    if citations:
        lines += [
            "| Source | Description | URL | Accessed |",
            "|---|---|---|---|",
        ]
        for c in citations:
            url_str = f"[link]({c.url})" if c.url else "n/a"
            lines.append(f"| {c.source} | {c.description} | {url_str} | {c.accessed_date or ''} |")
    else:
        lines.append("_No citations available._")
    lines += ["<!-- /EDITABLE: citations -->", ""]

    # --- Safety disclaimers ---
    lines += [
        "<!-- EDITABLE: safety-disclaimers -->",
        "## Safety Disclaimers",
        "",
        "- This report is a **research coordination artifact only**. It is not a clinical or veterinary report.",
        "- No dosing, injection, formulation, or manufacturing instructions are included.",
        "- All candidate antigen predictions are computational estimates requiring expert validation.",
        "- Ethics board review and professional oversight are mandatory before any real-world action.",
        "- This system cannot authorise, replace, or expedite any regulatory approval process.",
        "<!-- /EDITABLE: safety-disclaimers -->",
        "",
    ]

    # --- Version watermark ---
    lines += [
        "---",
        f"_Generated by FoldAgent — Version {version_meta['version']} — "
        f"Hash `{version_meta['hash'] or 'n/a'}` — {version_meta['generated_at']}_",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Veterinary consent draft
# ---------------------------------------------------------------------------


def build_veterinary_consent(case_id: str, db: "Session") -> dict:
    """Build a veterinary owner consent draft for a case.

    Species-aware: dog cases include species-specific language.
    TEMPLATE ONLY — must be reviewed and signed by a licensed veterinary professional.
    """
    from backend.app.models import Case, CandidateAntigen

    case = db.get(Case, case_id)
    species = case.species.value if case else "unknown"
    candidate_count = (
        db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).count()
        if case
        else 0
    )

    is_dog = species == "dog"
    animal_desc = "canine patient" if is_dog else f"{species} patient"
    species_note = (
        "The research pipeline uses the CanFam4 dog reference genome and canine-specific "
        "MHC (DLA) allele databases for binding predictions."
        if is_dog
        else f"The research pipeline uses species-appropriate reference data for {species}."
    )

    body = f"""VETERINARY OWNER/GUARDIAN INFORMED CONSENT FOR PARTICIPATION IN EXPERIMENTAL RESEARCH COORDINATION

TEMPLATE ONLY — This document must be completed, reviewed, and signed by the supervising licensed veterinarian.
FoldAgent outputs are research coordination artifacts only and do not constitute veterinary advice.

---

OWNER/GUARDIAN INFORMATION
Name: [OWNER NAME]
Address: [ADDRESS]
Phone: [PHONE]
Email: [EMAIL]

---

ANIMAL PATIENT INFORMATION
Animal name: [ANIMAL NAME]
Species/Breed: {species.title()} / [BREED]
Age/DOB: [AGE / DATE OF BIRTH]
Sex: [SEX]
Weight: [WEIGHT]
FoldAgent case reference: {case_id}

---

DESCRIPTION OF RESEARCH COORDINATION ACTIVITY

The supervising veterinarian has used FoldAgent, a computational research coordination tool,
to analyse genomic data for your {animal_desc}. This tool identified {candidate_count} candidate
neoantigen(s) as research candidates based on computational analysis of tumour-associated variants.

{species_note}

THIS IS NOT A TREATMENT PLAN. FoldAgent does not prescribe, formulate, or administer any
therapeutic agent. All findings are preliminary computational research outputs that require
expert veterinary review, experimental validation, and appropriate regulatory/ethics approval
before any further steps are considered.

---

NATURE OF EXPERIMENTAL / INVESTIGATIONAL ACTIVITY

[ ] Standard-of-care options have been discussed and documented separately.
[ ] This activity involves experimental or investigational research coordination.
[ ] No approved veterinary therapeutic product has been prescribed based solely on these outputs.
[ ] The supervising veterinarian has reviewed and interprets all FoldAgent outputs.

---

RISKS AND UNCERTAINTIES

I/We understand that:
1. Computational candidate antigen predictions may be inaccurate and require experimental validation.
2. FoldAgent provides research coordination support only — it is not a validated clinical tool.
3. Any further experimental steps carry risks that must be discussed with the supervising veterinarian.
4. There is no guarantee of benefit from any experimental research activity.
5. The owner/guardian retains the right to withdraw consent at any time.

---

SUPERVISING VETERINARIAN ATTESTATION

I, the undersigned licensed veterinarian, confirm that:
- I have reviewed all FoldAgent research coordination outputs for this case.
- I have discussed the experimental nature of this activity with the owner/guardian.
- No dosing, injection, or treatment protocol has been derived directly from FoldAgent outputs.
- All further steps are subject to appropriate ethics/regulatory review.

Veterinarian name: [VETERINARIAN NAME]
License number: [LICENSE NUMBER]
Institution: [INSTITUTION]
Date: [DATE]
Signature: ________________________

---

OWNER/GUARDIAN CONSENT SIGNATURE

I/We have read and understood the above information and consent to the described research coordination activity.

Owner/guardian name: [OWNER NAME]
Date: [DATE]
Signature: ________________________

---

WITNESS (if required by jurisdiction):
Name: [WITNESS NAME]
Date: [DATE]
Signature: ________________________
"""

    return {
        "title": f"Veterinary Owner Consent Draft — Case {case_id}",
        "body": body,
        "attestation_fields": [
            {"field": "owner_name", "label": "Owner/guardian full name", "required": True},
            {"field": "animal_name", "label": "Animal patient name", "required": True},
            {"field": "species_breed", "label": "Species and breed", "required": True},
            {"field": "vet_name", "label": "Supervising veterinarian name", "required": True},
            {"field": "vet_license", "label": "Veterinary license number", "required": True},
            {"field": "vet_institution", "label": "Institution", "required": True},
            {"field": "date_signed", "label": "Date of signing", "required": True},
            {"field": "owner_signature", "label": "Owner/guardian signature", "required": True},
            {"field": "vet_signature", "label": "Veterinarian signature", "required": True},
        ],
        "warnings": [
            "TEMPLATE ONLY — must be completed and reviewed by a licensed veterinarian.",
            "This template does not constitute a legal consent document until reviewed by qualified legal counsel.",
            "No dosing, injection, formulation, or manufacturing guidance is included.",
            "Jurisdiction-specific requirements may require additional fields or signatures.",
            "Ethics committee / IACUC approval may also be required.",
        ],
        "species": species,
        "case_id": case_id,
        "candidate_count": candidate_count,
        "is_dog_specific": is_dog,
    }


# ---------------------------------------------------------------------------
# Human research consent draft
# ---------------------------------------------------------------------------


def build_human_research_consent(case_id: str, db: "Session") -> dict:
    """Build a human research participant consent draft.

    STRONG DISCLAIMER: This is a TEMPLATE ONLY.
    It is NOT legal or medical advice. It must be reviewed by an IRB and
    qualified legal/medical counsel before any use.
    """
    from backend.app.models import Case, CandidateAntigen

    case = db.get(Case, case_id)
    candidate_count = (
        db.query(CandidateAntigen).filter(CandidateAntigen.case_id == case_id).count()
        if case
        else 0
    )

    body = f"""HUMAN RESEARCH PARTICIPANT INFORMED CONSENT FORM

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
CRITICAL WARNING: THIS IS A TEMPLATE ONLY.
- This document is NOT a legally valid consent form.
- This document is NOT medical advice.
- This document has NOT been reviewed or approved by any IRB or ethics board.
- This document MUST be reviewed by qualified legal and medical counsel before use.
- FoldAgent is a research coordination tool only. It cannot produce approved consent forms.
- DO NOT use this template as a substitute for institutional consent processes.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

FoldAgent Case Reference: {case_id}

---

STUDY TITLE: [INSERT FULL STUDY TITLE]
Principal Investigator: [PI NAME, CREDENTIALS, INSTITUTION]
IRB Protocol Number: [IRB PROTOCOL NUMBER — REQUIRED]
IRB Contact: [IRB CONTACT INFORMATION]
Study Sponsor / Funding: [SPONSOR / FUNDING SOURCE]

---

PARTICIPANT INFORMATION
Name: [PARTICIPANT NAME]
Date of Birth: [DATE OF BIRTH]
Medical Record Number (if applicable): [MRN]

---

INTRODUCTION AND PURPOSE

You are being invited to participate in a research study. This form explains the study and what
your participation would involve. Please read it carefully and ask questions before agreeing to
participate.

The purpose of this research study is: [INSERT STUDY PURPOSE].

FoldAgent, a computational research coordination tool, has identified {candidate_count}
candidate neoantigen(s) associated with your genomic data as potential research subjects.
These are computational predictions only and have not been experimentally validated.

IMPORTANT: Participation in this research study is entirely voluntary. You may withdraw at any
time without penalty or loss of benefits to which you are otherwise entitled.

---

STUDY PROCEDURES

If you agree to participate, the following procedures will be performed:
[INSERT DETAILED STUDY PROCEDURES — to be completed by qualified medical researcher]

Note: FoldAgent provides computational research coordination only. It does not specify,
prescribe, or authorise any study procedures, dosing, administration routes, or treatments.

---

RISKS AND DISCOMFORTS

Potential risks include:
[INSERT DETAILED RISK INFORMATION — to be completed by qualified medical researcher]

General risks associated with experimental neoantigen research may include:
- Adverse immune reactions (type and severity to be specified by the investigator)
- Unknown or unforeseen risks associated with experimental interventions
- Psychological risks associated with receiving genetic research results
- Privacy risks related to genomic data (see Data Privacy section below)

---

POTENTIAL BENEFITS

Potential benefits to you:
[INSERT BENEFITS — to be completed by qualified medical researcher]

Potential benefits to society:
[INSERT SOCIETAL BENEFITS — to be completed by qualified medical researcher]

There is no guarantee that participation will provide direct medical benefit.

---

ALTERNATIVES TO PARTICIPATION

Your alternative to participating in this study is to not participate. Standard care options
include: [INSERT STANDARD-OF-CARE ALTERNATIVES — to be completed by treating physician].

---

WITHDRAWAL FROM STUDY

Your participation is voluntary. You may withdraw at any time by informing the principal
investigator. Withdrawal will not affect your standard medical care.

---

DATA PRIVACY AND CONFIDENTIALITY

Your genomic data and personal health information will be handled as follows:
[INSERT DATA HANDLING DETAILS — to be completed by data protection officer and PI]

- Data will be stored: [STORAGE LOCATION AND SECURITY MEASURES]
- Data may be shared with: [LIST OF PARTIES — requires IRB approval]
- Data retention period: [RETENTION PERIOD]
- De-identification methods: [DESCRIBE DE-IDENTIFICATION]

Compliance with applicable data protection regulations (e.g., HIPAA, GDPR, local laws) is
required. Consult a qualified data protection officer.

---

COSTS AND COMPENSATION

Costs to participant: [INSERT ANY COSTS]
Compensation for participation: [INSERT COMPENSATION DETAILS]

---

CONTACT INFORMATION

For questions about this research:
Principal Investigator: [PI NAME] — [PHONE] — [EMAIL]

For questions about your rights as a research participant:
IRB Contact: [IRB NAME] — [PHONE] — [EMAIL]

---

SIGNATURE BLOCKS

PARTICIPANT CONSENT
I have read and understood this consent form. I have had the opportunity to ask questions.
I voluntarily agree to participate in this research study.

Participant name: [NAME]
Date: [DATE]
Signature: ________________________

LEGALLY AUTHORISED REPRESENTATIVE (if applicable)
Name: [NAME]
Relationship: [RELATIONSHIP]
Date: [DATE]
Signature: ________________________

PERSON OBTAINING CONSENT
I have explained the study to the participant and answered their questions.

Investigator/designee name: [NAME], [CREDENTIALS]
Date: [DATE]
Signature: ________________________

WITNESS (required by some IRBs)
Name: [NAME]
Date: [DATE]
Signature: ________________________

---

IRB APPROVAL STAMP / WATERMARK: [TO BE ADDED BY IRB UPON APPROVAL]
"""

    return {
        "title": f"Human Research Consent Draft — Case {case_id} — TEMPLATE ONLY",
        "body": body,
        "attestation_fields": [
            {"field": "irb_protocol_number", "label": "IRB protocol number", "required": True},
            {"field": "pi_name", "label": "Principal investigator name", "required": True},
            {
                "field": "pi_credentials",
                "label": "PI credentials and institution",
                "required": True,
            },
            {"field": "study_title", "label": "Full study title", "required": True},
            {"field": "participant_name", "label": "Participant full name", "required": True},
            {"field": "participant_dob", "label": "Participant date of birth", "required": True},
            {"field": "date_signed", "label": "Date of signing", "required": True},
            {"field": "participant_signature", "label": "Participant signature", "required": True},
            {
                "field": "investigator_signature",
                "label": "Investigator/designee signature",
                "required": True,
            },
        ],
        "warnings": [
            "CRITICAL: THIS IS A TEMPLATE ONLY — NOT A LEGALLY VALID CONSENT FORM.",
            "THIS IS NOT MEDICAL ADVICE.",
            "This template has NOT been reviewed or approved by any IRB or ethics board.",
            "This template MUST be reviewed by qualified legal and medical counsel before any use.",
            "IRB approval is mandatory before use in any human research context.",
            "Jurisdiction-specific requirements may require additional fields, language, or processes.",
            "No dosing, injection, formulation, or manufacturing guidance is included.",
            "FoldAgent cannot produce approved consent forms — this is a coordination scaffold only.",
        ],
        "case_id": case_id,
        "candidate_count": candidate_count,
        "irb_required": True,
        "legal_review_required": True,
    }
