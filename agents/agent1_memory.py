"""
agent1_memory.py — Creator Intelligence Agent (Persistent Memory Brain)

This is the long-term brain of the Recursive Creator Intelligence System.
It does NOT simply store facts. It synthesises conclusions.

Core responsibilities:
  - Maintain the persistent knowledge graph
  - Extract generalised patterns from content performance data
  - Update confidence scores as new evidence arrives
  - Ingest creator feedback and learn from it
  - Hand a rich CreatorContext to Agent 3 each cycle
"""

import os
import json
from typing import List, Optional
from datetime import datetime
from openai import OpenAI

from agents.models import (
    CreatorProfile,
    ContentItem,
    LearnedPattern,
    ContentIdea,
    Feedback,
    CreatorContext,
    _uid,
    _now,
)
from tools.memory_tool import MemoryStore


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

AGENT1_SYSTEM_PROMPT = """
You are the Creator Intelligence Agent — the long-term memory brain of a
creative strategy system. Your job is to synthesise knowledge, not just store it.

When given a list of content performance records, extract GENERALISED conclusions.
Never just restate facts. Transform data into strategic wisdom.

Rules:
1. Express every learning as a generalised rule (not a fact about one video).
2. Assign a confidence score 0.0–1.0 based on how much evidence supports it.
3. Assign a category: format | topic | length | audience | timing | engagement.
4. Be concise — one sentence per pattern.
5. If a new observation contradicts an existing pattern, note it but don\'t delete the pattern.
6. Never create duplicate patterns. Update confidence instead.
7. Return ONLY valid JSON — a list of pattern objects.

Output format (JSON array):
[
  {
    "pattern": "<one-sentence generalised conclusion>",
    "category": "<format|topic|length|audience|timing|engagement>",
    "confidence": <0.0–1.0>,
    "evidence_count": <int>
  }
]
"""


class CreatorMemoryAgent:
    """
    Agent 1: The persistent knowledge brain.

    All state lives in MemoryStore (JSON on disk).
    The LLM is used only for pattern extraction — it never stores anything itself.
    """

    def __init__(self, memory_path: Optional[str] = None):
        self.store = MemoryStore(memory_path or os.environ.get("MEMORY_PATH", "./memory/knowledge_graph.json"))
        self.client = OpenAI(
            api_key=os.environ.get("NVIDIA_API_KEY"),
            base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        )
        self.model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

    # ------------------------------------------------------------------
    # Public API — called by Agent 3
    # ------------------------------------------------------------------

    def get_creator_context(self) -> CreatorContext:
        """
        Returns a full CreatorContext for Agent 3 to use when generating
        recommendations. This is the primary read interface.
        """
        profile = self.store.get_profile()
        patterns = self.store.get_patterns(min_confidence=0.4)
        items = self.store.get_content_items()
        ideas = self.store.get_ideas(status="pending")

        # Derive top performing topics from content items
        topic_views: dict = {}
        for item in items:
            for topic in item.topics:
                topic_views[topic] = topic_views.get(topic, 0) + item.views
        top_topics = sorted(topic_views, key=lambda t: topic_views[t], reverse=True)[:5]

        return CreatorContext(
            profile=profile,
            learned_patterns=patterns,
            top_performing_topics=top_topics,
            avoid_topics=profile.avoid_topics,
            pending_ideas=ideas,
            total_content_items=len(items),
            run_count=self.store.get_run_count(),
            last_updated=_now(),
        )

    def ingest_content_result(self, item: ContentItem) -> None:
        """
        Ingest a new or updated content performance record.
        After ingesting, re-runs pattern extraction.
        """
        self.store.add_content_item(item)
        print(f"[Agent1] Ingested content item: '{item.title}'")
        self._run_pattern_extraction()

    def ingest_feedback(self, feedback: Feedback) -> None:
        """
        Ingest creator feedback on a recommendation.
        This is the core of the recursive learning loop.
        Patterns are updated based on accepted/rejected signals.
        """
        self.store.add_feedback(feedback)
        print(f"[Agent1] Feedback ingested: '{feedback.recommendation_title}' -> {feedback.action}")

        if feedback.action == "rejected" and feedback.notes:
            self._learn_from_rejection(feedback)

        if feedback.outcome_views is not None:
            self._learn_from_outcome(feedback)

    def ingest_profile(self, profile: CreatorProfile) -> None:
        """Store or update the creator profile."""
        self.store.save_profile(profile)
        print(f"[Agent1] Creator profile saved for niche: '{profile.niche}'")

    def add_content_idea(self, idea: ContentIdea) -> None:
        """Add a new content idea to the pending queue."""
        self.store.add_idea(idea)

    def get_patterns(self, min_confidence: float = 0.5) -> List[LearnedPattern]:
        """Return patterns above confidence threshold."""
        return self.store.get_patterns(min_confidence=min_confidence)

    def increment_run(self) -> int:
        """Call at the start of each Agent 3 cycle. Returns new run count."""
        return self.store.increment_run()

    def get_metrics(self) -> dict:
        """Return improvement metrics for display."""
        return self.store.get_metrics()

    # ------------------------------------------------------------------
    # Pattern Extraction Engine (Milestone 1.2)
    # ------------------------------------------------------------------

    def _run_pattern_extraction(self) -> None:
        """
        Sends accumulated content items to the LLM and extracts generalised
        patterns. Updates existing patterns or adds new ones.
        """
        items = self.store.get_content_items()
        if len(items) < 2:
            print("[Agent1] Not enough content items to extract patterns (need >= 2).")
            return

        # Build a compact summary for the LLM
        summaries = []
        for item in items:
            summaries.append(
                f"Title: {item.title} | Format: {item.format} | "
                f"Length: {item.length_min}min | Views: {item.views} | "
                f"Retention: {item.retention_pct}% | Topics: {', '.join(item.topics)}"
            )

        user_msg = "Analyse the following content performance records and extract generalised patterns:\n\n"
        user_msg += "\n".join(summaries)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": AGENT1_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            extracted = json.loads(raw)
            self._merge_patterns(extracted)

        except Exception as e:
            print(f"[Agent1] Pattern extraction failed: {e}")

    def _merge_patterns(self, extracted: list) -> None:
        """
        Merge newly extracted patterns into the store.
        Updates existing patterns if a similar one exists; creates new if not.
        """
        for ep in extracted:
            category = ep.get("category", "")
            # Use first two meaningful words as a similarity key
            keyword = " ".join(ep.get("pattern", "").split()[:3])

            existing = self.store.find_similar_pattern(category, keyword)
            if existing:
                # Update confidence using a weighted average
                new_evidence = ep.get("evidence_count", 1)
                total_evidence = existing.evidence_count + new_evidence
                new_confidence = (
                    (existing.confidence * existing.evidence_count + ep.get("confidence", 0.5) * new_evidence)
                    / total_evidence
                )
                self.store.update_pattern(existing.id, {
                    "confidence": round(min(new_confidence, 0.98), 3),
                    "evidence_count": total_evidence,
                    "pattern": ep["pattern"],  # refresh wording
                })
                print(f"[Agent1] Updated pattern '{existing.id}': confidence={new_confidence:.2f}")
            else:
                new_pattern = LearnedPattern(
                    pattern=ep["pattern"],
                    category=category,
                    confidence=ep.get("confidence", 0.5),
                    evidence_count=ep.get("evidence_count", 1),
                )
                self.store.add_pattern(new_pattern)
                print(f"[Agent1] New pattern learned: '{new_pattern.pattern[:60]}...'")

    def _learn_from_rejection(self, feedback: Feedback) -> None:
        """
        When a recommendation is rejected with notes, extract a new avoid-pattern.
        """
        avoid_note = feedback.notes.strip()
        if not avoid_note:
            return

        pattern = LearnedPattern(
            pattern=f"Creator tends to avoid: {avoid_note}",
            category="audience",
            confidence=0.6,
            evidence_count=1,
        )
        existing = self.store.find_similar_pattern("audience", avoid_note[:20])
        if existing:
            self.store.update_pattern(existing.id, {
                "confidence": min(existing.confidence + 0.1, 0.98),
                "evidence_count": existing.evidence_count + 1,
            })
        else:
            self.store.add_pattern(pattern)
            print(f"[Agent1] Rejection pattern recorded: '{avoid_note[:50]}'")

    def _learn_from_outcome(self, feedback: Feedback) -> None:
        """
        When a video result comes back, create a synthetic ContentItem and
        re-run pattern extraction to capture the new data point.
        """
        synthetic = ContentItem(
            title=feedback.recommendation_title,
            views=feedback.outcome_views or 0,
            retention_pct=feedback.outcome_retention or 0.0,
            outcome=feedback.outcome_notes,
            published_date=feedback.outcome_date or _now(),
        )
        self.store.add_content_item(synthetic)
        self._run_pattern_extraction()
        print(f"[Agent1] Outcome learned for: '{feedback.recommendation_title}'")

    # ------------------------------------------------------------------
    # Confidence Decay (Milestone 1.2)
    # ------------------------------------------------------------------

    def decay_stale_patterns(self, days_threshold: int = 30) -> None:
        """
        Reduce confidence on patterns that haven't been updated recently
        and haven't been cited much. Prevents stale assumptions from
        dominating recommendations.
        """
        now = datetime.utcnow()
        for pattern in self.store.get_patterns(min_confidence=0.0):
            try:
                updated = datetime.fromisoformat(pattern.last_updated)
                age_days = (now - updated).days
            except Exception:
                continue

            if age_days > days_threshold and pattern.times_cited < 2:
                decayed = round(pattern.confidence * 0.9, 3)  # 10% decay
                self.store.update_pattern(pattern.id, {"confidence": decayed})
                print(f"[Agent1] Decayed stale pattern '{pattern.id}': {pattern.confidence:.2f} -> {decayed:.2f}")

    # ------------------------------------------------------------------
    # Diagnostic / display helpers
    # ------------------------------------------------------------------

    def print_knowledge_summary(self) -> None:
        """Print a human-readable summary of current knowledge state."""
        ctx = self.get_creator_context()
        metrics = self.get_metrics()

        print("\n" + "=" * 60)
        print("  AGENT 1 — KNOWLEDGE GRAPH SUMMARY")
        print("=" * 60)
        print(f"  Run count          : {ctx.run_count}")
        print(f"  Content items      : {ctx.total_content_items}")
        print(f"  Learned patterns   : {len(ctx.learned_patterns)}")
        print(f"  Pending ideas      : {len(ctx.pending_ideas)}")
        print(f"  Avg confidence     : {metrics.get('avg_confidence_current', 'N/A')}")
        print(f"  Acceptance rate    : {metrics.get('acceptance_rate', 'N/A')}")
        print()
        if ctx.learned_patterns:
            print("  TOP PATTERNS:")
            sorted_p = sorted(ctx.learned_patterns, key=lambda p: p.confidence, reverse=True)
            for p in sorted_p[:5]:
                bar = int(p.confidence * 20) * "█"
                print(f"  [{bar:<20}] {p.confidence:.2f}  {p.pattern[:55]}")
        print("=" * 60 + "\n")
