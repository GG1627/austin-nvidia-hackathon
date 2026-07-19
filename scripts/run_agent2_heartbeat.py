"""Run Agent 2 as a long-lived heartbeat. Two modes, auto-detected:

- Supabase mode (SUPABASE_URL / SUPABASE_SERVICE_KEY set): reads real Agent 1
  context and logs research episodes through Agent 1's public API. Requires
  AGENT_RUN_ID — Agent 3 owns run creation.
- Standalone mode (no Supabase): context comes from the local mock memory
  graph and no episodes are logged, but the heartbeat still refreshes
  memory/agent2/latest.json so Agent 3 and the dashboard get live research.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent2_heartbeat import Agent2Heartbeat
from agents.agent2_research import ResearchAgent
from tools.nim_client import load_env


def main() -> None:
    load_env()
    interval = float(os.environ.get("AGENT2_HEARTBEAT_SECONDS", "300"))

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        run_id = os.environ.get("AGENT_RUN_ID")
        if not run_id:
            raise SystemExit(
                "Supabase is configured: set AGENT_RUN_ID to the Agent 3-owned run id."
            )
        from agents.memory import get_context, log_episode

        context_provider = lambda: get_context("Find fresh creator content opportunities.")  # noqa: E731
        episode_logger = log_episode
        print(f"  [agent2] Supabase mode (run_id={run_id}, every {interval:.0f}s)")
    else:
        from agents.stubs import MockMemoryAgent

        run_id = os.environ.get("AGENT_RUN_ID", "local")
        context_provider = MockMemoryAgent().get_creator_context
        episode_logger = lambda kind, payload, rid: 0  # noqa: E731 — episodes need Supabase
        print(f"  [agent2] standalone mode — no Supabase; writing handoff only (every {interval:.0f}s)")

    heartbeat = Agent2Heartbeat(
        ResearchAgent(),
        context_provider=context_provider,
        episode_logger=episode_logger,
        handoff_directory=os.environ.get("AGENT2_HANDOFF_DIR", "memory/agent2"),
        interval_seconds=interval,
    )
    heartbeat.run_forever(lambda: run_id)


if __name__ == "__main__":
    main()
