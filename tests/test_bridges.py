"""Tests for agents/bridges.py and the heartbeat failure-preservation fix."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agents.agent2_heartbeat import Agent2Heartbeat
from agents.bridges import HandoffResearchAgent, opportunity_from_handoff
from agents.contracts import CreatorContext, Opportunity

HANDOFF_ITEM = {
    "id": "opp_8f4e536cef8f",
    "topic": "AI-powered indieweb hosting",
    "suggested_angle": "Benchmark a $0.01/day self-hosted site",
    "reasoning": "Aligns with the creator's benchmark format.",
    "trend_velocity": 100.0,
    "niche_alignment": 92.0,
    "competition_gap": 88.0,
    "recency_bonus": 82.22,
    "composite_score": 93.02,
    "freshness": "2026-07-18T21:45:12+00:00",
    "sources": [
        {
            "name": "hacker_news",
            "title": "Hardcore IndieWeb",
            "url": "https://example.com/indieweb",
            "published_at": "2026-07-18T21:45:12+00:00",
            "engagement": 213.0,
        }
    ],
}


def write_handoff(path: Path, opportunities: list) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "agent2-handoff/v1",
                "run_id": 7,
                "generated_at": "2026-07-19T06:49:13+00:00",
                "source_errors": {"reddit": "rate limited"},
                "opportunities": opportunities,
            }
        ),
        encoding="utf-8",
    )


class TestOpportunityAdapter(unittest.TestCase):
    def test_maps_agent2_fields_to_agent3_contract(self):
        opp = opportunity_from_handoff(HANDOFF_ITEM)
        self.assertIsInstance(opp, Opportunity)
        self.assertEqual(opp.id, "opp_8f4e536cef8f")
        self.assertEqual(opp.trend_score, 100.0)  # trend_velocity
        self.assertEqual(opp.reason, "Aligns with the creator's benchmark format.")
        self.assertEqual(opp.composite_score, 93.02)
        self.assertEqual(opp.sources[0].name, "hacker_news")
        self.assertEqual(opp.sources[0].url, "https://example.com/indieweb")
        self.assertIn("Hardcore IndieWeb", opp.sources[0].detail)
        self.assertIn("213 engagement", opp.sources[0].detail)

    def test_tolerates_missing_fields(self):
        opp = opportunity_from_handoff({"id": "opp_x", "topic": "t"})
        self.assertEqual(opp.trend_score, 0.0)
        self.assertEqual(opp.sources, [])


class _SurfacedMemory:
    def __init__(self, surfaced):
        self._surfaced = surfaced

    def get_surfaced_topics(self):
        return self._surfaced


class TestHandoffResearchAgent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "latest.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_latest_json_and_sorts_by_composite(self):
        low = dict(HANDOFF_ITEM, id="opp_low", composite_score=10.0)
        write_handoff(self.path, [low, HANDOFF_ITEM])
        agent = HandoffResearchAgent(handoff_path=str(self.path))
        opps = agent.get_opportunities(CreatorContext())
        self.assertEqual([o.id for o in opps], ["opp_8f4e536cef8f", "opp_low"])
        self.assertEqual(agent.last_source_errors, {"reddit": "rate limited"})

    def test_filters_surfaced_ids_from_memory_agent(self):
        write_handoff(self.path, [HANDOFF_ITEM])
        agent = HandoffResearchAgent(
            memory_agent=_SurfacedMemory(["opp_8f4e536cef8f"]),
            handoff_path=str(self.path),
        )
        self.assertEqual(agent.get_opportunities(CreatorContext()), [])
        self.assertEqual(agent.last_duplicates_filtered, 1)

    def test_missing_handoff_returns_empty(self):
        agent = HandoffResearchAgent(handoff_path=str(self.path))
        self.assertEqual(agent.get_opportunities(CreatorContext()), [])


class _FailingResearchAgent:
    ollama_model = "nemotron-test"

    def get_opportunities(self, creator_context, top_n=5):
        raise RuntimeError("network down")


class TestHeartbeatFailurePreservesHandoff(unittest.TestCase):
    def test_failure_keeps_last_good_opportunities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_handoff(root / "latest.json", [HANDOFF_ITEM])
            heartbeat = Agent2Heartbeat(
                _FailingResearchAgent(),
                context_provider=lambda: {},
                episode_logger=lambda kind, payload, run_id: 1,
                handoff_directory=root,
                interval_seconds=1,
            )
            heartbeat._write_failure("network down")
            latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["source_errors"], {"heartbeat": "network down"})
            self.assertEqual(len(latest["opportunities"]), 1)
            self.assertEqual(latest["opportunities"][0]["id"], "opp_8f4e536cef8f")
            self.assertEqual(latest["run_id"], 7)
            self.assertEqual(
                latest["stale"]["last_good_generated_at"], "2026-07-19T06:49:13+00:00"
            )

    def test_failure_with_no_previous_snapshot_writes_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            heartbeat = Agent2Heartbeat(
                _FailingResearchAgent(),
                context_provider=lambda: {},
                episode_logger=lambda kind, payload, run_id: 1,
                handoff_directory=root,
                interval_seconds=1,
            )
            heartbeat._write_failure("network down")
            latest = json.loads((root / "latest.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["opportunities"], [])
            self.assertNotIn("stale", latest)


class TestStrategistConsolidateHook(unittest.TestCase):
    def test_consolidate_called_after_feedback(self):
        from agents.agent3_strategist import StrategistAgent
        from agents.contracts import Feedback
        from agents.stubs import MockMemoryAgent

        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            memory = MockMemoryAgent(os.path.join(tmp, "graph.json"))
            memory.consolidate = lambda: calls.append("consolidate")
            write_handoff(Path(tmp) / "latest.json", [HANDOFF_ITEM])
            research = HandoffResearchAgent(memory, handoff_path=os.path.join(tmp, "latest.json"))
            strategist = StrategistAgent(
                memory_agent=memory,
                research_agent=research,
                history_path=os.path.join(tmp, "history.json"),
                print_fn=lambda *_: None,
            )
            result = strategist.run_cycle(
                feedback_provider=lambda rec: Feedback(rec.id, "accepted", "")
            )
        self.assertEqual(calls, ["consolidate"])
        self.assertTrue(result.recommendations)
        self.assertEqual(result.recommendations[0].opportunity_id, "opp_8f4e536cef8f")


if __name__ == "__main__":
    unittest.main()
