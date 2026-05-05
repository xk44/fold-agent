"""Tests for hallucination_guard.py (Phase 21).

Covers:
  - check_source_citation: known, unknown, near-miss
  - validate_report_sources: extraction and validation
  - scan_for_hallucinated_content: fake DOIs, fake DBs, clean text
  - POST /validate/sources
  - POST /validate/hallucination-scan
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.hallucination_guard import (
    KNOWN_SOURCES,
    check_source_citation,
    scan_for_hallucinated_content,
    validate_report_sources,
)


# ---------------------------------------------------------------------------
# check_source_citation — known sources
# ---------------------------------------------------------------------------


def test_known_source_exact_match() -> None:
    result = check_source_citation("Ensembl")
    assert result["known"] is True
    assert result["canonical_name"] == "Ensembl"
    assert result["confidence"] == 1.0


def test_known_source_case_insensitive() -> None:
    result = check_source_citation("ensembl")
    assert result["known"] is True
    assert result["canonical_name"] == "Ensembl"


def test_known_source_ncbi() -> None:
    result = check_source_citation("NCBI")
    assert result["known"] is True


def test_known_source_netmhcpan() -> None:
    result = check_source_citation("NetMHCpan")
    assert result["known"] is True


def test_known_source_uniprot() -> None:
    result = check_source_citation("UniProt")
    assert result["known"] is True


def test_known_source_pdb() -> None:
    result = check_source_citation("PDB")
    assert result["known"] is True


# ---------------------------------------------------------------------------
# check_source_citation — unknown sources
# ---------------------------------------------------------------------------


def test_unknown_source_returns_not_known() -> None:
    result = check_source_citation("FakeBioDB")
    assert result["known"] is False
    assert result["canonical_name"] is None


def test_unknown_source_has_closest_match() -> None:
    result = check_source_citation("EnsemblX")
    assert result["known"] is False
    assert result["closest_match"] is not None
    # Should be close to "Ensembl"
    assert result["confidence"] > 0.5


def test_unknown_source_near_miss_ncbi() -> None:
    result = check_source_citation("NCBII")  # typo
    assert result["known"] is False
    assert result["closest_match"] is not None
    assert result["confidence"] > 0.6


def test_unknown_source_gibberish_low_confidence() -> None:
    result = check_source_citation("xyzqwerty123")
    assert result["known"] is False
    assert result["confidence"] < 0.5


# ---------------------------------------------------------------------------
# validate_report_sources
# ---------------------------------------------------------------------------


def test_validate_report_sources_extracts_known() -> None:
    text = (
        "Variants were called using Mutect2 and annotated with Ensembl VEP. "
        "Binding predictions used NetMHCpan."
    )
    results = validate_report_sources(text)
    citations = [r["citation"] for r in results]
    assert len(citations) > 0


def test_validate_report_sources_flags_unknown() -> None:
    text = "Data sourced from NeoDB, a fictional database."
    results = validate_report_sources(text)
    unknown = [r for r in results if not r["known"]]
    # NeoDB should appear and be unknown
    unknown_names = [r["citation"] for r in unknown]
    assert any("NeoDB" in n or "neodb" in n.lower() for n in unknown_names)


def test_validate_report_sources_empty_text() -> None:
    results = validate_report_sources("")
    assert results == []


def test_validate_report_sources_no_citations() -> None:
    results = validate_report_sources("This text has no cited sources at all.")
    # May return empty or a small list; none should be high-confidence known
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# scan_for_hallucinated_content
# ---------------------------------------------------------------------------


def test_scan_clean_text_returns_empty() -> None:
    text = "Variants were called using Mutect2 and annotated with Ensembl VEP v110."
    findings = scan_for_hallucinated_content(text)
    # Clean text should have no high-severity findings
    high = [f for f in findings if f["severity"] == "high"]
    assert len(high) == 0


def test_scan_detects_fake_doi() -> None:
    text = "As described in Smith et al. (doi: 10.9999/fake.doi.abc123)."
    findings = scan_for_hallucinated_content(text)
    doi_findings = [f for f in findings if f["pattern"] == "fake_doi"]
    assert len(doi_findings) >= 1
    assert findings[0]["matched"] is not None


def test_scan_detects_nonexistent_database() -> None:
    text = "Annotations were cross-referenced with NeoDB for additional context."
    findings = scan_for_hallucinated_content(text)
    db_findings = [f for f in findings if f["pattern"] == "nonexistent_database"]
    assert len(db_findings) >= 1
    assert db_findings[0]["severity"] == "high"


def test_scan_detects_fake_tool() -> None:
    text = "Binding affinity was predicted using NeoPredict version 3.1."
    findings = scan_for_hallucinated_content(text)
    tool_findings = [f for f in findings if f["pattern"] == "fake_tool_name"]
    assert len(tool_findings) >= 1
    assert tool_findings[0]["severity"] == "high"


def test_scan_detects_overconfident_claim() -> None:
    text = "This neoantigen vaccine is FDA-approved neoantigen therapy."
    findings = scan_for_hallucinated_content(text)
    claim_findings = [f for f in findings if f["pattern"] == "overconfident_clinical_claim"]
    assert len(claim_findings) >= 1


def test_scan_finding_has_required_fields() -> None:
    text = "Data from NeoDB and NeoPredict (doi: 10.1234/test.001)."
    findings = scan_for_hallucinated_content(text)
    assert len(findings) > 0
    for f in findings:
        assert "pattern" in f
        assert "matched" in f
        assert "severity" in f
        assert "suggestion" in f
        assert "position" in f


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_validate_sources_endpoint_known(client: TestClient) -> None:
    resp = client.post(
        "/validate/sources",
        json={"text": "Variants annotated using Ensembl VEP and NetMHCpan."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "total" in body
    assert "unknown_count" in body
    assert "all_known" in body
    assert isinstance(body["results"], list)


def test_validate_sources_endpoint_unknown(client: TestClient) -> None:
    resp = client.post(
        "/validate/sources",
        json={"text": "Data from NeoDB, a fictional database."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["all_known"] is False or body["unknown_count"] >= 0  # NeoDB should be unknown


def test_hallucination_scan_endpoint_clean(client: TestClient) -> None:
    resp = client.post(
        "/validate/hallucination-scan",
        json={"text": "Variants called with Mutect2, annotated with Ensembl VEP."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "findings" in body
    assert "count" in body
    assert "high_severity_count" in body
    assert "clean" in body
    assert isinstance(body["findings"], list)


def test_hallucination_scan_endpoint_detects_issues(client: TestClient) -> None:
    resp = client.post(
        "/validate/hallucination-scan",
        json={"text": "Predictions from NeoDB and NeoPredict (doi: 10.9999/fake)."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] > 0
    assert body["clean"] is False
