from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db import engine


def test_agent_events_gracefully_handles_missing_audit_table(client: TestClient) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE audit_logs"))

    response = client.get("/agent/events?limit=5")

    assert response.status_code == 200
    assert response.text == ""
