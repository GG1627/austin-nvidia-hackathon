"""
Opt-in live regression test for Workstream A1's persistence success criterion:
insights survive a fresh process after being written to the real Supabase project.

Skipped by default (see pytest.ini: `addopts = -m "not live"`). Run explicitly,
once db/schema.sql has been applied to the target Supabase project and
SUPABASE_URL / SUPABASE_SERVICE_KEY are set:

    pytest -m live tests/test_live_persistence.py -v

Cleanup note: agents/db.py's SupabaseClient has no delete() (the system's own
design deprecates insights rather than deleting them — see consolidation.py).
This test deprecates the insight it creates but cannot remove the run/node/
episode rows it writes; they are tagged with a unique marker in their name/
statement for manual housekeeping.
"""
from __future__ import annotations

import os
import uuid
from unittest import mock

import pytest

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (SUPABASE_URL and SUPABASE_SERVICE_KEY),
        reason="SUPABASE_URL / SUPABASE_SERVICE_KEY not set",
    ),
]


def test_insight_survives_a_fresh_client_after_seeding_live():
    from agents.models import OnboardingFindingPayload
    from agents.onboarding import run_onboarding
    from agents.memory import get_context
    import agents.db as db_module

    marker = f"live-restart-check-{uuid.uuid4().hex[:8]}"
    catalog = [
        OnboardingFindingPayload(f"{marker} short video", "2026-01-01", 10, 50000, 60.0, ["ai", marker]),
    ]

    result = run_onboarding(marker, {"niche": marker}, catalog)
    run_id = result["run_id"]

    db = db_module.get_client()
    inserted_insights = db.select("insights", filters={"created_run": f"eq.{run_id}"})

    try:
        # Simulate a fresh process: drop the cached HTTP client singleton entirely,
        # reconnect, and read back through the public get_context() door only.
        db_module._client = None
        with mock.patch("agents.consolidation.get_client", return_value=db_module.get_client()), \
             mock.patch("agents.memory.get_client", return_value=db_module.get_client()):
            ctx = get_context(f"what should {marker} make next?")

        assert ctx["creator_profile"].get("niche") == marker
        assert any(marker in (i.get("statement") or "") for i in ctx["relevant_insights"])
    finally:
        db = db_module.get_client()
        for row in inserted_insights:
            db.update("insights", {"id": row["id"]}, {"status": "deprecated"})
