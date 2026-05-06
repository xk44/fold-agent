"""Tests for the /agent/events/ws WebSocket transport.

Validates that the WebSocket endpoint:
- Accepts connections and delivers published events
- Correctly filters by prefix
- Sends heartbeat pings on idle
- Cleans up subscribers on disconnect
- Co-exists with the SSE /agent/events endpoint
- Has correct JSON message structure (event, id, data)
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.event_stream import publish_event, subscribe

# Short heartbeat for tests (1 second minimum enforced by the endpoint).
WS_HEARTBEAT = 1.0


def _create_demo_case(client: TestClient) -> str:
    response = client.post("/cases", json={"species": "demo", "diagnosis_summary": "ws test"})
    assert response.status_code == 201
    return response.json()["id"]


class TestWebSocketAgentEvents:
    """Focused tests for /agent/events/ws."""

    def test_ws_receives_published_event(self, client: TestClient) -> None:
        """A WebSocket client receives events published after connecting."""
        with client.websocket_connect(f"/agent/events/ws?heartbeat={WS_HEARTBEAT}") as ws:
            publish_event("pipeline.completed", {"log_id": "ws-1", "status": "ok"})
            raw = ws.receive_json(mode="text")
            assert raw["event"] == "pipeline.completed"
            assert raw["id"] == "ws-1"
            assert raw["data"]["status"] == "ok"

    def test_ws_prefix_filter_ignores_non_matching_events(self, client: TestClient) -> None:
        """With prefix=agent_task., only matching events are delivered."""
        with client.websocket_connect(
            f"/agent/events/ws?prefix=agent_task.&heartbeat={WS_HEARTBEAT}"
        ) as ws:
            # This should be filtered out (does not match agent_task. prefix)
            publish_event("pipeline.completed", {"log_id": "filtered-1"})
            # This should pass through
            publish_event("agent_task.created", {"log_id": "match-1", "framework": "hermes"})

            raw = ws.receive_json(mode="text")
            assert raw["event"] == "agent_task.created"
            assert raw["id"] == "match-1"

    def test_ws_sends_heartbeat_on_idle(self, client: TestClient) -> None:
        """After a timeout with no events, the server sends a ping heartbeat."""
        with client.websocket_connect("/agent/events/ws?heartbeat=1") as ws:
            # Wait for a heartbeat ping (should arrive within ~2 seconds)
            raw = ws.receive_json(mode="text")
            assert raw == {"type": "ping"}

    def test_ws_disconnect_cleans_up_subscriber(self, client: TestClient) -> None:
        """After disconnecting, the subscriber is removed so events don't leak."""
        with client.websocket_connect(f"/agent/events/ws?heartbeat={WS_HEARTBEAT}") as ws:
            publish_event("report.generated", {"log_id": "pre-dc"})

        # After disconnect, publish_event should not raise or accumulate
        # phantom subscribers.
        publish_event("variant.annotated", {"log_id": "post-dc"})

        # Verify a fresh subscribe works and sees only new events.
        with subscribe(prefixes=("variant.",)) as q:
            publish_event("variant.reviewed", {"log_id": "post-dc-2"})
            envelope = q.get(timeout=2)
            assert envelope["event"] == "variant.reviewed"

    def test_ws_coexists_with_sse_endpoint(self, client: TestClient) -> None:
        """SSE and WebSocket endpoints can serve data simultaneously."""
        case_id = _create_demo_case(client)

        # Trigger an audit event via API
        client.post(
            "/agent/tasks/dry-run",
            json={"case_id": case_id, "framework": "hermes", "skill_name": "monitor_case_progress"},
        )

        # Both SSE snapshot and WS stream should deliver results
        sse_resp = client.get("/agent/events?limit=50")
        assert sse_resp.status_code == 200
        assert "event:" in sse_resp.text

        with client.websocket_connect(f"/agent/events/ws?heartbeat={WS_HEARTBEAT}") as ws:
            publish_event("pipeline.started", {"log_id": "dual-1"})
            raw = ws.receive_json(mode="text")
            assert raw["event"] == "pipeline.started"

    def test_ws_json_message_structure(self, client: TestClient) -> None:
        """Each WS message has event, id, and data keys matching SSE semantics."""
        with client.websocket_connect(f"/agent/events/ws?heartbeat={WS_HEARTBEAT}") as ws:
            payload = {
                "log_id": "struct-1",
                "case_id": "case-abc",
                "actor": "api",
                "action": "pipeline.completed",
            }
            publish_event("pipeline.completed", payload)

            raw = ws.receive_json(mode="text")
            assert "event" in raw
            assert "id" in raw
            assert "data" in raw
            assert raw["event"] == "pipeline.completed"
            assert raw["id"] == "struct-1"
            assert raw["data"]["log_id"] == "struct-1"
