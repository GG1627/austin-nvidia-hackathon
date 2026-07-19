"""
In-memory, PostgREST-shaped fake of agents.db.SupabaseClient.

Lets the memory layer (consolidation / memory / onboarding) be tested end
to end without a live Supabase project, per spec section 11: "The layer is
fully testable without Agents 2 and 3."
"""
from __future__ import annotations
from typing import Any


def _to_str(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


class FakeSupabaseClient:
    TABLES = ("runs", "episodes", "insights", "nodes", "edges", "insight_snapshots")
    NO_AUTO_ID = ("edges", "insight_snapshots")

    def __init__(self):
        self.tables: dict[str, list[dict]] = {t: [] for t in self.TABLES}
        self._next_id: dict[str, int] = {t: 1 for t in self.TABLES}

    def _alloc_id(self, table: str) -> int:
        i = self._next_id[table]
        self._next_id[table] += 1
        return i

    @classmethod
    def _match(cls, row: dict, filters: dict) -> bool:
        for key, cond in filters.items():
            val = row.get(key)
            if isinstance(cond, str) and cond.startswith("eq."):
                if _to_str(val) != cond[3:]:
                    return False
            elif isinstance(cond, str) and cond.startswith("neq."):
                if _to_str(val) == cond[4:]:
                    return False
            else:
                if val != cond:
                    return False
        return True

    # -- generic table helpers, mirroring agents.db.SupabaseClient ---------

    def insert(self, table: str, data: dict) -> dict:
        row = dict(data)
        if table not in self.NO_AUTO_ID and "id" not in row:
            row["id"] = self._alloc_id(table)
        self.tables[table].append(row)
        return row

    def select(self, table: str, filters: dict | None = None, order: str | None = None, limit: int = 100) -> list:
        rows = list(self.tables[table])
        if filters:
            rows = [r for r in rows if self._match(r, filters)]
        if order:
            col, _, direction = order.partition(".")
            rows.sort(key=lambda r: r.get(col) or 0, reverse=(direction == "desc"))
        return rows[:limit]

    def update(self, table: str, match: dict, data: dict) -> list:
        cond = {k: f"eq.{v}" for k, v in match.items()}
        rows = [r for r in self.tables[table] if self._match(r, cond)]
        for r in rows:
            r.update(data)
        return rows

    def upsert(self, table: str, data: dict, on_conflict: str) -> dict:
        keys = on_conflict.split(",")
        for r in self.tables[table]:
            if all(r.get(k) == data.get(k) for k in keys):
                r.update(data)
                return r
        return self.insert(table, data)

    def rpc(self, fn_name: str, params: dict) -> Any:
        if fn_name == "match_insights":
            from agents.embeddings import parse_embedding, cosine_similarity

            query = parse_embedding(params.get("query_embedding"))
            threshold = params.get("match_threshold", 0.0)
            count = params.get("match_count", 10)
            exclude_status = params.get("exclude_status", "deprecated")

            scored = []
            for row in self.tables["insights"]:
                if row.get("status") == exclude_status:
                    continue
                emb = parse_embedding(row.get("embedding"))
                if not emb:
                    continue
                sim = cosine_similarity(query, emb)
                if sim > threshold:
                    scored.append((sim, row))
            scored.sort(key=lambda t: -t[0])
            return [
                {
                    "id": row["id"],
                    "statement": row.get("statement"),
                    "category": row.get("category"),
                    "confidence": row.get("confidence"),
                    "status": row.get("status"),
                    "volatility": row.get("volatility"),
                    "expires_at": row.get("expires_at"),
                    "similarity": sim,
                }
                for sim, row in scored[:count]
            ]
        raise NotImplementedError(f"FakeSupabaseClient.rpc: no emulation for {fn_name!r}")


def fake_embed(text: str):
    """Deterministic, non-zero, per-text embedding for exercising the cosine-dedup path
    without a real embedding API. Identical text -> identical vector -> similarity 1.0."""
    import hashlib
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:16]]
