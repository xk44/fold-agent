"""FoldAgent Hallucination Guard (Phase 21)

Detects potentially hallucinated content in AI-generated reports:
- Unknown or near-miss source citations
- Fake DOIs, non-existent databases, made-up tool names
- Common hallucination patterns in biomedical text

Research safety utility — not a guarantee of accuracy.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

# ---------------------------------------------------------------------------
# Known legitimate sources
# ---------------------------------------------------------------------------

KNOWN_SOURCES: set[str] = {
    # Genome/gene databases
    "Ensembl",
    "NCBI",
    "NCBI GenBank",
    "NCBI RefSeq",
    "UniProt",
    "UniProtKB",
    "PDB",
    "RCSB PDB",
    # Variant databases
    "ClinVar",
    "dbSNP",
    "gnomAD",
    "ExAC",
    "COSMIC",
    "TCGA",
    "cBioPortal",
    "OncoKB",
    # Annotation tools
    "Ensembl VEP",
    "ANNOVAR",
    "SnpEff",
    "CADD",
    "SIFT",
    "PolyPhen-2",
    "PolyPhen2",
    # MHC/immunology
    "NetMHCpan",
    "NetMHC",
    "MHCflurry",
    "IEDB",
    "IMGT",
    "IPD-IMGT/HLA",
    # Variant callers
    "GATK",
    "Mutect2",
    "MuTect2",
    "Strelka2",
    "VarScan2",
    "FreeBayes",
    # Structural biology
    "AlphaFold",
    "AlphaFold2",
    "AlphaFold3",
    "ColabFold",
    "RoseTTAFold",
    "PyMOL",
    "UCSF ChimeraX",
    # RNA-seq
    "STAR",
    "HISAT2",
    "DESeq2",
    "EdgeR",
    "Salmon",
    "kallisto",
    # pVAC / neoantigen
    "pVACtools",
    "pVACseq",
    "pVACbind",
    "Neoantigen Vaccine Center",
    # Alignment
    "BWA",
    "BWA-MEM",
    "Bowtie2",
    # Ontologies/standards
    "HGNC",
    "GO",
    "Gene Ontology",
    "OMIM",
    "HPO",
    "Human Phenotype Ontology",
    # Literature
    "PubMed",
    "PubMed Central",
    "PMC",
    "bioRxiv",
    "medRxiv",
    "Nature",
    "Science",
    "Cell",
    "NEJM",
    "New England Journal of Medicine",
    # Canine-specific
    "Vet-COSMIC",
    "Canine Cancer Genome Atlas",
    "CCGA",
}

# Lowercase lookup for matching
_KNOWN_SOURCES_LOWER: dict[str, str] = {s.lower(): s for s in KNOWN_SOURCES}


# ---------------------------------------------------------------------------
# Hallucination patterns
# ---------------------------------------------------------------------------

HALLUCINATION_PATTERNS: list[dict] = [
    {
        "name": "fake_doi",
        "pattern": r"\b10\.\d{4,}/[a-zA-Z0-9._/-]{3,}\b",
        "description": "DOI-format string — verify it resolves at doi.org",
        "severity": "medium",
        "suggestion": "Verify this DOI resolves at https://doi.org/ before citing.",
    },
    {
        "name": "nonexistent_database",
        "pattern": (
            r"\b(?:NeoDB|NeoBase|VaccinDB|NeoAntigenDB|PeptideAtlas2|"
            r"CancerNeoAg|ImmunoDB|HLAdb Pro|MHCdb Plus|VaccineDB|"
            r"TumorNeoantigenDB|FoldAgentDB|OpenNeoAg)\b"
        ),
        "description": "Known non-existent or unverified database name",
        "severity": "high",
        "suggestion": "This database name is not recognized. Use IEDB, IMGT, or NCBI instead.",
    },
    {
        "name": "fake_tool_name",
        "pattern": (
            r"\b(?:NeoPredict|AlphaVax|VaccineForge|PeptideAI|NeoCalc|"
            r"ImmunoPredict|BindingOracle|HLAPredict Pro|VaxDesigner|"
            r"NeoOptimizer|MHCAssign|PeptideMatcher Pro)\b"
        ),
        "description": "Unrecognized tool name that may be hallucinated",
        "severity": "high",
        "suggestion": "This tool is not in the known-tools registry. Use pVACtools, NetMHCpan, or MHCflurry.",
    },
    {
        "name": "overconfident_clinical_claim",
        "pattern": (
            r"\b(?:proven(?:\s+to)?\s+(?:cure|treat|eliminate|eradicate)|"
            r"clinically\s+(?:proven|validated|approved)\s+(?:neoantigen|peptide|vaccine)|"
            r"FDA[- ]approved\s+neoantigen|EMA[- ]approved\s+neoantigen)\b"
        ),
        "description": "Overconfident or false clinical approval claim",
        "severity": "high",
        "suggestion": "Neoantigen vaccines are investigational. Remove clinical approval language.",
    },
    {
        "name": "suspiciously_round_pvalue",
        "pattern": r"\bp[- ]?value\s*[=<>]\s*0\.0+\b",
        "description": "Suspiciously round or zero p-value",
        "severity": "low",
        "suggestion": "Verify this p-value — exact zero p-values are statistically unusual.",
    },
    {
        "name": "undefined_acronym",
        "pattern": r"\b[A-Z]{4,7}\b(?!\s*\()",
        "description": "Undefined multi-letter acronym",
        "severity": "low",
        "suggestion": "Expand or define this acronym on first use.",
    },
]

# Pre-compile patterns
_COMPILED_PATTERNS: list[tuple[dict, re.Pattern]] = [
    (p, re.compile(p["pattern"], re.IGNORECASE))
    for p in HALLUCINATION_PATTERNS
]

# Pattern to extract cited source names from report text
_CITATION_PATTERN = re.compile(
    r"(?:using|via|from|with|by|source[d]?\s+from|cited\s+from|"
    r"database[d]?|tool|software|platform|pipeline)\s+([A-Z][A-Za-z0-9/_\-\.]{1,40})",
    re.IGNORECASE,
)
# Also match parenthetical citations like (Ensembl VEP, 2023) or [IEDB]
_PAREN_CITATION = re.compile(r"\(([A-Z][A-Za-z0-9 /_\-\.]{2,40}?)(?:,\s*\d{4})?\)", re.IGNORECASE)
_BRACKET_CITATION = re.compile(r"\[([A-Z][A-Za-z0-9 /_\-\.]{2,40}?)\]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------


def check_source_citation(citation: str) -> dict:
    """Check whether a cited source is in the known-sources registry.

    Returns::

        {
            "citation": str,
            "known": bool,
            "canonical_name": str | None,  # exact match name from KNOWN_SOURCES
            "closest_match": str | None,   # best near-miss if not known
            "confidence": float,           # similarity score 0.0–1.0
        }
    """
    key = citation.strip().lower()
    if key in _KNOWN_SOURCES_LOWER:
        canonical = _KNOWN_SOURCES_LOWER[key]
        return {
            "citation": citation,
            "known": True,
            "canonical_name": canonical,
            "closest_match": canonical,
            "confidence": 1.0,
        }

    # Near-miss: find closest known source
    best_match: Optional[str] = None
    best_score: float = 0.0
    for known_lower, canonical in _KNOWN_SOURCES_LOWER.items():
        score = SequenceMatcher(None, key, known_lower).ratio()
        if score > best_score:
            best_score = score
            best_match = canonical

    return {
        "citation": citation,
        "known": False,
        "canonical_name": None,
        "closest_match": best_match,
        "confidence": round(best_score, 4),
    }


def validate_report_sources(report_text: str) -> list[dict]:
    """Extract all cited source names from report_text and validate each.

    Returns a list of validation results (one per unique extracted citation).
    """
    candidates: set[str] = set()

    for m in _CITATION_PATTERN.finditer(report_text):
        token = m.group(1).strip().rstrip(".,;:")
        if len(token) >= 2:
            candidates.add(token)

    for m in _PAREN_CITATION.finditer(report_text):
        token = m.group(1).strip()
        if len(token) >= 2:
            candidates.add(token)

    for m in _BRACKET_CITATION.finditer(report_text):
        token = m.group(1).strip()
        if len(token) >= 2:
            candidates.add(token)

    results = []
    for citation in sorted(candidates):
        result = check_source_citation(citation)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Hallucinated content scanning
# ---------------------------------------------------------------------------


def scan_for_hallucinated_content(text: str) -> list[dict]:
    """Scan text for patterns that commonly indicate hallucinated content.

    Returns a list of findings::

        [
            {
                "pattern": str,       # pattern name
                "matched": str,       # the matched text
                "severity": str,      # low / medium / high
                "suggestion": str,
                "position": int,      # character offset of match
            },
            ...
        ]
    """
    findings: list[dict] = []
    for meta, compiled in _COMPILED_PATTERNS:
        for match in compiled.finditer(text):
            findings.append(
                {
                    "pattern": meta["name"],
                    "description": meta["description"],
                    "matched": match.group(0),
                    "severity": meta["severity"],
                    "suggestion": meta["suggestion"],
                    "position": match.start(),
                }
            )
    return findings
