from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
RUN_FLAG = "FOLDAGENT_RUN_REDIS_SMOKE"
EXTERNAL_URL_FLAG = "FOLDAGENT_REDIS_SMOKE_URL"


if os.getenv(RUN_FLAG) != "1":
    pytest.skip(
        f"set {RUN_FLAG}=1 to run live Redis smoke tests",
        allow_module_level=True,
    )


try:
    import redis
except Exception as exc:  # pragma: no cover - hard fail only in opt-in mode
    raise RuntimeError("redis package required for live Redis smoke") from exc


def _command_ok(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=20
        )
    except Exception:
        return False
    return result.returncode == 0


def _wait_for_redis(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client = redis.Redis.from_url(url, decode_responses=True)
            if client.ping():
                return
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for Redis at {url}")


def _port_in_use(host: str = "127.0.0.1", port: int = 6379) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for HTTP endpoint at {url}")


class _UvicornServer:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self.port = _pick_free_port()
        self.process: subprocess.Popen[str] | None = None
        self.database_url = f"sqlite:////tmp/foldagent_redis_smoke_{uuid4().hex}.db"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        env["FOLDAGENT_EVENT_BACKEND"] = "redis"
        env["FOLDAGENT_REDIS_URL"] = self.redis_url
        env["FOLDAGENT_DATABASE_URL"] = self.database_url
        self.process = subprocess.Popen(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_http(f"{self.base_url}/health")
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.base_url

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None


class _ComposeRedis:
    def __init__(self) -> None:
        self.started = False

    def __enter__(self) -> str:
        external = os.getenv(EXTERNAL_URL_FLAG)
        if external:
            _wait_for_redis(external)
            return external

        if _port_in_use():
            try:
                _wait_for_redis(DEFAULT_REDIS_URL, timeout=5.0)
                return DEFAULT_REDIS_URL
            except Exception as exc:
                raise RuntimeError(
                    "localhost:6379 already in use by a non-ready service; set FOLDAGENT_REDIS_SMOKE_URL to a reachable Redis or free the port"
                ) from exc

        if not _command_ok(["docker", "compose", "version"]):
            raise RuntimeError("docker compose is required for live Redis smoke")

        up = subprocess.run(
            ["docker", "compose", "--profile", "worker", "up", "-d", "redis"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if up.returncode != 0:
            raise RuntimeError(f"failed to start compose redis: {up.stderr or up.stdout}")
        self.started = True
        _wait_for_redis(DEFAULT_REDIS_URL)
        return DEFAULT_REDIS_URL

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.started:
            return
        subprocess.run(
            ["docker", "compose", "--profile", "worker", "down"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )


def _publish_remote(redis_url: str, channel: str, event_name: str, payload: dict) -> None:
    code = f"""
import sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
from backend.app.event_backends.redis_backend import RedisEventBackend
backend = RedisEventBackend(redis_url={redis_url!r}, channel={channel!r})
backend.publish({event_name!r}, {payload!r})
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _configure_live_redis_backend(redis_url: str, channel: str):
    from backend.app.event_backends.redis_backend import RedisEventBackend
    from backend.app.event_stream import InMemoryEventBackend, configure_backend

    original = configure_backend(backend=InMemoryEventBackend())
    live_backend = RedisEventBackend(redis_url=redis_url, channel=channel)
    configure_backend(backend=live_backend)
    return live_backend, original


def test_live_redis_backend_cross_process_pubsub_smoke() -> None:
    from backend.app.event_backends.redis_backend import RedisEventBackend

    channel = f"foldagent:events:smoke:{uuid4().hex}"
    with _ComposeRedis() as redis_url:
        backend = RedisEventBackend(redis_url=redis_url, channel=channel)
        raw_client = redis.Redis.from_url(redis_url, decode_responses=True)
        pubsub = raw_client.pubsub()
        pubsub.subscribe(channel)
        try:
            with backend.subscribe(prefixes=("smoke.",)) as subscriber:
                payload = {"marker": "local-publish"}
                backend.publish("smoke.local", payload)

                local_envelope = subscriber.get(timeout=5)
                assert local_envelope["event"] == "smoke.local"
                assert local_envelope["payload"] == payload

                deadline = time.time() + 10
                published = None
                while time.time() < deadline:
                    message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message.get("type") == "message":
                        published = json.loads(message["data"])
                        break
                assert published is not None, "expected backend.publish to reach real Redis pubsub"
                assert published["event"] == "smoke.local"
                assert published["payload"] == payload
                assert isinstance(published.get("_src_pid"), int)

                remote_payload = {"marker": "remote-process"}
                _publish_remote(redis_url, channel, "smoke.remote", remote_payload)

                envelope = subscriber.get(timeout=10)
                assert envelope["event"] == "smoke.remote"
                assert envelope["payload"] == remote_payload
        finally:
            pubsub.close()


def test_live_redis_backend_websocket_end_to_end_smoke() -> None:
    from backend.app.event_stream import InMemoryEventBackend, configure_backend
    from backend.app.main import app

    channel = f"foldagent:events:smoke:ws:{uuid4().hex}"
    with _ComposeRedis() as redis_url:
        live_backend, _ = _configure_live_redis_backend(redis_url, channel)
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/agent/events/ws?prefix=smoke.&heartbeat=1") as ws:
                    remote_payload = {"marker": "ws-remote"}
                    _publish_remote(redis_url, channel, "smoke.remote_ws", remote_payload)
                    message = ws.receive_json(mode="text")
                    assert message["event"] == "smoke.remote_ws"
                    assert message["data"] == remote_payload
                    assert message["id"] is None
        finally:
            configure_backend(backend=InMemoryEventBackend())
            live_backend._stop_listener()


def test_live_redis_backend_sse_follow_end_to_end_smoke() -> None:
    from backend.app.event_backends.redis_backend import CHANNEL_DEFAULT

    channel = CHANNEL_DEFAULT
    with _ComposeRedis() as redis_url:
        with _UvicornServer(redis_url) as base_url:
            with httpx.stream(
                "GET",
                f"{base_url}/agent/events",
                params={"follow": "true", "prefix": "smoke.", "limit": 1},
                headers={"Accept": "text/event-stream"},
                timeout=20.0,
            ) as response:
                assert response.status_code == 200
                _publish_remote(redis_url, channel, "smoke.remote_sse", {"marker": "sse-remote"})

                lines: list[str] = []
                deadline = time.time() + 15
                for line in response.iter_lines():
                    if time.time() > deadline:
                        break
                    if not line:
                        if any(item.startswith("data: ") for item in lines):
                            payload_line = next(item for item in lines if item.startswith("data: "))
                            event_line = next(item for item in lines if item.startswith("event: "))
                            payload = json.loads(payload_line.split(": ", 1)[1])
                            event = event_line.split(": ", 1)[1]
                            if event == "smoke.remote_sse":
                                assert payload == {"marker": "sse-remote"}
                                return
                        lines = []
                        continue
                    lines.append(line)

                raise AssertionError(
                    "did not receive remote SSE event through live redis-backed /agent/events follow stream"
                )
