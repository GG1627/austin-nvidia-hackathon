"""
Agent 1 - Memory & Knowledge Engineer
Data models for the Recursive Creator Intelligence System.

These mirror db/schema.sql exactly. Field names here ARE the frozen
contract Agent 2 and Agent 3 build against — do not rename without
updating the schema and every consumer.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from datetime import datetime

# ---------------------------------------------------------------------------
# Lifecycle & classification types
# ---------------------------------------------------------------------------

InsightStatus = Literal["hypothesis", "validated", "core", "deprecated"]
VolatilityClass = Literal["stable", "semi_stable", "volatile"]
EpisodeKind = Literal[
    "observation",
    "recommendation",
    "outcome",
    "feedback",
    "research_finding",
    "onboarding_finding",
]
NodeType = Literal["creator", "topic", "video", "audience_segment", "opportunity"]

# ---------------------------------------------------------------------------
# Frozen payload contracts (spec section 6) — shared with Agent 2 & Agent 3
# ---------------------------------------------------------------------------


@dataclass
class OnboardingFindingPayload:
    video_title: str
    published_at: str  # ISO-8601
    duration_minutes: float
    views: int
    retention_pct: float  # 0-100
    topic_tags: List[str] = field(default_factory=list)
    raw_ref: Optional[str] = None


@dataclass
class ResearchFindingPayload:
    source: str
    topic: str
    trend_score: float
    reason: str
    suggested_angle: str
    raw_ref: Optional[str] = None


@dataclass
class RecommendationPayload:
    statement: str
    reasoning: str
    cited_insight_ids: List[int] = field(default_factory=list)
    predicted_outcome: dict = field(default_factory=dict)


@dataclass
class OutcomePayload:
    recommendation_episode_id: int
    actual: dict
    prediction_correct: bool


@dataclass
class FeedbackPayload:
    recommendation_episode_id: int
    action: str  # accepted | rejected | ignored | modified
    creator_note: str = ""


@dataclass
class ObservationPayload:
    note: str


# ---------------------------------------------------------------------------
# Table-mirroring domain objects (spec section 5) — field names match
# db/schema.sql column names 1:1.
# ---------------------------------------------------------------------------


@dataclass
class Run:
    id: Optional[int] = None
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metrics: dict = field(default_factory=dict)


@dataclass
class Episode:
    id: Optional[int] = None
    run_id: Optional[int] = None
    ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    kind: EpisodeKind = "observation"
    payload: dict = field(default_factory=dict)
    consolidated: bool = False
    embedding: Optional[List[float]] = None


@dataclass
class Insight:
    id: Optional[int] = None
    statement: str = ""
    category: Optional[str] = None  # format | topic | timing | audience | style
    confidence: float = 0.3
    status: InsightStatus = "hypothesis"
    evidence_for: int = 0
    evidence_against: int = 0
    supporting_episode_ids: List[int] = field(default_factory=list)
    volatility: VolatilityClass = "semi_stable"
    expires_at: Optional[str] = None
    created_run: Optional[int] = None
    last_updated_run: Optional[int] = None
    embedding: Optional[List[float]] = None


@dataclass
class Node:
    id: Optional[int] = None
    type: NodeType = "topic"
    name: str = ""
    attrs: dict = field(default_factory=dict)


@dataclass
class Edge:
    src: int = 0
    dst: int = 0
    relation: str = ""
    weight: float = 1.0
    attrs: dict = field(default_factory=dict)


@dataclass
class GetContextResult:
    """Return shape consumed by Agent 3 (spec section 7)."""

    creator_profile: dict
    core_insights: List[dict]
    relevant_insights: List[dict]
    related_entities: List[dict]
    last_run: Optional[dict]
