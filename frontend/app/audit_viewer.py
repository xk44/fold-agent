from __future__ import annotations

import json


def build_audit_action_options(entries: list[dict] | None) -> list[str]:
    actions = sorted({entry.get("action") for entry in entries or [] if entry.get("action")})
    return ["all", *actions]


def _entry_search_blob(entry: dict) -> str:
    parts = [
        entry.get("id"),
        entry.get("action"),
        entry.get("actor"),
        entry.get("safety_gate_result"),
    ]
    details = entry.get("details")
    if details is not None:
        parts.append(json.dumps(details, sort_keys=True))
    return " ".join(str(part) for part in parts if part).lower()


def filter_audit_entries(entries: list[dict] | None, *, selected_action: str = "all", query: str = "") -> list[dict]:
    filtered = list(entries or [])
    if selected_action and selected_action != "all":
        filtered = [entry for entry in filtered if entry.get("action") == selected_action]
    if query.strip():
        query_lower = query.strip().lower()
        filtered = [entry for entry in filtered if query_lower in _entry_search_blob(entry)]
    return sorted(filtered, key=lambda entry: entry.get("timestamp") or "", reverse=True)


def format_audit_entry_preview(entry: dict) -> str:
    details = entry.get("details") or {}
    detail_parts = []
    for key, value in details.items():
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
        else:
            rendered = str(value)
        detail_parts.append(f"{key}={rendered}")
    detail_summary = "; ".join(detail_parts) if detail_parts else "no details"
    return (
        f"{entry.get('timestamp') or 'unknown time'} · {entry.get('action') or 'unknown action'}\n"
        f"actor={entry.get('actor') or 'unknown'} · gate={entry.get('safety_gate_result') or 'unknown'}\n"
        f"{detail_summary}"
    )
