"""
Agent 1 - Supabase client wrapper.
All DB access goes through this module.
"""
from __future__ import annotations
import os
import json
import httpx
from typing import Any, Optional

class SupabaseClient:
    """Minimal REST client for Supabase (no SDK dependency required)."""

    def __init__(self, url: str = "", key: str = ""):
        # Env is read here, not at import time, so this module works no
        # matter when it is imported relative to load_env().
        url = url or os.getenv("SUPABASE_URL", "")
        key = key or os.getenv("SUPABASE_SERVICE_KEY", "")  # service key for writes
        if not url or not key:
            raise ValueError(
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables."
            )
        self.base = url.rstrip("/") + "/rest/v1"
        self.rpc_base = url.rstrip("/") + "/rest/v1/rpc"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    # ------------------------------------------------------------------
    # Generic table helpers
    # ------------------------------------------------------------------

    def insert(self, table: str, data: dict) -> dict:
        r = httpx.post(
            f"{self.base}/{table}",
            headers=self.headers,
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else data

    def select(
        self,
        table: str,
        filters: Optional[dict] = None,
        order: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        params: dict[str, Any] = {"limit": limit}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        r = httpx.get(
            f"{self.base}/{table}",
            headers=self.headers,
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def update(self, table: str, match: dict, data: dict) -> list:
        params = {k: f"eq.{v}" for k, v in match.items()}
        r = httpx.patch(
            f"{self.base}/{table}",
            headers=self.headers,
            params=params,
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def update_in(self, table: str, column: str, values: list, data: dict) -> list:
        """Bulk update every row whose `column` is in `values` (one PATCH)."""
        if not values:
            return []
        params = {column: f"in.({','.join(str(v) for v in values)})"}
        r = httpx.patch(
            f"{self.base}/{table}",
            headers=self.headers,
            params=params,
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def upsert(self, table: str, data: dict, on_conflict: str) -> dict:
        headers = {**self.headers, "Prefer": f"resolution=merge-duplicates,return=representation"}
        r = httpx.post(
            f"{self.base}/{table}?on_conflict={on_conflict}",
            headers=headers,
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else data

    def rpc(self, fn_name: str, params: dict) -> Any:
        r = httpx.post(
            f"{self.rpc_base}/{fn_name}",
            headers=self.headers,
            json=params,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()


_client: Optional[SupabaseClient] = None


def get_client() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
