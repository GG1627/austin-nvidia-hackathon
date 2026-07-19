"""Run Agent 2 as a long-lived heartbeat. Two modes, auto-detected:

- Supabase mode (SUPABASE_URL / SUPABASE_SERVICE_KEY set): reads real Agent 1
  context and logs research episodes through Agent 1's public API. AGENT_RUN_ID
  is optional — set it to pin episodes to an Agent 3-owned run; otherwise
  episodes carry run_id=null (the schema tolerates this, matching the bridge's
  behavior when run creation fails). If Supabase is unreachable mid-run, the
  beat falls back to the mock context so live research keeps flowing.
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
        run_id = os.environ.get("AGENT_RUN_ID", "local")
        from agents.memory import get_context, log_episode
        from agents.stubs import MockMemoryAgent

        mock_context = MockMemoryAgent().get_creator_context

        def context_provider():
            try:
                return get_context("Find fresh creator content opportunities.")
            except Exception as exc:  # noqa: BLE001 — a dead network must not stop research
                print(f"  [agent2] Supabase context unavailable ({exc}); using mock context this beat")
                return mock_context()

        def episode_logger(kind, payload, rid):
            try:
                return log_episode(kind, payload, int(rid) if str(rid).isdigit() else None)
            except Exception as exc:  # noqa: BLE001 — losing one episode must not lose the beat
                print(f"  [agent2] could not log {kind} episode ({exc})")
                return 0

        pinned = f"run_id={run_id}" if str(run_id).isdigit() else "episodes carry run_id=null"
        print(f"  [agent2] Supabase mode ({pinned}, every {interval:.0f}s)")
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
