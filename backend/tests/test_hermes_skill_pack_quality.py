from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERMES_DIR = PROJECT_ROOT / "skills" / "hermes"


def _skill_paths():
    return sorted(path for path in HERMES_DIR.glob("*/SKILL.md"))


def test_all_hermes_skills_have_steps_and_guardrails() -> None:
    paths = _skill_paths()
    assert len(paths) == 9
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "## Steps" in text, f"{path} missing Steps section"
        assert "## Hermes Self-Improvement Guardrails" in text, f"{path} missing guardrails section"
        assert "## Audit Log Integration Notes" in text, f"{path} missing audit notes section"
        assert "Do not self-improve" in text, f"{path} missing self-improvement guardrail text"


def test_all_hermes_skills_have_rich_endpoint_and_artifact_sections() -> None:
    for path in _skill_paths():
        text = path.read_text(encoding="utf-8")
        assert "## Required NeoVax API Endpoints" in text
        assert " — " in text, f"{path} endpoints should include purpose annotations"
        assert "## Expected Output Artifact" in text
        assert text.count("- ") >= 8, f"{path} should have multiple bullet details after enrichment"
