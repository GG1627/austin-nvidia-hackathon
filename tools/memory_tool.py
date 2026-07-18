"""
memory_tool.py — Low-level JSON persistence layer for the knowledge graph.

All reads and writes go through MemoryStore. Agents never touch the JSON file
directly.
"""

import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional, Any, Dict

from agents.models import (
    CreatorProfile,
    ContentItem,
    LearnedPattern,
    ContentIdea,
    Feedback,
)

DEFAULT_PATH = os.environ.get("MEMORY_PATH", "./memory/knowledge_graph.json")


class MemoryStore:
    """
    Persistent knowledge graph backed by a JSON file.

    Layout of the JSON file:
    {
        "version": 1,
        "run_count": int,
        "last_updated": str,
        "creator_profile": { ... },
        "content_items": [ ... ],
        "learned_patterns": [ ... ],
        "content_ideas": [ ... ],
        "feedback_history": [ ... ],
        "surfaced_opportunity_ids": [ str ],
        "metrics": { ... }
    }
    """

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._data: Dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load graph from disk, or initialise a fresh one."""
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self._data = json.load(f)
        else:
            self._data = self._empty_graph()

    def _save(self) -> None:
        """Atomic write: write to .tmp then rename."""
        os.makedirs(os.path.dirname(self.path) if os.path.dirname(self.path) else ".", exist_ok=True)
        tmp = self.path + ".tmp"
        self._data["last_updated"] = datetime.utcnow().isoformat()
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        shutil.move(tmp, self.path)

    @staticmethod
    def _empty_graph() -> Dict[str, Any]:
        return {
            "version": 1,
            "run_count": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "creator_profile": asdict(CreatorProfile()),
            "content_items": [],
            "learned_patterns": [],
            "content_ideas": [],
            "feedback_history": [],
            "surfaced_opportunity_ids": [],
            "metrics": {
                "total_patterns": 0,
                "acceptance_rate": None,
                "avg_confidence_run1": None,
                "avg_confidence_current": None,
            },
        }

    # ------------------------------------------------------------------
    # Creator Profile
    # ------------------------------------------------------------------

    def get_profile(self) -> CreatorProfile:
        return CreatorProfile(**self._data["creator_profile"])

    def save_profile(self, profile: CreatorProfile) -> None:
        self._data["creator_profile"] = asdict(profile)
        self._save()

    # ------------------------------------------------------------------
    # Content Items
    # ------------------------------------------------------------------

    def add_content_item(self, item: ContentItem) -> None:
        self._data["content_items"].append(asdict(item))
        self._save()

    def get_content_items(self) -> List[ContentItem]:
        return [ContentItem(**d) for d in self._data["content_items"]]

    # ------------------------------------------------------------------
    # Learned Patterns
    # ------------------------------------------------------------------

    def add_pattern(self, pattern: LearnedPattern) -> None:
        self._data["learned_patterns"].append(asdict(pattern))
        self._update_metrics()
        self._save()

    def get_patterns(self, min_confidence: float = 0.0, active_only: bool = True) -> List[LearnedPattern]:
        return [
            LearnedPattern(**d)
            for d in self._data["learned_patterns"]
            if d["confidence"] >= min_confidence
            and (not active_only or d.get("active", True))
        ]

    def update_pattern(self, pattern_id: str, updates: Dict[str, Any]) -> bool:
        """Patch specific fields on a pattern by id. Returns True if found."""
        for d in self._data["learned_patterns"]:
            if d["id"] == pattern_id:
                d.update(updates)
                d["last_updated"] = datetime.utcnow().isoformat()
                self._update_metrics()
                self._save()
                return True
        return False

    def find_similar_pattern(self, category: str, keyword: str) -> Optional[LearnedPattern]:
        """Naive duplicate check: same category + keyword in pattern text."""
        kw = keyword.lower()
        for d in self._data["learned_patterns"]:
            if d["category"] == category and kw in d["pattern"].lower():
                return LearnedPattern(**d)
        return None

    def increment_pattern_citation(self, pattern_id: str) -> None:
        for d in self._data["learned_patterns"]:
            if d["id"] == pattern_id:
                d["times_cited"] = d.get("times_cited", 0) + 1
                self._save()
                return

    # ------------------------------------------------------------------
    # Content Ideas
    # ------------------------------------------------------------------

    def add_idea(self, idea: ContentIdea) -> None:
        self._data["content_ideas"].append(asdict(idea))
        self._save()

    def get_ideas(self, status: Optional[str] = None) -> List[ContentIdea]:
        items = self._data["content_ideas"]
        if status:
            items = [d for d in items if d["status"] == status]
        return [ContentIdea(**d) for d in items]

    def update_idea(self, idea_id: str, updates: Dict[str, Any]) -> bool:
        for d in self._data["content_ideas"]:
            if d["id"] == idea_id:
                d.update(updates)
                self._save()
                return True
        return False

    # ------------------------------------------------------------------
    # Feedback History
    # ------------------------------------------------------------------

    def add_feedback(self, feedback: Feedback) -> None:
        self._data["feedback_history"].append(asdict(feedback))
        self._update_metrics()
        self._save()

    def get_feedback(self) -> List[Feedback]:
        return [Feedback(**d) for d in self._data["feedback_history"]]

    # ------------------------------------------------------------------
    # Opportunity deduplication
    # ------------------------------------------------------------------

    def mark_opportunity_surfaced(self, opportunity_id: str) -> None:
        if opportunity_id not in self._data["surfaced_opportunity_ids"]:
            self._data["surfaced_opportunity_ids"].append(opportunity_id)
            self._save()

    def was_opportunity_surfaced(self, opportunity_id: str) -> bool:
        return opportunity_id in self._data["surfaced_opportunity_ids"]

    # ------------------------------------------------------------------
    # Run counter
    # ------------------------------------------------------------------

    def increment_run(self) -> int:
        self._data["run_count"] += 1
        self._save()
        return self._data["run_count"]

    def get_run_count(self) -> int:
        return self._data["run_count"]

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _update_metrics(self) -> None:
        patterns = self._data["learned_patterns"]
        feedback = self._data["feedback_history"]

        self._data["metrics"]["total_patterns"] = len(patterns)

        if patterns:
            avg_conf = sum(p["confidence"] for p in patterns) / len(patterns)
            self._data["metrics"]["avg_confidence_current"] = round(avg_conf, 3)
            if self._data["metrics"]["avg_confidence_run1"] is None:
                self._data["metrics"]["avg_confidence_run1"] = round(avg_conf, 3)

        if feedback:
            accepted = sum(1 for f in feedback if f["action"] == "accepted")
            self._data["metrics"]["acceptance_rate"] = round(accepted / len(feedback), 3)

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self._data["metrics"])

    def get_full_snapshot(self) -> Dict[str, Any]:
        """Return full graph data (read-only copy for Agent 3 display)."""
        return dict(self._data)
