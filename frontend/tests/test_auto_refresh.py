"""Tests for auto-refresh configuration helpers — pure functions, no Streamlit dependency.

Covers: compute_auto_refresh_config, AutoRefreshConfig, format_auto_refresh_mode_label
from frontend.app.event_stream.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frontend.app.event_stream import (
    AutoRefreshConfig,
    compute_auto_refresh_config,
    format_auto_refresh_mode_label,
    render_auto_refresh,
)


class TestAutoRefreshConfig:
    """Test the AutoRefreshConfig dataclass defaults."""

    def test_default_config(self):
        cfg = AutoRefreshConfig()
        assert cfg.interval_seconds == 10
        assert cfg.enabled is True
        assert cfg.mode == "heuristic"

    def test_custom_config_heuristic(self):
        cfg = AutoRefreshConfig(interval_seconds=30, enabled=True, mode="heuristic")
        assert cfg.interval_seconds == 30
        assert cfg.enabled is True
        assert cfg.mode == "heuristic"

    def test_custom_config_manual(self):
        cfg = AutoRefreshConfig(interval_seconds=42, enabled=True, mode="manual")
        assert cfg.interval_seconds == 42
        assert cfg.mode == "manual"

    def test_custom_config_disabled(self):
        cfg = AutoRefreshConfig(interval_seconds=0, enabled=False, mode="disabled")
        assert cfg.enabled is False
        assert cfg.mode == "disabled"


class TestComputeAutoRefreshConfig:
    """Test the pure logic that decides refresh interval from system state."""

    def test_default_is_enabled_with_moderate_interval(self):
        """With no arguments, auto-refresh should be enabled at a moderate interval."""
        cfg = compute_auto_refresh_config()
        assert cfg.enabled is True
        assert cfg.interval_seconds >= 5
        assert cfg.mode == "heuristic"

    def test_active_jobs_trigger_fast_refresh(self):
        """Running/pending jobs should cause faster refresh."""
        job_cards = [
            {"status": "running", "job_type": "pipeline_run"},
            {"status": "pending", "job_type": "alphafold"},
        ]
        cfg = compute_auto_refresh_config(job_cards=job_cards)
        assert cfg.enabled is True
        assert cfg.interval_seconds <= 10  # fast for active work
        assert cfg.mode == "heuristic"

    def test_completed_jobs_slower_refresh(self):
        """Only completed/failed jobs → slower refresh."""
        job_cards = [
            {"status": "completed"},
            {"status": "completed"},
            {"status": "failed"},
        ]
        cfg = compute_auto_refresh_config(job_cards=job_cards)
        assert cfg.enabled is True
        # All done → should use idle/slow interval
        assert cfg.interval_seconds >= 15
        assert cfg.mode == "heuristic"

    def test_no_jobs_moderate_refresh(self):
        """No jobs at all → moderate (idle) refresh."""
        cfg = compute_auto_refresh_config(job_cards=[])
        assert cfg.enabled is True
        # No jobs → idle interval
        assert cfg.interval_seconds >= 15
        assert cfg.mode == "heuristic"

    def test_connection_error_backs_off(self):
        """Connection errors should trigger a slower refresh to avoid hammering."""
        cfg = compute_auto_refresh_config(has_connection_error=True)
        assert cfg.enabled is True
        assert cfg.interval_seconds >= 20  # back off
        assert cfg.mode == "heuristic"

    def test_connection_error_with_active_jobs_uses_faster(self):
        """Active jobs override error backoff — still refresh fast."""
        job_cards = [{"status": "running"}]
        cfg = compute_auto_refresh_config(
            job_cards=job_cards, has_connection_error=True
        )
        # Active jobs take priority: refresh should be faster than pure error backoff
        error_only_cfg = compute_auto_refresh_config(has_connection_error=True)
        assert cfg.interval_seconds <= error_only_cfg.interval_seconds
        assert cfg.mode == "heuristic"

    def test_explicit_disable(self):
        """Passing enabled=False should disable auto-refresh."""
        cfg = compute_auto_refresh_config(enabled=False)
        assert cfg.enabled is False
        assert cfg.mode == "disabled"

    def test_explicit_disable_with_jobs(self):
        """Disabled overrides everything, even with active jobs."""
        job_cards = [{"status": "running"}]
        cfg = compute_auto_refresh_config(job_cards=job_cards, enabled=False)
        assert cfg.enabled is False
        assert cfg.mode == "disabled"
        assert cfg.interval_seconds == 0

    def test_explicit_interval_override(self):
        """If caller specifies an interval, use that."""
        cfg = compute_auto_refresh_config(interval_seconds=42)
        assert cfg.interval_seconds == 42
        assert cfg.mode == "manual"

    def test_explicit_interval_overrides_heuristic(self):
        """Explicit interval overrides the heuristic even with active jobs."""
        job_cards = [{"status": "running"}]
        cfg = compute_auto_refresh_config(job_cards=job_cards, interval_seconds=99)
        assert cfg.interval_seconds == 99
        assert cfg.mode == "manual"

    def test_explicit_interval_zero_treated_as_manual(self):
        """Explicit interval_seconds=0 is still mode=manual (enabled)."""
        cfg = compute_auto_refresh_config(interval_seconds=0)
        assert cfg.mode == "manual"
        # Note: interval_seconds=0 with enabled=True is a valid config —
        # render_auto_refresh handles it by not rendering the timer.

    def test_events_count_does_not_affect_basic_logic(self):
        """total_events shouldn't change the basic interval — it's about buffer state."""
        cfg_no_events = compute_auto_refresh_config(total_events=0)
        cfg_some_events = compute_auto_refresh_config(total_events=50)
        # With no jobs in either case, the interval should be the same
        assert cfg_no_events.interval_seconds == cfg_some_events.interval_seconds
        assert cfg_no_events.mode == cfg_some_events.mode

    def test_mixed_status_jobs_uses_fast_refresh(self):
        """If any job is running/pending, use fast refresh."""
        job_cards = [
            {"status": "completed"},
            {"status": "running"},
            {"status": "completed"},
        ]
        cfg = compute_auto_refresh_config(job_cards=job_cards)
        assert cfg.interval_seconds <= 10
        assert cfg.mode == "heuristic"

    def test_blocked_job_uses_moderate_refresh(self):
        """Blocked jobs are not active but not done — moderate refresh."""
        job_cards = [{"status": "blocked"}]
        cfg = compute_auto_refresh_config(job_cards=job_cards)
        assert cfg.interval_seconds >= 10
        assert cfg.mode == "heuristic"

    def test_mode_is_disabled_when_enabled_false(self):
        """All disabled configs should have mode='disabled'."""
        for job_cards in [None, [], [{"status": "running"}]]:
            cfg = compute_auto_refresh_config(job_cards=job_cards, enabled=False)
            assert cfg.mode == "disabled"

    def test_mode_is_manual_when_interval_overridden(self):
        """All configs with explicit interval_seconds should have mode='manual'."""
        for interval in [1, 10, 60, 300]:
            cfg = compute_auto_refresh_config(interval_seconds=interval)
            assert cfg.mode == "manual"

    def test_mode_is_heuristic_by_default(self):
        """Default (no override, not disabled) uses heuristic mode."""
        cfg = compute_auto_refresh_config()
        assert cfg.mode == "heuristic"


class TestFormatAutoRefreshModeLabel:
    """Test the pure format_auto_refresh_mode_label function."""

    def test_disabled_label(self):
        cfg = AutoRefreshConfig(interval_seconds=0, enabled=False, mode="disabled")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: disabled"

    def test_heuristic_label(self):
        cfg = AutoRefreshConfig(interval_seconds=30, enabled=True, mode="heuristic")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: heuristic (30s)"

    def test_manual_label(self):
        cfg = AutoRefreshConfig(interval_seconds=42, enabled=True, mode="manual")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: manual override (42s)"

    def test_heuristic_fast_label(self):
        cfg = AutoRefreshConfig(interval_seconds=5, enabled=True, mode="heuristic")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: heuristic (5s)"

    def test_unknown_mode_falls_back(self):
        cfg = AutoRefreshConfig(interval_seconds=10, enabled=True, mode="custom")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: custom (10s)"

    def test_disabled_overrides_other_flags(self):
        """Even if mode is 'heuristic' and enabled is False, disabled label wins."""
        cfg = AutoRefreshConfig(interval_seconds=30, enabled=False, mode="heuristic")
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: disabled"

    def test_label_from_compute_config_disabled(self):
        """Integration: compute → label for disabled state."""
        cfg = compute_auto_refresh_config(enabled=False)
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: disabled"

    def test_label_from_compute_config_manual(self):
        """Integration: compute → label for manual override."""
        cfg = compute_auto_refresh_config(interval_seconds=60)
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: manual override (60s)"

    def test_label_from_compute_config_heuristic_idle(self):
        """Integration: compute → label for heuristic idle state."""
        cfg = compute_auto_refresh_config(job_cards=[])
        # Idle interval is 30s
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: heuristic (30s)"

    def test_label_from_compute_config_heuristic_active(self):
        """Integration: compute → label for heuristic active state."""
        cfg = compute_auto_refresh_config(job_cards=[{"status": "running"}])
        # Active interval is 5s
        assert format_auto_refresh_mode_label(cfg) == "Auto-refresh: heuristic (5s)"


class TestRenderAutoRefresh:
    def test_render_auto_refresh_uses_positive_height_for_iframe(self, monkeypatch):
        calls = []

        fake_streamlit = SimpleNamespace(
            iframe=lambda *args, **kwargs: calls.append((args, kwargs)),
            session_state={},
        )
        monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

        render_auto_refresh(5)

        assert len(calls) == 1
        assert calls[0][1]["height"] > 0
