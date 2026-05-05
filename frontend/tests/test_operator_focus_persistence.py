"""Tests for persistent operator focus — extract_restorable_focus and
apply_restored_focus (pure functions, no Streamlit dependency) and
operator_focus_store (file I/O).

Covers:
- extract_restorable_focus: empty state, static keys, dynamic prefixed keys,
  FILTER_ALL suppression, None/empty suppression, mixed values
- apply_restored_focus: empty saved focus, non-destructive merge (doesn't
  overwrite active selections), applies into empty slots, dynamic key
  expansion, idempotent application
- operator_focus_store: save then load roundtrip, missing file returns {},
  corrupt JSON returns {}, wrong version returns {}, atomic write
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    FILTER_ALL,
    _CTX_EVENT_KEY,
    _CTX_JOB_KEY,
    _CTX_PIPELINE_CASE_KEY,
    _CTX_INSPECT_CASE_KEY,
    _CTX_FILTER_STATUS_KEY,
    _CTX_FILTER_JOB_TYPE_KEY,
    _CTX_FILTER_CASE_ID_KEY,
    _CTX_REPORT_KEY_PREFIX,
    _CTX_STRUCTURE_JOB_KEY_PREFIX,
    _RESTORABLE_FOCUS_KEYS,
    _RESTORABLE_FOCUS_PREFIXES,
    extract_restorable_focus,
    apply_restored_focus,
)
from frontend.app.operator_focus_store import (
    load_operator_focus,
    save_operator_focus,
    default_focus_path,
)


# ---------------------------------------------------------------------------
# extract_restorable_focus
# ---------------------------------------------------------------------------

class TestExtractRestorableFocusEmpty:
    """Empty session state produces an empty focus dict."""

    def test_empty_dict(self):
        result = extract_restorable_focus({})
        assert result == {}

    def test_all_none_values(self):
        state = {key: None for key in _RESTORABLE_FOCUS_KEYS}
        result = extract_restorable_focus(state)
        assert result == {}

    def test_all_empty_strings(self):
        state = {key: "" for key in _RESTORABLE_FOCUS_KEYS}
        result = extract_restorable_focus(state)
        assert result == {}

    def test_all_filter_all(self):
        state = {key: FILTER_ALL for key in _RESTORABLE_FOCUS_KEYS}
        result = extract_restorable_focus(state)
        assert result == {}


class TestExtractRestorableFocusStaticKeys:
    """Static focus keys are extracted correctly."""

    def test_single_event_key(self):
        state = {_CTX_EVENT_KEY: "case.created @ 2025-04-20"}
        result = extract_restorable_focus(state)
        assert result[_CTX_EVENT_KEY] == "case.created @ 2025-04-20"

    def test_multiple_static_keys(self):
        state = {
            _CTX_EVENT_KEY: "pipeline.completed",
            _CTX_JOB_KEY: "pipeline_run — running (abc12345)",
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_INSPECT_CASE_KEY: "case-beta",
            _CTX_FILTER_STATUS_KEY: "running",
            _CTX_FILTER_JOB_TYPE_KEY: "pipeline_run",
            _CTX_FILTER_CASE_ID_KEY: "case-42",
        }
        result = extract_restorable_focus(state)
        assert len(result) == 7
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert result[_CTX_FILTER_STATUS_KEY] == "running"

    def test_pipeline_case_takes_precedence(self):
        """Both pipeline and inspect case are saved; both are static keys."""
        state = {
            _CTX_PIPELINE_CASE_KEY: "case-alpha",
            _CTX_INSPECT_CASE_KEY: "case-beta",
        }
        result = extract_restorable_focus(state)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-alpha"
        assert result[_CTX_INSPECT_CASE_KEY] == "case-beta"

    def test_non_restorable_keys_ignored(self):
        """Keys not in _RESTORABLE_FOCUS_KEYS are not extracted."""
        state = {
            "ar_enabled": True,
            "live_feed_job_cards": [{"job_id": "x"}],
            _CTX_PIPELINE_CASE_KEY: "case-42",
        }
        result = extract_restorable_focus(state)
        assert "ar_enabled" not in result
        assert "live_feed_job_cards" not in result
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"


class TestExtractRestorableFocusFilterAllSuppression:
    """FILTER_ALL and empty values are suppressed."""

    def test_filter_all_not_captured(self):
        state = {_CTX_FILTER_STATUS_KEY: FILTER_ALL}
        result = extract_restorable_focus(state)
        assert _CTX_FILTER_STATUS_KEY not in result

    def test_empty_string_not_captured(self):
        state = {_CTX_PIPELINE_CASE_KEY: ""}
        result = extract_restorable_focus(state)
        assert _CTX_PIPELINE_CASE_KEY not in result

    def test_mixed_filter_all_and_real(self):
        state = {
            _CTX_FILTER_STATUS_KEY: FILTER_ALL,
            _CTX_FILTER_JOB_TYPE_KEY: "pipeline_run",
        }
        result = extract_restorable_focus(state)
        assert _CTX_FILTER_STATUS_KEY not in result
        assert result[_CTX_FILTER_JOB_TYPE_KEY] == "pipeline_run"


class TestExtractRestorableFocusDynamicPrefixes:
    """Dynamic prefixed keys (report-detail-*, structure-job-*) are captured."""

    def test_report_detail_key_captured(self):
        state = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-99ab",
        }
        result = extract_restorable_focus(state)
        assert "report_detail_keys" in result
        assert result["report_detail_keys"]["case-42"] == "rep-99ab"

    def test_structure_job_key_captured(self):
        state = {
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42": "sj-42b1",
        }
        result = extract_restorable_focus(state)
        assert "structure_job_keys" in result
        assert result["structure_job_keys"]["case-42"] == "sj-42b1"

    def test_dynamic_prefix_empty_value_skipped(self):
        state = {
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "",
        }
        result = extract_restorable_focus(state)
        # Should not include the bucket at all since no truthy values
        assert "report_detail_keys" not in result

    def test_dynamic_prefix_filter_all_skipped(self):
        state = {
            f"{_CTX_REPORT_KEY_PREFIX}case-42": FILTER_ALL,
        }
        result = extract_restorable_focus(state)
        assert "report_detail_keys" not in result

    def test_multiple_dynamic_keys(self):
        state = {
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-a",
            f"{_CTX_REPORT_KEY_PREFIX}case-99": "rep-b",
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42": "sj-x",
        }
        result = extract_restorable_focus(state)
        assert result["report_detail_keys"]["case-42"] == "rep-a"
        assert result["report_detail_keys"]["case-99"] == "rep-b"
        assert result["structure_job_keys"]["case-42"] == "sj-x"

    def test_non_matching_prefix_ignored(self):
        state = {
            "some-random-prefix-case-42": "value",
        }
        result = extract_restorable_focus(state)
        assert "report_detail_keys" not in result
        assert "structure_job_keys" not in result
        # The key itself should not appear as a static key
        assert "some-random-prefix-case-42" not in result

    def test_values_are_strings(self):
        """All values in the focus dict are strings (JSON-serialisable)."""
        state = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
        }
        result = extract_restorable_focus(state)
        for key, val in result.items():
            if isinstance(val, dict):
                for k2, v2 in val.items():
                    assert isinstance(v2, str)
            else:
                assert isinstance(val, str)


class TestExtractRestorableFocusCombined:
    """Combination of static and dynamic keys."""

    def test_full_focus_extraction(self):
        state = {
            _CTX_EVENT_KEY: "pipeline.completed",
            _CTX_JOB_KEY: "pipeline_run — running (abc12345)",
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-99ab",
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42": "sj-42b1",
            # Should be ignored:
            "ar_enabled": True,
            _CTX_FILTER_JOB_TYPE_KEY: FILTER_ALL,
            f"{_CTX_REPORT_KEY_PREFIX}case-empty": "",
        }
        result = extract_restorable_focus(state)
        assert result[_CTX_EVENT_KEY] == "pipeline.completed"
        assert result[_CTX_JOB_KEY] == "pipeline_run — running (abc12345)"
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert result[_CTX_FILTER_STATUS_KEY] == "running"
        assert _CTX_FILTER_JOB_TYPE_KEY not in result
        assert "ar_enabled" not in result
        assert result["report_detail_keys"]["case-42"] == "rep-99ab"
        assert "case-empty" not in result.get("report_detail_keys", {})
        assert result["structure_job_keys"]["case-42"] == "sj-42b1"


# ---------------------------------------------------------------------------
# apply_restored_focus
# ---------------------------------------------------------------------------

class TestApplyRestoredFocusEmpty:
    """Applying empty or no focus doesn't change session state."""

    def test_empty_saved_focus(self):
        state = {_CTX_PIPELINE_CASE_KEY: "case-42"}
        result = apply_restored_focus(state, {})
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"

    def test_none_saved_focus(self):
        """Applying with empty dict returns unchanged state."""
        state = {_CTX_PIPELINE_CASE_KEY: "case-42"}
        result = apply_restored_focus(state, {})
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"


class TestApplyRestoredFocusNonDestructive:
    """Saved focus does NOT overwrite active session state."""

    def test_existing_value_preserved(self):
        """If a key already has a value in session_state, it's not overwritten."""
        state = {_CTX_PIPELINE_CASE_KEY: "case-current"}
        saved = {_CTX_PIPELINE_CASE_KEY: "case-saved"}
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-current"

    def test_filter_all_treated_as_empty(self):
        """FILTER_ALL in session_state is treated as empty and IS overwritten."""
        state = {_CTX_FILTER_STATUS_KEY: FILTER_ALL}
        saved = {_CTX_FILTER_STATUS_KEY: "running"}
        result = apply_restored_focus(state, saved)
        assert result[_CTX_FILTER_STATUS_KEY] == "running"

    def test_empty_string_treated_as_empty(self):
        """Empty string in session_state is treated as empty and IS overwritten."""
        state = {_CTX_PIPELINE_CASE_KEY: ""}
        saved = {_CTX_PIPELINE_CASE_KEY: "case-saved"}
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-saved"

    def test_none_treated_as_empty(self):
        """None in session_state is treated as empty and IS overwritten."""
        state = {_CTX_PIPELINE_CASE_KEY: None}
        saved = {_CTX_PIPELINE_CASE_KEY: "case-saved"}
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-saved"


class TestApplyRestoredFocusIntoEmpty:
    """Applying focus into an empty/default session state works."""

    def test_apply_into_empty_state(self):
        state = {}
        saved = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
        }
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert result[_CTX_FILTER_STATUS_KEY] == "running"

    def test_apply_into_state_with_unrelated_keys(self):
        """Unrelated session keys are preserved."""
        state = {"ar_enabled": True, "live_feed_job_cards": []}
        saved = {_CTX_PIPELINE_CASE_KEY: "case-42"}
        result = apply_restored_focus(state, saved)
        assert result["ar_enabled"] is True
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"


class TestApplyRestoredFocusDynamicKeys:
    """Dynamic prefixed keys are expanded correctly."""

    def test_report_detail_expanded(self):
        state = {}
        saved = {
            "report_detail_keys": {"case-42": "rep-99ab"},
        }
        result = apply_restored_focus(state, saved)
        assert result[f"{_CTX_REPORT_KEY_PREFIX}case-42"] == "rep-99ab"

    def test_structure_job_expanded(self):
        state = {}
        saved = {
            "structure_job_keys": {"case-42": "sj-42b1"},
        }
        result = apply_restored_focus(state, saved)
        assert result[f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42"] == "sj-42b1"

    def test_dynamic_key_non_destructive(self):
        """Dynamic keys don't overwrite existing session values."""
        state = {f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-current"}
        saved = {"report_detail_keys": {"case-42": "rep-saved"}}
        result = apply_restored_focus(state, saved)
        assert result[f"{_CTX_REPORT_KEY_PREFIX}case-42"] == "rep-current"

    def test_dynamic_key_empty_value_overwritten(self):
        """Dynamic keys DO overwrite empty session values."""
        full_key = f"{_CTX_REPORT_KEY_PREFIX}case-42"
        state = {full_key: ""}
        saved = {"report_detail_keys": {"case-42": "rep-saved"}}
        result = apply_restored_focus(state, saved)
        assert result[full_key] == "rep-saved"

    def test_dynamic_key_filter_all_overwritten(self):
        """Dynamic keys DO overwrite FILTER_ALL values."""
        full_key = f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42"
        state = {full_key: FILTER_ALL}
        saved = {"structure_job_keys": {"case-42": "sj-saved"}}
        result = apply_restored_focus(state, saved)
        assert result[full_key] == "sj-saved"


class TestApplyRestoredFocusIdempotent:
    """Applying focus twice produces the same result as once."""

    def test_idempotent_apply(self):
        saved = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
            "report_detail_keys": {"case-42": "rep-99ab"},
        }
        state = {}
        result1 = apply_restored_focus(dict(state), saved)
        result2 = apply_restored_focus(dict(result1), saved)
        assert result1 == result2


class TestApplyRestoredFocusPartialSaved:
    """Saved focus with only some keys present works fine."""

    def test_only_pipeline_case(self):
        state = {}
        saved = {_CTX_PIPELINE_CASE_KEY: "case-42"}
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert _CTX_FILTER_STATUS_KEY not in result

    def test_saved_has_extra_unrecognized_keys(self):
        """Unrecognized keys in saved_focus are silently ignored."""
        state = {}
        saved = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            "unknown_key": "some_value",
        }
        result = apply_restored_focus(state, saved)
        assert result[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert "unknown_key" not in result


# ---------------------------------------------------------------------------
# Roundtrip: extract → apply
# ---------------------------------------------------------------------------

class TestExtractApplyRoundtrip:
    """extraction followed by application restores the original focus."""

    def test_roundtrip_simple(self):
        original = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
        }
        focus = extract_restorable_focus(original)
        restored = {}
        apply_restored_focus(restored, focus)
        assert restored[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert restored[_CTX_FILTER_STATUS_KEY] == "running"

    def test_roundtrip_with_dynamic_keys(self):
        original = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-99",
            f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42": "sj-1",
        }
        focus = extract_restorable_focus(original)
        restored = {}
        apply_restored_focus(restored, focus)
        assert restored[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert restored[_CTX_FILTER_STATUS_KEY] == "running"
        assert restored[f"{_CTX_REPORT_KEY_PREFIX}case-42"] == "rep-99"
        assert restored[f"{_CTX_STRUCTURE_JOB_KEY_PREFIX}case-42"] == "sj-1"

    def test_roundtrip_empty_values_not_restored(self):
        """Empty/FILTER_ALL values are not extracted, so they don't get restored."""
        original = {
            _CTX_PIPELINE_CASE_KEY: "",
            _CTX_FILTER_STATUS_KEY: FILTER_ALL,
        }
        focus = extract_restorable_focus(original)
        assert focus == {}  # Nothing extracted
        restored = {}
        apply_restored_focus(restored, focus)
        assert restored == {}  # Nothing restored


class TestExtractApplyMergeWithExisting:
    """Restored focus does not overwrite active selections."""

    def test_active_selection_preserved(self):
        saved_state = {
            _CTX_PIPELINE_CASE_KEY: "case-saved",
            _CTX_FILTER_STATUS_KEY: "running",
        }
        current_state = {
            _CTX_PIPELINE_CASE_KEY: "case-current",
        }
        focus = extract_restorable_focus(saved_state)
        apply_restored_focus(current_state, focus)
        # Active selection preserved, missing filter restored
        assert current_state[_CTX_PIPELINE_CASE_KEY] == "case-current"
        assert current_state[_CTX_FILTER_STATUS_KEY] == "running"


# ---------------------------------------------------------------------------
# operator_focus_store — file I/O tests
# ---------------------------------------------------------------------------

class TestOperatorFocusStore:
    """File-based persistence round-trip and edge cases."""

    def test_save_and_load_roundtrip(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
        }
        save_operator_focus(focus, path=focus_path)
        loaded = load_operator_focus(path=focus_path)
        assert loaded == focus

    def test_save_and_load_with_dynamic_keys(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            "report_detail_keys": {"case-42": "rep-99ab"},
            "structure_job_keys": {"case-42": "sj-1"},
        }
        save_operator_focus(focus, path=focus_path)
        loaded = load_operator_focus(path=focus_path)
        assert loaded == focus

    def test_load_missing_file_returns_empty(self, tmp_path):
        focus_path = tmp_path / "nonexistent.json"
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_load_corrupt_json_returns_empty(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus_path.write_text("NOT VALID JSON {{{", encoding="utf-8")
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_load_wrong_version_returns_empty(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus_path.write_text(
            json.dumps({"version": 99, "focus": {"some_key": "some_val"}}),
            encoding="utf-8",
        )
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_load_missing_focus_field_returns_empty(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus_path.write_text(
            json.dumps({"version": 1}),
            encoding="utf-8",
        )
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_load_non_dict_focus_returns_empty(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        focus_path.write_text(
            json.dumps({"version": 1, "focus": "not_a_dict"}),
            encoding="utf-8",
        )
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_save_empty_focus_still_writes(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        save_operator_focus({}, path=focus_path)
        assert focus_path.exists()
        loaded = load_operator_focus(path=focus_path)
        assert loaded == {}

    def test_save_overwrites_previous(self, tmp_path):
        focus_path = tmp_path / "focus.json"
        save_operator_focus({_CTX_PIPELINE_CASE_KEY: "case-1"}, path=focus_path)
        save_operator_focus({_CTX_PIPELINE_CASE_KEY: "case-2"}, path=focus_path)
        loaded = load_operator_focus(path=focus_path)
        assert loaded[_CTX_PIPELINE_CASE_KEY] == "case-2"

    def test_full_roundtrip_extract_save_load_apply(self, tmp_path):
        """End-to-end: extract from state, save, load, apply into fresh state."""
        focus_path = tmp_path / "focus.json"

        # 1. Extract from a "session state"
        session = {
            _CTX_PIPELINE_CASE_KEY: "case-42",
            _CTX_FILTER_STATUS_KEY: "running",
            f"{_CTX_REPORT_KEY_PREFIX}case-42": "rep-99ab",
            "ar_enabled": True,  # not a restorable key
        }
        focus = extract_restorable_focus(session)

        # 2. Save to disk
        save_operator_focus(focus, path=focus_path)

        # 3. Load back from disk
        loaded = load_operator_focus(path=focus_path)

        # 4. Apply into a fresh session state
        fresh_state = {}
        apply_restored_focus(fresh_state, loaded)

        assert fresh_state[_CTX_PIPELINE_CASE_KEY] == "case-42"
        assert fresh_state[_CTX_FILTER_STATUS_KEY] == "running"
        assert fresh_state[f"{_CTX_REPORT_KEY_PREFIX}case-42"] == "rep-99ab"
        assert "ar_enabled" not in fresh_state

    def test_default_focus_path_is_under_home(self):
        path = default_focus_path()
        assert str(path).endswith("operator_focus.json")
        assert ".neovax" in str(path)


class TestConstantsIntegrity:
    """Verify constants are correctly configured for the restorable system."""

    def test_report_key_prefix(self):
        assert _CTX_REPORT_KEY_PREFIX == "report-detail-"

    def test_structure_job_key_prefix(self):
        assert _CTX_STRUCTURE_JOB_KEY_PREFIX == "structure-job-"

    def test_restorable_keys_include_core_selectors(self):
        assert _CTX_EVENT_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_JOB_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_PIPELINE_CASE_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_INSPECT_CASE_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_FILTER_STATUS_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_FILTER_JOB_TYPE_KEY in _RESTORABLE_FOCUS_KEYS
        assert _CTX_FILTER_CASE_ID_KEY in _RESTORABLE_FOCUS_KEYS

    def test_restorable_prefixes_include_dynamic_buckets(self):
        prefixes = [prefix for prefix, _ in _RESTORABLE_FOCUS_PREFIXES]
        assert _CTX_REPORT_KEY_PREFIX in prefixes
        assert _CTX_STRUCTURE_JOB_KEY_PREFIX in prefixes

    def test_restorable_prefix_buckets(self):
        buckets = [bucket for _, bucket in _RESTORABLE_FOCUS_PREFIXES]
        assert "report_detail_keys" in buckets
        assert "structure_job_keys" in buckets