"""
Agent 1 - LLM clients for the consolidation engine.

PRIMARY (proposer):    Nemotron, served via an OpenAI-compatible vLLM/NIM
                        endpoint. One batch call per consolidation pass —
                        unconsolidated episodes + active insights in,
                        structured JSON out.
CALIBRATE (2nd model):  A second, independently-hosted model served via
                        self-hosted vLLM. Re-runs the same batch of
                        proposed/supported insights to independently agree
                        or disagree — dual agreement earns the faster 0.20
                        support factor instead of 0.15 (see consolidation.py).

Both PRIMARY and CALIBRATE degrade to an empty result when their endpoint
isn't configured, so tests and offline demos still run end to end
(deterministic code in consolidation.py never depends on the LLM being
reachable). PRIMARY is gated on an API key (NVIDIA NIM requires one);
CALIBRATE is gated on its base URL being set, since a self-hosted vLLM
server typically runs with no auth at all — set VLLM_CALIBRATE_API_KEY
only if you started vLLM with --api-key.
"""
from __future__ import annotations
import os
import json

# Env is read per call (see _primary_env/_calibrate_env), not at import time,
# so this module works no matter when it is imported relative to load_env().


def _primary_env() -> tuple[str, str, str]:
    return (
        os.getenv("NVIDIA_API_KEY", ""),
        os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
    )


def _calibrate_env() -> tuple[str, str, str]:
    # Self-hosted vLLM instance serving the calibration model, e.g.:
    #   vllm serve Qwen/Qwen2.5-7B-Instruct --port 8001
    return (
        os.getenv("VLLM_CALIBRATE_API_KEY", ""),
        os.getenv("VLLM_CALIBRATE_BASE_URL", ""),
        os.getenv("VLLM_CALIBRATE_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
    )


def _chat(base_url: str, api_key: str, model: str, messages: list, max_tokens: int = 1024) -> str:
    """Send an OpenAI-compatible chat-completion request; return the content string."""
    import httpx
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    r = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return raw


PROPOSE_SYSTEM_PROMPT = """You are the consolidation model for a creator intelligence memory system.
You are given a batch of unconsolidated episodes (raw observations, recommendations, outcomes,
feedback, research findings, and onboarding findings) plus the list of currently active insights.

You PROPOSE only. A deterministic rules engine — not you — applies confidence math and lifecycle
promotions to whatever you return. Reply with ONLY valid JSON, no markdown fences, no prose, in
exactly this shape:

{
  "new_hypotheses": [
    {"statement": "<generalised, one-sentence conclusion>", "category": "format|topic|timing|audience|style", "volatility": "stable|semi_stable|volatile", "episode_ids": [<supporting episode id ints>]}
  ],
  "evidence_updates": [
    {"insight_id": <int>, "direction": "support|contradict", "episode_id": <int>}
  ],
  "contradictions": [
    {"insight_id": <int>, "episode_id": <int>, "reason": "<why this episode contradicts the insight>"}
  ]
}

Rules:
- Never restate a raw fact about a single episode as a hypothesis — generalise across evidence.
- If an episode supports or contradicts an insight already in the active_insights list, emit an
  evidence_updates (or contradictions) entry referencing its insight_id instead of a new hypothesis.
- Only propose a new hypothesis when no active insight already covers the claim.
- "volatile" is for trend-derived claims that go stale in days; "stable" is for durable creator
  facts; default to "semi_stable" for performance patterns.
"""


def propose_consolidation(episodes: list[dict], active_insights: list[dict]) -> dict:
    """
    One structured Nemotron call per consolidation pass (spec section 8, step 2).
    Returns {"new_hypotheses": [...], "evidence_updates": [...], "contradictions": [...]}.
    """
    empty = {"new_hypotheses": [], "evidence_updates": [], "contradictions": []}
    api_key, base_url, model = _primary_env()
    if not api_key:
        return empty

    messages = [
        {"role": "system", "content": PROPOSE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"episodes": episodes, "active_insights": active_insights})},
    ]
    try:
        raw = _chat(base_url, api_key, model, messages, max_tokens=2048)
        data = json.loads(_strip_fences(raw))
        for key in ("new_hypotheses", "evidence_updates", "contradictions"):
            data.setdefault(key, [])
        return data
    except Exception as exc:  # noqa: BLE001
        print(f"[llm] Nemotron consolidation call failed: {exc}")
        return empty


CALIBRATE_SYSTEM_PROMPT = """You are the calibration model for a creator intelligence memory system.
You are given candidate insight statements proposed or reinforced by another model, each with the
episode ids offered as evidence. Independently judge whether each is a reasonable, non-trivial,
well-supported generalisation. Do not assume the other model was right. Reply with ONLY valid JSON:

{"agreements": [{"index": <int>, "agree": true|false}]}
"""


def calibrate_batch(candidates: list[dict]) -> dict[int, bool]:
    """
    Run the same batch of support candidates through the second, independently-hosted
    vLLM model (spec section 8, step 5). Returns {candidate_index: agreed_bool};
    missing/failed entries default to False, which keeps the slower single-model
    0.15 support factor.
    """
    api_key, base_url, model = _calibrate_env()
    if not base_url or not candidates:
        return {}

    payload = [
        {"index": i, "statement": c.get("statement", ""), "episode_ids": c.get("episode_ids", [])}
        for i, c in enumerate(candidates)
    ]
    messages = [
        {"role": "system", "content": CALIBRATE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload)},
    ]
    try:
        raw = _chat(base_url, api_key, model, messages, max_tokens=1024)
        data = json.loads(_strip_fences(raw))
        return {a["index"]: bool(a.get("agree", False)) for a in data.get("agreements", [])}
    except Exception as exc:  # noqa: BLE001
        print(f"[llm] vLLM calibration call failed: {exc}")
        return {}
