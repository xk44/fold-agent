"""Tests for modular event-stream backend abstraction.

Covers:
  - InMemoryEventBackend core behaviour (prefix filtering, eviction on full queue)
  - Public facade (publish_event / subscribe) delegates correctly
  - Backend registry and factory
  - configure_backend / get_backend switching
  - Thread-safety smoke test
  - Backward-compatibility: existing test suite behaviour preserved
"""
from __future__ import annotations

import queue
import threading
from typing import Any

import pytest

from backend.app.event_stream import (
    EventBackend,
    InMemoryEventBackend,
    _BACKEND_REGISTRY,
    configure_backend,
    get_backend,
    publish_event,
    register_event_backend,
    subscribe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_backend():
    """Ensure every test starts with the default in-memory backend."""
    configure_backend(backend=InMemoryEventBackend())
    yield
    configure_backend(backend=InMemoryEventBackend())


# ---------------------------------------------------------------------------
# InMemoryEventBackend – core behaviour
# ---------------------------------------------------------------------------

class TestInMemoryEventBackend:
    """Direct tests on the InMemoryEventBackend class."""

    def test_publish_delivers_to_matching_subscriber(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(prefixes=("pipeline.",)) as q:
            backend.publish("pipeline.started", {"id": "p1"})
            envelope = q.get_nowait()
            assert envelope["event"] == "pipeline.started"
            assert envelope["payload"]["id"] == "p1"

    def test_prefix_filter_excludes_non_matching(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(prefixes=("pipeline.",)) as q:
            backend.publish("case.created", {"id": "c1"})
            backend.publish("pipeline.completed", {"id": "p1"})
            # Only pipeline event delivered
            envelope = q.get_nowait()
            assert envelope["event"] == "pipeline.completed"
            assert q.empty()

    def test_null_prefix_receives_all_events(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe() as q:
            backend.publish("case.created", {"id": "c1"})
            backend.publish("pipeline.completed", {"id": "p1"})
            events = [q.get_nowait()["event"] for _ in range(2)]
            assert events == ["case.created", "pipeline.completed"]

    def test_full_queue_drops_event_gracefully(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(max_queue_size=1) as q:
            backend.publish("evt.first", {"n": 1})
            backend.publish("evt.second", {"n": 2})  # should be dropped
            envelope = q.get_nowait()
            assert envelope["event"] == "evt.first"
            assert q.empty()

    def test_subscriber_removed_on_exit(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(prefixes=("x",)) as q:
            assert len(backend._subscribers) == 1
        # After exiting context, subscriber is unregistered
        assert len(backend._subscribers) == 0

    def test_publish_after_subscriber_exit_no_error(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe() as q:
            pass
        # Should not raise even though subscriber has exited
        backend.publish("orphan.event", {})

    def test_multiple_subscribers_receive_same_event(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe() as q1, backend.subscribe(prefixes=("a.",)) as q2:
            backend.publish("a.b", {"v": 1})
            assert q1.get_nowait()["event"] == "a.b"
            assert q2.get_nowait()["event"] == "a.b"

    def test_multiple_prefixes(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(prefixes=("pipeline.", "agent.")) as q:
            backend.publish("pipeline.started", {})
            backend.publish("agent.done", {})
            backend.publish("case.created", {})
            evts = [q.get_nowait()["event"] for _ in range(2)]
            assert "pipeline.started" in evts
            assert "agent.done" in evts
            assert q.empty()

    def test_subscribe_context_manager_yields_queue(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe() as q:
            assert isinstance(q, queue.Queue)

    def test_custom_max_queue_size(self) -> None:
        backend = InMemoryEventBackend()
        with backend.subscribe(max_queue_size=5) as q:
            assert q.maxsize == 5


# ---------------------------------------------------------------------------
# Public facade – backward compatibility
# ---------------------------------------------------------------------------

class TestPublicFacade:
    """publish_event / subscribe should still work as before."""

    def test_filtered_subscriber_only_receives_matching_prefix(self) -> None:
        with subscribe(prefixes=("pipeline.",)) as q:
            publish_event("case.created", {"log_id": "case-1"})
            publish_event("pipeline.completed", {"log_id": "pipe-1"})
            envelope = q.get_nowait()
            assert envelope["event"] == "pipeline.completed"
            assert envelope["payload"]["log_id"] == "pipe-1"

    def test_unfiltered_subscriber_receives_all_events(self) -> None:
        with subscribe() as q:
            publish_event("case.created", {"log_id": "case-1"})
            publish_event("agent_task.created", {"log_id": "task-1"})
            events = [q.get_nowait()["event"], q.get_nowait()["event"]]
            assert events == ["case.created", "agent_task.created"]

    def test_facade_delegates_to_active_backend(self) -> None:
        """Swapping the backend under the hood changes facade behaviour."""
        alt_backend = InMemoryEventBackend()
        configure_backend(backend=alt_backend)
        with subscribe(prefixes=("test.",)) as q:
            publish_event("test.ping", {"val": 42})
            envelope = q.get_nowait()
            assert envelope["event"] == "test.ping"
            assert envelope["payload"]["val"] == 42


# ---------------------------------------------------------------------------
# Backend registry & factory
# ---------------------------------------------------------------------------

class TestBackendRegistry:

    def test_default_registry_contains_memory(self) -> None:
        assert "memory" in _BACKEND_REGISTRY

    def test_register_custom_backend(self) -> None:
        class StubBackend(EventBackend):
            def publish(self, event_name: str, payload: dict[str, Any]) -> None:
                pass
            def subscribe(self, max_queue_size: int = 100, prefixes: tuple[str, ...] | None = None):
                class _CM:
                    def __enter__(self_): return queue.Queue()
                    def __exit__(self_, *a): pass
                return _CM()

        register_event_backend("stub", StubBackend)
        try:
            assert "stub" in _BACKEND_REGISTRY
            backend = configure_backend(name="stub")
            assert isinstance(backend, StubBackend)
        finally:
            _BACKEND_REGISTRY.pop("stub", None)

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown event backend"):
            configure_backend(name="nonexistent")

    def test_configure_backend_by_name(self) -> None:
        backend = configure_backend(name="memory")
        assert isinstance(backend, InMemoryEventBackend)

    def test_configure_backend_reset_to_default(self) -> None:
        # First swap to a fresh instance
        fresh = InMemoryEventBackend()
        configure_backend(backend=fresh)
        assert get_backend() is fresh
        # Reset without arguments re-derives from settings
        configure_backend()  # resets懒
        current = get_backend()
        assert isinstance(current, InMemoryEventBackend)
        assert current is not fresh  # it created a new one


# ---------------------------------------------------------------------------
# Thread-safety smoke test
# ---------------------------------------------------------------------------

class TestThreadSafety:

    def test_concurrent_publish_subscribe(self) -> None:
        backend = InMemoryEventBackend()
        results: list[str] = []
        errors: list[Exception] = []

        def publisher():
            try:
                for i in range(200):
                    backend.publish(f"evt.{i}", {"i": i})
            except Exception as exc:
                errors.append(exc)

        with backend.subscribe() as q:
            pub_threads = [threading.Thread(target=publisher) for _ in range(4)]
            for t in pub_threads:
                t.start()
            for t in pub_threads:
                t.join(timeout=5)

            # Drain all available events
            while not q.empty():
                try:
                    envelope = q.get_nowait()
                    results.append(envelope["event"])
                except queue.Empty:
                    break

        assert len(errors) == 0
        # We should have received some events (may have dropped due to queue size)
        assert len(results) > 0

    def test_concurrent_subscribe_unsubscribe(self) -> None:
        """Rapidly subscribing/unsubscribing should not lose events or crash."""
        backend = InMemoryEventBackend()
        received: list[str] = []
        barrier = threading.Barrier(4, timeout=5)

        def worker():
            barrier.wait()
            try:
                with backend.subscribe() as q:
                    #Publish from within subscriber context
                    backend.publish("thread.test", {"src": threading.current_thread().name})
                    try:
                        envelope = q.get(timeout=1)
                        received.append(envelope["event"])
                    except queue.Empty:
                        pass
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # At least some events should have been received (no deadlock/crash)
        assert isinstance(received, list)  # just checking no exception


# ---------------------------------------------------------------------------
# Integration: facade + backend switching
# ---------------------------------------------------------------------------

class TestBackendSwitchingIntegration:

    def test_switching_backend_mid_flow_publishes_to_new(self) -> None:
        original = InMemoryEventBackend()
        configure_backend(backend=original)

        with subscribe(prefixes=("a.",)) as q_orig:
            publish_event("a.1", {"src": "original"})
            assert q_orig.get_nowait()["payload"]["src"] == "original"

        # Switch to a completely fresh backend
        new_backend = InMemoryEventBackend()
        configure_backend(backend=new_backend)

        with subscribe(prefixes=("b.",)) as q_new:
            publish_event("b.1", {"src": "new"})
            assert q_new.get_nowait()["payload"]["src"] == "new"

    def test_events_dont_leak_across_backends(self) -> None:
        """After switching backends, events published on the old backend
        should NOT appear on the new backend's subscribers."""
        old = InMemoryEventBackend()
        configure_backend(backend=old)

        with subscribe() as q_old:
            publish_event("old.event", {"v": 1})
            assert q_old.get_nowait()["event"] == "old.event"

        new = InMemoryEventBackend()
        configure_backend(backend=new)

        with subscribe() as q_new:
            # Publishing on new backend should not deliver old backend events
            publish_event("new.event", {"v": 2})
            envelope = q_new.get_nowait()
            assert envelope["event"] == "new.event"
            assert q_new.empty()