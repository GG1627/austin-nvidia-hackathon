"""Reddit connector for Agent 2.

Reddit's public *.json endpoints are frequently IP-blocked (403) without
OAuth. When REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are configured, this
connector uses application-only OAuth (client_credentials grant) against
oauth.reddit.com; otherwise it falls back to the public endpoint, which may
work depending on the network. Either way, failures surface as a source
error in the handoff instead of killing the run.
"""
from __future__ import annotations
import os
import time

_token_cache: dict = {"token": "", "expires_at": 0.0}


def _user_agent() -> str:
    return os.getenv("REDDIT_USER_AGENT", "script:creator-intelligence:0.1 (hackathon demo)")


def _oauth_token(client) -> str:
    """Application-only OAuth token, cached until shortly before expiry."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    response = client.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(os.getenv("REDDIT_CLIENT_ID", ""), os.getenv("REDDIT_CLIENT_SECRET", "")),
        headers={"User-Agent": _user_agent()},
    )
    response.raise_for_status()
    payload = response.json()
    _token_cache["token"] = payload["access_token"]
    _token_cache["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
    return _token_cache["token"]


def fetch_reddit_signals(client, max_per_source):
    from agents.agent2_research import RawSignal, _unix_iso, _valid_signals

    use_oauth = bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))
    headers = {"User-Agent": _user_agent()}
    if use_oauth:
        headers["Authorization"] = f"Bearer {_oauth_token(client)}"
        base = "https://oauth.reddit.com"
    else:
        base = "https://www.reddit.com"

    signals = []
    for subreddit in (x.strip() for x in os.getenv("REDDIT_SUBREDDITS", "LocalLLaMA,MachineLearning,artificial").split(",")):
        if not subreddit:
            continue
        response = client.get(f"{base}/r/{subreddit}/hot.json?limit={max_per_source}", headers=headers)
        response.raise_for_status()
        for child in response.json().get("data", {}).get("children", []):
            data = child.get("data", {})
            signals.append(RawSignal("reddit", data.get("title", ""), f"https://www.reddit.com{data.get('permalink', '')}", _unix_iso(data.get("created_utc")), float(data.get("score", 0)) + float(data.get("num_comments", 0)), raw_evidence=data.get("selftext", "")[:800]))
    return _valid_signals(signals)
