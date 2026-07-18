from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.agent2_heartbeat import Agent2Heartbeat
from agents.agent2_handoff import HANDOFF_SCHEMA_VERSION, build_handoff, write_latest_handoff
from agents.agent2_research import Opportunity, ResearchAgent, ResearchResult, _profile_dict


def opportunity():
    return Opportunity(
        id="opp_test",
        topic="Local AI benchmarks",
        suggested_angle="Benchmark small local models",
        reasoning="Two live sources",
        trend_velocity=80,
        niche_alignment=90,
        competition_gap=70,
        recency_bonus=95,
        composite_score=83.5,
        sources=[{"name": "hacker_news", "url": "https://news.ycombinator.com", "title": "Local AI", "published_at": "2026-07-18T12:00:00+00:00", "engagement": 100}],
        freshness="2026-07-18T12:00:00+00:00",
    )


class FakeResearchAgent:
    ollama_model = "nemotron-test"
    last_result = ResearchResult(source_errors={"reddit": "rate limited"})

    def get_opportunities(self, creator_context, top_n=5):
        return [opportunity()][:top_n]

    @staticmethod
    def to_research_finding(item):
        return ResearchAgent.to_research_finding(item)


def test_handoff_is_versioned_and_preserves_agent3_fields():
    context = {
        "creator_profile": {"niche": "AI tools"},
        "core_insights": [{"id": 3, "statement": "Benchmarks perform well"}],
        "relevant_insights": [{"id": 8, "statement": "Local models are growing"}],
    }
    payload = build_handoff([opportunity()], run_id=42, source_errors={}, creator_context=context, model="nemotron")
    with TemporaryDirectory(dir=Path.cwd()) as directory:
        root = Path(directory)
        path = write_latest_handoff(payload, root)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["schema_version"] == HANDOFF_SCHEMA_VERSION
        assert saved["run_id"] == 42
        assert saved["context_basis"]["core_insight_ids"] == [3]
        assert saved["opportunities"][0]["id"] == "opp_test"
        assert (root / "history" / "42.json").exists()


def test_heartbeat_logs_agent2_findings_via_injected_agent1_interface():
    episodes = []
    context = {
        "creator_profile": {"niche": "AI tools"},
        "core_insights": [{"id": 3, "statement": "Benchmarks perform well"}],
    }

    def log_episode(kind, payload, run_id):
        episodes.append((kind, payload, run_id))
        return len(episodes)

    with TemporaryDirectory(dir=Path.cwd()) as directory:
        root = Path(directory)
        heartbeat = Agent2Heartbeat(
            FakeResearchAgent(),
            context_provider=lambda: context,
            episode_logger=log_episode,
            handoff_directory=root,
            interval_seconds=1,
        )
        payload = heartbeat.run_once(17)
        assert payload["heartbeat"]["research_findings_logged"] == 1
        assert episodes == [("research_finding", asdict(ResearchAgent.to_research_finding(opportunity())), 17)]
        assert json.loads((root / "latest.json").read_text())["run_id"] == 17


def test_agent1_insights_are_consumed_as_research_context():
    profile = _profile_dict({
        "creator_profile": {"niche": "AI tools"},
        "core_insights": [{"statement": "Benchmark videos outperform opinion pieces"}],
        "relevant_insights": [{"statement": "Local model topics drive retention"}],
    })
    assert profile["learned_insights"] == [
        "Benchmark videos outperform opinion pieces",
        "Local model topics drive retention",
    ]


def test_agent1_insights_change_keyword_alignment():
    from agents.agent2_research import _keyword_alignment

    baseline = _keyword_alignment("Local model benchmark", {"niche": "AI tools"})
    learned = _keyword_alignment(
        "Local model benchmark",
        {"niche": "AI tools", "learned_insights": ["Local model topics drive retention"]},
    )
    assert learned > baseline
