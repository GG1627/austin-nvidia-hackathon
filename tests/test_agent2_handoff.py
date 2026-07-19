from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time

import pytest

from agents.agent2_heartbeat import Agent2Heartbeat
from agents.agent2_handoff import (
    HANDOFF_SCHEMA_VERSION,
    UnsupportedHandoffVersion,
    build_handoff,
    validate_schema_version,
    write_latest_handoff,
)
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


def test_validate_schema_version_accepts_current_version():
    payload = build_handoff([], run_id=1, source_errors={}, creator_context={}, model="m")
    validate_schema_version(payload)  # must not raise


@pytest.mark.parametrize("version", [
    "agent2-handoff/v2",
    "agent2-handoff/v0",
    "other-schema/v1",
    "not-a-version-string",
    "",
])
def test_validate_schema_version_rejects_unknown_majors(version):
    with pytest.raises(UnsupportedHandoffVersion):
        validate_schema_version({"schema_version": version})


def test_validate_schema_version_rejects_missing_field():
    with pytest.raises(UnsupportedHandoffVersion):
        validate_schema_version({})


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


def test_run_forever_survives_failures_and_writes_a_valid_error_snapshot():
    """A2 heartbeat's failure path (sprint2.md A4): a research-agent exception must not
    kill run_forever's loop, and _write_failure()'s payload must satisfy write_latest_handoff()'s
    own contract (a run_id, so the history/<run_id>.json snapshot can be named) -- previously
    _write_failure() omitted run_id entirely, so the "safe" failure path itself raised
    KeyError and took the loop down with it."""

    class BrokenResearchAgent:
        ollama_model = "nemotron-test"

        def get_opportunities(self, creator_context, top_n=5):
            raise RuntimeError("simulated live failure: research agent unreachable")

    with TemporaryDirectory(dir=Path.cwd()) as directory:
        root = Path(directory)
        heartbeat = Agent2Heartbeat(
            BrokenResearchAgent(),
            context_provider=lambda: {"creator_profile": {}},
            episode_logger=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not log on failure")),
            handoff_directory=root,
            interval_seconds=1,
        )

        stop_event = Event()
        thread = Thread(target=heartbeat.run_forever, args=(lambda: 999,), kwargs={"stop_event": stop_event})
        thread.start()
        time.sleep(2.5)  # long enough for at least two failed ticks at interval_seconds=1
        stop_event.set()
        thread.join(timeout=5)

        assert not thread.is_alive()  # the loop kept running through repeated failures, then stopped cleanly
        latest = json.loads((root / "latest.json").read_text())
        assert latest["run_id"] == 999
        assert "simulated live failure" in latest["source_errors"]["heartbeat"]
        assert (root / "history" / "999.json").exists()
        validate_schema_version(latest)  # the error snapshot is itself a valid handoff payload


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
