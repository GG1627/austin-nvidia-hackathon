"""Versioned Agent 2 handoff artifact consumed by Agent 3.

The durable source of learning remains Agent 1's episode/insight store. This module
only materializes a portable snapshot of the current live-research run so the
strategist can read it without importing Agent 2 internals.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable

from agents.agent2_research import Opportunity

HANDOFF_SCHEMA_VERSION = "agent2-handoff/v1"
HISTORY_RETENTION = 100  # newest snapshots kept in history/


def build_handoff(
    opportunities: Iterable[Opportunity],
    *,
    run_id: int | str,
    source_errors: dict[str, str],
    creator_context: Any,
    model: str,
) -> dict[str, Any]:
    """Create the stable Agent 2 -> Agent 3 payload."""
    context = _context_summary(creator_context)
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": {"agent": "agent2_research", "model": model},
        "context_basis": context,
        "source_errors": dict(source_errors),
        "opportunities": [asdict(item) for item in opportunities],
    }


def write_latest_handoff(payload: dict[str, Any], directory: str | Path = "memory/agent2") -> Path:
    """Atomically replace latest.json and retain an immutable per-beat snapshot.

    Snapshot names are timestamp-prefixed so repeated run_ids (standalone mode
    reuses "local" every beat) never overwrite earlier snapshots; only the
    newest HISTORY_RETENTION files are kept."""
    root = Path(directory)
    history = root / "history"
    history.mkdir(parents=True, exist_ok=True)

    stamp = re.sub(r"[^0-9T]", "", str(payload.get("generated_at", ""))[:19]) or "unknown"
    _atomic_json_write(history / f"{stamp}-{payload['run_id']}.json", payload)
    for stale in sorted(history.glob("*.json"))[:-HISTORY_RETENTION]:
        stale.unlink(missing_ok=True)
    latest = root / "latest.json"
    _atomic_json_write(latest, payload)
    return latest


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    shutil.move(str(temporary), str(path))


def _context_summary(context: Any) -> dict[str, Any]:
    if isinstance(context, dict):
        profile = dict(context.get("creator_profile") or context.get("profile") or {})
        core = list(context.get("core_insights") or [])
        relevant = list(context.get("relevant_insights") or [])
    else:
        profile_value = getattr(context, "creator_profile", None) or getattr(context, "profile", None) or {}
        profile = dict(profile_value) if isinstance(profile_value, dict) else getattr(profile_value, "__dict__", {})
        core = list(getattr(context, "core_insights", []) or [])
        relevant = list(getattr(context, "relevant_insights", []) or [])
    return {
        "creator_profile": profile,
        "core_insight_ids": [item.get("id") for item in core if isinstance(item, dict) and item.get("id") is not None],
        "relevant_insight_ids": [item.get("id") for item in relevant if isinstance(item, dict) and item.get("id") is not None],
    }
