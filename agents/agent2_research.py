"""Live research and opportunity ranking for the Recursive Creator Intelligence System.

External services are deliberately best-effort: a bad API key, a rate limit, or a
temporarily unavailable website must not stop a creator from receiving the signals
that *are* available.  Ollama is used to turn grounded source material into a
creator-specific angle; URLs and source metrics always come from connectors.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

from agents.models import Episode, ResearchFindingPayload


HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
NVIDIA_RSS_URL = "https://nvidianews.nvidia.com/releases.xml"
GITHUB_TRENDING_URL = "https://github.com/trending?since=weekly"


@dataclass
class RawSignal:
    source: str
    title: str
    url: str
    published_at: Optional[str] = None
    engagement: float = 0.0
    topic: Optional[str] = None
    raw_evidence: str = ""


@dataclass
class Opportunity:
    id: str
    topic: str
    suggested_angle: str
    reasoning: str
    trend_velocity: float
    niche_alignment: float
    competition_gap: float
    recency_bonus: float
    composite_score: float
    sources: list[dict[str, Any]]
    freshness: str


@dataclass
class ResearchResult:
    """Optional diagnostics for a UI without changing the main return contract."""
    opportunities: list[Opportunity] = field(default_factory=list)
    source_errors: dict[str, str] = field(default_factory=dict)


class ResearchAgent:
    """Collect live signals and return ranked, evidence-backed opportunities."""

    def __init__(
        self,
        *,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        inference_base_url: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        youtube_api_key: Optional[str] = None,
        x_bearer_token: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        memory_store: Any = None,
        max_per_source: int = 12,
    ) -> None:
        self.ollama_url = (ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        # NemoClaw is the secure runtime, not an Ollama model. This 4B
        # Nemotron model is a practical local default for an 8 GB RTX laptop.
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "nemotron-3-nano:4b")
        self.inference_base_url = (inference_base_url or os.getenv("INFERENCE_BASE_URL", "")).rstrip("/")
        self.tavily_api_key = tavily_api_key if tavily_api_key is not None else os.getenv("TAVILY_API_KEY", "")
        self.youtube_api_key = youtube_api_key if youtube_api_key is not None else os.getenv("YOUTUBE_API_KEY", "")
        self.x_bearer_token = x_bearer_token if x_bearer_token is not None else os.getenv("X_BEARER_TOKEN", "")
        self.max_per_source = max_per_source
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=12, follow_redirects=True)
        self.memory_store = memory_store
        self.system_prompt = Path(__file__).parents[1].joinpath("prompts", "agent2_system.txt").read_text(encoding="utf-8")
        self.last_result = ResearchResult()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_opportunities(self, creator_context: Any, top_n: int = 5) -> list[Opportunity]:
        """Return ranked opportunities.  Source errors are available in ``last_result``."""
        signals: list[RawSignal] = []
        errors: dict[str, str] = {}
        fetchers: list[tuple[str, Callable[[], list[RawSignal]]]] = [
            ("reddit", self.fetch_reddit_signals),
            ("hacker_news", self.fetch_hn_signals),
            ("google_trends", self.fetch_trends),
            ("github", self.fetch_github_trending),
            ("nvidia_rss", self.fetch_nvidia_news),
            ("tavily", self.fetch_tavily_signals),
            ("youtube", self.fetch_youtube_signals),
        ]
        if os.getenv("ENABLE_X", "false").lower() in {"1", "true", "yes"}:
            fetchers.append(("x", self.fetch_x_signals))
        for name, fetch in fetchers:
            try:
                signals.extend(fetch())
            except Exception as exc:  # A source is never allowed to kill the run.
                errors[name] = str(exc)

        opportunities = self._build_opportunities(signals, creator_context)
        if self.memory_store:
            opportunities = [item for item in opportunities if not self.memory_store.was_opportunity_surfaced(item.id)]
        opportunities.sort(key=lambda item: item.composite_score, reverse=True)
        self.last_result = ResearchResult(opportunities=opportunities[:top_n], source_errors=errors)
        if self.memory_store:
            for item in self.last_result.opportunities:
                self.memory_store.mark_opportunity_surfaced(item.id)
        return self.last_result.opportunities

    # ---- Connectors -------------------------------------------------

    def fetch_reddit_signals(self) -> list[RawSignal]:
        from tools.reddit_tool import fetch_reddit_signals
        return fetch_reddit_signals(self._client, self.max_per_source)

    def fetch_hn_signals(self) -> list[RawSignal]:
        from tools.trends_tool import fetch_hn_signals
        return fetch_hn_signals(self._client, self.max_per_source)

    def fetch_trends(self) -> list[RawSignal]:
        from tools.trends_tool import fetch_trends
        return fetch_trends(self.max_per_source)

    def fetch_github_trending(self) -> list[RawSignal]:
        from tools.world_sources import fetch_github_trending
        return fetch_github_trending(self._client, self.max_per_source)

    def fetch_nvidia_news(self) -> list[RawSignal]:
        from tools.world_sources import fetch_nvidia_news
        return fetch_nvidia_news(self._client, self.max_per_source)

    def fetch_tavily_signals(self) -> list[RawSignal]:
        from tools.world_sources import fetch_tavily_signals
        return fetch_tavily_signals(self._client, self.max_per_source, self.tavily_api_key)

    def fetch_youtube_signals(self) -> list[RawSignal]:
        from tools.social_sources import fetch_youtube_signals
        return fetch_youtube_signals(self._client, self.max_per_source, self.youtube_api_key)

    def fetch_x_signals(self) -> list[RawSignal]:
        from tools.social_sources import fetch_x_signals
        return fetch_x_signals(self._client, self.max_per_source, self.x_bearer_token)

    # ---- Analysis, ranking, and integration ------------------------

    def _build_opportunities(self, signals: list[RawSignal], creator_context: Any) -> list[Opportunity]:
        grouped: dict[str, list[RawSignal]] = {}
        for signal in _deduplicate(signals):
            grouped.setdefault(_topic_key(signal.topic or signal.title), []).append(signal)

        opportunities: list[Opportunity] = []
        for key, group in grouped.items():
            analysis = self._analyse_group(group, creator_context)
            if not analysis:
                continue
            topic = analysis["topic"]
            if self._is_avoided(topic, creator_context):
                continue
            trend, alignment, gap, recency = self._scores(group, analysis, creator_context)
            composite = round(trend * .35 + alignment * .35 + gap * .20 + recency * .10, 2)
            evidence = [{"name": s.source, "title": s.title, "url": s.url, "published_at": s.published_at, "engagement": s.engagement} for s in group]
            digest = hashlib.sha1(key.encode()).hexdigest()[:12]
            opportunities.append(Opportunity(f"opp_{digest}", topic, analysis["suggested_angle"], analysis["reasoning"], trend, alignment, gap, recency, composite, evidence, max((s.published_at or "" for s in group), default="")))
        return opportunities

    def _analyse_group(self, group: list[RawSignal], creator_context: Any) -> Optional[dict[str, Any]]:
        profile = _profile_dict(creator_context)
        payload = {"creator_profile": profile, "signals": [asdict(s) for s in group]}
        prompt = self.system_prompt + "\n" + json.dumps(payload)
        try:
            if self.inference_base_url:
                response = self._client.post(f"{self.inference_base_url}/chat/completions", json={"model": self.ollama_model, "messages": [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": json.dumps(payload)}], "response_format": {"type": "json_object"}}, timeout=45)
                response.raise_for_status()
                data = json.loads(response.json()["choices"][0]["message"]["content"])
            else:
                response = self._client.post(f"{self.ollama_url}/api/generate", json={"model": self.ollama_model, "prompt": prompt, "stream": False, "format": "json"}, timeout=45)
                response.raise_for_status()
                data = json.loads(response.json()["response"])
            if not all(isinstance(data.get(k), str) and data[k].strip() for k in ("topic", "suggested_angle", "reasoning")):
                return self._fallback_analysis(group, profile)
            return data
        except Exception:
            # A usable deterministic fallback keeps the live-monitor promise when Ollama is offline.
            first = group[0]
            return {"topic": first.topic or first.title, "suggested_angle": f"Practical developer guide to {first.topic or first.title}", "reasoning": f"Grounded in {len(group)} live signal(s), led by {first.source}.", "niche_alignment": _keyword_alignment(first.title, profile), "competition_gap": 50}

    @staticmethod
    def _fallback_analysis(group: list[RawSignal], profile: dict[str, Any]) -> dict[str, Any]:
        """Keep live opportunities usable when a local model is unavailable or malformed."""
        first = group[0]
        topic = first.topic or first.title
        return {"topic": topic, "suggested_angle": f"Practical developer guide to {topic}", "reasoning": f"Grounded in {len(group)} live signal(s), led by {first.source}.", "niche_alignment": _keyword_alignment(first.title, profile), "competition_gap": 50}

    def _scores(self, group: list[RawSignal], analysis: dict[str, Any], creator_context: Any) -> tuple[float, float, float, float]:
        max_engagement = max((s.engagement for s in group), default=0)
        trend = min(100.0, 20.0 * len(group) + min(80.0, max_engagement ** .5 * 8))
        alignment = _clamp(analysis.get("niche_alignment", _keyword_alignment(analysis["topic"], _profile_dict(creator_context))))
        gap = _clamp(analysis.get("competition_gap", 50))
        recency = max((_recency_score(s.published_at) for s in group), default=30.0)
        return round(trend, 2), round(alignment, 2), round(gap, 2), round(recency, 2)

    def _is_avoided(self, topic: str, creator_context: Any) -> bool:
        profile = _profile_dict(creator_context)
        return any(word.lower() in topic.lower() for word in profile.get("avoid_topics", []))

    @staticmethod
    def to_research_finding(opportunity: Opportunity) -> ResearchFindingPayload:
        source_names = ", ".join(sorted({source["name"] for source in opportunity.sources}))
        return ResearchFindingPayload(source=source_names, topic=opportunity.topic, trend_score=round(opportunity.composite_score / 100, 3), reason=opportunity.reasoning, suggested_angle=opportunity.suggested_angle, raw_ref=opportunity.sources[0]["url"])

    @classmethod
    def to_research_episode(cls, opportunity: Opportunity, run_id: str = "") -> Episode:
        return Episode(run_id=run_id, kind="research_finding", payload=asdict(cls.to_research_finding(opportunity)))


def _valid_signals(signals: Iterable[RawSignal]) -> list[RawSignal]:
    return [signal for signal in signals if signal.title.strip() and signal.url.strip()]


def _deduplicate(signals: Iterable[RawSignal]) -> list[RawSignal]:
    seen: set[tuple[str, str]] = set()
    result = []
    for signal in signals:
        key = (_topic_key(signal.title), signal.url.rstrip("/"))
        if key not in seen:
            seen.add(key)
            result.append(signal)
    return result


def _topic_key(value: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", value.lower()).split()
    stop_words = {"a", "an", "the", "for", "to", "with", "and", "on", "in", "how", "why", "guide", "tutorial", "release", "launch"}
    return " ".join(word for word in words if word not in stop_words)


def _profile_dict(context: Any) -> dict[str, Any]:
    profile = getattr(context, "creator_profile", None) or getattr(context, "profile", None) or (context.get("creator_profile") if isinstance(context, dict) else None) or {}
    return asdict(profile) if hasattr(profile, "__dataclass_fields__") else dict(profile)


def _keyword_alignment(text: str, profile: dict[str, Any]) -> float:
    words = set(_topic_key(text).split())
    niche_words = set(_topic_key(str(profile.get("niche", ""))).split())
    return min(100.0, 35.0 + 20.0 * len(words & niche_words))


def _recency_score(value: Optional[str]) -> float:
    if not value:
        return 30.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 50.0  # RSS date parsing is deliberately conservative.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    hours = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600)
    return max(10.0, 100.0 - hours * 2)


def _unix_iso(value: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 50.0
