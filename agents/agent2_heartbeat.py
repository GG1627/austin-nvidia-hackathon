"""Heartbeat-driven Agent 2 execution.

This runner intentionally depends only on injected Agent 1 public interfaces:
a context provider (normally memory.get_context) and an episode logger
(normally memory.log_episode). Agent 2 never writes to Agent 1 tables directly.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Callable, Optional, Union
import time

from agents.agent2_handoff import build_handoff, write_latest_handoff
from agents.agent2_research import ResearchAgent

ContextProvider = Callable[[], Any]
EpisodeLogger = Callable[[str, dict[str, Any], Union[int, str]], int]


class Agent2Heartbeat:
    """Run Agent 2 repeatedly while persisting each Agent-3-ready snapshot."""

    def __init__(
        self,
        research_agent: ResearchAgent,
        context_provider: ContextProvider,
        episode_logger: EpisodeLogger,
        *,
        handoff_directory: str | Path = "memory/agent2",
        interval_seconds: float = 300,
        top_n: int = 5,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.research_agent = research_agent
        self.context_provider = context_provider
        self.episode_logger = episode_logger
        self.handoff_directory = Path(handoff_directory)
        self.interval_seconds = interval_seconds
        self.top_n = top_n

    def run_once(self, run_id: int | str) -> dict[str, Any]:
        """Collect, log, and materialize one research heartbeat."""
        context = self.context_provider()
        opportunities = self.research_agent.get_opportunities(context, top_n=self.top_n)
        for opportunity in opportunities:
            payload = asdict(self.research_agent.to_research_finding(opportunity))
            self.episode_logger("research_finding", payload, run_id)

        payload = build_handoff(
            opportunities,
            run_id=run_id,
            source_errors=self.research_agent.last_result.source_errors,
            creator_context=context,
            model=self.research_agent.ollama_model,
        )
        payload["heartbeat"] = {
            "interval_seconds": self.interval_seconds,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "research_findings_logged": len(opportunities),
        }
        write_latest_handoff(payload, self.handoff_directory)
        return payload

    def run_forever(
        self,
        run_id_provider: Callable[[], int | str],
        *,
        stop_event: Optional[Event] = None,
    ) -> None:
        """Wake on a stable interval until stopped; exceptions do not kill the loop."""
        stopper = stop_event or Event()
        while not stopper.is_set():
            run_id: int | str | None = None
            try:
                run_id = run_id_provider()
                self.run_once(run_id)
            except Exception as exc:
                self._write_failure(str(exc), run_id)
            stopper.wait(self.interval_seconds)

    def _write_failure(self, error: str, run_id: int | str | None = None) -> None:
        payload = {
            "schema_version": "agent2-handoff/v1",
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer": {"agent": "agent2_research", "model": self.research_agent.ollama_model},
            "source_errors": {"heartbeat": error},
            "opportunities": [],
        }
        write_latest_handoff(payload, self.handoff_directory)
