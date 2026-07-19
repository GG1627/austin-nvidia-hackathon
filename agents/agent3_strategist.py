"""Agent 3 — Strategist / Execution Agent.

Decision layer and creator interface for the Recursive Creator Intelligence
System. Combines creator knowledge from Agent 1 with live opportunities from
Agent 2 to generate reasoned, prioritized recommendations, collects creator
feedback, and pushes the learnings back to Agent 1.

Dependencies are injected, so this file has no knowledge of whether it is
talking to the real agents or the stubs in agents/stubs.py:

    memory_agent.get_creator_context() -> CreatorContext
    memory_agent.ingest_feedback(feedback, recommendation=None) -> None
    research_agent.get_opportunities(creator_context) -> List[Opportunity]

The LLM (NVIDIA NIM) is optional: when unavailable or when its output fails
validation, a deterministic rule-based engine produces recommendations that
still meet the quality standard in docs/AGENTS.md (what/why/evidence/
confidence/action steps). This keeps the demo alive without network access.
"""

from __future__ import annotations

import datetime as _dt
import inspect
import json
import os
import re
from typing import Callable, Dict, List, Optional, Sequence

from agents import agent3_fallback, agent3_presenter
from agents.contracts import (
    FEEDBACK_ACTIONS,
    CreatorContext,
    CycleResult,
    Feedback,
    Opportunity,
    Recommendation,
)

DEFAULT_PROMPT_PATH = os.path.join("prompts", "agent3_system.txt")
DEFAULT_HISTORY_PATH = os.path.join("memory", "cycle_history.json")

# FeedbackProvider: (recommendation) -> Feedback. Used for simulation/tests;
# when None, feedback is collected interactively on the CLI.
FeedbackProvider = Callable[[Recommendation], Feedback]


class StrategistAgent:
    def __init__(
        self,
        memory_agent,
        research_agent,
        llm=None,
        prompt_path: str = DEFAULT_PROMPT_PATH,
        history_path: str = DEFAULT_HISTORY_PATH,
        max_recommendations: int = 3,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
    ) -> None:
        self.memory = memory_agent
        self.research = research_agent
        self.llm = llm
        self.prompt_path = prompt_path
        self.history_path = history_path
        self.max_recommendations = max_recommendations
        self._input = input_fn
        self._print = print_fn
        self.last_engine = "none"  # "nim" or "fallback" (for transparency)

    # ------------------------------------------------------------------
    # Orchestration core (Milestone 3.1)
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        feedback_provider: Optional[FeedbackProvider] = None,
        collect_feedback: bool = True,
    ) -> CycleResult:
        """Execute one full recursive loop and log it.

        1. Get creator context (Agent 1)
        2. Get opportunities (Agent 2)
        3. Generate recommendations
        4. Present to creator
        5. Collect feedback
        6. Push learnings back to Agent 1

        With collect_feedback=False (the dashboard flow) steps 5-6 are
        skipped entirely: no synthetic feedback is fabricated, nothing is
        ingested into memory, and the creator's real votes arrive later
        through the /api/feedback endpoint.
        """
        run_number = self._next_run_number()
        self._print(f"\n{'=' * 62}")
        self._print(f"  CYCLE {run_number} — {_dt.datetime.now():%Y-%m-%d %H:%M}")
        self._print(f"{'=' * 62}")

        context = self.memory.get_creator_context()
        patterns_before = {
            p.id: p.confidence for p in context.learned_patterns
        }
        self._print(
            f"  [Agent 1] Loaded creator context: "
            f"{len(context.learned_patterns)} learned pattern(s), "
            f"{len(context.pending_ideas)} pending idea(s)"
        )

        opportunities = self.research.get_opportunities(context)
        duplicates_filtered = getattr(
            self.research, "last_duplicates_filtered", 0
        )
        self._print(
            f"  [Agent 2] {len(opportunities)} opportunity(ies) surfaced, "
            f"{duplicates_filtered} duplicate(s) filtered"
        )

        recommendations = self.generate_recommendations(context, opportunities)
        self._print(
            f"  [Agent 3] Generated {len(recommendations)} recommendation(s) "
            f"via {self.last_engine}"
        )

        self.present_recommendations(recommendations, opportunities)
        feedback: List[Feedback] = []
        if collect_feedback:
            feedback = self.collect_feedback(recommendations, feedback_provider)

        # Only opportunities the creator actually responded to count as
        # surfaced; unanswered recommendations may resurface next cycle.
        recs_by_id = {r.id: r for r in recommendations}
        self._mark_surfaced(
            [recs_by_id[fb.recommendation_id] for fb in feedback
             if fb.recommendation_id in recs_by_id]
        )
        for fb in feedback:
            self._ingest_feedback(fb, recs_by_id.get(fb.recommendation_id))

        # Memory layers with a consolidation engine (the real Agent 1) turn the
        # cycle's episodes into insights now, so the next run starts smarter.
        if hasattr(self.memory, "consolidate"):
            self.memory.consolidate()

        self._show_learning_summary(patterns_before)

        metrics = self._cycle_metrics(
            recommendations, feedback, duplicates_filtered
        )
        result = CycleResult(
            run_number=run_number,
            timestamp=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            recommendations=recommendations,
            feedback=feedback,
            metrics=metrics,
        )
        self._append_history(result)
        return result

    def _next_run_number(self) -> int:
        if hasattr(self.memory, "increment_run_count"):
            run_number = self.memory.increment_run_count()
            if run_number:  # 0 means the backing store was unreachable
                return run_number
        return len(self._load_history()) + 1

    def _mark_surfaced(self, recommendations: Sequence[Recommendation]) -> None:
        if not hasattr(self.memory, "mark_surfaced"):
            return
        for rec in recommendations:
            if rec.opportunity_id:
                self.memory.mark_surfaced(rec.opportunity_id)

    def _ingest_feedback(
        self, feedback: Feedback, recommendation: Optional[Recommendation]
    ) -> None:
        """Push feedback to Agent 1, passing the recommendation for extra
        learning context when the implementation accepts it."""
        try:
            sig = inspect.signature(self.memory.ingest_feedback)
            accepts_rec = "recommendation" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
        except (TypeError, ValueError):
            accepts_rec = False
        if accepts_rec:
            self.memory.ingest_feedback(feedback, recommendation=recommendation)
        else:
            self.memory.ingest_feedback(feedback)

    # ------------------------------------------------------------------
    # Recommendation engine (Milestone 3.2)
    # ------------------------------------------------------------------

    def generate_recommendations(
        self,
        context: CreatorContext,
        opportunities: List[Opportunity],
    ) -> List[Recommendation]:
        """Synthesize context + opportunities into ranked recommendations.

        Tries NVIDIA NIM first; falls back to the deterministic engine when
        the LLM is unavailable or returns output that fails validation.
        """
        candidates = self._eligible_opportunities(context, opportunities)
        if not candidates:
            self.last_engine = "none"
            return []

        if self.llm is not None and getattr(self.llm, "available", True):
            try:
                recs = self._llm_recommendations(context, candidates)
                if recs:
                    self.last_engine = "nim"
                    return recs
            except Exception as exc:  # any LLM failure -> deterministic path
                self._print(f"  [Agent 3] NIM unavailable ({exc}); using fallback")

        recs = self._fallback_recommendations(context, candidates)
        self.last_engine = "fallback"
        return recs

    def _eligible_opportunities(
        self, context: CreatorContext, opportunities: List[Opportunity]
    ) -> List[Opportunity]:
        avoid = [t.lower() for t in context.avoid_topics]
        eligible = []
        for opp in opportunities:
            if opp.already_surfaced:
                continue
            haystack = f"{opp.topic} {opp.suggested_angle}".lower()
            if any(term in haystack for term in avoid):
                continue
            eligible.append(opp)
        eligible.sort(key=lambda o: o.composite_score, reverse=True)
        return eligible

    # -- LLM path -------------------------------------------------------

    def _system_prompt(self) -> str:
        with open(self.prompt_path, "r", encoding="utf-8") as fh:
            return fh.read()

    def _llm_recommendations(
        self, context: CreatorContext, opportunities: List[Opportunity]
    ) -> List[Recommendation]:
        user_payload = json.dumps(
            {
                "creator_context": context.to_dict(),
                "opportunities": [o.to_dict() for o in opportunities],
                "max_recommendations": self.max_recommendations,
            },
            indent=2,
        )
        raw = self.llm.chat(self._system_prompt(), user_payload)
        parsed = self._parse_llm_json(raw)

        valid_opp_ids = {o.id for o in opportunities}
        known_patterns = {p.id for p in context.learned_patterns}
        recs: List[Recommendation] = []
        for item in parsed[: self.max_recommendations]:
            rec = Recommendation.from_dict(item)
            if not self._is_valid(rec, valid_opp_ids, known_patterns):
                continue
            rec.supporting_patterns = [
                pid for pid in rec.supporting_patterns if pid in known_patterns
            ]
            recs.append(rec)

        # Re-rank and assign ids/ranks locally — never trust LLM ordering.
        recs.sort(key=lambda r: r.confidence, reverse=True)
        for i, rec in enumerate(recs, start=1):
            rec.rank = i
            rec.id = rec.id or f"rec_{i:03d}"
        return recs

    @staticmethod
    def _parse_llm_json(raw: str) -> List[dict]:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON array found in LLM output")
        parsed = json.loads(text[start : end + 1])
        if not isinstance(parsed, list):
            raise ValueError("LLM output is not a JSON array")
        return [p for p in parsed if isinstance(p, dict)]

    def _is_valid(
        self,
        rec: Recommendation,
        valid_opp_ids: set,
        known_patterns: set,
    ) -> bool:
        """Enforce the recommendation quality standard from docs/AGENTS.md."""
        if not rec.title or not rec.why:
            return False
        if rec.opportunity_id not in valid_opp_ids:
            return False
        if not (0.0 <= rec.confidence <= 1.0):
            return False
        if len(rec.action_steps) < 3:
            return False
        # Must cite at least one real pattern when patterns exist.
        if known_patterns and not any(
            pid in known_patterns for pid in rec.supporting_patterns
        ):
            return False
        return True

    # -- Deterministic fallback path (agents/agent3_fallback.py) --------

    def _fallback_recommendations(
        self, context: CreatorContext, opportunities: List[Opportunity]
    ) -> List[Recommendation]:
        return agent3_fallback.fallback_recommendations(
            context, opportunities, self.max_recommendations
        )

    # ------------------------------------------------------------------
    # Creator interface (Milestone 3.3)
    # ------------------------------------------------------------------

    def present_recommendations(
        self,
        recommendations: List[Recommendation],
        opportunities: Optional[List[Opportunity]] = None,
    ) -> None:
        agent3_presenter.present_recommendations(
            recommendations, opportunities, self._print
        )

    def collect_feedback(
        self,
        recommendations: List[Recommendation],
        feedback_provider: Optional[FeedbackProvider] = None,
    ) -> List[Feedback]:
        feedback: List[Feedback] = []
        for rec in recommendations:
            if feedback_provider is not None:
                fb = feedback_provider(rec)
            else:
                fb = self._interactive_feedback(rec)
            if fb.action not in FEEDBACK_ACTIONS:
                fb.action = "deferred"
            feedback.append(fb)
        return feedback

    def _interactive_feedback(self, rec: Recommendation) -> Feedback:
        return agent3_presenter.interactive_feedback(rec, self._input, self._print)

    def _show_learning_summary(self, patterns_before: Dict[str, float]) -> None:
        after = {p.id: p for p in self.memory.get_creator_context().learned_patterns}
        agent3_presenter.show_learning_summary(patterns_before, after, self._print)

    # ------------------------------------------------------------------
    # Improvement metrics dashboard (Milestone 3.4)
    # ------------------------------------------------------------------

    def _cycle_metrics(
        self,
        recommendations: List[Recommendation],
        feedback: List[Feedback],
        duplicates_filtered: int,
    ) -> Dict[str, object]:
        decided = [f for f in feedback if f.action in ("accepted", "rejected")]
        accepted = [f for f in feedback if f.action == "accepted"]
        avg_conf = (
            round(sum(r.confidence for r in recommendations) / len(recommendations), 2)
            if recommendations else 0.0
        )
        avg_steps = (
            round(sum(len(r.action_steps) for r in recommendations) / len(recommendations), 1)
            if recommendations else 0.0
        )
        patterns = (
            self.memory.pattern_count()
            if hasattr(self.memory, "pattern_count")
            else len(self.memory.get_creator_context().learned_patterns)
        )
        return {
            "learned_patterns": patterns,
            "avg_confidence": avg_conf,
            "acceptance_rate": (
                round(len(accepted) / len(decided), 2) if decided else None
            ),
            "duplicates_filtered": duplicates_filtered,
            "avg_action_steps": avg_steps,
            "engine": self.last_engine,
        }

    def _load_history(self) -> List[CycleResult]:
        if not os.path.exists(self.history_path):
            return []
        with open(self.history_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return [CycleResult.from_dict(r) for r in data.get("runs", [])]

    def _append_history(self, result: CycleResult) -> None:
        history = self._load_history()
        history.append(result)
        os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
        tmp_path = self.history_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump({"runs": [r.to_dict() for r in history]}, fh, indent=2)
        os.replace(tmp_path, self.history_path)

    def show_improvement_metrics(self) -> None:
        agent3_presenter.render_improvement_metrics(self._load_history(), self._print)
