"""Modular event-stream backend abstraction for FoldAgent.

Public API (unchanged):
    publish_event(event_name, payload) -> None
    subscribe(max_queue_size, prefixes) -> context manager yielding queue

Internally, calls are delegated to a *backend* instance selected via
``Settings.event_backend``.  The default ``"memory"`` backend preserves
the original in-process, thread-safe behaviour.  Additional backends
(e.g. ``"redis"``) are registered from the ``event_backends`` subpackage.
Adding a new backend only requires implementing the ``EventBackend``
protocol and registering it in ``_BACKEND_REGISTRY``.
"""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Abstract backend protocol
# ---------------------------------------------------------------------------


class EventBackend(ABC):
    """Interface that every event-stream backend must implement.

    A backend owns the subscriber lifecycle.  ``subscribe`` returns a
    context-manager that yields a ``queue.Queue``; the backend decides
    how published events reach that queue.
    """

    @abstractmethod
    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        """Broadcast *event_name* + *payload* to all matching subscribers."""

    @abstractmethod
    def subscribe(
        self,
        max_queue_size: int = 100,
        prefixes: tuple[str, ...] | None = None,
    ) -> Iterator[queue.Queue[dict[str, Any]]]:
        """Context-managed subscription returning a ``Queue`` of envelopes."""


# ---------------------------------------------------------------------------
# In-memory (default) backend
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Subscriber:
    """Internal bookkeeping for the in-memory backend."""

    queue: queue.Queue[dict[str, Any]]
    prefixes: tuple[str, ...] | None = None

    def matches(self, event_name: str) -> bool:
        return self.prefixes is None or event_name.startswith(self.prefixes)


class InMemoryEventBackend(EventBackend):
    """Thread-safe, in-process pub/sub using ``queue.Queue`` per subscriber.

    This is the original behaviour and the default backend.
    """

    def __init__(self) -> None:
        self._subscribers: list[_Subscriber] = []
        self._lock = threading.Lock()

    # -- publish --------------------------------------------------------------

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        envelope = {"event": event_name, "payload": payload}
        for sub in subscribers:
            if not sub.matches(event_name):
                continue
            try:
                sub.queue.put_nowait(envelope)
            except queue.Full:
                continue

    # -- subscribe ------------------------------------------------------------

    @contextmanager
    def subscribe(  # type: ignore[override]  # contextmanager return
        self,
        max_queue_size: int = 100,
        prefixes: tuple[str, ...] | None = None,
    ) -> Iterator[queue.Queue[dict[str, Any]]]:
        sub = _Subscriber(
            queue=queue.Queue(maxsize=max_queue_size),
            prefixes=prefixes,
        )
        with self._lock:
            self._subscribers.append(sub)
        try:
            yield sub.queue
        finally:
            with self._lock:
                if sub in self._subscribers:
                    self._subscribers.remove(sub)


# ---------------------------------------------------------------------------
# Backend registry & factory
# ---------------------------------------------------------------------------

_BACKEND_REGISTRY: dict[str, type[EventBackend]] = {
    "memory": InMemoryEventBackend,
}

_backends_loaded = False


def _ensure_backends_loaded() -> None:
    """Import and register shipped backends on first use.

    Deferred from module-level import to avoid circular dependencies:
    ``event_backends`` imports ``EventBackend`` from this module, so
    we must not import it until this module is fully initialised.
    """
    global _backends_loaded
    if _backends_loaded:
        return
    _backends_loaded = True
    try:
        from backend.app.event_backends import _auto_register

        _auto_register()
    except Exception:
        # If the backends subpackage is unavailable (e.g. redis not
        # installed), silently skip registration.  The "memory" backend
        # is always available.
        pass


def register_event_backend(name: str, cls: type[EventBackend]) -> None:
    """Register a custom backend class under *name*.

    This allows third-party code (or a future ``backend/app/event_backends/redis.py``)
    to plug in without modifying this module.
    """
    _BACKEND_REGISTRY[name] = cls


def _create_backend(name: str) -> EventBackend:
    """Instantiate the backend identified by *name*.

    Raises ``ValueError`` for unknown names.
    """
    _ensure_backends_loaded()
    try:
        return _BACKEND_REGISTRY[name]()
    except KeyError:
        available = ", ".join(sorted(_BACKEND_REGISTRY))
        raise ValueError(f"Unknown event backend {name!r}; available: {available}") from None


# ---------------------------------------------------------------------------
# Module-level singleton (facade)
# ---------------------------------------------------------------------------

_backend: EventBackend | None = None
_backend_lock = threading.RLock()  # RLock allows re-entrancy from configure_backend


def _resolve_backend() -> EventBackend:
    """Return the active backend, creating one from settings if needed."""
    global _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        from backend.app.config import settings

        _backend = _create_backend(settings.event_backend)
        return _backend


def configure_backend(
    name: str | None = None, *, backend: EventBackend | None = None
) -> EventBackend:
    """Set (or reset) the active event backend.

    Pass *name* to select from the registry (e.g. ``"memory"``),
    or pass a pre-built *backend* instance directly.
    Calling with neither argument resets to the setting-derived default.
    """
    global _backend
    with _backend_lock:
        if backend is not None:
            _backend = backend
        elif name is not None:
            _backend = _create_backend(name)
        else:
            _backend = None
            # _resolve_backend re-acquires the RLock (safe with RLock)
            _backend = _resolve_backend()
    return _backend


def get_backend() -> EventBackend:
    """Return the currently active backend (public read accessor)."""
    return _resolve_backend()


# ---------------------------------------------------------------------------
# Public API – thin facade delegating to the active backend
# ---------------------------------------------------------------------------


def publish_event(event_name: str, payload: dict[str, Any]) -> None:
    """Publish an event via the active backend.

    Fully backward-compatible with the original module-level function.
    """
    _resolve_backend().publish(event_name, payload)


@contextmanager
def subscribe(
    max_queue_size: int = 100,
    prefixes: tuple[str, ...] | None = None,
) -> Iterator[queue.Queue[dict[str, Any]]]:
    """Subscribe to events via the active backend.

    Fully backward-compatible with the original module-level function.
    """
    with _resolve_backend().subscribe(max_queue_size=max_queue_size, prefixes=prefixes) as q:
        yield q
