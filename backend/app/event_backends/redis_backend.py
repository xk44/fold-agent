"""Redis pub/sub backend for FoldAgent event stream.

Requires the ``redis`` Python package (included in the ``worker`` extra).
Connects to a Redis server (via ``Settings.redis_url`` or
``redis://localhost:6379``) and uses Redis pub/sub to distribute events
across processes.

Channel layout
~~~~~~~~~~~~~~
All events are published to a single Redis channel (default
``foldagent:events``).  Each message is a JSON envelope::

    {"event": "<event_name>", "payload": {...}, "_src_pid": <int>}

``_src_pid`` is an implementation detail used for deduplication –
local subscribers receive messages synchronously from ``publish()``,
and the background listener skips messages that originated from the
same process to avoid double-delivery.

Prefix filtering happens on the consumer side, matching the
``InMemoryEventBackend`` semantics exactly.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from backend.app.event_stream import EventBackend

logger = logging.getLogger(__name__)

CHANNEL_DEFAULT = "foldagent:events"


class _Subscriber:
    """Internal bookkeeping for a local subscriber queue."""

    __slots__ = ("queue", "prefixes")

    def __init__(
        self,
        q: queue.Queue[dict[str, Any]],
        prefixes: tuple[str, ...] | None,
    ) -> None:
        self.queue = q
        self.prefixes = prefixes

    def matches(self, event_name: str) -> bool:
        return self.prefixes is None or event_name.startswith(self.prefixes)


class RedisEventBackend(EventBackend):
    """Redis-backed pub/sub event backend.

    Events are broadcast via Redis pub/sub so that consumers in
    separate processes (or on separate machines) receive them.
    Local, in-process subscribers receive messages **immediately**
    from ``publish()`` (synchronous delivery) and the background
    listener thread is responsible only for cross-process messages.

    Parameters
    ----------
    redis_url:
        Redis connection URL.  When *None* the URL is resolved from
        ``Settings.redis_url``; if that is also unset,
        ``redis://localhost:6379`` is used.
    channel:
        Redis pub/sub channel name.  Default: ``foldagent:events``.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        channel: str = CHANNEL_DEFAULT,
    ) -> None:
        self._redis_url = redis_url
        self._channel = channel
        # Lazy-initialised Redis / pubsub objects
        self._redis: Any = None
        self._pubsub: Any = None
        # Local subscriber bookkeeping
        self._subscribers: list[_Subscriber] = []
        self._lock = threading.Lock()
        # Listener thread management
        self._listener_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._listener_started = threading.Event()
        # Connection state – stays False until first successful connect
        self._connected = False

    # -- Redis lazy connection ------------------------------------------------

    @staticmethod
    def _resolve_redis_url(url: str | None) -> str:
        """Return *url* if given, otherwise consult Settings, else default."""
        if url is not None:
            return url
        try:
            from backend.app.config import settings

            if settings.redis_url:
                return settings.redis_url
        except Exception:
            pass
        return "redis://localhost:6379"

    def _connect(self) -> bool:
        """Lazily connect to Redis.  Returns *True* on success."""
        if self._connected and self._redis is not None:
            return True
        try:
            import redis as _redis  # type: ignore[import-untyped]

            url = self._resolve_redis_url(self._redis_url)
            client = _redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            self._redis = client
            self._connected = True
            logger.info("Redis event backend connected to %s", url)
            return True
        except Exception:
            self._connected = False
            self._redis = None
            logger.warning(
                "Redis event backend: connection failed – "
                "events will be local-only until Redis becomes available",
            )
            return False

    # -- publish --------------------------------------------------------------

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        envelope: dict[str, Any] = {"event": event_name, "payload": payload}
        # 1) Synchronous local delivery (always, even if Redis is down)
        self._deliver_local(envelope)
        # 2) Asynchronous cross-process delivery via Redis
        if self._connected or self._connect():
            outbound = {**envelope, "_src_pid": os.getpid()}
            try:
                self._redis.publish(self._channel, json.dumps(outbound))
            except Exception:
                logger.exception(
                    "Failed to publish event %r to Redis – "
                    "message was delivered locally",
                    event_name,
                )

    # -- subscribe ------------------------------------------------------------

    @contextmanager
    def subscribe(
        self,
        max_queue_size: int = 100,
        prefixes: tuple[str, ...] | None = None,
    ) -> Iterator[queue.Queue[dict[str, Any]]]:  # type: ignore[override]
        sub = _Subscriber(
            q=queue.Queue(maxsize=max_queue_size),
            prefixes=prefixes,
        )
        with self._lock:
            self._subscribers.append(sub)
            need_start = len(self._subscribers) == 1
        if need_start:
            self._start_listener()
        try:
            yield sub.queue
        finally:
            with self._lock:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)
                need_stop = len(self._subscribers) == 0
            if need_stop:
                self._stop_listener()

    # -- listener thread ------------------------------------------------------

    def _start_listener(self) -> None:
        """Start the background listener thread if not already running."""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        self._stop_event.clear()
        self._listener_started.clear()
        thread = threading.Thread(
            target=self._listener_loop,
            name="foldagent-redis-event-listener",
            daemon=True,
        )
        self._listener_thread = thread
        thread.start()
        # Wait (briefly) for the thread to indicate it has started
        self._listener_started.wait(timeout=5)

    def _stop_listener(self) -> None:
        """Signal the listener thread to stop and clean up."""
        if self._listener_thread is None:
            return
        self._stop_event.set()
        # Unsubscribe to unblock any blocking pubsub call
        try:
            if self._pubsub is not None:
                self._pubsub.unsubscribe(self._channel)
                self._pubsub.close()
        except Exception:
            pass
        self._listener_thread.join(timeout=5)
        self._listener_thread = None
        self._pubsub = None

    def _listener_loop(self) -> None:
        """Background thread: read from Redis pub/sub, fan out locally."""
        self._listener_started.set()
        if not self._connected and not self._connect():
            # Without a Redis connection there is nothing to listen for;
            # the thread exits.  It will be re-created on next subscribe().
            logger.info("Redis listener exiting – no connection available")
            return

        try:
            pubsub = self._get_pubsub()
        except Exception:
            logger.warning("Redis listener: could not create pubsub – exiting")
            return

        while not self._stop_event.is_set():
            try:
                msg = pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if msg is None:
                    continue
                if msg.get("type") != "message":
                    continue
                data = msg.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    envelope = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in Redis event message")
                    continue
                # Skip messages we already delivered locally (same process)
                if envelope.get("_src_pid") == os.getpid():
                    continue
                self._deliver_local(envelope)
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.debug("Error in Redis event listener", exc_info=True)

    def _get_pubsub(self) -> Any:
        """Return (and lazily create) the pubsub object."""
        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()
            self._pubsub.subscribe(self._channel)
        return self._pubsub

    # -- local delivery -------------------------------------------------------

    def _deliver_local(self, envelope: dict[str, Any]) -> None:
        """Fan out *envelope* to matching local subscriber queues."""
        event_name = envelope.get("event", "")
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            if not sub.matches(event_name):
                continue
            try:
                sub.queue.put_nowait(envelope)
            except queue.Full:
                continue


# Register on direct import as well as via event_backends._auto_register().
# This keeps explicit imports and tests predictable while remaining harmless
# if the package-level auto-register path also runs.
try:  # pragma: no cover - import side effect
    from backend.app.event_stream import register_event_backend

    register_event_backend("redis", RedisEventBackend)
except Exception:
    pass
