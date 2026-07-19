"""Deterministic recommendation engine for Agent 3.

Used whenever NVIDIA NIM is unavailable or its output fails validation, so
recommendations always meet the quality standard in docs/AGENTS.md
(what/why/evidence/confidence/action steps) without network access.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from agents.contracts import (
    CreatorContext,
    LearnedPattern,
    Opportunity,
    PendingIdea,
    Recommendation,
)

_STOPWORDS = {
    "a", "an", "and", "for", "in", "is", "of", "on", "or", "the", "this",
    "to", "with", "vs", "your", "you", "i", "we", "so",
}


def _keywords(text: str) -> set:
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def fallback_recommendations(
    context: CreatorContext,
    opportunities: List[Opportunity],
    max_recommendations: int,
) -> List[Recommendation]:
    recs: List[Recommendation] = []
    for i, opp in enumerate(opportunities[:max_recommendations], 1):
        pattern = best_pattern(context.learned_patterns, opp)
        idea = matching_idea(context.pending_ideas, opp)
        recs.append(
            Recommendation(
                id=f"rec_{i:03d}",
                rank=i,
                title=opp.suggested_angle or opp.topic,
                why=build_why(opp, pattern, idea),
                supporting_patterns=[pattern.id] if pattern else [],
                opportunity_id=opp.id,
                confidence=confidence(opp, pattern),
                action_steps=build_action_steps(context, opp, idea),
            )
        )
    recs.sort(key=lambda r: r.confidence, reverse=True)
    for i, rec in enumerate(recs, start=1):
        rec.rank = i
    return recs


def best_pattern(
    patterns: List[LearnedPattern], opp: Opportunity
) -> Optional[LearnedPattern]:
    if not patterns:
        return None
    opp_words = _keywords(f"{opp.topic} {opp.suggested_angle}")
    scored: List[Tuple[float, LearnedPattern]] = []
    for p in patterns:
        if p.id.startswith("p_avoid"):
            continue
        overlap = len(opp_words & _keywords(p.pattern))
        scored.append((overlap + p.confidence, p))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


def matching_idea(
    ideas: List[PendingIdea], opp: Opportunity
) -> Optional[PendingIdea]:
    opp_words = _keywords(f"{opp.topic} {opp.suggested_angle}")
    for idea in ideas:
        # A single shared word (e.g. "nvidia") is too weak to claim the
        # idea's research applies to this opportunity.
        if len(_keywords(idea.title) & opp_words) >= 2:
            return idea
    return None


def confidence(opp: Opportunity, pattern: Optional[LearnedPattern]) -> float:
    # Cold start (no patterns) lands near 0.4; strong patterns push
    # toward 0.9 — matching the trajectory in docs/RECURSIVE_LOOP.md.
    base = 0.2 + 0.25 * (opp.composite_score / 100.0)
    if pattern:
        base += 0.5 * pattern.confidence
    return round(min(0.95, max(0.05, base)), 2)


def build_why(
    opp: Opportunity,
    pattern: Optional[LearnedPattern],
    idea: Optional[PendingIdea],
) -> str:
    parts = [
        f"{opp.reason}.",
        f"Trend score {opp.trend_score:.0f}/100, "
        f"niche alignment {opp.niche_alignment:.0f}/100, "
        f"competition gap {opp.competition_gap:.0f}/100 "
        f"(composite {opp.composite_score:.0f}).",
    ]
    if opp.sources:
        src = ", ".join(
            f"{s.name} ({s.detail})" if s.detail else s.name
            for s in opp.sources
        )
        parts.append(f"Evidence: {src}.")
    if pattern:
        parts.append(
            f"Matches learned pattern {pattern.id}: \"{pattern.pattern}\" "
            f"(confidence {pattern.confidence:.2f}, "
            f"{pattern.evidence_count} supporting items)."
        )
    else:
        parts.append(
            "No learned patterns yet — reasoning from live signals only, "
            "so confidence is conservative."
        )
    if idea:
        parts.append(
            f"You already have {idea.research_complete * 100:.0f}% of the "
            f"research done in pending idea \"{idea.title}\"."
        )
    return " ".join(parts)


def build_action_steps(
    context: CreatorContext,
    opp: Opportunity,
    idea: Optional[PendingIdea],
) -> List[str]:
    steps = []
    if idea:
        steps.append(
            f"Review your existing notes for \"{idea.title}\" "
            f"({idea.research_complete * 100:.0f}% research complete)"
        )
    elif opp.sources:
        steps.append(
            f"Collect source material starting from {opp.sources[0].name}"
        )
    else:
        steps.append(f"Research the topic \"{opp.topic}\" and collect sources")
    steps.append(
        f"Outline the video around the angle: \"{opp.suggested_angle or opp.topic}\""
    )
    length = context.creator_profile.preferred_length
    if length:
        steps.append(
            f"Target a {length} runtime to match your audience retention data"
        )
    else:
        steps.append("Keep the runtime tight; front-load the strongest section")
    steps.append(
        "After publishing, log views/retention back into the system so the "
        "next cycle learns from the outcome"
    )
    return steps
