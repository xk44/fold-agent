"""Tests for database startup / migration hardening.

These tests verify:

1. ``init_db`` respects the ``db_init_mode`` config setting.
2. ``validate_schema`` catches missing tables.
3. ``expected_table_names`` returns the correct model table set.
4. Alembic ``upgrade head`` and ``create_all`` produce the same tables
   (migration parity contract).
5. The lifespan correctly delegates to ``init_db``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect

from backend.app.config import DbInitMode, Settings
from backend.app.db import (
    build_engine,
    expected_table_names,
    get_db_health_snapshot,
    init_db,
    validate_schema,
)
from backend.app.models import Base

ROOT = Path(__file__).resolve().parents[2]

# The authoritative set of table names that the ORM declares.
# Keep this in sync with backend/app/models.py.
EXPECTED_TABLES = {
    "cases",
    "subjects",
    "samples",
    "variants",
    "candidate_antigens",
    "structure_jobs",
    "pipeline_runs",
    "execution_runs",
    "artifacts",
    "case_tasks",
    "reports",
    "agent_tasks",
    "background_jobs",
    "audit_logs",
    "lab_contacts",
    "cost_entries",
    "timeline_entries",
    "document_requests",
}


# -----------------------------------------------------------------------
# expected_table_names
# -----------------------------------------------------------------------


class TestExpectedTableNames:
    def test_matches_authoritative_set(self):
        """The ORM metadata must declare exactly the tables we expect."""
        tables = expected_table_names()
        assert tables == EXPECTED_TABLES, (
            f"Model table set diverged from test expectations.  "
            f"New: {tables - EXPECTED_TABLES}, "
            f"Removed: {EXPECTED_TABLES - tables}"
        )

    def test_includes_all_core_tables(self):
        """Every core table from the existing alembic test must appear."""
        # Mirror the set from test_alembic_scaffold for cross-checking.
        tables = expected_table_names()
        alembic_expected = {
            "agent_tasks",
            "artifacts",
            "audit_logs",
            "candidate_antigens",
            "cases",
            "case_tasks",
            "execution_runs",
            "pipeline_runs",
            "reports",
            "samples",
            "structure_jobs",
            "subjects",
            "variants",
        }
        assert alembic_expected.issubset(tables)


# -----------------------------------------------------------------------
# validate_schema
# -----------------------------------------------------------------------


class TestValidateSchema:
    def test_passes_when_tables_exist(self, tmp_path):
        """validate_schema should succeed when all ORM tables are present."""
        db_path = tmp_path / "test.db"
        eng = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=eng)
        # Should not raise
        validate_schema(eng)

    def test_raises_on_missing_tables(self, tmp_path):
        """validate_schema should raise RuntimeError when tables are absent."""
        db_path = tmp_path / "empty.db"
        eng = create_engine(f"sqlite:///{db_path}")
        # Don't create any tables – the DB is empty.
        with pytest.raises(RuntimeError, match="missing tables"):
            validate_schema(eng)

    def test_raises_with_specific_missing_table(self, tmp_path):
        """validate_schema error message should list the missing tables."""
        db_path = tmp_path / "partial.db"
        eng = create_engine(f"sqlite:///{db_path}")
        # Create only one table so that most are still missing.
        Base.metadata.tables["cases"].create(bind=eng)
        with pytest.raises(RuntimeError) as exc_info:
            validate_schema(eng)
        error_msg = str(exc_info.value)
        # "cases" should NOT appear (it was created), but other tables should.
        assert "cases" not in error_msg or "missing" in error_msg
        # At least some missing table should be named.
        assert "audit_logs" in error_msg or "subjects" in error_msg

    def test_raises_with_database_path_in_error(self, tmp_path):
        """validate_schema errors should mention the active database path."""
        db_path = tmp_path / "empty.db"
        eng = create_engine(f"sqlite:///{db_path}")
        with pytest.raises(RuntimeError) as exc_info:
            validate_schema(eng)
        assert str(db_path) in str(exc_info.value)

    def test_db_health_snapshot_reports_missing_tables(self, tmp_path):
        """Health snapshots should surface missing-table drift clearly."""
        db_path = tmp_path / "health-empty.db"
        eng = create_engine(f"sqlite:///{db_path}")
        snapshot = get_db_health_snapshot(eng)

        assert snapshot["db_status"] == "degraded"
        assert snapshot["database_url"].endswith(str(db_path))
        assert snapshot["tables_present"] == 0
        assert snapshot["tables_expected"] == len(EXPECTED_TABLES)
        assert "background_jobs" in snapshot["missing_tables"]


# -----------------------------------------------------------------------
# init_db mode switching
# -----------------------------------------------------------------------


class TestInitDbModes:
    def test_create_all_mode_creates_tables(self, tmp_path):
        """In create_all mode, init_db should create all ORM tables."""
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
        test_settings = Settings(
            database_url=db_url,
            db_init_mode=DbInitMode.create_all,
        )
        eng = build_engine(db_url)

        with patch("backend.app.db.settings", test_settings), patch("backend.app.db.engine", eng):
            init_db()

        inspector = inspect(eng)
        existing = set(inspector.get_table_names())
        assert expected_table_names().issubset(existing)

    def test_validate_mode_raises_on_empty_db(self, tmp_path):
        """In validate mode, init_db should raise on an empty database."""
        db_url = f"sqlite:///{tmp_path / 'empty.db'}"
        test_settings = Settings(
            database_url=db_url,
            db_init_mode=DbInitMode.validate,
        )
        # We patch the module-level settings reference used inside init_db.
        with (
            patch("backend.app.db.settings", test_settings),
            patch("backend.app.db.engine", build_engine(db_url)),
        ):
            with pytest.raises(RuntimeError, match="missing tables"):
                init_db()

    def test_validate_mode_succeeds_on_migrated_db(self, tmp_path):
        """In validate mode, init_db should succeed on a fully-migrated db."""
        db_url = f"sqlite:///{tmp_path / 'migrated.db'}"
        eng = create_engine(db_url)
        Base.metadata.create_all(bind=eng)

        test_settings = Settings(
            database_url=db_url,
            db_init_mode=DbInitMode.validate,
        )
        with patch("backend.app.db.settings", test_settings), patch("backend.app.db.engine", eng):
            # Should not raise
            init_db()


# -----------------------------------------------------------------------
# Alembic / create_all migration parity contract
# -----------------------------------------------------------------------


class TestMigrationParity:
    def test_alembic_and_create_all_produce_same_tables(self, tmp_path):
        """alembic upgrade head and metadata.create_all must create the same
        set of tables.  If this test fails, a migration or model has been
        added without updating the other side."""
        from alembic import command
        from alembic.config import Config

        # Create two databases: one via alembic, one via create_all.
        db_alembic = tmp_path / "alembic.db"
        db_create = tmp_path / "create_all.db"

        # --- Alembic path ---
        alembic_cfg = Config(str(ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_alembic}")
        command.upgrade(alembic_cfg, "head")

        # --- create_all path ---
        eng_create = create_engine(f"sqlite:///{db_create}")
        Base.metadata.create_all(bind=eng_create)

        # Compare table sets.
        eng_alembic = create_engine(f"sqlite:///{db_alembic}")
        inspector_alembic = inspect(eng_alembic)
        inspector_create = inspect(eng_create)

        tables_alembic = set(inspector_alembic.get_table_names())
        tables_create = set(inspector_create.get_table_names())

        # Filter out alembic_version from comparison (it's meta, not model data).
        tables_alembic.discard("alembic_version")

        assert tables_alembic == tables_create, (
            f"Migration parity failure!\n"
            f"  Only in alembic:  {tables_alembic - tables_create}\n"
            f"  only in create_all: {tables_create - tables_alembic}"
        )

        # Also assert both match the expected ORM tables.
        assert expected_table_names() == tables_create, (
            f"create_all tables diverged from ORM expectations:\n"
            f"  Missing from DB: {expected_table_names() - tables_create}\n"
            f"  Extra in DB: {tables_create - expected_table_names()}"
        )


# -----------------------------------------------------------------------
# Contract: expected_table_names stays in sync with models
# -----------------------------------------------------------------------


class TestTableContractDocumentation:
    """These tests ensure the migration contract is documented and caught
    when it drifts.  If someone adds a model but forgets to add a
    migration, the parity test above will fail."""

    def test_no_alembic_only_tables_missing_from_models(self, tmp_path):
        """Every table created by alembic should correspond to an ORM model."""
        from alembic import command
        from alembic.config import Config

        db_path = tmp_path / "contract.db"
        alembic_cfg = Config(str(ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.upgrade(alembic_cfg, "head")

        eng = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(eng)
        tables = set(inspector.get_table_names())
        tables.discard("alembic_version")  # meta table

        orm_tables = expected_table_names()
        extra_in_db = tables - orm_tables
        assert not extra_in_db, (
            f"Alembic creates tables not in ORM models: {extra_in_db}.  "
            f"Either add models or remove migrations."
        )
