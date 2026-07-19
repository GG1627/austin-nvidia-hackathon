"""Shared inter-agent data contracts (Phase 0 deliverable).

These dataclasses mirror the JSON contracts documented in docs/ARCHITECTURE.md.
All three agents should import from this module so the contracts stay in sync.

Every class provides `to_dict()` / `from_dict()` that tolerate missing keys,
so Agent 1 and Agent 2 can integrate incrementally without breaking Agent 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def _get(d: Dict[str, Any], key: str, default: Any) -> Any:
    value = d.get(key, default)
    return default if value is None else value


# ---------------------------------------------------------------------------
# Creator Context (Agent 1 -> Agent 3)
# ---------------------------------------------------------------------------

@dataclass
class CreatorProfile:
    niche: str = ""
    audience: str = ""
    preferred_length: str = ""
    posting_frequency: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CreatorProfile":
        return cls(
            niche=_get(d, "niche", ""),
            audience=_get(d, "audience", ""),
            preferred_length=_get(d, "preferred_length", ""),
            posting_frequency=_get(d, "posting_frequency", ""),
        )


@dataclass
class LearnedPattern:
    id: str
    pattern: str
    confidence: float = 0.5
    evidence_count: int = 1
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LearnedPattern":
        return cls(
            id=_get(d, "id", ""),
            pattern=_get(d, "pattern", ""),
            confidence=float(_get(d, "confidence", 0.5)),
            evidence_count=int(_get(d, "evidence_count", 1)),
            last_updated=_get(d, "last_updated", ""),
        )


@dataclass
class PendingIdea:
    title: str
    research_complete: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PendingIdea":
        return cls(
            title=_get(d, "title", ""),
            research_complete=float(_get(d, "research_complete", 0.0)),
        )


@dataclass
class CreatorContext:
    creator_profile: CreatorProfile = field(default_factory=CreatorProfile)
    learned_patterns: List[LearnedPattern] = field(default_factory=list)
    top_performing_topics: List[str] = field(default_factory=list)
    avoid_topics: List[str] = field(default_factory=list)
    pending_ideas: List[PendingIdea] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "creator_profile": self.creator_profile.to_dict(),
            "learned_patterns": [p.to_dict() for p in self.learned_patterns],
            "top_performing_topics": list(self.top_performing_topics),
            "avoid_topics": list(self.avoid_topics),
            "pending_ideas": [i.to_dict() for i in self.pending_ideas],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CreatorContext":
        return cls(
            creator_profile=CreatorProfile.from_dict(_get(d, "creator_profile", {})),
            learned_patterns=[
                LearnedPattern.from_dict(p) for p in _get(d, "learned_patterns", [])
            ],
            top_performing_topics=list(_get(d, "top_performing_topics", [])),
            avoid_topics=list(_get(d, "avoid_topics", [])),
            pending_ideas=[PendingIdea.from_dict(i) for i in _get(d, "pending_ideas", [])],
        )


# ---------------------------------------------------------------------------
# Opportunity (Agent 2 -> Agent 3)
# ---------------------------------------------------------------------------

@dataclass
class OpportunitySource:
    name: str = ""
    url: str = ""
    detail: str = ""  # e.g. "1840 upvotes" or "312 points"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OpportunitySource":
        detail = _get(d, "detail", "")
        if not detail:
            # Tolerate the raw shapes from ARCHITECTURE.md examples.
            if "upvotes" in d:
                detail = f"{d['upvotes']} upvotes"
            elif "points" in d:
                detail = f"{d['points']} points"
        return cls(name=_get(d, "name", ""), url=_get(d, "url", ""), detail=detail)


@dataclass
class Opportunity:
    id: str
    topic: str
    trend_score: float = 0.0
    niche_alignment: float = 0.0
    competition_gap: float = 0.0
    composite_score: float = 0.0
    reason: str = ""
    suggested_angle: str = ""
    sources: List[OpportunitySource] = field(default_factory=list)
    freshness: str = ""
    already_surfaced: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sources"] = [s.to_dict() for s in self.sources]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Opportunity":
        return cls(
            id=_get(d, "id", ""),
            topic=_get(d, "topic", ""),
            trend_score=float(_get(d, "trend_score", 0.0)),
            niche_alignment=float(_get(d, "niche_alignment", 0.0)),
            competition_gap=float(_get(d, "competition_gap", 0.0)),
            composite_score=float(_get(d, "composite_score", 0.0)),
            reason=_get(d, "reason", ""),
            suggested_angle=_get(d, "suggested_angle", ""),
            sources=[OpportunitySource.from_dict(s) for s in _get(d, "sources", [])],
            freshness=_get(d, "freshness", ""),
            already_surfaced=bool(_get(d, "already_surfaced", False)),
        )


# ---------------------------------------------------------------------------
# Recommendation (Agent 3 -> Creator)
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    id: str
    rank: int
    title: str
    why: str
    supporting_patterns: List[str] = field(default_factory=list)
    opportunity_id: str = ""
    confidence: float = 0.0
    action_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Recommendation":
        return cls(
            id=_get(d, "id", ""),
            rank=int(_get(d, "rank", 0)),
            title=_get(d, "title", ""),
            why=_get(d, "why", ""),
            supporting_patterns=list(_get(d, "supporting_patterns", [])),
            opportunity_id=_get(d, "opportunity_id", ""),
            confidence=float(_get(d, "confidence", 0.0)),
            action_steps=list(_get(d, "action_steps", [])),
        )


# ---------------------------------------------------------------------------
# Feedback (Creator -> Agent 1, routed through Agent 3)
# ---------------------------------------------------------------------------

FEEDBACK_ACTIONS = ("accepted", "rejected", "deferred")


@dataclass
class Feedback:
    recommendation_id: str
    action: str  # accepted | rejected | deferred
    notes: str = ""
    outcome: Optional[str] = None
    outcome_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feedback":
        return cls(
            recommendation_id=_get(d, "recommendation_id", ""),
            action=_get(d, "action", "deferred"),
            notes=_get(d, "notes", ""),
            outcome=d.get("outcome"),
            outcome_date=d.get("outcome_date"),
        )


# ---------------------------------------------------------------------------
# Cycle result (Agent 3 run log)
# ---------------------------------------------------------------------------

@dataclass
class CycleResult:
    run_number: int
    timestamp: str
    recommendations: List[Recommendation] = field(default_factory=list)
    feedback: List[Feedback] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_number": self.run_number,
            "timestamp": self.timestamp,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "feedback": [f.to_dict() for f in self.feedback],
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CycleResult":
        return cls(
            run_number=int(_get(d, "run_number", 0)),
            timestamp=_get(d, "timestamp", ""),
            recommendations=[
                Recommendation.from_dict(r) for r in _get(d, "recommendations", [])
            ],
            feedback=[Feedback.from_dict(f) for f in _get(d, "feedback", [])],
            metrics=dict(_get(d, "metrics", {})),
        )
