"""Database wiring for NeoVax-Agent."""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import DbInitMode, settings
from backend.app.models import Base

logger = logging.getLogger(__name__)


def engine_kwargs_for_url(database_url: str) -> dict[str, object]:
    engine_kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return engine_kwargs


def _set_sqlite_wal_mode(engine: Engine) -> None:
    """Enable WAL mode on SQLite for better concurrent write handling."""
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def build_engine(database_url: str) -> Engine:
    eng = create_engine(database_url, **engine_kwargs_for_url(database_url))
    if database_url.startswith("sqlite"):
        _set_sqlite_wal_mode(eng)
    return eng


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=build_engine(database_url), autoflush=False, autocommit=False)


def _safe_database_url(bind: Engine) -> str:
    return bind.url.render_as_string(hide_password=True)


def is_missing_table_error(exc: OperationalError, *table_names: str) -> bool:
    error_text = str(exc).lower()
    if not any(pattern in error_text for pattern in ("no such table", "does not exist", "doesn't exist")):
        return False
    if not table_names:
        return True
    return any(table_name.lower() in error_text for table_name in table_names)


def schema_drift_detail(*table_names: str) -> str:
    if not table_names:
        return "database schema may be out of date or pointing at the wrong database"
    quoted = ", ".join(sorted(table_names))
    noun = "table" if len(table_names) == 1 else "tables"
    return f"{quoted} {noun} unavailable; database schema may be out of date or pointing at the wrong database"


def get_db_health_snapshot(bind: Engine) -> dict[str, object]:
    expected = expected_table_names()
    database_url = _safe_database_url(bind)
    try:
        with bind.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        existing = set(inspect(bind).get_table_names())
    except Exception as exc:
        return {
            "db_status": "degraded",
            "database_url": database_url,
            "db_init_mode": settings.db_init_mode.value,
            "tables_present": 0,
            "tables_expected": len(expected),
            "missing_tables": sorted(expected),
            "extra_tables": [],
            "error": str(exc),
        }

    present = expected & existing
    missing = sorted(expected - existing)
    extra = sorted(existing - expected)
    return {
        "db_status": "ok" if not missing else "degraded",
        "database_url": database_url,
        "db_init_mode": settings.db_init_mode.value,
        "tables_present": len(present),
        "tables_expected": len(expected),
        "missing_tables": missing,
        "extra_tables": extra,
        "error": None,
    }


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------

def expected_table_names() -> set[str]:
    """Return the set of table names declared in the ORM model metadata."""
    return set(Base.metadata.tables.keys())


def validate_schema(bind: Engine) -> None:
    """Verify that every ORM-declared table exists in the database.

    Raises ``RuntimeError`` listing any missing tables.  This is intended
    for production deployments where Alembic owns the schema: calling this
    at startup catches migration drift before the application serves
    requests.
    """
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    expected = expected_table_names()
    missing = expected - existing
    if missing:
        raise RuntimeError(
            f"Database schema at {_safe_database_url(bind)} is missing tables expected by the ORM models: "
            f"{sorted(missing)}. Run Alembic migrations or switch "
            f"NEOVAX_DB_INIT_MODE to 'create_all' for development."
        )


def _alembic_upgrade_head(database_url: str) -> None:
    """Run ``alembic upgrade head`` programmatically.

    This is a convenience helper for single-process deployments that want
    automatic migration at startup.  For production use prefer running
    Alembic manually as part of the deploy pipeline.
    """
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    alembic_cfg = Config(str(Path(__file__).resolve().parents[2].parent / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic upgrade head completed")


# ---------------------------------------------------------------------------
# init_db – the main entry-point called from the FastAPI lifespan
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Initialise the database schema according to ``settings.db_init_mode``.

    Modes:
        create_all – legacy behaviour; calls ``Base.metadata.create_all``.
        validate   – asserts all ORM tables exist; raises on mismatch.
        alembic    – delegates to ``alembic upgrade head``.
    """
    mode = settings.db_init_mode

    if mode == DbInitMode.create_all:
        logger.info("db_init_mode=create_all: creating tables via metadata.create_all")
        Base.metadata.create_all(bind=engine)

    elif mode == DbInitMode.validate:
        logger.info("db_init_mode=validate: checking schema consistency")
        validate_schema(engine)

    elif mode == DbInitMode.alembic:
        logger.info("db_init_mode=alembic: running upgrade head")
        _alembic_upgrade_head(settings.database_url)

    else:
        raise ValueError(f"Unknown db_init_mode: {mode!r}")

    snapshot = get_db_health_snapshot(engine)
    logger_method = logger.info if snapshot["db_status"] == "ok" else logger.warning
    logger_method(
        "db_init_complete database_url=%s db_init_mode=%s tables_present=%s tables_expected=%s missing_tables=%s extra_tables=%s error=%s",
        snapshot["database_url"],
        snapshot["db_init_mode"],
        snapshot["tables_present"],
        snapshot["tables_expected"],
        snapshot["missing_tables"],
        snapshot["extra_tables"],
        snapshot["error"],
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()