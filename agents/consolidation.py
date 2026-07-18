"""
Agent 1 - Consolidation Engine.
Deterministic confidence math — LLM only proposes, code always disposes.

Lifecycle promotions:
  hypothesis  -> validated : support_count >= 3 AND confidence > 0.60
  validated   -> core      : support_count >= 5 AND confidence > 0.85
  any status  -> deprecated: confidence < 0.20

Onboarding cap: nothing reaches `core` during the bootstrap pass.

Confidence math:
  support (single model) : c = c + 0.15 * (1 - c)
  support (dual model)   : c = c + 0.20 * (1 - c)
  contradict             : c = c * 0.60
  new hypothesis         : c = 0.30

Dedup: cosine similarity > 0.9 → merge as evidence (no new row).
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import Optional

from .db import get_client
from .embeddings import embed, cosine_similarity
from .llm import propose_insights, dual_model_agree, propose_entities

# Thresholds
DEDUP_THRESHOLD = 0.90
VALIDATED_MIN_SUPPORT = 3
VALIDATED_MIN_CONF = 0.60
CORE_MIN_SUPPORT = 5
CORE_MIN_CONF = 0.85
DEPRECATED_CONF = 0.20

# Volatile TTL in hours
VOLATILE_TTL_HOURS = 72


def _apply_support(confidence: float, dual: bool = False) -> float:
    factor = 0.20 if dual else 0.15
    return confidence + factor * (1 - confidence)


def _apply_contradict(confidence: float) -> float:
    return confidence * 0.60


def _promote_status(
    current_status: str,
    support_count: int,
    confidence: float,
    onboarding: bool = False,
) -> str:
    if confidence < DEPRECATED_CONF:
        return "deprecated"
    if current_status in ("hypothesis", "validated"):
        if support_count >= CORE_MIN_SUPPORT and confidence > CORE_MIN_CONF:
            return "core" if not onboarding else "validated"
        if support_count >= VALIDATED_MIN_SUPPORT and confidence > VALIDATED_MIN_CONF:
            return "validated"
    return current_status


def _existing_similar(db, embedding: list, threshold: float = DEDUP_THRESHOLD) -> Optional[dict]:
    """Return an existing insight whose embedding is within threshold, or None."""
    # Pull all non-deprecated insights (small enough for hackathon scale)
    rows = db.select(
        "insights",
        filters={"status": "neq.deprecated"},
        limit=500,
    )
    for row in rows:
        existing_emb = row.get("embedding")
        if not existing_emb:
            continue
        if isinstance(existing_emb, str):
            try:
                existing_emb = json.loads(existing_emb)
            except Exception:
                continue
        sim = cosine_similarity(embedding, existing_emb)
        if sim >= threshold:
            return row
    return None


def consolidate_episode(
    episode: dict,
    onboarding: bool = False,
) -> list[str]:
    """
    Consolidate a single episode into insights + entity graph.
    Returns list of affected insight IDs.
    """
    db = get_client()
    episode_text = json.dumps(episode.get("payload", {}))
    episode_id = episode["id"]

    # 1. LLM proposes insights
    proposed = propose_insights(episode_text)
    affected_ids = []

    for proposal in proposed:
        text = proposal.get("text", "").strip()
        volatility = proposal.get("volatility", "semi_stable")
        if not text:
            continue

        emb = embed(text)
        existing = _existing_similar(db, emb)

        if existing:
            # Merge as supporting evidence
            dual = dual_model_agree(text)
            new_conf = _apply_support(existing["confidence"], dual=dual)
            new_support = existing["support_count"] + 1
            new_status = _promote_status(
                existing["status"], new_support, new_conf, onboarding=onboarding
            )
            src_ids = existing.get("source_episode_ids") or []
            if isinstance(src_ids, str):
                try:
                    src_ids = json.loads(src_ids)
                except Exception:
                    src_ids = []
            if episode_id not in src_ids:
                src_ids.append(episode_id)

            db.update(
                "insights",
                {"id": existing["id"]},
                {
                    "confidence": round(new_conf, 6),
                    "support_count": new_support,
                    "status": new_status,
                    "source_episode_ids": json.dumps(src_ids),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            affected_ids.append(existing["id"])
        else:
            # Insert new hypothesis
            expires_at = None
            if volatility == "volatile":
                expires_at = (
                    datetime.utcnow() + timedelta(hours=VOLATILE_TTL_HOURS)
                ).isoformat()

            row = {
                "text": text,
                "confidence": 0.30,
                "status": "hypothesis",
                "volatility": volatility,
                "support_count": 0,
                "contradict_count": 0,
                "embedding": json.dumps(emb),
                "expires_at": expires_at,
                "source_episode_ids": json.dumps([episode_id]),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            inserted = db.insert("insights", row)
            insight_id = inserted.get("id", row.get("id", ""))
            if insight_id:
                affected_ids.append(insight_id)

    # 2. Snapshot
    for iid in affected_ids:
        try:
            row = db.select("insights", filters={"id": f"eq.{iid}"}, limit=1)
            if row:
                db.insert("insight_snapshots", {
                    "insight_id": iid,
                    "snapshot": json.dumps(row[0]),
                    "created_at": datetime.utcnow().isoformat(),
                })
        except Exception as exc:
            print(f"[consolidation] snapshot error for {iid}: {exc}")

    # 3. Entity graph
    try:
        entities = propose_entities(episode_text)
        for ent in entities:
            label = ent.get("label", "").strip()
            kind = ent.get("kind", "entity")
            if not label:
                continue
            db.upsert(
                "nodes",
                {
                    "label": label,
                    "kind": kind,
                    "attributes": json.dumps({}),
                    "created_at": datetime.utcnow().isoformat(),
                },
                on_conflict="label",
            )
    except Exception as exc:
        print(f"[consolidation] entity graph error: {exc}")

    # 4. Mark episode consolidated
    db.update("episodes", {"id": episode_id}, {"consolidated": True})

    return affected_ids


def run_consolidation(onboarding: bool = False) -> dict:
    """
    Consolidate all unconsolidated episodes.
    Called by the heartbeat agent (or immediately during onboarding bootstrap).
    """
    db = get_client()
    episodes = db.select(
        "episodes",
        filters={"consolidated": "eq.false"},
        limit=200,
    )
    total_insights = 0
    for ep in episodes:
        ids = consolidate_episode(ep, onboarding=onboarding)
        total_insights += len(ids)

    return {"episodes_processed": len(episodes), "insights_affected": total_insights}
