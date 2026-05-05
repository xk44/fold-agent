from backend.app.safety.preflight import PreflightResult, check_text_for_unsafe_patterns, preflight_action


def test_unsafe_text_is_blocked() -> None:
    result = preflight_action(
        action="generate_report",
        species_mode="demo",
        content="Here is a dosing schedule and injection instruction.",
        is_export=True,
    )

    assert result.status == PreflightResult.BLOCK
    assert result.blocked


def test_external_upload_requires_approval() -> None:
    result = preflight_action(
        action="submit_alphafold_job",
        species_mode="demo",
        involves_external_upload=True,
    )

    assert result.status == PreflightResult.REQUIRES_APPROVAL
    assert result.needs_approval


def test_safe_text_passes() -> None:
    is_safe, matches = check_text_for_unsafe_patterns("Candidate review summary for expert research discussion.")

    assert is_safe is True
    assert matches == []
