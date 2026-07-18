"""
Agent 1 - Memory & Knowledge Engineer
Data models for the Recursive Creator Intelligence System.
Spec-compliant: Supabase + pgvector backend.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Literal
from datetime import datetime
import uuid

# ---------------------------------------------------------------------------
# Lifecycle & classification types
# ---------------------------------------------------------------------------

InsightStatus = Literal["hypothesis", "validated", "core", "deprecated"]
VolatilityClass = Literal["stable", "semi_stable", "volatile"]
EpisodeKind = Literal[
    "onboarding_finding",
    "research_finding",
    "recommendation",
    "outcome",
    "feedback",
    "observation",
]

# ---------------------------------------------------------------------------
# Frozen payload contracts (shared with Agent 2 & Agent 3)
# ---------------------------------------------------------------------------

@dataclass
class OnboardingFindingPayload:
    video_title: str
    published_at: str           # ISO-8601
    duration_minutes: float
    views: int
    retention_pct: float        # 0-100
    topic_tags: List[str]
    raw_ref: Optional[str] = None

@dataclass
class ResearchFindingPayload:
    source: str
    topic: str
    trend_score: float          # 0-1
    reason: str
    suggested_angle: str
    raw_ref: Optional[str] = None

@dataclass
class RecommendationPayload:
    statement: str
    reasoning: str
    cited_insight_ids: List[str]
    predicted_outcome: str

@dataclass
class OutcomePayload:
    recommendation_episode_id: str
    actual: str
    prediction_correct: bool

@dataclass
class FeedbackPayload:
    recommendation_episode_id: str
    action: str
    creator_note: str

@dataclass
class ObservationPayload:
    note: str

# ---------------------------------------------------------------------------
# Core domain objects
# ---------------------------------------------------------------------------

@dataclass
class Run:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "active"      # active | complete | failed
    creator_id: Optional[str] = None

@dataclass
class Episode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    kind: EpisodeKind = "observation"
    payload: dict = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    consolidated: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class Insight:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    confidence: float = 0.3     # new hypotheses start at 0.3
    status: InsightStatus = "hypothesis"
    volatility: VolatilityClass = "semi_stable"
    support_count: int = 0
    contradict_count: int = 0
    embedding: Optional[List[float]] = None
    expires_at: Optional[str] = None
    source_episode_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class Node:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "entity"        # entity | concept | topic
    label: str = ""
    attributes: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class Edge:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_node_id: str = ""
    to_node_id: str = ""
    relation: str = ""
    weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class GetContextResult:
    """Return shape consumed by Agent 3."""
    creator_profile: dict
    core_insights: List[dict]
    relevant_insights: List[dict]
    related_entities: List[dict]
    last_run: Optional[str]
