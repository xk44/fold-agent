from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.app.db import engine
from backend.app.main import app
from backend.app.models import Base


@pytest.fixture(autouse=True)
def reset_db() -> Generator[None, None, None]:
    # Shut down the background job executor to release SQLite connections
    # before dropping tables.  This avoids "database is locked" errors.
    from backend.app import jobs as _jobs_mod

    old_executor = _jobs_mod._executor
    old_executor.shutdown(wait=True)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Recreate a fresh executor for the test
    from concurrent.futures import ThreadPoolExecutor

    _jobs_mod._executor = ThreadPoolExecutor(
        max_workers=4, thread_name_prefix="bg-job"
    )
    # Also clear the in-memory cancel/future registries
    _jobs_mod._cancel_events.clear()
    _jobs_mod._job_futures.clear()

    yield

    # Teardown: shut down the fresh executor to release connections
    _jobs_mod._executor.shutdown(wait=True)
    _jobs_mod._cancel_events.clear()
    _jobs_mod._job_futures.clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client