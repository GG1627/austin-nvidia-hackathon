"""
Agent 1 - Embedding client via Featherless AI (OpenAI-compatible).
Falls back to a zero-vector stub when FEATHERLESS_API_KEY is not set
so unit tests and offline runs work without live credentials.

EMBEDDING_DIM must match db/schema.sql's `vector(1024)` columns — if you
change EMBEDDING_MODEL to something with a different output dimension,
update the schema's vector(1024) columns (and reindex) to match.
"""
from __future__ import annotations
import json
import os
from typing import List, Union

FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY", "")
FEATHERLESS_BASE_URL = os.getenv(
    "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
EMBEDDING_DIM = 1024


def embed(text: str) -> List[float]:
    """Return an EMBEDDING_DIM-dim embedding vector for *text*."""
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
