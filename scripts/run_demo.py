"""FoldAgent Demo Pipeline Runner (Phase 21)

Exercises the full demo pipeline end-to-end via the REST API:
  1. Create a demo case
  2. Check data completeness
  3. Run pipeline dry-run
  4. Check evidence level
  5. Generate report (HTML + Markdown)
  6. Check safety (FP risk, source citations)
  7. Scan for hallucinated content
  8. Print summary

Usage::

    python scripts/run_demo.py --api-base http://localhost:8000

Requirements: httpx or requests (httpx preferred).
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from typing import Any

try:
    import httpx as _http_lib
    _USE_HTTPX = True
except ImportError:
    try:
        import requests as _http_lib  # type: ignore[no-redef]
        _USE_HTTPX = False
    except ImportError:
        print("[ERROR] Neither httpx nor requests is installed. Run: pip install httpx")
        sys.exit(1)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get(base: str, path: str, params: dict | None = None) -> tuple[int, Any]:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if _USE_HTTPX:
        resp = _http_lib.get(url, params=params, timeout=30)
    else:
        resp = _http_lib.get(url, params=params, timeout=30)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body


def _post(base: str, path: str, json_body: dict | None = None, params: dict | None = None) -> tuple[int, Any]:
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if _USE_HTTPX:
        resp = _http_lib.post(url, json=json_body or {}, params=params, timeout=30)
    else:
        resp = _http_lib.post(url, json=json_body or {}, params=params, timeout=30)
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    return resp.status_code, body


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


def step(n: int, label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Step {n}: {label}")
    print(f"{'='*60}")


def ok(msg: str) -> None:
    print(f"  [OK]  {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def err(msg: str) -> None:
    print(f"  [ERR] {msg}")


def info(msg: str) -> None:
    print(f"        {msg}")


# ---------------------------------------------------------------------------
# Main demo runner
# ---------------------------------------------------------------------------


def run_demo(api_base: str) -> int:
    """Run the full demo pipeline. Returns 0 on success, 1 on fatal error."""
    print(f"\nFoldAgent Demo Pipeline Runner")
    print(f"API base: {api_base}")
    print(f"{'='*60}")

    errors: list[str] = []

    # --- Step 0: health check ---
    step(0, "Health check")
    status, body = _get(api_base, "/health")
    if status == 200:
        ok(f"API reachable — status={body.get('status', 'ok') if isinstance(body, dict) else 'ok'}")
    else:
        err(f"Health check failed: {status} {body}")
        print("\n[FATAL] Cannot reach API. Is the server running?")
        return 1

    # --- Step 1: demo mode status ---
    step(1, "Demo mode status")
    status, body = _get(api_base, "/demo/status")
    if status == 200:
        demo_enabled = body.get("demo_mode", False)
        ok(f"demo_mode={demo_enabled}")
        if not demo_enabled:
            warn("FOLDAGENT_DEMO_MODE is not set — demo data will still be created but flag is off")
    else:
        warn(f"Could not check demo status: {status}")

    # --- Step 2: create demo case ---
    step(2, "Create demo case")
    status, body = _post(api_base, "/demo/create-case")
    if status not in (200, 201):
        err(f"Failed to create demo case: {status} {body}")
        errors.append("demo_create_case failed")
        return 1

    case_id = body["case_id"]
    ok(f"case_id={case_id}")
    info(f"subject={body.get('subject_display_name')}, species={body.get('species')}")
    info(f"samples={body.get('sample_count')}, variants={body.get('variant_count')}, candidates={body.get('candidate_count')}")
    info(f"structure_job_id={body.get('structure_job_id')}")
    info(f"report_id={body.get('report_id')}")

    # --- Step 3: data completeness ---
    step(3, "Check data completeness")
    status, body = _get(api_base, f"/cases/{case_id}/missing-data")
    if status == 200:
        missing = body.get("missing_fields", [])
        if missing:
            warn(f"Missing fields: {', '.join(missing)}")
        else:
            ok("No missing data fields")
        info(f"checklist items: {len(body.get('checklist', []))}")
    else:
        warn(f"Could not check completeness: {status}")

    # --- Step 4: pipeline dry-run ---
    step(4, "Pipeline dry-run")
    status, body = _post(api_base, f"/cases/{case_id}/pipeline/run")
    if status in (200, 201):
        ok(f"Pipeline run submitted — status={body.get('status', 'unknown')}")
        info(f"pipeline_run_id={body.get('id')}")
    else:
        warn(f"Pipeline run returned: {status} — {body}")

    # --- Step 5: evidence level ---
    step(5, "Evidence level assessment")
    status, body = _get(api_base, f"/cases/{case_id}/evidence")
    if status == 200:
        level = body.get("level", "unknown")
        flags = body.get("flags", [])
        ok(f"Evidence level: {level}")
        for flag in flags[:5]:
            info(f"flag: {flag}")
    else:
        warn(f"Could not assess evidence level: {status}")

    # --- Step 6: generate HTML report ---
    step(6, "Generate HTML report")
    status, body = _get(api_base, f"/cases/{case_id}/report/html")
    if status == 200:
        content = body if isinstance(body, str) else str(body)
        ok(f"HTML report generated ({len(content)} chars)")
    else:
        warn(f"HTML report returned: {status}")

    # --- Step 6b: Markdown report ---
    status, body = _get(api_base, f"/cases/{case_id}/report/markdown")
    if status == 200:
        md = body.get("content", "")
        ok(f"Markdown report generated ({len(md)} chars)")
    else:
        warn(f"Markdown report returned: {status}")

    # --- Step 7: false-positive risk ---
    step(7, "Safety checks")
    status, body = _get(api_base, f"/cases/{case_id}/false-positive-risk")
    if status == 200:
        risk = body.get("risk", "unknown")
        ok(f"False-positive risk level: {risk}")
        fp_flags = body.get("flags", [])
        for flag in fp_flags[:3]:
            info(f"fp-flag: {flag}")
    else:
        warn(f"FP risk check returned: {status}")

    # --- Step 7b: citations ---
    status, body = _get(api_base, f"/cases/{case_id}/report/citations")
    if status == 200:
        citations = body.get("citations", [])
        ok(f"Citations: {len(citations)} found")
    else:
        warn(f"Citations check returned: {status}")

    # --- Step 7c: source validation ---
    sample_text = (
        "Variants were called using Mutect2 and annotated with Ensembl VEP. "
        "Binding predictions used NetMHCpan 4.1. Structure prediction via AlphaFold2. "
        "Expression quantified using Salmon against GENCODE v44. "
        "Additional annotations from NeoDB (unverified)."
    )
    status, body = _post(api_base, "/validate/sources", json_body={"text": sample_text})
    if status == 200:
        unknown_count = body.get("unknown_count", 0)
        total = body.get("total", 0)
        ok(f"Source validation: {total - unknown_count}/{total} known sources")
        for r in body.get("results", []):
            if not r["known"]:
                warn(f"  Unknown citation: '{r['citation']}' (closest: {r.get('closest_match')})")
    else:
        warn(f"Source validation returned: {status}")

    # --- Step 7d: hallucination scan ---
    status, body = _post(api_base, "/validate/hallucination-scan", json_body={"text": sample_text})
    if status == 200:
        count = body.get("count", 0)
        high = body.get("high_severity_count", 0)
        clean = body.get("clean", True)
        if clean:
            ok("Hallucination scan: clean")
        else:
            warn(f"Hallucination scan: {count} findings, {high} high-severity")
            for f in body.get("findings", [])[:3]:
                info(f"  [{f['severity']}] {f['pattern']}: '{f['matched']}'")
    else:
        warn(f"Hallucination scan returned: {status}")

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"  DEMO PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  case_id : {case_id}")
    if errors:
        print(f"  errors  : {len(errors)}")
        for e in errors:
            print(f"    - {e}")
        return 1
    else:
        print(f"  status  : OK — all steps passed")
        print(f"\n  DISCLAIMER: All data is synthetic. Not for clinical use.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            FoldAgent Demo Pipeline Runner.
            Exercises the full pipeline end-to-end via the REST API.
            All data created is synthetic — NOT FOR CLINICAL USE.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
        help="Base URL of the FoldAgent API (default: http://localhost:8000)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.exit(run_demo(args.api_base))


if __name__ == "__main__":
    main()
