"""Tests for the dashboard HTTP shim (scripts/serve_dashboard.py) — the
run-cycle / feedback flow the React app drives. Offline, mock agents only.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import serve_dashboard  # noqa: E402


class TestDashboardApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)  # all memory/* paths are cwd-relative
        serve_dashboard._strategist = None

    def tearDown(self):
        os.chdir(self.old_cwd)
        serve_dashboard._strategist = None
        self.tmp.cleanup()

    @staticmethod
    def _quiet(fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def _history_last_run(self):
        path = os.path.join("memory", "cycle_history.json")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)["runs"][-1]

    def test_cycle_records_no_synthetic_feedback(self):
        result = self._quiet(serve_dashboard.run_cycle)
        self.assertTrue(result["recommendations"])
        # No fabricated "deferred" feedback pollutes history or memory.
        self.assertEqual(self._history_last_run()["feedback"], [])
        memory = serve_dashboard.strategist().memory
        self.assertEqual(memory.graph["acceptance_history"], [])
        # Nothing marked surfaced until the creator actually responds, so
        # repeated cycles cannot exhaust the opportunity pool.
        self.assertEqual(memory.get_surfaced_topics(), [])

    def test_feedback_written_back_to_history(self):
        result = self._quiet(serve_dashboard.run_cycle)
        rec = result["recommendations"][0]
        out = self._quiet(
            serve_dashboard.submit_feedback,
            {"recommendation_id": rec["id"], "action": "accepted", "notes": "great"},
        )
        self.assertTrue(out["ok"])

        run = self._history_last_run()
        self.assertEqual(run["feedback"][0]["recommendation_id"], rec["id"])
        self.assertEqual(run["feedback"][0]["action"], "accepted")
        self.assertEqual(run["metrics"]["acceptance_rate"], 1.0)

        memory = serve_dashboard.strategist().memory
        self.assertIn(rec["opportunity_id"], memory.get_surfaced_topics())
        self.assertGreaterEqual(memory.pattern_count(), 1)  # learning happened

        # The vote survives a reload: dashboard payload reports feedbackGiven.
        payload = serve_dashboard.dashboard_payload()
        self.assertTrue(payload["move"]["feedbackGiven"])

    def test_double_vote_is_rejected(self):
        result = self._quiet(serve_dashboard.run_cycle)
        rec_id = result["recommendations"][0]["id"]
        self._quiet(serve_dashboard.submit_feedback, {"recommendation_id": rec_id, "action": "accepted"})
        with self.assertRaises(serve_dashboard.FeedbackConflict):
            serve_dashboard.submit_feedback({"recommendation_id": rec_id, "action": "rejected"})
        # Memory was not double-counted: still exactly one feedback entry.
        memory = serve_dashboard.strategist().memory
        self.assertEqual(len(memory.graph["acceptance_history"]), 1)

    def test_deferred_vote_recorded_and_can_be_upgraded(self):
        result = self._quiet(serve_dashboard.run_cycle)
        rec_id = result["recommendations"][0]["id"]
        self._quiet(serve_dashboard.submit_feedback,
                    {"recommendation_id": rec_id, "action": "deferred", "notes": "maybe later"})
        payload = self._quiet(serve_dashboard.dashboard_payload)
        self.assertTrue(payload["move"]["feedbackGiven"])  # deferred settles the card
        self.assertEqual(payload["plan"]["later"][0]["run"], 1)
        # A deferred vote is not final: it can still become a decision.
        self._quiet(serve_dashboard.submit_feedback,
                    {"recommendation_id": rec_id, "action": "accepted"})
        run = self._history_last_run()
        entries = [f for f in run["feedback"] if f["recommendation_id"] == rec_id]
        self.assertEqual(len(entries), 1)  # updated in place, not duplicated
        self.assertEqual(entries[0]["action"], "accepted")

    def test_payload_exposes_patterns_plan_and_opportunities(self):
        result = self._quiet(serve_dashboard.run_cycle)
        rec = result["recommendations"][0]
        self._quiet(serve_dashboard.submit_feedback,
                    {"recommendation_id": rec["id"], "action": "accepted"})
        payload = self._quiet(serve_dashboard.dashboard_payload)
        self.assertTrue(payload["patterns"])  # accepted vote created a pattern
        self.assertEqual(payload["plan"]["committed"][0]["title"], rec["title"])
        self.assertEqual(payload["acceptanceRate"], 1.0)
        self.assertIsInstance(payload["opportunities"], list)
        self.assertTrue(any("creator accepted" in line for line in payload["activity"]))

    def test_profile_endpoint_persists_creator(self):
        out = self._quiet(serve_dashboard.submit_profile,
                          {"name": "Maya Chen", "niche": "AI tools", "audience": "devs"})
        self.assertTrue(out["ok"])
        payload = self._quiet(serve_dashboard.dashboard_payload)
        self.assertEqual(payload["creator"]["name"], "Maya Chen")
        self.assertEqual(payload["creator"]["niche"], "AI tools")
        with self.assertRaises(ValueError):
            serve_dashboard.submit_profile({"name": ""})
        with self.assertRaises(ValueError):
            serve_dashboard.submit_profile({"name": "x" * 201})

    def test_unknown_or_invalid_feedback_rejected(self):
        with self.assertRaises(ValueError):
            serve_dashboard.submit_feedback({"recommendation_id": "rec_nope", "action": "accepted"})
        with self.assertRaises(ValueError):
            serve_dashboard.submit_feedback({"recommendation_id": "", "action": "accepted"})
        with self.assertRaises(ValueError):
            serve_dashboard.submit_feedback({"recommendation_id": "rec_001", "action": "meh"})


if __name__ == "__main__":
    unittest.main()
