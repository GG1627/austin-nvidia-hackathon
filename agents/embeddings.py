"""
Agent 1 - Embedding client via a self-hosted vLLM instance (OpenAI-compatible
/v1/embeddings). Falls back to a zero-vector stub when VLLM_EMBEDDING_BASE_URL
isn't set, so unit tests and offline runs work without a live GPU box.

EMBEDDING_DIM must match db/schema.sql's `vector(1024)` columns — if you
change VLLM_EMBEDDING_MODEL to something with a different output dimension,
update the schema's vector(1024) columns (and reindex) to match.
"""
from __future__ import annotations
import json
import os
from typing import List, Union

# Self-hosted vLLM instance serving an embedding model, e.g.:
#   vllm serve Qwen/Qwen3-Embedding-0.6B --port 8002 --task embed
VLLM_EMBEDDING_BASE_URL = os.getenv("VLLM_EMBEDDING_BASE_URL", "")
VLLM_EMBEDDING_MODEL = os.getenv("VLLM_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
VLLM_EMBEDDING_API_KEY = os.getenv("VLLM_EMBEDDING_API_KEY", "")
EMBEDDING_DIM = 1024


def embed(text: str) -> List[float]:
    """Return an EMBEDDING_DIM-dim embedding vector for *text*."""
    if not VLLM_EMBEDDING_BASE_URL:
        # Stub: deterministic zero vector for offline tests / no vLLM server yet.
        return [0.0] * EMBEDDING_DIM

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if VLLM_EMBEDDING_API_KEY:
            headers["Authorization"] = f"Bearer {VLLM_EMBEDDING_API_KEY}"
        r = httpx.post(
            f"{VLLM_EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
            headers=headers,
            json={"model": VLLM_EMBEDDING_MODEL, "input": text},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as exc:  # noqa: BLE001
        # Graceful fallback so a transient network error doesn't crash consolidation
        print(f"[embeddings] warning: {exc}; using zero vector")
        return [0.0] * EMBEDDING_DIM


def to_pgvector_param(vec: List[float]) -> str:
    """
    Serialize an embedding for a PostgREST insert/update/RPC body.
    pgvector columns don't accept a bare JSON array over PostgREST — send
    the vector's text literal form ("[0.1,0.2,...]") as a JSON string instead.
    """
    return json.dumps(vec)


def parse_embedding(value: Union[str, list, None]) -> List[float]:
    """Parse an embedding value read back from Supabase, which may come back
    as a JSON-string, a list, or null depending on driver/PostgREST version."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return list(value)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Pure-Python cosine similarity (no numpy dependency)."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
