"""
Agent 1 - Onboarding bootstrap (spec section 4).

A one-time job, distinct from Agent 2's ongoing external trend monitoring.
Run once per creator signup, right after Agent 2's bootstrap scrape of the
creator's own content history (reusing the same Apify infrastructure it
uses for external monitoring, pointed at a different target). This is
what makes run 1's get_context() return a populated creator_profile and
a handful of onboarding-derived hypothesis insights instead of an empty
shell — the deliberate source of Agent 3's first recommendation.
"""
from __future__ import annotations
from typing import Optional

from .db import get_client
from .memory import log_episode
from .consolidation import run_consolidation
from .models import OnboardingFindingPayload


def _upsert_node(db, node_type: str, name: str, attrs: Optional[dict] = None) -> int:
    row = db.upsert(
        "nodes",
        {"type": node_type, "name": name, "attrs": attrs or {}},
        on_conflict="type,name",
    )
    return row["id"]


def _upsert_edge(db, src: int, dst: int, relation: str, weight: float, attrs: Optional[dict] = None) -> None:
    db.upsert(
        "edges",
        {"src": src, "dst": dst, "relation": relation, "weight": weight, "attrs": attrs or {}},
        on_conflict="src,dst,relation",
    )


def run_onboarding(
    creator_name: str,
    creator_attrs: dict,
    findings: list[OnboardingFindingPayload],
) -> dict:
    """
    Sequence (spec section 4):
      1. Agent 2 already ran the bootstrap scrape — `findings` is its output.
      2. Every finding becomes an onboarding_finding episode via log_episode,
         never handed to Agent 3 directly.
      3. Build the entity graph in the same pass: one creator node, a video
         node per past upload, topic nodes extracted from topic_tags, and
         performed_well / underperformed edges weighted by the performance
         signal available (views, retention).
      4. Run consolidation immediately against this batch — not on the next
         heartbeat tick — with onboarding=True so nothing reaches `core` and
         confidence stays intentionally lower than a fed-back system would
         produce.
    """
    db = get_client()

    run_row = db.insert("runs", {"metrics": {}})
    run_id = run_row["id"]

    creator_id = _upsert_node(db, "creator", creator_name, creator_attrs)

    avg_views = sum(f.views for f in findings) / len(findings) if findings else 0.0
    avg_retention = sum(f.retention_pct for f in findings) / len(findings) if findings else 0.0

    episode_ids = []
    for finding in findings:
        payload = {
            "video_title": finding.video_title,
            "published_at": finding.published_at,
            "duration_minutes": finding.duration_minutes,
            "views": finding.views,
            "retention_pct": finding.retention_pct,
            "topic_tags": finding.topic_tags,
            "raw_ref": finding.raw_ref,
        }
        episode_id = log_episode("onboarding_finding", payload, run_id)
        episode_ids.append(episode_id)

        video_id = _upsert_node(db, "video", finding.video_title, {
            "published_at": finding.published_at,
            "duration_minutes": finding.duration_minutes,
            "views": finding.views,
            "retention_pct": finding.retention_pct,
            "episode_id": episode_id,
        })

        # A video counts performed_well / underperformed only when it's on the
        # same side of the catalog average on every signal available — mixed
        # signals stay unscored rather than forcing a call either way.
        performed_well = finding.views >= avg_views and finding.retention_pct >= avg_retention
        underperformed = finding.views < avg_views and finding.retention_pct < avg_retention
        weight = round(
            (finding.views / avg_views if avg_views else 1.0)
            * (finding.retention_pct / avg_retention if avg_retention else 1.0),
            3,
        )

        if performed_well:
            _upsert_edge(db, creator_id, video_id, "performed_well", weight)
        elif underperformed:
            _upsert_edge(db, creator_id, video_id, "underperformed", weight)

        for tag in finding.topic_tags:
            topic_id = _upsert_node(db, "topic", tag)
            topic_relation = "performed_well" if performed_well else ("underperformed" if underperformed else "covers")
            _upsert_edge(db, video_id, topic_id, topic_relation, weight)

    consolidation_result = run_consolidation(run_id=run_id, onboarding=True)

    return {
        "run_id": run_id,
        "creator_node_id": creator_id,
        "episodes_logged": len(episode_ids),
        "consolidation": consolidation_result,
    }
