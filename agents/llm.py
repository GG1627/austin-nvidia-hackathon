"""
Agent 1 - LLM client via Featherless AI (OpenAI-compatible).
Two models are used:
  PRIMARY   = Llama-3.1-70B  (insight proposal)
  CALIBRATE = Qwen2.5-72B    (dual-model calibration)
"""
from __future__ import annotations
import os
import json
from typing import Optional

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_BASE_URL = os.getenv(
    "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
)

PRIMARY_MODEL = "meta-llama/Llama-3.1-70B-Instruct"
CALIBRATE_MODEL = "Qwen/Qwen2.5-72B-Instruct"


def _chat(model: str, messages: list, max_tokens: int = 512) -> str:
    """Send a chat-completion request; return the assistant content string."""
    if not FEATHERLESS_API_KEY:
        return json.dumps({"insights": [], "entities": []})

    import httpx
    r = httpx.post(
        f"{FEATHERLESS_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def propose_insights(episode_text: str, model: str = PRIMARY_MODEL) -> list[dict]:
    """
    Ask the LLM to propose insights from an episode text.
    Returns a list of {text, volatility} dicts.
    LLM proposes; confidence math is always deterministic (code disposes).
    """
    system = (
        "You are an insight extractor for a creator intelligence system. "
        "Given an episode (a structured creator data event), extract 1-5 actionable insights. "
        "For each insight return: text (string), volatility (stable|semi_stable|volatile). "
        "Reply ONLY with valid JSON: {\"insights\": [{\"text\": \"...\", \"volatility\": \"...\"}]}. "
        "No explanations, no markdown fences."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Episode data:\n{episode_text}"},
    ]
    raw = _chat(model, messages, max_tokens=512)
    try:
        data = json.loads(raw)
        return data.get("insights", [])
    except json.JSONDecodeError:
        return []


def dual_model_agree(insight_text: str) -> bool:
    """
    Check whether both PRIMARY and CALIBRATE models independently
    flag this insight as valid. Used to apply the faster 0.20 support factor.
    """
    if not FEATHERLESS_API_KEY:
        return False

    prompt = (
        f"Is this insight about a content creator factually reasonable and non-trivial? "
        f"Reply only YES or NO.\nInsight: {insight_text}"
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        r1 = _chat(PRIMARY_MODEL, messages, max_tokens=10).strip().upper()
        r2 = _chat(CALIBRATE_MODEL, messages, max_tokens=10).strip().upper()
        return r1.startswith("YES") and r2.startswith("YES")
    except Exception:  # noqa: BLE001
        return False


def propose_entities(episode_text: str) -> list[dict]:
    """
    Extract named entities (people, channels, topics, brands) from an episode.
    Returns list of {label, kind} dicts.
    """
    system = (
        "Extract named entities from creator data. "
        "Kinds: entity | concept | topic. "
        "Reply ONLY with valid JSON: {\"entities\": [{\"label\": \"...\", \"kind\": \"...\"}]}."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": episode_text},
    ]
    raw = _chat(PRIMARY_MODEL, messages, max_tokens=256)
    try:
        return json.loads(raw).get("entities", [])
    except json.JSONDecodeError:
        return []
