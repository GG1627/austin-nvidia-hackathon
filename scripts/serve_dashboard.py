"""Thin HTTP shim exposing the real agent system to the frontend.

Standard library only (no new installs). Serves the same wiring as main.py
(auto-detected real agents, stub fallback) over three endpoints:

    GET  /api/dashboard   aggregated live state for the React dashboard
    POST /api/cycle       run one Agent 3 cycle (no feedback collected; the UI
                          submits real feedback afterwards via /api/feedback)
    POST /api/feedback    {"recommendation_id", "action", "notes"} -> Agent 1

Run:  python3 scripts/serve_dashboard.py   (default port 8787)
The Vite dev server proxies /api to this process (frontend/vite.config.ts).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.contracts import Feedback, Recommendation
from main import build_strategist
from tools.nim_client import load_env

HANDOFF_PATH = os.path.join("memory", "agent2", "latest.json")
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))

_lock = threading.RLock()
_strategist = None


class FeedbackConflict(Exception):
    """Raised when a recommendation already has decided feedback."""


def strategist():
    global _strategist
    with _lock:
        if _strategist is None:
            _strategist = build_strategist()
        return _strategist


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: str, data: dict) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp_path, path)


def _age_seconds(iso: str):
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - then).total_seconds()))
    except ValueError:
        return None


def _ago(iso: str) -> str:
    seconds = _age_seconds(iso)
    if seconds is None:
        return "unknown"
    if seconds < 90:
        return f"{seconds} sec ago"
    if seconds < 5400:
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} hr ago"


def dashboard_payload() -> dict:
    s = strategist()
    context = s.memory.get_creator_context()
    handoff = _read_json(HANDOFF_PATH)
    history = _read_json(s.history_path).get("runs", [])
    last_run = history[-1] if history else {}

    opportunities = handoff.get("opportunities", [])
    top = opportunities[0] if opportunities else {}
    errors = handoff.get("source_errors", {})
    sources_line = ("all sources healthy" if not errors
                    else f"{len(errors)} source error(s): " + ", ".join(sorted(errors)))
    # A snapshot is stale when the failure path flagged it, or when it is
    # simply old (heartbeat not running) — 3 missed intervals, min 15 min.
    interval = float((handoff.get("heartbeat") or {}).get("interval_seconds") or 300)
    age = _age_seconds(handoff.get("generated_at", "")) if handoff else None
    stale = bool(handoff.get("stale")) or (age is not None and age > max(3 * interval, 900))

    recommendations = last_run.get("recommendations", [])
    move = recommendations[0] if recommendations else {}
    fed_back = {f.get("recommendation_id") for f in last_run.get("feedback", [])
                if f.get("action") in ("accepted", "rejected")}

    activity = []
    if handoff.get("generated_at"):
        activity.append(f"Agent 2 heartbeat completed {_ago(handoff['generated_at'])}")
    if top:
        activity.append(f"Top opportunity scored {round(top.get('composite_score', 0))} / 100")
    if last_run:
        activity.append(
            f"Agent 3 run {last_run.get('run_number')} produced "
            f"{len(recommendations)} recommendation(s) via {last_run.get('metrics', {}).get('engine', 'fallback')}"
        )
    patterns = context.learned_patterns
    return {
        "creator": {
            "name": (handoff.get("context_basis", {}).get("creator_profile", {}).get("name")
                     or "Creator"),
            "niche": context.creator_profile.niche,
            "audience": context.creator_profile.audience,
        },
        "heartbeat": {
            "status": "Live" if handoff else "No heartbeat yet",
            "lastRun": _ago(handoff.get("generated_at", "")) if handoff else "never",
            "sources": (sources_line
                        if handoff else "run scripts/run_agent2_heartbeat.py"),
            "stale": stale,
        },
        "opportunity": {
            "id": top.get("id", ""),
            "topic": top.get("topic", ""),
            "angle": top.get("suggested_angle", ""),
            "score": round(top.get("composite_score", 0)),
            "freshness": _ago(handoff.get("generated_at", "")) if handoff else "",
            "sources": sorted({src.get("name", "") for src in top.get("sources", [])}),
            "signal": top.get("reasoning", top.get("reason", "")),
        } if top else None,
        "insights": [p.pattern for p in sorted(patterns, key=lambda p: -p.confidence)[:3]],
        "brain": {
            "memories": len(patterns) + len(last_run.get("feedback", [])),
            "patterns": len(patterns),
        },
        "move": {
            "id": move.get("id", ""),
            "title": move.get("title", ""),
            "why": move.get("why", ""),
            "steps": move.get("action_steps", [])[:3],
            "confidence": move.get("confidence", 0),
            "feedbackGiven": move.get("id") in fed_back,
        } if move else None,
        "activity": activity,
        "engine": last_run.get("metrics", {}).get("engine", "none"),
        "runCount": len(history),
    }


def run_cycle() -> dict:
    """Run one cycle without fabricating feedback — the creator's real
    votes arrive later via /api/feedback."""
    with _lock:
        result = strategist().run_cycle(collect_feedback=False)
    return {"run_number": result.run_number,
            "recommendations": [r.to_dict() for r in result.recommendations]}


def submit_feedback(body: dict) -> dict:
    action = body.get("action", "")
    if action not in ("accepted", "rejected", "deferred"):
        raise ValueError(f"invalid action {action!r}")
    rec_id = body.get("recommendation_id", "")
    if not rec_id:
        raise ValueError("recommendation_id is required")
    s = strategist()

    with _lock:
        history = _read_json(s.history_path)
        run, recommendation = None, None
        for candidate in reversed(history.get("runs", [])):
            for rec in candidate.get("recommendations", []):
                if rec.get("id") == rec_id:
                    run, recommendation = candidate, Recommendation.from_dict(rec)
                    break
            if run:
                break
        if run is None:
            raise ValueError(f"unknown recommendation_id {rec_id!r}")

        feedback_list = run.setdefault("feedback", [])
        existing = next((f for f in feedback_list
                         if f.get("recommendation_id") == rec_id), None)
        if existing and existing.get("action") in ("accepted", "rejected"):
            raise FeedbackConflict(f"feedback for {rec_id} already recorded")

        feedback = Feedback(rec_id, action, body.get("notes", ""))
        s.memory.ingest_feedback(feedback, recommendation=recommendation)
        if recommendation.opportunity_id and hasattr(s.memory, "mark_surfaced"):
            s.memory.mark_surfaced(recommendation.opportunity_id)
        if hasattr(s.memory, "consolidate"):
            s.memory.consolidate()

        # Fold the vote back into cycle history so feedbackGiven and
        # acceptance_rate survive reloads instead of living only in React state.
        if existing:
            existing.update(feedback.to_dict())
        else:
            feedback_list.append(feedback.to_dict())
        decided = [f for f in feedback_list if f.get("action") in ("accepted", "rejected")]
        accepted = [f for f in decided if f.get("action") == "accepted"]
        run.setdefault("metrics", {})["acceptance_rate"] = (
            round(len(accepted) / len(decided), 2) if decided else None
        )
        _write_json(s.history_path, history)
    return {"ok": True, "recommendation_id": rec_id, "action": action}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # CORS preflight when not using the Vite proxy
        self._send(204, {})

    def do_GET(self) -> None:
        if self.path == "/api/dashboard":
            self._send(200, dashboard_payload())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON body"})
            return
        try:
            if self.path == "/api/cycle":
                self._send(200, run_cycle())
            elif self.path == "/api/feedback":
                self._send(200, submit_feedback(body))
            else:
                self._send(404, {"error": "not found"})
        except FeedbackConflict as exc:
            self._send(409, {"error": str(exc)})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the demo server
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt, *args):  # quieter default logging
        print(f"  [server] {self.address_string()} {fmt % args}")


def main() -> None:
    load_env()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"  Dashboard API on http://127.0.0.1:{PORT} (GET /api/dashboard)")
    server.serve_forever()


if __name__ == "__main__":
    main()
