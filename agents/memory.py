"""
Agent 1 - Public interfaces (spec sections 6 & 7).

log_episode() and get_context() are the ONLY way anything outside this
package touches the memory layer. Agents 2 and 3 never query
episodes/insights/nodes/edges directly.
"""
from __future__ import annotations
import json
from typing import Optional

from .db import get_client
from .embeddings import embed, cosine_similarity, to_pgvector_param, parse_embedding
from .consolidation import active_insights, _is_expired


def log_episode(kind: str, payload: dict, run_id: int) -> int:
    """Embed, insert, return episode id. Called by Agents 2 and 3 (and onboarding)."""
    db = get_client()
    text = json.dumps(payload, sort_keys=True)
    row = db.insert("episodes", {
        "run_id": run_id,
        "kind": kind,
        "payload": payload,
        "consolidated": False,
        "embedding": to_pgvector_param(embed(text)),
    })
    return row["id"]


def _rough_token_count(obj) -> int:
    """Cheap ~4-chars/token approximation — good enough for a context *budget*."""
    return max(1, len(json.dumps(obj)) // 4)


def _load_creator_profile(db) -> dict:
    """The creator_profile is the single `creator` node plus its attrs."""
    rows = db.select("nodes", filters={"type": "eq.creator"}, limit=1)
    if rows:
        node = rows[0]
        return {"name": node.get("name"), **(node.get("attrs") or {})}
    return {}


def get_context(task: str, token_budget: int = 4000) -> dict:
    """
    The single read door into the memory layer (spec section 7). Assembles
    layered context in priority order until the token budget is spent.

    Deprecated insights and expired volatile insights are never returned.
    Every returned insight carries its status so Agent 3 can hedge on
    hypotheses. On the very first call after onboarding, core/relevant
    insights carry created_run == the onboarding run id.
    """
    db = get_client()

    result = {
        "creator_profile": _load_creator_profile(db),
        "core_insights": [],
        "relevant_insights": [],
        "related_entities": [],
        "last_run": None,
    }
    spent = _rough_token_count(result["creator_profile"])

    pool = active_insights(db)

    # 1. Core insights — always prioritised first.
    for i in sorted((r for r in pool if r["status"] == "core"), key=lambda r: -r["confidence"]):
        item = {"id": i["id"], "statement": i["statement"], "status": i["status"], "confidence": i["confidence"]}
        cost = _rough_token_count(item)
        if spent + cost > token_budget:
            break
        result["core_insights"].append(item)
        spent += cost

    # 2. Relevant insights — pgvector match against the task, falling back to a
    #    local cosine ranking if the RPC isn't reachable (e.g. offline demo).
    task_emb = embed(task, input_type="query")
    seen_ids = {i["id"] for i in result["core_insights"]}
    ranked: list[dict] = []
    if not any(task_emb):
        # No embedding signal available (no embedding provider configured) — there's
        # nothing to semantically rank against, so surface the active pool by
        # confidence rather than silently returning an empty context.
        ranked = sorted((i for i in pool if i["id"] not in seen_ids), key=lambda r: -r["confidence"])
    else:
        try:
            matches = db.rpc("match_insights", {
                "query_embedding": to_pgvector_param(task_emb),
                "match_threshold": 0.0,
                "match_count": 20,
            })
            ranked = [m for m in matches if m["id"] not in seen_ids]
        except Exception as exc:  # noqa: BLE001
            print(f"[memory] match_insights RPC unavailable for get_context, using local cosine: {exc}")
            scored = [
                (cosine_similarity(task_emb, parse_embedding(i.get("embedding"))), i)
                for i in pool if i["id"] not in seen_ids
            ]
            scored.sort(key=lambda t: t[0], reverse=True)
            ranked = [i for _, i in scored]

    for i in ranked:
        if _is_expired(i):
            continue
        item = {"id": i["id"], "statement": i.get("statement"), "status": i["status"], "confidence": i["confidence"]}
        cost = _rough_token_count(item)
        if spent + cost > token_budget:
            break
        result["relevant_insights"].append(item)
        spent += cost

    # 3. Related entities — graph nodes with at least one outgoing edge.
    nodes = db.select("nodes", limit=100)
    edges = db.select("edges", limit=300)
    edges_by_src: dict = {}
    for e in edges:
        edges_by_src.setdefault(e["src"], []).append(e)

    for node in nodes:
        node_edges = edges_by_src.get(node["id"], [])
        if not node_edges:
            continue
        item = {
            "type": node["type"],
            "name": node["name"],
            "edges": [{"relation": e["relation"], "weight": e["weight"]} for e in node_edges],
        }
        cost = _rough_token_count(item)
        if spent + cost > token_budget:
            break
        result["related_entities"].append(item)
        spent += cost

    # 4. Last run — most recent recommendations + outcomes.
    runs = db.select("runs", order="id.desc", limit=1)
    if runs:
        last_run_id = runs[0]["id"]
        recs = db.select("episodes", filters={"run_id": f"eq.{last_run_id}", "kind": "eq.recommendation"}, limit=20)
        outcomes = db.select("episodes", filters={"run_id": f"eq.{last_run_id}", "kind": "eq.outcome"}, limit=20)
        result["last_run"] = {
            "run_id": last_run_id,
            "recommendations": [r["payload"] for r in recs],
            "outcomes": [o["payload"] for o in outcomes],
        }

    return result
