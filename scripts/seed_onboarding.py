#!/usr/bin/env python3
"""
seed_onboarding.py — end-to-end proof of the Agent 1 memory layer.

Simulates Agent 2's bootstrap scrape of a creator's own catalog with fake
onboarding_finding data, runs the onboarding bootstrap (spec section 4),
and prints the resulting get_context() so you can see run 1 already looks
like a grounded strategist opinion instead of a cold start.

Requires a real Supabase project with db/schema.sql applied. Reads
credentials from a .env file in the repo root (see .env.example), or from
already-exported environment variables:
    python scripts/seed_onboarding.py

NVIDIA_API_KEY / VLLM_CALIBRATE_BASE_URL / VLLM_EMBEDDING_BASE_URL are optional — without them the
consolidation LLM calls degrade to no-ops, so this proves the deterministic
plumbing (episodes, entity graph, get_context) end to end even before the
model keys are wired up.
"""
from __future__ import annotations
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.models import OnboardingFindingPayload
from agents.onboarding import run_onboarding
from agents.memory import get_context


def fake_catalog() -> list[OnboardingFindingPayload]:
    """A plausible past-upload history for an AI-tools-for-developers channel,
    deliberately including a cluster of long, underperforming videos so the
    onboarding pass has a real pattern to find (spec section 4, step 5)."""
    return [
        OnboardingFindingPayload("I built an agent that never sleeps", "2026-03-11", 14, 62000, 58.0,
                                  ["ai agents", "automation"]),
        OnboardingFindingPayload("LLM Benchmark Showdown: Llama vs Nemotron", "2026-02-20", 12, 145000, 71.0,
                                  ["llm", "benchmark", "nvidia"]),
        OnboardingFindingPayload("Local AI setup on a single GPU", "2026-01-15", 11, 98000, 66.0,
                                  ["local ai", "gpu"]),
        OnboardingFindingPayload("My honest opinion on AI hype", "2025-12-02", 22, 21000, 33.0,
                                  ["opinion", "ai"]),
        OnboardingFindingPayload("A rambling deep dive into agent memory", "2025-11-10", 27, 18000, 29.0,
                                  ["ai agents", "memory"]),
        OnboardingFindingPayload("Everything wrong with vector databases", "2025-10-05", 31, 15500, 24.0,
                                  ["vector db", "opinion"]),
        OnboardingFindingPayload("Benchmark: fine-tuning on consumer GPUs", "2025-09-18", 13, 132000, 69.0,
                                  ["benchmark", "fine-tuning", "gpu"]),
        OnboardingFindingPayload("Building recursive agents from scratch", "2025-08-22", 15, 110000, 64.0,
                                  ["ai agents", "tutorial"]),
    ]


def main() -> None:
    creator_name = "Demo Creator"
    creator_attrs = {
        "niche": "AI tools for developers",
        "audience_description": "software engineers and ML practitioners aged 25-40",
        "preferred_format": "benchmark",
        "platform": "YouTube",
    }

    print(f"Onboarding '{creator_name}' with {len(fake_catalog())} past uploads...\n")
    result = run_onboarding(creator_name, creator_attrs, fake_catalog())

    print("=" * 70)
    print("ONBOARDING RESULT (run 1 / bootstrap baseline)")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))

    print("\n" + "=" * 70)
    print("get_context() — Agent 3's first call, right after onboarding")
    print("=" * 70)
    ctx = get_context("What should this creator make next?")
    print(json.dumps(ctx, indent=2, default=str))

    hyp_count = len(ctx["relevant_insights"]) + len(ctx["core_insights"])
    print(f"\n{hyp_count} insight(s) surfaced, {len(ctx['related_entities'])} entities with edges — "
          f"run 1 is grounded, not a cold start.")


if __name__ == "__main__":
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.\n"
            "Apply db/schema.sql to a Supabase project, then:\n"
            "  export SUPABASE_URL=...\n"
            "  export SUPABASE_SERVICE_KEY=...\n"
            "  python scripts/seed_onboarding.py",
            file=sys.stderr,
        )
        sys.exit(1)
    main()
