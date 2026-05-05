from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"
PACKS = ("hermes", "openclaw", "claude-code")
REQUIRED_SECTIONS = (
    "## When to Use",
    "## When NOT to Use",
    "## Safety Boundaries",
    "## Required NeoVax API Endpoints",
    "## Required User Confirmation Points",
    "## Expected Output Artifact",
    "## Steps",
    "## Logging Requirements",
    "## Failure Handling",
    "## No Medical Advice Warning",
    "## Audit Log Integration Notes",
)
PACK_GUARDRAIL_SECTIONS = {
    "hermes": "## Hermes Self-Improvement Guardrails",
    "openclaw": "## OpenClaw Self-Improvement Guardrails",
    "claude-code": "## Claude Code Self-Improvement Guardrails",
}
PACK_CONTEXT_SECTIONS = {
    "hermes": "## Hermes Memory Seed Template",
    "openclaw": "## OpenClaw Memory Seed Template",
    "claude-code": "## Claude Code Context Seed Template",
}
ENDPOINT_RE = re.compile(r"`((?:GET|POST|PUT|PATCH|DELETE) [^`]+)`")


def _pack_dir(pack: str) -> Path:
    return SKILLS_DIR / pack


def _skill_names(pack: str) -> set[str]:
    return {path.parent.name for path in _pack_dir(pack).glob("*/SKILL.md")}


def _skill_paths(pack: str) -> list[Path]:
    return sorted(_pack_dir(pack).glob("*/SKILL.md"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _endpoints(text: str) -> set[str]:
    return set(ENDPOINT_RE.findall(text))


def test_skill_sets_match_across_all_packs() -> None:
    baseline = _skill_names("hermes")
    assert len(baseline) == 9
    for pack in PACKS[1:]:
        assert _skill_names(pack) == baseline


def test_every_skill_has_required_sections_and_pack_specific_guardrails() -> None:
    for pack in PACKS:
        for path in _skill_paths(pack):
            text = _read(path)
            for section in REQUIRED_SECTIONS:
                assert section in text, f"{path} missing {section}"
            assert PACK_GUARDRAIL_SECTIONS[pack] in text, f"{path} missing pack guardrails"
            assert PACK_CONTEXT_SECTIONS[pack] in text, f"{path} missing pack context section"
            assert "Do not self-improve" in text, f"{path} missing self-improvement guardrail text"


def test_every_skill_has_enrichment_depth() -> None:
    for pack in PACKS:
        for path in _skill_paths(pack):
            text = _read(path)
            assert len(text.splitlines()) >= 100, f"{path} too short after enrichment"
            assert text.count("- ") >= 8, f"{path} should have rich bullet detail"
            assert text.count(" — ") >= 5, f"{path} endpoints should include purpose annotations"
            assert "See also: `skills/shared/safety_policy.md`" in text, f"{path} missing safety policy cross-reference"


def test_cross_pack_endpoint_parity_against_hermes() -> None:
    for hermes_path in _skill_paths("hermes"):
        skill_name = hermes_path.parent.name
        hermes_endpoints = _endpoints(_read(hermes_path))
        assert hermes_endpoints, f"{hermes_path} should list endpoints"
        for pack in ("openclaw", "claude-code"):
            other_path = _pack_dir(pack) / skill_name / "SKILL.md"
            other_endpoints = _endpoints(_read(other_path))
            assert other_endpoints == hermes_endpoints, (
                f"{other_path} endpoint drift vs hermes for {skill_name}: "
                f"missing={sorted(hermes_endpoints - other_endpoints)} extra={sorted(other_endpoints - hermes_endpoints)}"
            )


def test_pack_frontmatter_contains_required_framework_metadata() -> None:
    for path in _skill_paths("hermes"):
        text = _read(path)
        assert "framework: Hermes" in text
        assert "memory_seed_template: default" in text
        assert "audit_log_integration: required" in text
        assert "version: 0.2.0" in text
    for path in _skill_paths("openclaw"):
        text = _read(path)
        assert "framework: OpenClaw" in text
        assert "install_path: ~/.openclaw/skills/<skill_name>" in text
        assert "memory_seed_template: default" in text
        assert "audit_log_integration: required" in text
        assert "version: 0.2.0" in text
    for path in _skill_paths("claude-code"):
        text = _read(path)
        assert "framework: Claude Code" in text
        assert "memory_seed_template: default" in text
        assert "audit_log_integration: required" in text
        assert "version: 0.2.0" in text
