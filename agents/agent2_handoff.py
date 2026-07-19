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
import shutil
from typing import Any, Iterable

from agents.agent2_research import Opportunity

HANDOFF_SCHEMA_VERSION = "agent2-handoff/v1"


class UnsupportedHandoffVersion(ValueError):
    """Raised when a handoff payload's schema_version major isn't one this consumer understands."""


def _schema_major(version: str) -> str:
    return version.split("/", 1)[-1] if "/" in version else version


def validate_schema_version(payload: dict[str, Any]) -> None:
    """Reject a handoff payload whose schema_version major this consumer doesn't understand.

    Per docs/AGENT2_HANDOFF.md: "Consumers must reject unknown major versions rather than
    silently guessing field meanings." Agent 3 (or any other consumer) should call this
    before trusting `payload["opportunities"]` / `payload["context_basis"]` field shapes.
    """
    version = payload.get("schema_version")
    if not isinstance(version, str) or not version.startswith("agent2-handoff/"):
        raise UnsupportedHandoffVersion(f"Unrecognized handoff schema_version: {version!r}")
    if _schema_major(version) != _schema_major(HANDOFF_SCHEMA_VERSION):
        raise UnsupportedHandoffVersion(
            f"Unsupported handoff schema_version: {version!r} "
            f"(this consumer understands {HANDOFF_SCHEMA_VERSION!r})"
        )


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
    """Atomically replace latest.json and retain an immutable per-run snapshot."""
    root = Path(directory)
    history = root / "history"
    history.mkdir(parents=True, exist_ok=True)

    run_id = str(payload["run_id"])
    _atomic_json_write(history / f"{run_id}.json", payload)
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
