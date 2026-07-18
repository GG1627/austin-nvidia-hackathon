"""
Agent 1 - Embedding client via Featherless AI (OpenAI-compatible).
Falls back to a zero-vector stub when FEATHERLESS_API_KEY is not set
so unit tests can run without live credentials.
"""
from __future__ import annotations
import os
from typing import List, Optional

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_BASE_URL = os.getenv(
    "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "Qwen/Qwen2.5-72B-Instruct"
)
EMBEDDING_DIM = 1536  # Featherless embedding dimension


def embed(text: str) -> List[float]:
    """Return a 1536-dim embedding vector for *text*."""
    if not FEATHERLESS_API_KEY:
        # Stub: deterministic zero vector for offline tests
        return [0.0] * EMBEDDING_DIM

    try:
        import httpx
        r = httpx.post(
            f"{FEATHERLESS_BASE_URL}/embeddings",
            headers={
                "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as exc:  # noqa: BLE001
        # Graceful fallback so a transient network error doesn't crash consolidation
        print(f"[embeddings] warning: {exc}; using zero vector")
        return [0.0] * EMBEDDING_DIM


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Pure-Python cosine similarity (no numpy dependency)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
