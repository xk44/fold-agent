"""Pluggable event-stream backend implementations.

Each submodule defines a backend class and registers it into the
``_BACKEND_REGISTRY`` via ``register_event_backend``.  The core
``event_stream`` module calls ``_auto_register()`` at import time
so users never need to import this package explicitly.
"""

from backend.app.event_backends.redis_backend import RedisEventBackend  # noqa: F401


def _auto_register() -> None:
    """Register all shipped backends into the global registry.

    Called by ``event_stream`` at module-load time.  Defined as a
    function (rather than at import-time side-effect) to avoid
    circular imports – ``redis_backend`` can import the ABC
    ``EventBackend`` from ``event_stream`` without also pulling in
    ``register_event_backend`` at module level.
    """
    from backend.app.event_stream import register_event_backend

    register_event_backend("redis", RedisEventBackend)