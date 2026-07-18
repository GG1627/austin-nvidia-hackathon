"""Reddit connector for Agent 2."""
from __future__ import annotations
import os

def fetch_reddit_signals(client, max_per_source):
    from agents.agent2_research import RawSignal, _unix_iso, _valid_signals
    headers = {"User-Agent": os.getenv("REDDIT_USER_AGENT", "creator-intelligence/0.1")}
    signals = []
    for subreddit in (x.strip() for x in os.getenv("REDDIT_SUBREDDITS", "LocalLLaMA,MachineLearning,artificial").split(",")):
        if not subreddit:
            continue
        response = client.get(f"https://www.reddit.com/r/{subreddit}/hot.json?limit={max_per_source}", headers=headers)
        response.raise_for_status()
        for child in response.json().get("data", {}).get("children", []):
            data = child.get("data", {})
            signals.append(RawSignal("reddit", data.get("title", ""), f"https://www.reddit.com{data.get('permalink', '')}", _unix_iso(data.get("created_utc")), float(data.get("score", 0)) + float(data.get("num_comments", 0)), raw_evidence=data.get("selftext", "")[:800]))
    return _valid_signals(signals)
