"""Run Agent 2 as a long-lived heartbeat after Harrison-Agent1 is merged.

Agent 3 owns creation of AGENT_RUN_ID. This process only reads Agent 1 context,
logs research episodes through Agent 1's public API, and refreshes the Agent 3
handoff artifact.
"""
from __future__ import annotations

import os

from agents.agent2_heartbeat import Agent2Heartbeat
from agents.agent2_research import ResearchAgent
from agents.memory import get_context, log_episode


def main() -> None:
    run_id = os.environ.get("AGENT_RUN_ID")
    if not run_id:
        raise SystemExit("Set AGENT_RUN_ID to the Agent 3-owned Agent 1 run ID.")
    interval = float(os.environ.get("AGENT2_HEARTBEAT_SECONDS", "300"))
    heartbeat = Agent2Heartbeat(
        ResearchAgent(),
        context_provider=lambda: get_context("Find fresh creator content opportunities."),
        episode_logger=log_episode,
        handoff_directory=os.environ.get("AGENT2_HANDOFF_DIR", "memory/agent2"),
        interval_seconds=interval,
    )
    heartbeat.run_forever(lambda: run_id)


if __name__ == "__main__":
    main()
