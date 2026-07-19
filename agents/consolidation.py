"""
Agent 1 - Consolidation Engine.
Deterministic confidence math — the LLM proposes, this module disposes.

Runs inside the NemoClaw heartbeat whenever episodes.consolidated = false
rows exist, plus once immediately after onboarding (spec section 8).

Lifecycle promotions:
  hypothesis  -> validated : evidence_for >= 3 AND confidence > 0.60
  validated   -> core      : evidence_for >= 5 AND confidence > 0.85
  any status  -> deprecated: confidence < 0.20 (kept, never deleted)

Onboarding exception: nothing reaches `core` during the bootstrap pass —
promotion caps at `validated` regardless of support count/confidence,
because evidence from a single historical batch isn't the same as
evidence accumulated across live feedback cycles.

Confidence math:
  support (single model) : c = c + 0.15 * (1 - c)
  support (dual model)   : c = c + 0.20 * (1 - c)
  contradict              : c = c * 0.60
  new hypothesis           : c = 0.30

Dedup: embed each candidate statement, pgvector cosine search against
existing insights (via the match_insights RPC, with a local cosine
fallback), similarity above ~0.9 merges as evidence instead of inserting.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from .db import get_client
from .embeddings import embed, cosine_similarity, to_pgvector_param, parse_embedding
from .llm import propose_consolidation, calibrate_batch

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


def _is_expired(insight: dict) -> bool:
    exp = insight.get("expires_at")
    if not exp:
        return False
    try:
        exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return exp_dt < datetime.now(timezone.utc)
    except Exception:
        return False


def active_insights(db=None) -> list[dict]:
    """Non-deprecated, non-expired insights — the pool consolidation and get_context read from."""
    db = db or get_client()
    rows = db.select("insights", filters={"status": "neq.deprecated"}, limit=500)
    return [r for r in rows if not _is_expired(r)]


def _find_similar(db, embedding: list, pool: list[dict], threshold: float = DEDUP_THRESHOLD) -> Optional[dict]:
    """Find an existing insight whose embedding is within `threshold` cosine similarity."""
    if any(embedding):
        try:
            matches = db.rpc("match_insights", {
                "query_embedding": to_pgvector_param(embedding),
                "match_threshold": threshold,
                "match_count": 1,
            })
            if matches and matches[0].get("similarity", 0) >= threshold:
                full = db.select("insights", filters={"id": f"eq.{matches[0]['id']}"}, limit=1)
                if full:
                    return full[0]
        except Exception as exc:  # noqa: BLE001
            print(f"[consolidation] match_insights RPC unavailable, using local cosine: {exc}")

    for row in pool:
        emb = parse_embedding(row.get("embedding"))
        if not emb or not any(emb):
            continue
        if cosine_similarity(embedding, emb) >= threshold:
            return row
    return None


def run_consolidation(run_id: Optional[int] = None, onboarding: bool = False) -> dict:
    """
    Consolidate all unconsolidated episodes in one batch pass.
    Called by the heartbeat agent, or immediately during onboarding bootstrap
    (in which case `onboarding=True` caps promotion at `validated`).
    """
    db = get_client()

    episodes = db.select("episodes", filters={"consolidated": "eq.false"}, limit=200)
    result = {
        "episodes_processed": 0,
        "insights_new": 0,
        "insights_updated": 0,
        "promoted": 0,
        "deprecated": 0,
        "duplicates_merged": 0,
        "calibration_agreement_rate": None,
    }
    if not episodes:
        return result

    pool = active_insights(db)
    by_id = {row["id"]: row for row in pool}

    episodes_compact = [{"id": e["id"], "kind": e["kind"], "payload": e.get("payload", {})} for e in episodes]
    active_compact = [
        {"id": i["id"], "statement": i["statement"], "confidence": i["confidence"], "status": i["status"]}
        for i in pool
    ]
    proposal = propose_consolidation(episodes_compact, active_compact)

    # 1. New hypotheses -> dedup check against the active pool.
    pending_inserts: list[dict] = []
    support_candidates: list[dict] = []  # dedup merges, resolved as "support" against an existing row
    for cand in proposal["new_hypotheses"]:
        statement = (cand.get("statement") or "").strip()
        if not statement:
            continue
        emb = embed(statement)
        episode_ids = cand.get("episode_ids") or [e["id"] for e in episodes]
        match = _find_similar(db, emb, pool)
        if match:
            support_candidates.append({"statement": statement, "episode_ids": episode_ids, "existing": match})
        else:
            pending_inserts.append({
                "statement": statement,
                "category": cand.get("category"),
                "volatility": cand.get("volatility", "semi_stable"),
                "episode_ids": episode_ids,
                "embedding": emb,
            })

    # 2. Explicit evidence updates / contradictions Nemotron tied to known insight ids.
    support_updates: list[dict] = []
    contradict_updates: list[dict] = []
    for upd in proposal["evidence_updates"]:
        row = by_id.get(upd.get("insight_id"))
        if not row:
            continue
        if upd.get("direction") == "support":
            support_updates.append({"row": row, "episode_id": upd.get("episode_id")})
        elif upd.get("direction") == "contradict":
            contradict_updates.append({"row": row, "episode_id": upd.get("episode_id")})
    for c in proposal["contradictions"]:
        row = by_id.get(c.get("insight_id"))
        if row:
            contradict_updates.append({"row": row, "episode_id": c.get("episode_id")})

    # 3. Calibrate every "support" candidate (dedup merges + explicit support updates) as one
    #    vLLM batch, per spec section 8 step 5.
    calibration_pool: list[dict] = []
    calibration_meta: list[tuple[str, dict]] = []
    for sc in support_candidates:
        calibration_pool.append({"statement": sc["statement"], "episode_ids": sc["episode_ids"]})
        calibration_meta.append(("dedup", sc))
    for su in support_updates:
        calibration_pool.append({"statement": su["row"]["statement"], "episode_ids": [su["episode_id"]]})
        calibration_meta.append(("update", su))

    agreements = calibrate_batch(calibration_pool) if calibration_pool else {}
    if calibration_pool:
        result["calibration_agreement_rate"] = round(
            sum(1 for v in agreements.values() if v) / len(calibration_pool), 3
        )

    def _apply_support_row(row: dict, episode_ids: list, dual: bool) -> str:
        nonlocal result
        new_conf = _apply_support(row["confidence"], dual=dual)
        new_support = row["evidence_for"] + 1
        src_ids = list(row.get("supporting_episode_ids") or [])
        for eid in episode_ids:
            if eid is not None and eid not in src_ids:
                src_ids.append(eid)
        new_status = _promote_status(row["status"], new_support, new_conf, onboarding=onboarding)
        if new_status != row["status"]:
            if new_status in ("validated", "core"):
                result["promoted"] += 1
            elif new_status == "deprecated":
                result["deprecated"] += 1
        db.update("insights", {"id": row["id"]}, {
            "confidence": round(new_conf, 6),
            "evidence_for": new_support,
            "status": new_status,
            "supporting_episode_ids": src_ids,
            "last_updated_run": run_id,
        })
        result["insights_updated"] += 1
        return new_status

    for idx, (kind, obj) in enumerate(calibration_meta):
        dual = agreements.get(idx, False)
        if kind == "dedup":
            _apply_support_row(obj["existing"], obj["episode_ids"], dual)
            result["duplicates_merged"] += 1
        else:
            eid = obj["episode_id"]
            _apply_support_row(obj["row"], [eid] if eid is not None else [], dual)

    # 4. Contradictions.
    for cu in contradict_updates:
        row = cu["row"]
        new_conf = _apply_contradict(row["confidence"])
        new_status = "deprecated" if new_conf < DEPRECATED_CONF else row["status"]
        if new_status == "deprecated" and row["status"] != "deprecated":
            result["deprecated"] += 1
        db.update("insights", {"id": row["id"]}, {
            "confidence": round(new_conf, 6),
            "evidence_against": row["evidence_against"] + 1,
            "status": new_status,
            "last_updated_run": run_id,
        })
        result["insights_updated"] += 1

    # 5. Insert genuinely new hypotheses at the fixed starting confidence.
    for ins in pending_inserts:
        expires_at = None
        if ins["volatility"] == "volatile":
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=VOLATILE_TTL_HOURS)).isoformat()
        db.insert("insights", {
            "statement": ins["statement"],
            "category": ins["category"],
            "confidence": 0.30,
            "status": "hypothesis",
            "evidence_for": 0,
            "evidence_against": 0,
            "supporting_episode_ids": ins["episode_ids"],
            "volatility": ins["volatility"],
            "expires_at": expires_at,
            "created_run": run_id,
            "last_updated_run": run_id,
            "embedding": to_pgvector_param(ins["embedding"]),
        })
        result["insights_new"] += 1

    # 6. Mark episodes consolidated.
    for e in episodes:
        db.update("episodes", {"id": e["id"]}, {"consolidated": True})
    result["episodes_processed"] = len(episodes)

    # 7. Snapshot the post-consolidation active insight list, update runs.metrics.
    if run_id is not None:
        final_pool = active_insights(db)
        db.insert("insight_snapshots", {"run_id": run_id, "insights": final_pool})

        by_status: dict = {}
        for i in final_pool:
            by_status[i["status"]] = by_status.get(i["status"], 0) + 1

        db.update("runs", {"id": run_id}, {"metrics": {
            "episodes_consolidated": result["episodes_processed"],
            "insights_new": result["insights_new"],
            "insights_updated": result["insights_updated"],
            "promotions": result["promoted"],
            "deprecations": result["deprecated"],
            "duplicates_merged": result["duplicates_merged"],
            "calibration_agreement_rate": result["calibration_agreement_rate"],
            "insight_counts_by_status": by_status,
            "onboarding": onboarding,
        }})

    return result
