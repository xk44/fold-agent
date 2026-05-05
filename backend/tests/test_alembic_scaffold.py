from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
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


def test_alembic_upgrade_head_creates_core_tables(tmp_path) -> None:
    database_path = tmp_path / "alembic_test.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(table_names)
