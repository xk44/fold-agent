"""Unit tests for backend.app.config — Settings defaults and env var loading."""

from __future__ import annotations

import os
from unittest.mock import patch

from backend.app.config import (
    AlphaFoldBackendName,
    DbInitMode,
    Settings,
    SpeciesMode,
)

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_settings_default_api_port() -> None:
    s = Settings()
    assert s.api_port == 8010


def test_settings_default_dashboard_port() -> None:
    s = Settings()
    assert s.dashboard_port == 8502


def test_settings_default_database_url() -> None:
    s = Settings()
    assert s.database_url == "sqlite:///./foldagent.db"


def test_settings_default_db_init_mode() -> None:
    s = Settings()
    assert s.db_init_mode == DbInitMode.create_all


def test_settings_default_species_mode() -> None:
    s = Settings()
    assert s.species_mode == SpeciesMode.DEMO


def test_settings_default_alphafold_backend() -> None:
    s = Settings()
    assert s.alphafold_default_backend == AlphaFoldBackendName.MOCK


def test_settings_default_pipeline_mode() -> None:
    s = Settings()
    assert s.pipeline_mode == "mock"


def test_settings_default_safety_preflight_enabled() -> None:
    s = Settings()
    assert s.safety_preflight_enabled is True


def test_settings_default_require_professional_oversight() -> None:
    s = Settings()
    assert s.require_professional_oversight is True


def test_settings_default_cloud_upload_disabled() -> None:
    s = Settings()
    assert s.cloud_upload_enabled is False


def test_settings_default_encryption_disabled() -> None:
    s = Settings()
    assert s.encryption_at_rest_enabled is False
    assert s.encryption_key is None


def test_settings_default_redis_none() -> None:
    s = Settings()
    assert s.redis_url is None
    assert s.celery_broker_url is None
    assert s.celery_result_backend is None


def test_settings_default_log_level() -> None:
    s = Settings()
    assert s.log_level == "INFO"


def test_settings_default_secret_key() -> None:
    s = Settings()
    assert s.secret_key == "changeme-set-a-real-secret-key"


def test_settings_default_cors_origins_include_localhost() -> None:
    s = Settings()
    assert any("localhost" in origin for origin in s.cors_origins)


def test_settings_default_alphafold_allowed_backends_nonempty() -> None:
    s = Settings()
    assert len(s.alphafold_allowed_backends) > 0
    assert AlphaFoldBackendName.MOCK in s.alphafold_allowed_backends


def test_settings_default_pipeline_pvactools_alleles() -> None:
    s = Settings()
    assert "HLA-A*02:01" in s.pipeline_pvactools_alleles


# ---------------------------------------------------------------------------
# env_prefix
# ---------------------------------------------------------------------------


def test_env_prefix_is_foldagent() -> None:
    assert Settings.model_config["env_prefix"] == "FOLDAGENT_"


def test_settings_override_api_port_via_env() -> None:
    with patch.dict(os.environ, {"FOLDAGENT_API_PORT": "9999"}):
        s = Settings()
    assert s.api_port == 9999


def test_settings_override_species_mode_via_env() -> None:
    with patch.dict(os.environ, {"FOLDAGENT_SPECIES_MODE": "human"}):
        s = Settings()
    assert s.species_mode == SpeciesMode.HUMAN


def test_settings_override_pipeline_mode_via_env() -> None:
    with patch.dict(os.environ, {"FOLDAGENT_PIPELINE_MODE": "real"}):
        s = Settings()
    assert s.pipeline_mode == "real"


def test_settings_override_database_url_via_env() -> None:
    with patch.dict(os.environ, {"FOLDAGENT_DATABASE_URL": "sqlite:///./test.db"}):
        s = Settings()
    assert s.database_url == "sqlite:///./test.db"


def test_settings_override_alphafold_backend_via_env() -> None:
    with patch.dict(os.environ, {"FOLDAGENT_ALPHAFOLD_DEFAULT_BACKEND": "colabfold"}):
        s = Settings()
    assert s.alphafold_default_backend == AlphaFoldBackendName.COLABFOLD


def test_settings_non_foldagent_prefix_ignored() -> None:
    """Environment variables without FOLDAGENT_ prefix must not affect settings."""
    with patch.dict(os.environ, {"API_PORT": "1234"}):
        s = Settings()
    assert s.api_port == 8010


# ---------------------------------------------------------------------------
# Field existence
# ---------------------------------------------------------------------------


def test_all_expected_fields_exist() -> None:
    s = Settings()
    expected_fields = [
        "api_port",
        "dashboard_port",
        "cors_origins",
        "database_url",
        "db_init_mode",
        "redis_url",
        "celery_broker_url",
        "celery_result_backend",
        "background_job_backend",
        "event_backend",
        "species_mode",
        "cloud_upload_enabled",
        "cloud_upload_confirmation_required",
        "encryption_at_rest_enabled",
        "encryption_key",
        "alphafold_default_backend",
        "alphafold_allowed_backends",
        "alphafold_cache_outputs",
        "alphafold_store_confidence_metrics",
        "log_level",
        "structured_logs",
        "audit_log_path",
        "safety_preflight_enabled",
        "unsafe_text_scanner_enabled",
        "require_professional_oversight",
        "pipeline_mode",
        "pipeline_concurrent_workers",
        "pipeline_retry_max_attempts",
        "reports_default_format",
        "reports_research_only_label",
        "artifact_root",
        "secret_key",
    ]
    for field in expected_fields:
        assert hasattr(s, field), f"Missing field: {field}"
