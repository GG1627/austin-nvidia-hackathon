"""Tests for Agent 3 (strategist) — run with:  python3 -m unittest -v

Everything runs offline against the mock Agent 1/2 stubs; no API keys,
no network, no third-party packages.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from agents.agent3_strategist import StrategistAgent
from agents.contracts import (
    CreatorContext,
    CreatorProfile,
    CycleResult,
    Feedback,
    LearnedPattern,
    Opportunity,
    OpportunitySource,
    PendingIdea,
    Recommendation,
)
from agents.stubs import MockMemoryAgent, MockResearchAgent

PROMPT_PATH = os.path.join(REPO_ROOT, "prompts", "agent3_system.txt")


def make_context(with_patterns=True):
    return CreatorContext(
        creator_profile=CreatorProfile(
            niche="AI tools for developers",
            audience="engineers, 25-40",
            preferred_length="10-15 minutes",
            posting_frequency="weekly",
        ),
        learned_patterns=(
            [
                LearnedPattern("p_001", "Benchmark videos outperform opinion pieces",
                               confidence=0.87, evidence_count=6),
                LearnedPattern("p_002", "Videos under 15 minutes retain audience better",
                               confidence=0.79, evidence_count=4),
            ]
            if with_patterns else []
        ),
        top_performing_topics=["LLM benchmarks", "local AI", "NVIDIA tools"],
        avoid_topics=["crypto", "politics"],
        pending_ideas=[PendingIdea("NVIDIA Claw Deep Dive", 0.8)],
    )


def make_opportunities():
    return [
        Opportunity(
            id="opp_claw", topic="NVIDIA Claw Recursive Agents",
            trend_score=94, niche_alignment=91, competition_gap=78,
            composite_score=89, reason="Rapidly trending, low saturation",
            suggested_angle="Building Recursive Agents with NVIDIA Claw",
            sources=[OpportunitySource("Reddit r/LocalLLaMA", "https://reddit.com", "1840 upvotes")],
        ),
        Opportunity(
            id="opp_bench", topic="Local LLM benchmark shootout",
            trend_score=81, niche_alignment=95, competition_gap=60,
            composite_score=83, reason="Evergreen benchmark topic",
            suggested_angle="I benchmarked 7 local LLMs",
        ),
        Opportunity(
            id="opp_crypto", topic="Crypto mining on gaming GPUs",
            trend_score=70, niche_alignment=20, competition_gap=30,
            composite_score=47, reason="Trending but off-niche",
            suggested_angle="Is GPU crypto mining back?",
        ),
        Opportunity(
            id="opp_nim", topic="NVIDIA NIM microservices",
            trend_score=76, niche_alignment=88, competition_gap=82,
            composite_score=83, reason="Underexplored official tooling",
            suggested_angle="Ship an AI app with NVIDIA NIM",
        ),
    ]


def make_strategist(tmpdir, llm=None, input_fn=input):
    memory = MockMemoryAgent(os.path.join(tmpdir, "knowledge_graph.json"))
    research = MockResearchAgent(memory)
    strategist = StrategistAgent(
        memory_agent=memory,
        research_agent=research,
        llm=llm,
        prompt_path=PROMPT_PATH,
        history_path=os.path.join(tmpdir, "cycle_history.json"),
        input_fn=input_fn,
        print_fn=lambda *_: None,  # keep test output quiet
    )
    return strategist, memory, research


def simulated_feedback(rec):
    if rec.rank == 1:
        return Feedback(rec.id, "accepted", "starting outline")
    if rec.rank == 3:
        return Feedback(rec.id, "rejected", "too opinion-flavored")
    return Feedback(rec.id, "deferred", "")


class FakeLLM:
    available = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def chat(self, system, user, **kwargs):
        self.calls += 1
        return self.reply


class TestContracts(unittest.TestCase):
    def test_round_trip(self):
        ctx = make_context()
        self.assertEqual(
            CreatorContext.from_dict(ctx.to_dict()).to_dict(), ctx.to_dict()
        )
        opp = make_opportunities()[0]
        self.assertEqual(Opportunity.from_dict(opp.to_dict()).to_dict(), opp.to_dict())
        rec = Recommendation("rec_001", 1, "t", "w", ["p_001"], "opp_claw", 0.9,
                             ["a", "b", "c"])
        self.assertEqual(Recommendation.from_dict(rec.to_dict()), rec)
        fb = Feedback("rec_001", "accepted", "n")
        self.assertEqual(Feedback.from_dict(fb.to_dict()), fb)

    def test_tolerates_missing_keys(self):
        ctx = CreatorContext.from_dict({"creator_profile": {"niche": "x"}})
        self.assertEqual(ctx.creator_profile.niche, "x")
        self.assertEqual(ctx.learned_patterns, [])
        opp = Opportunity.from_dict({"id": "o1", "topic": "t"})
        self.assertEqual(opp.composite_score, 0.0)

    def test_source_tolerates_architecture_doc_shape(self):
        src = OpportunitySource.from_dict({"name": "HN", "url": "u", "points": 312})
        self.assertEqual(src.detail, "312 points")


class TestRecommendationEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.strategist, self.memory, _ = make_strategist(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fallback_meets_quality_standard(self):
        recs = self.strategist.generate_recommendations(
            make_context(), make_opportunities()
        )
        self.assertEqual(len(recs), 3)
        self.assertEqual(self.strategist.last_engine, "fallback")
        for rec in recs:
            self.assertTrue(rec.title)                      # What
            self.assertIn("p_", rec.why)                    # Why cites a pattern id
            self.assertTrue(rec.supporting_patterns)        # tied to Agent 1 patterns
            self.assertIn("Trend score", rec.why)           # Evidence from Agent 2
            self.assertTrue(0.0 <= rec.confidence <= 1.0)   # Confidence
            self.assertGreaterEqual(len(rec.action_steps), 3)  # Action steps
        # Ranked by confidence, ranks sequential from 1.
        confs = [r.confidence for r in recs]
        self.assertEqual(confs, sorted(confs, reverse=True))
        self.assertEqual([r.rank for r in recs], [1, 2, 3])

    def test_avoid_topics_and_surfaced_are_excluded(self):
        opps = make_opportunities()
        opps[1].already_surfaced = True
        recs = self.strategist.generate_recommendations(make_context(), opps)
        opp_ids = {r.opportunity_id for r in recs}
        self.assertNotIn("opp_crypto", opp_ids)   # avoid list
        self.assertNotIn("opp_bench", opp_ids)    # already surfaced
        self.assertEqual(opp_ids, {"opp_claw", "opp_nim"})

    def test_cold_start_has_low_confidence_and_says_so(self):
        recs = self.strategist.generate_recommendations(
            make_context(with_patterns=False), make_opportunities()
        )
        for rec in recs:
            self.assertLess(rec.confidence, 0.5)
            self.assertEqual(rec.supporting_patterns, [])
            self.assertIn("No learned patterns yet", rec.why)

    def test_pending_idea_referenced(self):
        recs = self.strategist.generate_recommendations(
            make_context(), make_opportunities()
        )
        claw = next(r for r in recs if r.opportunity_id == "opp_claw")
        self.assertIn("80%", claw.why)
        self.assertTrue(any("NVIDIA Claw Deep Dive" in s for s in claw.action_steps))

    def test_llm_path_used_when_valid(self):
        reply = json.dumps([
            {
                "rank": 1, "title": "Building Recursive Agents with NVIDIA Claw",
                "why": "Cites p_001 and trend 94/100", "supporting_patterns": ["p_001"],
                "opportunity_id": "opp_claw", "confidence": 0.91,
                "action_steps": ["Review notes", "Record benchmark first", "Target 12 min"],
            },
            {
                "rank": 2, "title": "Ship an AI app with NVIDIA NIM",
                "why": "Cites p_002, gap 82/100", "supporting_patterns": ["p_002"],
                "opportunity_id": "opp_nim", "confidence": 0.74,
                "action_steps": ["Outline", "Build demo app", "Record"],
            },
        ])
        llm = FakeLLM("```json\n" + reply + "\n```")
        strategist, _, _ = make_strategist(self.tmp.name, llm=llm)
        recs = strategist.generate_recommendations(make_context(), make_opportunities())
        self.assertEqual(strategist.last_engine, "nim")
        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0].opportunity_id, "opp_claw")
        self.assertEqual(recs[0].rank, 1)

    def test_llm_garbage_falls_back(self):
        strategist, _, _ = make_strategist(self.tmp.name, llm=FakeLLM("not json at all"))
        recs = strategist.generate_recommendations(make_context(), make_opportunities())
        self.assertEqual(strategist.last_engine, "fallback")
        self.assertEqual(len(recs), 3)

    def test_llm_below_quality_standard_falls_back(self):
        # Too few action steps + bogus opportunity id -> rejected by validator.
        reply = json.dumps([
            {"rank": 1, "title": "T", "why": "w", "supporting_patterns": ["p_001"],
             "opportunity_id": "opp_claw", "confidence": 0.9,
             "action_steps": ["only", "two"]},
            {"rank": 2, "title": "T2", "why": "w2", "supporting_patterns": ["p_001"],
             "opportunity_id": "opp_nonexistent", "confidence": 0.8,
             "action_steps": ["a", "b", "c"]},
        ])
        strategist, _, _ = make_strategist(self.tmp.name, llm=FakeLLM(reply))
        recs = strategist.generate_recommendations(make_context(), make_opportunities())
        self.assertEqual(strategist.last_engine, "fallback")
        self.assertEqual(len(recs), 3)


class TestCycleAndLearning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_cycle_end_to_end(self):
        strategist, memory, _ = make_strategist(self.tmp.name)
        result = strategist.run_cycle(feedback_provider=simulated_feedback)

        self.assertEqual(result.run_number, 1)
        self.assertEqual(len(result.recommendations), 3)
        self.assertEqual(len(result.feedback), 3)
        # Feedback reached Agent 1.
        self.assertEqual(len(memory.graph["acceptance_history"]), 3)
        # Accepted feedback created a learned pattern (recursive learning).
        self.assertGreaterEqual(memory.pattern_count(), 1)
        # Recommended opportunities were marked surfaced for dedup.
        self.assertEqual(len(memory.get_surfaced_topics()), 3)
        # Cycle was logged with metrics.
        history = strategist._load_history()
        self.assertEqual(len(history), 1)
        self.assertIn("avg_confidence", history[0].metrics)

    def test_interactive_feedback_collection(self):
        answers = iter(["a", "love it", "x", "r", "nope", "", ""])
        strategist, memory, _ = make_strategist(
            self.tmp.name, input_fn=lambda _prompt: next(answers)
        )
        recs = [
            Recommendation("rec_001", 1, "A", "w", [], "opp_a", 0.5, ["1", "2", "3"]),
            Recommendation("rec_002", 2, "B", "w", [], "opp_b", 0.5, ["1", "2", "3"]),
        ]
        feedback = strategist.collect_feedback(recs)
        self.assertEqual(feedback[0].action, "accepted")
        self.assertEqual(feedback[0].notes, "love it")
        # "x" is invalid and re-prompted; then "r" -> rejected.
        self.assertEqual(feedback[1].action, "rejected")

    def test_system_improves_over_three_runs(self):
        strategist, memory, _ = make_strategist(self.tmp.name)
        for _ in range(3):
            strategist.run_cycle(feedback_provider=simulated_feedback)

        history = strategist._load_history()
        self.assertEqual([r.run_number for r in history], [1, 2, 3])
        m1, m3 = history[0].metrics, history[2].metrics
        # Knowledge grows and confidence rises (the recursive-loop claim).
        self.assertGreater(m3["learned_patterns"], m1["learned_patterns"])
        self.assertGreater(m3["avg_confidence"], m1["avg_confidence"])
        # Dedup kicks in after run 1.
        self.assertEqual(m1["duplicates_filtered"], 0)
        self.assertGreaterEqual(history[1].metrics["duplicates_filtered"], 3)
        # No opportunity recommended twice across runs.
        seen = []
        for run in history:
            seen.extend(r.opportunity_id for r in run.recommendations)
        self.assertEqual(len(seen), len(set(seen)))

    def test_memory_survives_restart(self):
        strategist, _, _ = make_strategist(self.tmp.name)
        strategist.run_cycle(feedback_provider=simulated_feedback)

        # Fresh objects reading the same files = process restart.
        strategist2, memory2, _ = make_strategist(self.tmp.name)
        self.assertGreaterEqual(memory2.pattern_count(), 1)
        self.assertEqual(memory2.graph["run_count"], 1)
        result = strategist2.run_cycle(feedback_provider=simulated_feedback)
        self.assertEqual(result.run_number, 2)

    def test_metrics_dashboard_renders(self):
        lines = []
        strategist, memory, research = make_strategist(self.tmp.name)
        strategist._print = lines.append
        strategist.run_cycle(feedback_provider=simulated_feedback)
        strategist.run_cycle(feedback_provider=simulated_feedback)
        lines.clear()
        strategist.show_improvement_metrics()
        text = "\n".join(lines)
        self.assertIn("Run 1", text)
        self.assertIn("Run 2", text)
        self.assertIn("Learned patterns", text)
        self.assertIn("Run 1 → Run 2", text)


class TestMainEntryPoint(unittest.TestCase):
    def test_main_simulate_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "main.py"),
                 "--cycles", "2", "--simulate", "--offline"],
                cwd=tmp, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("CYCLE 1", proc.stdout)
            self.assertIn("CYCLE 2", proc.stdout)
            self.assertIn("IMPROVEMENT METRICS", proc.stdout)
            self.assertTrue(
                os.path.exists(os.path.join(tmp, "memory", "knowledge_graph.json"))
            )
            self.assertTrue(
                os.path.exists(os.path.join(tmp, "memory", "cycle_history.json"))
            )


if __name__ == "__main__":
    unittest.main()
