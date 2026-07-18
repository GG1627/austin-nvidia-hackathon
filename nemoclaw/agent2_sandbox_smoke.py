"""End-to-end Agent 2 check intended to run inside a NemoClaw sandbox."""
from __future__ import annotations

import json
import os
from agents.agent2_research import ResearchAgent


os.environ.setdefault("INFERENCE_BASE_URL", "https://inference.local/v1")
os.environ.setdefault("OLLAMA_MODEL", "nemotron-3-nano:30b")

context = {"creator_profile": {"niche": "AI tools for developers", "avoid_topics": ["crypto"]}}
agent = ResearchAgent(max_per_source=1)
signals = agent.fetch_hn_signals()
if not signals:
    raise RuntimeError("Hacker News returned no usable signals")
analysis = agent._analyse_group(signals[:1], context)
print(json.dumps({"source": signals[0].source, "title": signals[0].title, "analysis": analysis}, indent=2))
agent.close()
