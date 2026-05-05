"""Persistent operator focus store — simple local-file persistence.

This module provides a lightweight, file-based mechanism for saving and
restoring the operator's focus selections across Streamlit sessions and
reruns.  It uses a single JSON file (default: ``~/.foldagent/operator_focus.json``)
and is deliberately backend-free.

The heavy lifting (which keys to persist, how to merge with existing
state) lives in :func:`event_stream.extract_restorable_focus` and
:func:`event_stream.apply_restored_focus` — both pure, testable
functions.  This module handles only the I/O boundary.

Typical usage in ``dashboard.py``::

    from frontend.app.operator_focus_store import (
        load_operator_focus,
        save_operator_focus,
    )
    from frontend.app.event_stream import (
        extract_restorable_focus,
        apply_restored_focus,
    )

    # On session init — restore
    saved = load_operator_focus()
    if saved:
        apply_restored_focus(dict(st.session_state), saved)

    # On each render — persist
    focus = extract_restorable_focus(dict(st.session_state))
    save_operator_focus(focus)

The module is intentionally tolerant: if the file is missing, corrupt,
or unreadable, :func:`load_operator_focus` returns an empty dict so
the dashboard degrades gracefully to fresh-snapshot behaviour.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_DIR = Path(os.path.expanduser("~/.foldagent"))
_DEFAULT_FILENAME = "operator_focus.json"


def default_focus_path() -> Path:
    """Return the default path for the operator focus file.

    The path is ``~/.foldagent/operator_focus.json``.  The directory is
    created on demand by :func:`save_operator_focus`.
    """
    return _DEFAULT_DIR / _DEFAULT_FILENAME


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_operator_focus(path: Path | None = None) -> dict[str, Any]:
    """Load a previously saved operator focus snapshot from disk.

    Args:
        path: Optional path override.  Defaults to
            :func:`default_focus_path`.

    Returns:
        A dict (possibly empty) suitable for passing to
        :func:`event_stream.apply_restored_focus`.  Returns ``{}`` if
        the file does not exist, is not valid JSON, or is missing the
        expected ``version`` header.
    """
    focus_path = path or default_focus_path()
    if not focus_path.exists():
        return {}

    try:
        raw = focus_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}

    if not isinstance(data, dict):
        return {}

    # Version gate: only load matching schema versions
    version = data.get("version")
    if version != 1:
        return {}

    focus = data.get("focus")
    if not isinstance(focus, dict):
        return {}

    return focus


def save_operator_focus(
    focus: dict[str, Any],
    path: Path | None = None,
) -> None:
    """Persist an operator focus snapshot to disk.

    The file is written atomically (write to temp, then rename) so
    that a concurrent reader never sees a partial write.

    Args:
        focus: A focus dict as returned by
            :func:`event_stream.extract_restorable_focus`.
        path: Optional path override.  Defaults to
            :func:`default_focus_path`.
    """
    focus_path = path or default_focus_path()

    payload = {"version": 1, "focus": focus}

    # Ensure directory exists
    focus_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file in same dir, then rename
    tmp_path = focus_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.rename(focus_path)
    except OSError:
        # Best-effort: if rename fails (cross-filesystem, perms, etc.),
        # try direct write.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            focus_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # Silently swallow — the dashboard should never crash