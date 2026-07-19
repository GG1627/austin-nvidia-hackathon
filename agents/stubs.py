"""Stand-in implementations of Agent 1 (memory) and Agent 2 (research).

These exist so Agent 3 can be built, tested, and demoed end-to-end before the
real agents land. They implement the EXACT interfaces documented in
docs/AGENTS.md, persist to the same memory/knowledge_graph.json schema from
docs/ARCHITECTURE.md, and exhibit simple-but-real recursive learning
(feedback moves pattern confidence, dedup filters repeat opportunities).

INTEGRATION: to swap in the real agents, replace the two constructor calls in
main.py (see docs/AGENT3_INTEGRATION.md). Agent 3 only depends on:
    memory_agent.get_creator_context() -> CreatorContext
    memory_agent.ingest_feedback(feedback, recommendation=None) -> None
    research_agent.get_opportunities(creator_context) -> List[Opportunity]
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from typing import Dict, List, Optional

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


def _today() -> str:
    return _dt.date.today().isoformat()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ---------------------------------------------------------------------------
# Mock Agent 1 — Creator Memory Brain
# ---------------------------------------------------------------------------

_EMPTY_GRAPH = {
    "version": 1,
    "last_updated": "",
    "run_count": 0,
    "creator_profile": {},
    "content_items": [],
    "learned_patterns": [],
    "surfaced_opportunities": [],
    "acceptance_history": [],
    "metrics": {},
}

_DEMO_PROFILE = {
    "niche": "AI tools for developers",
    "audience": "engineers, 25-40",
    "preferred_length": "10-15 minutes",
    "posting_frequency": "weekly",
    "top_performing_topics": ["LLM benchmarks", "local AI", "NVIDIA tools"],
    "avoid_topics": ["crypto", "politics"],
    "pending_ideas": [
        {"title": "NVIDIA Claw Deep Dive", "research_complete": 0.8},
    ],
}


class MockMemoryAgent:
    """Persistent stand-in for Agent 1. Learns from feedback across runs."""

    def __init__(self, graph_path: str = "memory/knowledge_graph.json") -> None:
        self.graph_path = graph_path
        self.graph = self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> dict:
        if os.path.exists(self.graph_path):
            with open(self.graph_path, "r", encoding="utf-8") as fh:
                graph = json.load(fh)
            for key, default in _EMPTY_GRAPH.items():
                graph.setdefault(key, json.loads(json.dumps(default)))
            return graph
        graph = json.loads(json.dumps(_EMPTY_GRAPH))
        graph["creator_profile"] = json.loads(json.dumps(_DEMO_PROFILE))
        return graph

    def save(self) -> None:
        self.graph["last_updated"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.graph_path) or ".", exist_ok=True)
        tmp_path = self.graph_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self.graph, fh, indent=2)
        os.replace(tmp_path, self.graph_path)

    # -- Agent 1 public API (documented contract) ---------------------------

    def get_creator_context(self) -> CreatorContext:
        profile = self.graph.get("creator_profile", {})
        return CreatorContext(
            creator_profile=CreatorProfile.from_dict(profile),
            learned_patterns=[
                LearnedPattern.from_dict(p)
                for p in self.graph.get("learned_patterns", [])
            ],
            top_performing_topics=list(profile.get("top_performing_topics", [])),
            avoid_topics=list(profile.get("avoid_topics", [])),
            pending_ideas=[
                PendingIdea.from_dict(i) for i in profile.get("pending_ideas", [])
            ],
        )

    def ingest_feedback(
        self,
        feedback: Feedback,
        recommendation: Optional[Recommendation] = None,
    ) -> None:
        """Core of the recursive loop: feedback updates stored conclusions."""
        self.graph["acceptance_history"].append(
            {**feedback.to_dict(), "date": _today()}
        )

        patterns: List[dict] = self.graph["learned_patterns"]
        by_id: Dict[str, dict] = {p["id"]: p for p in patterns}

        if feedback.action == "accepted":
            reinforced = False
            if recommendation:
                for pid in recommendation.supporting_patterns:
                    if pid in by_id:
                        p = by_id[pid]
                        p["confidence"] = round(min(0.95, p["confidence"] + 0.08), 2)
                        p["evidence_count"] += 1
                        p["last_updated"] = _today()
                        reinforced = True
            if recommendation and not reinforced:
                # First signal about this kind of content: store a conclusion.
                topic_key = _slug(recommendation.title)[:40] or "general"
                pid = f"p_{topic_key}"
                if pid in by_id:
                    by_id[pid]["confidence"] = round(
                        min(0.95, by_id[pid]["confidence"] + 0.08), 2
                    )
                    by_id[pid]["evidence_count"] += 1
                    by_id[pid]["last_updated"] = _today()
                else:
                    patterns.append(
                        {
                            "id": pid,
                            "pattern": (
                                f"Creator responds well to content like "
                                f"'{recommendation.title}'"
                            ),
                            "confidence": 0.5,
                            "evidence_count": 1,
                            "created": _today(),
                            "last_updated": _today(),
                        }
                    )
        elif feedback.action == "rejected":
            if recommendation:
                for pid in recommendation.supporting_patterns:
                    if pid in by_id:
                        p = by_id[pid]
                        p["confidence"] = round(max(0.1, p["confidence"] - 0.05), 2)
                        p["last_updated"] = _today()
                reason = feedback.notes or "no reason given"
                pid = f"p_avoid_{_slug(recommendation.title)[:36] or 'general'}"
                if pid not in by_id:
                    patterns.append(
                        {
                            "id": pid,
                            "pattern": (
                                f"Creator rejected '{recommendation.title}' "
                                f"({reason})"
                            ),
                            "confidence": 0.6,
                            "evidence_count": 1,
                            "created": _today(),
                            "last_updated": _today(),
                        }
                    )
        # "deferred" is recorded in history but does not move confidence.
        self.save()

    # -- helpers used by Agent 2 (dedup) and Agent 3 (metrics) --------------

    def increment_run_count(self) -> int:
        self.graph["run_count"] = int(self.graph.get("run_count", 0)) + 1
        self.save()
        return self.graph["run_count"]

    def get_surfaced_topics(self) -> List[str]:
        return list(self.graph.get("surfaced_opportunities", []))

    def mark_surfaced(self, opportunity_id: str) -> None:
        surfaced = self.graph.setdefault("surfaced_opportunities", [])
        if opportunity_id not in surfaced:
            surfaced.append(opportunity_id)
        self.save()

    def pattern_count(self) -> int:
        return len(self.graph.get("learned_patterns", []))

    def acceptance_rate(self) -> Optional[float]:
        history = [
            h for h in self.graph.get("acceptance_history", [])
            if h.get("action") in ("accepted", "rejected")
        ]
        if not history:
            return None
        accepted = sum(1 for h in history if h["action"] == "accepted")
        return accepted / len(history)


# ---------------------------------------------------------------------------
# Mock Agent 2 — Research & Opportunity Monitor
# ---------------------------------------------------------------------------

# Deterministic sample pool standing in for live Reddit/HN/Trends data.
_SAMPLE_POOL = [
    {
        "topic": "NVIDIA Claw Recursive Agents",
        "trend_score": 94, "niche_alignment": 91, "competition_gap": 78,
        "reason": "Rapidly trending, matches creator's top performing category, low saturation",
        "suggested_angle": "Building Recursive Agents with NVIDIA Claw",
        "sources": [
            {"name": "Reddit r/LocalLLaMA", "url": "https://reddit.com/r/LocalLLaMA", "detail": "1840 upvotes"},
            {"name": "Hacker News", "url": "https://news.ycombinator.com", "detail": "312 points"},
        ],
    },
    {
        "topic": "Local LLM benchmark shootout",
        "trend_score": 81, "niche_alignment": 95, "competition_gap": 60,
        "reason": "Evergreen high-interest topic in creator's strongest category",
        "suggested_angle": "I benchmarked 7 local LLMs on one RTX 5090",
        "sources": [
            {"name": "Reddit r/LocalLLaMA", "url": "https://reddit.com/r/LocalLLaMA", "detail": "960 upvotes"},
        ],
    },
    {
        "topic": "Crypto mining on gaming GPUs",
        "trend_score": 70, "niche_alignment": 20, "competition_gap": 30,
        "reason": "Trending but off-niche for this creator",
        "suggested_angle": "Is GPU crypto mining back?",
        "sources": [
            {"name": "Google Trends", "url": "https://trends.google.com", "detail": "rising"},
        ],
    },
    {
        "topic": "NVIDIA NIM microservices",
        "trend_score": 76, "niche_alignment": 88, "competition_gap": 82,
        "reason": "Underexplored official tooling; strong fit with NVIDIA tools content",
        "suggested_angle": "Ship an AI app in 20 minutes with NVIDIA NIM",
        "sources": [
            {"name": "NVIDIA Newsroom", "url": "https://nvidianews.nvidia.com", "detail": "official RSS"},
            {"name": "Hacker News", "url": "https://news.ycombinator.com", "detail": "154 points"},
        ],
    },
    {
        "topic": "Agentic coding assistants compared",
        "trend_score": 88, "niche_alignment": 90, "competition_gap": 55,
        "reason": "High search velocity, benchmark-style comparison fits creator format",
        "suggested_angle": "Claude Code vs Cursor vs Copilot: real project test",
        "sources": [
            {"name": "Reddit r/programming", "url": "https://reddit.com/r/programming", "detail": "1200 upvotes"},
        ],
    },
    {
        "topic": "Open-weights model releases this week",
        "trend_score": 72, "niche_alignment": 84, "competition_gap": 66,
        "reason": "Fresh releases drive spike interest; fits local AI category",
        "suggested_angle": "This week's open-weights drops, tested locally",
        "sources": [
            {"name": "GitHub Trending", "url": "https://github.com/trending", "detail": "3 repos trending"},
        ],
    },
    {
        "topic": "RAG is dead? Long-context vs retrieval",
        "trend_score": 79, "niche_alignment": 82, "competition_gap": 48,
        "reason": "Hot debate topic with benchmarkable claims",
        "suggested_angle": "I tested long-context vs RAG so you don't have to",
        "sources": [
            {"name": "Hacker News", "url": "https://news.ycombinator.com", "detail": "287 points"},
        ],
    },
    {
        "topic": "Fine-tuning on consumer hardware",
        "trend_score": 68, "niche_alignment": 89, "competition_gap": 71,
        "reason": "Persistent audience demand in local AI category",
        "suggested_angle": "Fine-tune a 7B model on your gaming PC (full guide)",
        "sources": [
            {"name": "Reddit r/LocalLLaMA", "url": "https://reddit.com/r/LocalLLaMA", "detail": "740 upvotes"},
        ],
    },
    {
        "topic": "NVIDIA DGX Spark first look",
        "trend_score": 83, "niche_alignment": 86, "competition_gap": 74,
        "reason": "New hardware launch, official interest spike, few hands-on videos",
        "suggested_angle": "DGX Spark hands-on: what it means for local AI",
        "sources": [
            {"name": "NVIDIA Newsroom", "url": "https://nvidianews.nvidia.com", "detail": "official RSS"},
        ],
    },
    {
        "topic": "GPU inference cost optimization",
        "trend_score": 64, "niche_alignment": 85, "competition_gap": 77,
        "reason": "Underserved practical topic for engineering audience",
        "suggested_angle": "Cut your LLM inference bill 10x: a practical guide",
        "sources": [
            {"name": "Hacker News", "url": "https://news.ycombinator.com", "detail": "198 points"},
        ],
    },
    {
        "topic": "Speculative decoding explained",
        "trend_score": 61, "niche_alignment": 80, "competition_gap": 83,
        "reason": "Technical deep-dive gap; low competition, loyal-audience topic",
        "suggested_angle": "Why speculative decoding makes local LLMs 3x faster",
        "sources": [
            {"name": "GitHub Trending", "url": "https://github.com/trending", "detail": "2 repos trending"},
        ],
    },
    {
        "topic": "MLPerf results breakdown",
        "trend_score": 66, "niche_alignment": 87, "competition_gap": 69,
        "reason": "Benchmark-format topic; recurring seasonal interest",
        "suggested_angle": "MLPerf explained: what the new results actually mean",
        "sources": [
            {"name": "Hacker News", "url": "https://news.ycombinator.com", "detail": "143 points"},
        ],
    },
    {
        "topic": "Vision-language models on-device",
        "trend_score": 73, "niche_alignment": 81, "competition_gap": 72,
        "reason": "Rising interest, fits local AI category, few practical demos",
        "suggested_angle": "Running vision-language models on a laptop GPU",
        "sources": [
            {"name": "Reddit r/LocalLLaMA", "url": "https://reddit.com/r/LocalLLaMA", "detail": "610 upvotes"},
        ],
    },
]

# Documented scoring weights (docs/AGENTS.md).
_WEIGHTS = {"trend": 0.35, "niche": 0.35, "gap": 0.20, "recency": 0.10}


class MockResearchAgent:
    """Deterministic stand-in for Agent 2. Dedups against Agent 1 memory."""

    def __init__(self, memory_agent: MockMemoryAgent, top_n: int = 5) -> None:
        self.memory = memory_agent
        self.top_n = top_n
        self.last_duplicates_filtered = 0

    def get_opportunities(self, creator_context: CreatorContext) -> List[Opportunity]:
        surfaced = set(self.memory.get_surfaced_topics())
        avoid = [t.lower() for t in creator_context.avoid_topics]
        self.last_duplicates_filtered = 0

        opportunities: List[Opportunity] = []
        for raw in _SAMPLE_POOL:
            opp_id = f"opp_{_slug(raw['topic'])}"
            if opp_id in surfaced:
                self.last_duplicates_filtered += 1
                continue
            recency = 90  # sample pool is treated as fresh
            composite = round(
                raw["trend_score"] * _WEIGHTS["trend"]
                + raw["niche_alignment"] * _WEIGHTS["niche"]
                + raw["competition_gap"] * _WEIGHTS["gap"]
                + recency * _WEIGHTS["recency"]
            )
            opportunities.append(
                Opportunity(
                    id=opp_id,
                    topic=raw["topic"],
                    trend_score=raw["trend_score"],
                    niche_alignment=raw["niche_alignment"],
                    competition_gap=raw["competition_gap"],
                    composite_score=composite,
                    reason=raw["reason"],
                    suggested_angle=raw["suggested_angle"],
                    sources=[OpportunitySource.from_dict(s) for s in raw["sources"]],
                    freshness=_today(),
                    already_surfaced=False,
                )
            )

        # Flag (rather than hide) off-niche topics so Agent 3's avoid-list
        # filtering is exercised end-to-end.
        opportunities.sort(key=lambda o: o.composite_score, reverse=True)
        return opportunities[: self.top_n]
