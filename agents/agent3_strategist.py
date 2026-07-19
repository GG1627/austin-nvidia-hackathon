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
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from agents.contracts import (
    FEEDBACK_ACTIONS,
    CreatorContext,
    CycleResult,
    Feedback,
    LearnedPattern,
    Opportunity,
    PendingIdea,
    Recommendation,
)

DEFAULT_PROMPT_PATH = os.path.join("prompts", "agent3_system.txt")
DEFAULT_HISTORY_PATH = os.path.join("memory", "cycle_history.json")

# FeedbackProvider: (recommendation) -> Feedback. Used for simulation/tests;
# when None, feedback is collected interactively on the CLI.
FeedbackProvider = Callable[[Recommendation], Feedback]

_STOPWORDS = {
    "a", "an", "and", "for", "in", "is", "of", "on", "or", "the", "this",
    "to", "with", "vs", "your", "you", "i", "we", "so",
}


def _keywords(text: str) -> set:
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


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
        self, feedback_provider: Optional[FeedbackProvider] = None
    ) -> CycleResult:
        """Execute one full recursive loop and log it.

        1. Get creator context (Agent 1)
        2. Get opportunities (Agent 2)
        3. Generate recommendations
        4. Present to creator
        5. Collect feedback
        6. Push learnings back to Agent 1
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

        self._mark_surfaced(recommendations)
        self.present_recommendations(recommendations, opportunities)
        feedback = self.collect_feedback(recommendations, feedback_provider)

        recs_by_id = {r.id: r for r in recommendations}
        for fb in feedback:
            self._ingest_feedback(fb, recs_by_id.get(fb.recommendation_id))

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
            return self.memory.increment_run_count()
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

    # -- Deterministic fallback path ------------------------------------

    def _fallback_recommendations(
        self, context: CreatorContext, opportunities: List[Opportunity]
    ) -> List[Recommendation]:
        recs: List[Recommendation] = []
        for i, opp in enumerate(opportunities[: self.max_recommendations], 1):
            pattern = self._best_pattern(context.learned_patterns, opp)
            idea = self._matching_idea(context.pending_ideas, opp)
            confidence = self._confidence(opp, pattern)
            recs.append(
                Recommendation(
                    id=f"rec_{i:03d}",
                    rank=i,
                    title=opp.suggested_angle or opp.topic,
                    why=self._build_why(opp, pattern, idea),
                    supporting_patterns=[pattern.id] if pattern else [],
                    opportunity_id=opp.id,
                    confidence=confidence,
                    action_steps=self._build_action_steps(context, opp, idea),
                )
            )
        recs.sort(key=lambda r: r.confidence, reverse=True)
        for i, rec in enumerate(recs, start=1):
            rec.rank = i
        return recs

    @staticmethod
    def _best_pattern(
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

    @staticmethod
    def _matching_idea(
        ideas: List[PendingIdea], opp: Opportunity
    ) -> Optional[PendingIdea]:
        opp_words = _keywords(f"{opp.topic} {opp.suggested_angle}")
        for idea in ideas:
            # A single shared word (e.g. "nvidia") is too weak to claim the
            # idea's research applies to this opportunity.
            if len(_keywords(idea.title) & opp_words) >= 2:
                return idea
        return None

    @staticmethod
    def _confidence(
        opp: Opportunity, pattern: Optional[LearnedPattern]
    ) -> float:
        # Cold start (no patterns) lands near 0.4; strong patterns push
        # toward 0.9 — matching the trajectory in docs/RECURSIVE_LOOP.md.
        base = 0.2 + 0.25 * (opp.composite_score / 100.0)
        if pattern:
            base += 0.5 * pattern.confidence
        return round(min(0.95, max(0.05, base)), 2)

    @staticmethod
    def _build_why(
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

    @staticmethod
    def _build_action_steps(
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

    # ------------------------------------------------------------------
    # Creator interface (Milestone 3.3)
    # ------------------------------------------------------------------

    def present_recommendations(
        self,
        recommendations: List[Recommendation],
        opportunities: Optional[List[Opportunity]] = None,
    ) -> None:
        if not recommendations:
            self._print("\n  No recommendations this cycle (no eligible opportunities).")
            return
        opps = {o.id: o for o in (opportunities or [])}
        self._print("\n  ── TOP RECOMMENDATIONS " + "─" * 38)
        for rec in recommendations:
            bar = "█" * round(rec.confidence * 10) + "░" * (10 - round(rec.confidence * 10))
            self._print(f"\n  #{rec.rank}  {rec.title}")
            self._print(f"      confidence {rec.confidence:.2f} [{bar}]")
            self._print(f"      WHY: {rec.why}")
            if rec.supporting_patterns:
                self._print(
                    f"      PATTERNS CITED: {', '.join(rec.supporting_patterns)}"
                )
            opp = opps.get(rec.opportunity_id)
            if opp and opp.sources:
                for s in opp.sources:
                    detail = f" — {s.detail}" if s.detail else ""
                    self._print(f"      SOURCE: {s.name}{detail} ({s.url})")
            self._print("      ACTION STEPS:")
            for j, step in enumerate(rec.action_steps, 1):
                self._print(f"        {j}. {step}")
        self._print("\n  " + "─" * 60)

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
        self._print(f"\n  Feedback for #{rec.rank} \"{rec.title}\"")
        while True:
            raw = self._input(
                "    [a]ccept / [r]eject / [d]efer (default d): "
            ).strip().lower()
            action = {
                "a": "accepted", "accept": "accepted", "accepted": "accepted",
                "r": "rejected", "reject": "rejected", "rejected": "rejected",
                "d": "deferred", "defer": "deferred", "deferred": "deferred",
                "": "deferred",
            }.get(raw)
            if action:
                break
            self._print("    Please enter a, r, or d.")
        notes = self._input("    Notes (optional): ").strip()
        return Feedback(recommendation_id=rec.id, action=action, notes=notes)

    def _show_learning_summary(self, patterns_before: Dict[str, float]) -> None:
        """'What I learned' summary shown after each cycle."""
        context = self.memory.get_creator_context()
        after = {p.id: p for p in context.learned_patterns}
        new = [p for pid, p in after.items() if pid not in patterns_before]
        changed = [
            (p, patterns_before[pid])
            for pid, p in after.items()
            if pid in patterns_before and abs(p.confidence - patterns_before[pid]) > 1e-9
        ]
        self._print("\n  ── WHAT I LEARNED THIS CYCLE " + "─" * 32)
        if not new and not changed:
            self._print("    Nothing new — no feedback moved any conclusions.")
        for p in new:
            self._print(
                f"    NEW  {p.id}: \"{p.pattern}\" (confidence {p.confidence:.2f})"
            )
        for p, old in changed:
            arrow = "↑" if p.confidence > old else "↓"
            self._print(
                f"    {arrow}    {p.id}: confidence {old:.2f} → {p.confidence:.2f} "
                f"({p.evidence_count} evidence items)"
            )
        self._print("  " + "─" * 60)

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
        with open(self.history_path, "w", encoding="utf-8") as fh:
            json.dump({"runs": [r.to_dict() for r in history]}, fh, indent=2)

    def show_improvement_metrics(self) -> None:
        """Run-over-run dashboard proving the system is getting smarter."""
        history = self._load_history()
        self._print("\n  ── IMPROVEMENT METRICS " + "─" * 38)
        if not history:
            self._print("    No cycles logged yet. Run a cycle first.")
            self._print("  " + "─" * 60)
            return

        headers = ["metric"] + [f"Run {r.run_number}" for r in history]
        rows = [
            ("Learned patterns", [r.metrics.get("learned_patterns", 0) for r in history]),
            ("Avg confidence", [f"{r.metrics.get('avg_confidence', 0):.2f}" for r in history]),
            (
                "Acceptance rate",
                [
                    "—" if r.metrics.get("acceptance_rate") is None
                    else f"{r.metrics['acceptance_rate']:.0%}"
                    for r in history
                ],
            ),
            ("Duplicates filtered", [r.metrics.get("duplicates_filtered", 0) for r in history]),
            ("Action steps / rec", [r.metrics.get("avg_action_steps", 0) for r in history]),
        ]
        widths = [max(len(headers[0]), max(len(name) for name, _ in rows))] + [
            max(8, len(h)) for h in headers[1:]
        ]
        line = "    " + "  ".join(h.ljust(w) for h, w in zip(headers, widths))
        self._print(line)
        self._print("    " + "  ".join("-" * w for w in widths))
        for name, values in rows:
            cells = [name.ljust(widths[0])] + [
                str(v).ljust(w) for v, w in zip(values, widths[1:])
            ]
            self._print("    " + "  ".join(cells))

        first, last = history[0], history[-1]
        if len(history) > 1:
            d_patterns = last.metrics.get("learned_patterns", 0) - first.metrics.get("learned_patterns", 0)
            d_conf = last.metrics.get("avg_confidence", 0) - first.metrics.get("avg_confidence", 0)
            self._print(
                f"\n    Run {first.run_number} → Run {last.run_number}: "
                f"{d_patterns:+d} patterns, "
                f"{d_conf:+.2f} avg confidence"
            )
        self._print("  " + "─" * 60)
