"""
test_agent1.py — Unit tests for Agent 1 (Memory & Knowledge Engineer)

Run with:
    python -m pytest tests/test_agent1.py -v
    # or without pytest:
    python tests/test_agent1.py

Tests do NOT require an NVIDIA API key — pattern extraction is mocked.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.models import (
    ContentItem, CreatorProfile, LearnedPattern, Feedback, ContentIdea
)
from tools.memory_tool import MemoryStore
from agents.agent1_memory import CreatorMemoryAgent


class TestMemoryStore(unittest.TestCase):
    """Tests for the low-level persistence layer."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        self.store = MemoryStore(self.tmp)

    def tearDown(self):
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def test_initialises_empty(self):
        self.assertEqual(self.store.get_content_items(), [])
        self.assertEqual(self.store.get_patterns(), [])
        self.assertEqual(self.store.get_run_count(), 0)

    def test_add_and_retrieve_content_item(self):
        item = ContentItem(
            title="LLM Benchmarks 2026",
            format="benchmark",
            length_min=13.5,
            views=120000,
            retention_pct=64.0,
            topics=["LLM", "benchmark", "NVIDIA"],
        )
        self.store.add_content_item(item)
        items = self.store.get_content_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "LLM Benchmarks 2026")
        self.assertEqual(items[0].views, 120000)

    def test_add_and_retrieve_pattern(self):
        p = LearnedPattern(
            pattern="Benchmark videos outperform opinion pieces",
            category="format",
            confidence=0.82,
            evidence_count=4,
        )
        self.store.add_pattern(p)
        patterns = self.store.get_patterns(min_confidence=0.5)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].confidence, 0.82)

    def test_pattern_confidence_filter(self):
        self.store.add_pattern(LearnedPattern(
            pattern="Strong pattern", category="format", confidence=0.85, evidence_count=5
        ))
        self.store.add_pattern(LearnedPattern(
            pattern="Weak pattern", category="topic", confidence=0.3, evidence_count=1
        ))
        strong = self.store.get_patterns(min_confidence=0.5)
        self.assertEqual(len(strong), 1)
        self.assertEqual(strong[0].pattern, "Strong pattern")

    def test_update_pattern(self):
        p = LearnedPattern(
            pattern="Videos under 15 minutes retain audience",
            category="length",
            confidence=0.6,
            evidence_count=3,
        )
        self.store.add_pattern(p)
        result = self.store.update_pattern(p.id, {"confidence": 0.75, "evidence_count": 5})
        self.assertTrue(result)
        updated = self.store.get_patterns(min_confidence=0.0)[0]
        self.assertEqual(updated.confidence, 0.75)
        self.assertEqual(updated.evidence_count, 5)

    def test_persistence_survives_reload(self):
        item = ContentItem(title="Test Video", views=50000, format="tutorial")
        self.store.add_content_item(item)
        # Re-open the same file
        store2 = MemoryStore(self.tmp)
        items = store2.get_content_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Test Video")

    def test_run_counter_increments(self):
        self.assertEqual(self.store.increment_run(), 1)
        self.assertEqual(self.store.increment_run(), 2)
        self.assertEqual(self.store.increment_run(), 3)
        self.assertEqual(self.store.get_run_count(), 3)

    def test_feedback_acceptance_rate(self):
        self.store.add_feedback(Feedback(
            recommendation_id="r1", recommendation_title="Vid A", action="accepted"
        ))
        self.store.add_feedback(Feedback(
            recommendation_id="r2", recommendation_title="Vid B", action="accepted"
        ))
        self.store.add_feedback(Feedback(
            recommendation_id="r3", recommendation_title="Vid C", action="rejected"
        ))
        metrics = self.store.get_metrics()
        self.assertAlmostEqual(metrics["acceptance_rate"], 0.667, places=2)

    def test_opportunity_deduplication(self):
        self.store.mark_opportunity_surfaced("opp_001")
        self.assertTrue(self.store.was_opportunity_surfaced("opp_001"))
        self.assertFalse(self.store.was_opportunity_surfaced("opp_999"))


class TestCreatorMemoryAgent(unittest.TestCase):
    """Tests for the Agent 1 logic layer (LLM calls mocked)."""

    def setUp(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        # Patch OpenAI client so no real API calls happen
        self.patcher = patch("agents.agent1_memory.OpenAI")
        mock_openai_cls = self.patcher.start()
        self.mock_client = MagicMock()
        mock_openai_cls.return_value = self.mock_client
        self.agent = CreatorMemoryAgent(memory_path=self.tmp)

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.tmp):
            os.remove(self.tmp)

    def _mock_llm_patterns(self, patterns: list):
        """Configure the mock LLM to return the given pattern list."""
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = json.dumps(patterns)
        self.mock_client.chat.completions.create.return_value = mock_resp

    def test_ingest_profile(self):
        profile = CreatorProfile(
            niche="AI tools for developers",
            audience_description="engineers aged 25-40",
            preferred_format="benchmark",
            avoid_topics=["crypto", "politics"],
        )
        self.agent.ingest_profile(profile)
        stored = self.agent.store.get_profile()
        self.assertEqual(stored.niche, "AI tools for developers")
        self.assertEqual(stored.avoid_topics, ["crypto", "politics"])

    def test_ingest_content_item_triggers_pattern_extraction(self):
        self._mock_llm_patterns([
            {"pattern": "Benchmark videos outperform opinion pieces",
             "category": "format", "confidence": 0.82, "evidence_count": 2}
        ])
        # Need at least 2 items for extraction to fire
        self.agent.store.add_content_item(ContentItem(
            title="Opinion: Is AI Overhyped?", format="opinion", views=38000,
            retention_pct=42.0, length_min=18.0
        ))
        self.agent.ingest_content_result(ContentItem(
            title="LLM Benchmark Showdown", format="benchmark", views=122000,
            retention_pct=65.0, length_min=13.0
        ))
        patterns = self.agent.get_patterns(min_confidence=0.5)
        self.assertEqual(len(patterns), 1)
        self.assertIn("Benchmark", patterns[0].pattern)

    def test_three_items_extract_patterns(self):
        self._mock_llm_patterns([
            {"pattern": "Tutorial format drives highest retention",
             "category": "format", "confidence": 0.75, "evidence_count": 3},
            {"pattern": "Videos under 15 minutes retain audience better",
             "category": "length", "confidence": 0.68, "evidence_count": 3},
        ])
        items = [
            ContentItem(title="Tut A", format="tutorial", views=90000, retention_pct=68, length_min=12),
            ContentItem(title="Tut B", format="tutorial", views=110000, retention_pct=71, length_min=11),
        ]
        for item in items:
            self.agent.store.add_content_item(item)
        self.agent.ingest_content_result(
            ContentItem(title="Opinion C", format="opinion", views=35000, retention_pct=40, length_min=20)
        )
        patterns = self.agent.get_patterns(min_confidence=0.5)
        self.assertEqual(len(patterns), 2)

    def test_ingest_rejection_feedback_creates_pattern(self):
        self._mock_llm_patterns([])  # no content-based patterns
        feedback = Feedback(
            recommendation_id="rec_001",
            recommendation_title="Crypto Market Analysis",
            action="rejected",
            notes="not relevant to my audience at all",
        )
        self.agent.ingest_feedback(feedback)
        patterns = self.agent.store.get_patterns(min_confidence=0.0)
        self.assertTrue(any("avoid" in p.pattern.lower() for p in patterns))

    def test_get_creator_context_structure(self):
        profile = CreatorProfile(niche="AI", avoid_topics=["crypto"])
        self.agent.ingest_profile(profile)
        ctx = self.agent.get_creator_context()
        self.assertEqual(ctx.profile.niche, "AI")
        self.assertIsInstance(ctx.learned_patterns, list)
        self.assertIsInstance(ctx.top_performing_topics, list)
        self.assertIsInstance(ctx.pending_ideas, list)

    def test_run_counter(self):
        self.assertEqual(self.agent.increment_run(), 1)
        self.assertEqual(self.agent.increment_run(), 2)
        ctx = self.agent.get_creator_context()
        self.assertEqual(ctx.run_count, 2)

    def test_metrics_track_acceptance_rate(self):
        self.agent.store.add_feedback(Feedback(
            recommendation_id="r1", recommendation_title="A", action="accepted"
        ))
        self.agent.store.add_feedback(Feedback(
            recommendation_id="r2", recommendation_title="B", action="rejected"
        ))
        metrics = self.agent.get_metrics()
        self.assertAlmostEqual(metrics["acceptance_rate"], 0.5, places=2)


if __name__ == "__main__":
    print("Running Agent 1 tests...\n")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryStore))
    suite.addTests(loader.loadTestsFromTestCase(TestCreatorMemoryAgent))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
