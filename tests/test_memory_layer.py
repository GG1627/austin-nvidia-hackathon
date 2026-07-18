"""
test_memory_layer.py — Unit tests for Agent 1 (Memory & Knowledge Layer).

Covers spec section 11's test plan:
  - Seed fake onboarding_finding episodes simulating a creator's past
    catalog, trigger immediate onboarding consolidation, assert hypotheses
    appear at capped confidence, the entity graph populates, and
    get_context() returns a populated (not empty) response.
  - Layer on fake ongoing episodes across several simulated runs and assert
    the normal lifecycle rules: confidence moves per the deterministic
    math, duplicates merge instead of duplicating, and promotion to `core`
    only fires after run 1 (never during onboarding).

No live NVIDIA/vLLM/Supabase credentials are required — the LLM
proposal/calibration calls and the Supabase client are mocked, matching
how the LLM was already mocked in the project's original Agent 1 tests.

Run with:
    python -m pytest tests/test_memory_layer.py -v
    python tests/test_memory_layer.py
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fakes import FakeSupabaseClient, fake_embed
from agents.models import OnboardingFindingPayload
from agents.consolidation import (
    _apply_support,
    _apply_contradict,
    _promote_status,
    run_consolidation,
)
from agents.memory import log_episode, get_context
from agents.onboarding import run_onboarding


# ---------------------------------------------------------------------------
# Pure confidence math — no DB, no LLM.
# ---------------------------------------------------------------------------


class TestConsolidationMath(unittest.TestCase):
    def test_support_single_model_factor(self):
        self.assertAlmostEqual(_apply_support(0.30, dual=False), 0.30 + 0.15 * 0.70, places=6)

    def test_support_dual_model_factor_is_faster(self):
        single = _apply_support(0.30, dual=False)
        dual = _apply_support(0.30, dual=True)
        self.assertGreater(dual, single)
        self.assertAlmostEqual(dual, 0.30 + 0.20 * 0.70, places=6)

    def test_contradict_shrinks_confidence(self):
        self.assertAlmostEqual(_apply_contradict(0.50), 0.30, places=6)

    def test_promotion_to_validated_at_threshold(self):
        self.assertEqual(_promote_status("hypothesis", 3, 0.61), "validated")
        self.assertEqual(_promote_status("hypothesis", 2, 0.99), "hypothesis")  # not enough support
        self.assertEqual(_promote_status("hypothesis", 3, 0.60), "hypothesis")  # confidence not > 0.60

    def test_promotion_to_core_requires_five_support_and_high_confidence(self):
        self.assertEqual(_promote_status("validated", 5, 0.86), "core")
        self.assertEqual(_promote_status("validated", 4, 0.99), "validated")  # not enough support

    def test_onboarding_caps_promotion_at_validated(self):
        self.assertEqual(_promote_status("validated", 5, 0.86, onboarding=True), "validated")

    def test_low_confidence_deprecates_regardless_of_support(self):
        self.assertEqual(_promote_status("validated", 10, 0.19), "deprecated")


# ---------------------------------------------------------------------------
# Onboarding bootstrap + get_context, against an in-memory fake Supabase.
# ---------------------------------------------------------------------------


def _catalog() -> list[OnboardingFindingPayload]:
    return [
        OnboardingFindingPayload("Short benchmark A", "2026-01-01", 10, 120000, 65.0, ["ai", "benchmark"]),
        OnboardingFindingPayload("Short benchmark B", "2026-02-01", 11, 110000, 63.0, ["ai", "benchmark"]),
        OnboardingFindingPayload("Long ramble A", "2026-03-01", 25, 20000, 30.0, ["ai"]),
        OnboardingFindingPayload("Long ramble B", "2026-04-01", 28, 18000, 28.0, ["ai"]),
        OnboardingFindingPayload("Long ramble C", "2026-05-01", 30, 15000, 25.0, ["ai"]),
    ]


LONG_VIDEO_STATEMENT = "Videos over 20 minutes underperform in this creator's catalog"


def _propose_long_video_pattern(episodes_compact, active_compact):
    """Stand-in for the Nemotron consolidation call: emit/reinforce a single
    hypothesis whenever a >20min video episode shows up in the batch."""
    long_ids = [e["id"] for e in episodes_compact if e["payload"].get("duration_minutes", 0) > 20]
    if not long_ids:
        return {"new_hypotheses": [], "evidence_updates": [], "contradictions": []}

    existing = next((a for a in active_compact if a["statement"] == LONG_VIDEO_STATEMENT), None)
    if existing:
        return {
            "new_hypotheses": [],
            "evidence_updates": [{"insight_id": existing["id"], "direction": "support", "episode_id": long_ids[0]}],
            "contradictions": [],
        }
    return {
        "new_hypotheses": [{
            "statement": LONG_VIDEO_STATEMENT,
            "category": "timing",
            "volatility": "semi_stable",
            "episode_ids": long_ids,
        }],
        "evidence_updates": [],
        "contradictions": [],
    }


class TestOnboardingBootstrap(unittest.TestCase):
    def setUp(self):
        self.fake_db = FakeSupabaseClient()
        self.patchers = [
            mock.patch("agents.consolidation.get_client", return_value=self.fake_db),
            mock.patch("agents.memory.get_client", return_value=self.fake_db),
            mock.patch("agents.onboarding.get_client", return_value=self.fake_db),
        ]
        for p in self.patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patchers])

    def test_onboarding_seeds_capped_hypothesis_and_graph(self):
        with mock.patch("agents.consolidation.propose_consolidation", side_effect=_propose_long_video_pattern):
            result = run_onboarding("Test Creator", {"niche": "AI tools"}, _catalog())

        self.assertEqual(result["episodes_logged"], 5)

        # Hypothesis appears, at the fixed capped starting confidence — never higher on creation.
        insights = self.fake_db.tables["insights"]
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["status"], "hypothesis")
        self.assertEqual(insights[0]["confidence"], 0.30)
        self.assertEqual(insights[0]["created_run"], result["run_id"])

        # Entity graph populated: 1 creator, 5 videos, topic nodes, performance edges.
        nodes = self.fake_db.tables["nodes"]
        self.assertEqual(sum(1 for n in nodes if n["type"] == "creator"), 1)
        self.assertEqual(sum(1 for n in nodes if n["type"] == "video"), 5)
        self.assertTrue(any(n["type"] == "topic" and n["name"] == "benchmark" for n in nodes))

        edges = self.fake_db.tables["edges"]
        self.assertTrue(any(e["relation"] == "performed_well" for e in edges))
        self.assertTrue(any(e["relation"] == "underperformed" for e in edges))

        # get_context returns a populated response, not an empty shell.
        ctx = get_context("what should this creator make next?")
        self.assertEqual(ctx["creator_profile"].get("niche"), "AI tools")
        self.assertEqual(ctx["core_insights"], [])  # nothing reaches core on run 1
        self.assertEqual(len(ctx["relevant_insights"]), 1)
        self.assertEqual(ctx["relevant_insights"][0]["status"], "hypothesis")
        self.assertGreater(len(ctx["related_entities"]), 0)

    def test_promotion_caps_at_validated_during_onboarding_then_reaches_core_after(self):
        with mock.patch("agents.consolidation.propose_consolidation", side_effect=_propose_long_video_pattern):
            onboarding_result = run_onboarding("Test Creator", {}, _catalog())
        run_id = onboarding_result["run_id"]

        # Feed enough further "support" back in, still tagged onboarding=True, to cross
        # both the validated AND core numeric thresholds (support>=5, confidence>0.85).
        with mock.patch("agents.consolidation.propose_consolidation", side_effect=_propose_long_video_pattern), \
             mock.patch("agents.consolidation.calibrate_batch", return_value={0: True}):
            for i in range(7):
                log_episode("observation", {"note": f"another long video underperformed #{i}", "duration_minutes": 25}, run_id)
                run_consolidation(run_id=run_id, onboarding=True)

        insight = self.fake_db.tables["insights"][0]
        self.assertGreaterEqual(insight["evidence_for"], 5)
        self.assertGreater(insight["confidence"], 0.85)
        self.assertEqual(insight["status"], "validated")  # capped — never core during onboarding

        # The same evidence, arriving after onboarding (heartbeat-driven, onboarding=False),
        # is free to promote all the way to core.
        with mock.patch("agents.consolidation.propose_consolidation", side_effect=_propose_long_video_pattern), \
             mock.patch("agents.consolidation.calibrate_batch", return_value={0: True}):
            log_episode("observation", {"note": "yet another long video underperformed", "duration_minutes": 25}, run_id)
            run_consolidation(run_id=run_id, onboarding=False)

        insight = self.fake_db.tables["insights"][0]
        self.assertEqual(insight["status"], "core")

    def test_run1_metrics_record_onboarding_baseline(self):
        with mock.patch("agents.consolidation.propose_consolidation", side_effect=_propose_long_video_pattern):
            result = run_onboarding("Test Creator", {}, _catalog())

        run_row = next(r for r in self.fake_db.tables["runs"] if r["id"] == result["run_id"])
        metrics = run_row["metrics"]
        by_status = metrics["insight_counts_by_status"]
        self.assertEqual(by_status.get("hypothesis"), 1)
        self.assertEqual(by_status.get("validated", 0), 0)
        self.assertEqual(by_status.get("core", 0), 0)
        self.assertTrue(metrics["onboarding"])


# ---------------------------------------------------------------------------
# Dedup — the actual pgvector-cosine merge path in consolidation.py.
# ---------------------------------------------------------------------------


class TestDedupMerge(unittest.TestCase):
    def setUp(self):
        self.fake_db = FakeSupabaseClient()
        self.patchers = [
            mock.patch("agents.consolidation.get_client", return_value=self.fake_db),
            mock.patch("agents.memory.get_client", return_value=self.fake_db),
            mock.patch("agents.consolidation.embed", side_effect=fake_embed),
        ]
        for p in self.patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patchers])

    def test_repeated_statement_merges_instead_of_duplicating(self):
        run_row = self.fake_db.insert("runs", {"metrics": {}})
        run_id = run_row["id"]

        naive_proposal = {
            "new_hypotheses": [{
                "statement": "Benchmark-format videos outperform opinion pieces",
                "category": "format",
                "volatility": "semi_stable",
                "episode_ids": [],
            }],
            "evidence_updates": [],
            "contradictions": [],
        }

        for i in range(2):
            log_episode("observation", {"note": f"benchmark video did well #{i}"}, run_id)
            with mock.patch("agents.consolidation.propose_consolidation", return_value=naive_proposal), \
                 mock.patch("agents.consolidation.calibrate_batch", return_value={0: False}):
                result = run_consolidation(run_id=run_id, onboarding=False)

        insights = self.fake_db.tables["insights"]
        self.assertEqual(len(insights), 1)  # second pass merged, did not duplicate
        self.assertEqual(insights[0]["evidence_for"], 1)
        self.assertAlmostEqual(insights[0]["confidence"], 0.30 + 0.15 * 0.70, places=6)
        self.assertEqual(result["duplicates_merged"], 1)


# ---------------------------------------------------------------------------
# get_context on a cold / empty store.
# ---------------------------------------------------------------------------


class TestGetContextEmptyStore(unittest.TestCase):
    def test_empty_store_returns_well_shaped_empty_response(self):
        fake_db = FakeSupabaseClient()
        with mock.patch("agents.memory.get_client", return_value=fake_db), \
             mock.patch("agents.consolidation.get_client", return_value=fake_db):
            ctx = get_context("anything")

        self.assertEqual(ctx["creator_profile"], {})
        self.assertEqual(ctx["core_insights"], [])
        self.assertEqual(ctx["relevant_insights"], [])
        self.assertEqual(ctx["related_entities"], [])
        self.assertIsNone(ctx["last_run"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
