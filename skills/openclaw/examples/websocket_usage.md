---
title: WebSocket Usage — Real-Time Pipeline Status
framework: OpenClaw
skill: foldagent-openclaw
---

# WebSocket Usage: Real-Time Pipeline Status

The FoldAgent API exposes a WebSocket endpoint for live agent event streaming.
This lets OpenClaw tasks receive pipeline step completions, failures, and job
state changes without polling.

## Endpoint

```
ws://<FOLDAGENT_HOST>/agent/events/ws
```

### Query Parameters

| Parameter   | Type   | Default | Description                                                            |
| ----------- | ------ | ------- | ---------------------------------------------------------------------- |
| `prefix`    | string | (none)  | Comma-separated event name prefixes to filter. Example: `pipeline,job` |
| `heartbeat` | float  | `15.0`  | Seconds between ping frames when idle. Range: 1–300.                   |

## Message Format

Every server-pushed message is a JSON object:

```json
{
  "event": "pipeline.step.completed",
  "id": "audit-log-uuid",
  "data": {
    "case_id": "abc-123",
    "step": "mutect2",
    "status": "completed",
    "duration_seconds": 42.1
  }
}
```

Heartbeat pings (sent when no events occur within `heartbeat` seconds):

```json
{ "type": "ping" }
```

## Relevant Event Prefixes

| Prefix      | Events Delivered                                                                           |
| ----------- | ------------------------------------------------------------------------------------------ |
| `pipeline`  | `pipeline.step.completed`, `pipeline.step.failed`, `pipeline.completed`, `pipeline.failed` |
| `job`       | `job.started`, `job.completed`, `job.failed`, `job.cancelled`                              |
| `agent`     | All agent task events                                                                      |
| `candidate` | `candidate.reviewed`, `candidate.flagged`                                                  |
| (none)      | All events — use carefully, high volume                                                    |

## Python Example (asyncio)

```python
import asyncio
import json
import websockets

FOLDAGENT_WS = "ws://localhost:8000/agent/events/ws"

async def stream_pipeline_events(case_id: str) -> None:
    url = f"{FOLDAGENT_WS}?prefix=pipeline,job&heartbeat=15"
    async with websockets.connect(url) as ws:
        print(f"Connected. Watching pipeline events for case {case_id}...")
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "ping":
                continue  # heartbeat — ignore
            event = msg.get("event", "")
            data = msg.get("data", {})
            # Filter to our case
            if data.get("case_id") != case_id:
                continue
            print(f"[{event}] step={data.get('step')} status={data.get('status')}")
            if event in ("pipeline.completed", "pipeline.failed"):
                break

asyncio.run(stream_pipeline_events("abc-123"))
```

## OpenClaw Task Integration

In the `pipeline_run.yaml` task, the `stream_events` step connects to this
endpoint with `prefix=pipeline` and falls back to REST polling
(`GET /jobs/{job_id}`) if the WebSocket connection drops:

```yaml
- id: stream_events
  type: websocket
  endpoint: /agent/events/ws
  query_params:
    prefix: pipeline
  poll_fallback:
    endpoint: /jobs/{{ steps.run_pipeline_async.outputs.job_id }}
    interval_seconds: 10
    until: "{{ response.status in ['completed', 'failed', 'cancelled'] }}"
```

## SSE Alternative

For environments where WebSocket connections are not available, use the
Server-Sent Events (SSE) endpoint instead:

```
GET /agent/events
```

See `skills/shared/event_stream_client.py` for a ready-made SSE client.

## Security Notes

- The WebSocket endpoint does not require authentication in the default local
  deployment. In production, enforce token-based auth at the reverse proxy.
- Do not expose `/agent/events/ws` to untrusted networks. All events contain
  case IDs and audit log references.
- See `OPSEC_CHECKLIST.md` for full deployment security requirements.
