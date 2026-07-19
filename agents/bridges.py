"""Bridges that connect the real Agent 1 / Agent 2 implementations to Agent 3.

Agent 3 (agents/agent3_strategist.py) depends on the duck-typed interfaces
documented in docs/AGENTS.md:

    memory_agent.get_creator_context() -> contracts.CreatorContext
    memory_agent.ingest_feedback(feedback, recommendation=None) -> None
    research_agent.get_opportunities(creator_context) -> List[contracts.Opportunity]

The real implementations speak different dialects: Agent 1 exposes
get_context()/log_episode() over Supabase, and Agent 2 materializes its runs
as the memory/agent2/latest.json handoff artifact with its own Opportunity
shape (trend_velocity/reasoning/source dicts). This module translates both
so main.py can wire real agents in without either side changing.

Supabase modules are imported lazily so that .env is loaded (load_env in
main.py) before agents.db reads its environment variables.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from agents.contracts import (
    CreatorContext,
    CreatorProfile,
    Feedback,
    LearnedPattern,
    Opportunity,
    OpportunitySource,
    PendingIdea,
    Recommendation,
)

DEFAULT_HANDOFF_PATH = os.path.join("memory", "agent2", "latest.json")
DEFAULT_SURFACED_PATH = os.path.join("memory", "agent2", "surfaced.json")
CONTEXT_TASK = "What should this creator make next?"


# ---------------------------------------------------------------------------
# Agent 2 -> Agent 3: Opportunity adapter + handoff reader
# ---------------------------------------------------------------------------

def opportunity_from_handoff(item: Dict[str, Any]) -> Opportunity:
    """Map one agent2_research Opportunity dict to the contracts.Opportunity
    shape Agent 3 consumes (trend_velocity->trend_score, reasoning->reason,
    raw source dicts -> OpportunitySource)."""
    sources = []
    for src in item.get("sources", []):
        detail = src.get("title", "") or ""
        engagement = src.get("engagement")
        if engagement:
            detail = f"{detail} · {engagement:.0f} engagement" if detail else f"{engagement:.0f} engagement"
        sources.append(OpportunitySource(name=src.get("name", ""), url=src.get("url", ""), detail=detail))
    return Opportunity(
        id=item.get("id", ""),
        topic=item.get("topic", ""),
        trend_score=float(item.get("trend_velocity", item.get("trend_score", 0.0)) or 0.0),
        niche_alignment=float(item.get("niche_alignment", 0.0) or 0.0),
        competition_gap=float(item.get("competition_gap", 0.0) or 0.0),
        composite_score=float(item.get("composite_score", 0.0) or 0.0),
        reason=item.get("reasoning", item.get("reason", "")) or "",
        suggested_angle=item.get("suggested_angle", "") or "",
        sources=sources,
        freshness=item.get("freshness", "") or "",
    )


class HandoffResearchAgent:
    """Research agent backed by the Agent 2 heartbeat handoff artifact.

    Reads memory/agent2/latest.json (written by Agent2Heartbeat) instead of
    running live connectors, so Agent 3 consumes real research output without
    importing Agent 2 internals. Dedup consults the memory agent's surfaced
    ids when it exposes get_surfaced_topics().
    """

    def __init__(self, memory_agent: Any = None, handoff_path: str = DEFAULT_HANDOFF_PATH) -> None:
        self.memory = memory_agent
        self.handoff_path = handoff_path
        self.last_duplicates_filtered = 0
        self.last_generated_at = ""
        self.last_source_errors: Dict[str, str] = {}

    @staticmethod
    def available(handoff_path: str = DEFAULT_HANDOFF_PATH) -> bool:
        """A handoff is usable only when it parses and actually carries
        opportunities — a failure snapshot with an empty list must not
        shadow the mock research fallback."""
        try:
            with open(handoff_path, "r", encoding="utf-8") as fh:
                return bool(json.load(fh).get("opportunities"))
        except (OSError, json.JSONDecodeError):
            return False

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.handoff_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}

    def get_opportunities(self, creator_context: CreatorContext) -> List[Opportunity]:
        payload = self._load()
        self.last_generated_at = payload.get("generated_at", "")
        self.last_source_errors = dict(payload.get("source_errors", {}))
        surfaced = set()
        if self.memory is not None and hasattr(self.memory, "get_surfaced_topics"):
            surfaced = set(self.memory.get_surfaced_topics())

        self.last_duplicates_filtered = 0
        opportunities: List[Opportunity] = []
        for item in payload.get("opportunities", []):
            opp = opportunity_from_handoff(item)
            if opp.id in surfaced:
                self.last_duplicates_filtered += 1
                continue
            opportunities.append(opp)
        opportunities.sort(key=lambda o: o.composite_score, reverse=True)
        return opportunities


# ---------------------------------------------------------------------------
# Agent 3 -> Agent 1: feedback + consolidation bridge over Supabase
# ---------------------------------------------------------------------------

class SupabaseMemoryBridge:
    """Adapt the real Agent 1 memory layer to Agent 3's memory interface.

    Reads context through memory.get_context(), writes recommendation and
    feedback episodes through memory.log_episode(), and closes the learning
    loop by running the consolidation engine after each cycle. Surfaced
    opportunity ids are tracked in a local JSON file (the frozen Supabase
    schema has no surfaced table).
    """

    def __init__(
        self,
        context_task: str = CONTEXT_TASK,
        surfaced_path: str = DEFAULT_SURFACED_PATH,
    ) -> None:
        self.context_task = context_task
        self.surfaced_path = surfaced_path
        self.run_id: Optional[int] = None

    @staticmethod
    def available() -> bool:
        return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))

    # -- context ------------------------------------------------------------

    def get_creator_context(self) -> CreatorContext:
        from agents.memory import get_context

        ctx = get_context(self.context_task)
        profile = ctx.get("creator_profile") or {}
        patterns = [
            LearnedPattern(
                id=f"insight_{i['id']}",
                pattern=i.get("statement") or "",
                confidence=float(i.get("confidence") or 0.5),
            )
            for i in list(ctx.get("core_insights") or []) + list(ctx.get("relevant_insights") or [])
            if i.get("statement")
        ]
        return CreatorContext(
            creator_profile=CreatorProfile(
                niche=profile.get("niche", "") or "",
                audience=profile.get("audience", profile.get("audience_description", "")) or "",
                preferred_length=profile.get("preferred_length", "") or "",
                posting_frequency=profile.get("posting_frequency", "") or "",
            ),
            learned_patterns=patterns,
            top_performing_topics=list(profile.get("top_performing_topics", []) or []),
            avoid_topics=list(profile.get("avoid_topics", []) or []),
            pending_ideas=[
                PendingIdea.from_dict(i) for i in profile.get("pending_ideas", []) or []
            ],
        )

    # -- run lifecycle ------------------------------------------------------

    def increment_run_count(self) -> int:
        from agents.db import get_client

        try:
            row = get_client().insert("runs", {"metrics": None})
            self.run_id = int(row["id"])
            return self.run_id
        except Exception as exc:  # noqa: BLE001 — a dead network must not kill the cycle
            print(f"  [bridge] could not create Supabase run ({exc}); episodes will carry run_id=null")
            self.run_id = None
            return 0

    # -- feedback -> episodes -> consolidation -------------------------------

    def ingest_feedback(
        self, feedback: Feedback, recommendation: Optional[Recommendation] = None
    ) -> None:
        from agents.memory import log_episode

        try:
            if recommendation is not None:
                log_episode("recommendation", recommendation.to_dict(), self.run_id)
            log_episode("feedback", feedback.to_dict(), self.run_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  [bridge] could not log feedback episode ({exc})")

    def consolidate(self) -> None:
        """Called by Agent 3 after feedback ingestion each cycle."""
        from agents.consolidation import run_consolidation

        try:
            result = run_consolidation(run_id=self.run_id)
            if isinstance(result, dict):
                summary = ", ".join(f"{k}={v}" for k, v in result.items() if isinstance(v, (int, float)))
                if summary:
                    print(f"  [Agent 1] Consolidation pass: {summary}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [bridge] consolidation failed ({exc}); episodes remain unconsolidated")

    def pattern_count(self) -> int:
        return len(self.get_creator_context().learned_patterns)

    # -- surfaced-opportunity dedup (local store) ----------------------------

    def get_surfaced_topics(self) -> List[str]:
        try:
            with open(self.surfaced_path, "r", encoding="utf-8") as fh:
                return list(json.load(fh))
        except (OSError, json.JSONDecodeError):
            return []

    def mark_surfaced(self, opportunity_id: str) -> None:
        surfaced = self.get_surfaced_topics()
        if opportunity_id in surfaced:
            return
        surfaced.append(opportunity_id)
        os.makedirs(os.path.dirname(self.surfaced_path) or ".", exist_ok=True)
        with open(self.surfaced_path, "w", encoding="utf-8") as fh:
            json.dump(surfaced, fh, indent=2)


# ---------------------------------------------------------------------------
# Wiring factories (used by main.py and scripts/serve_dashboard.py)
# ---------------------------------------------------------------------------

def build_memory_agent(force_mock: bool = False) -> Tuple[Any, str]:
    """Real Supabase-backed Agent 1 when configured, mock otherwise."""
    from agents.stubs import MockMemoryAgent

    if not force_mock and SupabaseMemoryBridge.available():
        return SupabaseMemoryBridge(), "Supabase memory layer"
    return MockMemoryAgent(), "mock memory (set SUPABASE_URL/_SERVICE_KEY for the real layer)"


def build_research_agent(memory_agent: Any, force_mock: bool = False) -> Tuple[Any, str]:
    """Agent 2 handoff artifact when one exists, mock sample pool otherwise."""
    from agents.stubs import MockResearchAgent

    if not force_mock and HandoffResearchAgent.available():
        agent = HandoffResearchAgent(memory_agent)
        return agent, f"Agent 2 handoff ({agent.handoff_path})"
    return MockResearchAgent(memory_agent), "mock research (run scripts/run_agent2_heartbeat.py for live data)"
