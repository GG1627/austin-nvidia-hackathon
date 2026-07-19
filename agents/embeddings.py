"""
Agent 1 - Embedding client, OpenAI-compatible /v1/embeddings. Defaults to
NVIDIA's hosted nemotron-3-embed-1b (via integrate.api.nvidia.com) but works
against any OpenAI-compatible embeddings endpoint, including a self-hosted
vLLM instance. Falls back to a zero-vector stub when VLLM_EMBEDDING_BASE_URL
isn't set, so unit tests and offline runs work without a live endpoint.

EMBEDDING_DIM must match db/schema.sql's `vector(2048)` columns — if you
change VLLM_EMBEDDING_MODEL to something with a different output dimension,
update the schema's vector(2048) columns (and reindex) to match.
"""
from __future__ import annotations
import json
import os
from typing import List, Union

EMBEDDING_DIM = 2048


def embed(text: str, input_type: str = "passage") -> List[float]:
    """Return an EMBEDDING_DIM-dim embedding vector for *text*.

    input_type distinguishes indexed content ("passage", the default — used
    when storing episodes/insights) from search queries ("query" — used when
    ranking against that index in get_context). nemotron-3-embed-1b requires
    this to avoid accuracy loss; other OpenAI-compatible servers ignore it.
    """
    # Env is read per call, not at import time, so import order relative to
    # load_env() doesn't matter. Point these at a self-hosted vLLM instead
    # of the NVIDIA-hosted default, e.g.:
    #   vllm serve Qwen/Qwen3-Embedding-0.6B --port 8002 --task embed
    base_url = os.getenv("VLLM_EMBEDDING_BASE_URL", "")
    if not base_url:
        # Stub: deterministic zero vector for offline tests / no endpoint yet.
        return [0.0] * EMBEDDING_DIM

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("VLLM_EMBEDDING_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        r = httpx.post(
            f"{base_url.rstrip('/')}/embeddings",
            headers=headers,
            json={
                "model": os.getenv("VLLM_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b"),
                "input": text,
                "input_type": input_type,
            },
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
