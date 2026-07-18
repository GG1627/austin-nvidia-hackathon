"""Hacker News and Google Trends connectors for Agent 2."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from urllib.parse import quote_plus
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

def fetch_hn_signals(client, max_per_source):
    from agents.agent2_research import RawSignal, _unix_iso, _valid_signals
    response = client.get(HN_TOP_URL); response.raise_for_status()
    signals = []
    for story_id in response.json()[:max_per_source]:
        response = client.get(HN_ITEM_URL.format(id=story_id)); response.raise_for_status()
        data = response.json()
        if data and data.get("type") == "story":
            signals.append(RawSignal("hacker_news", data.get("title", ""), data.get("url") or f"https://news.ycombinator.com/item?id={story_id}", _unix_iso(data.get("time")), float(data.get("score", 0)) + float(data.get("descendants", 0)), raw_evidence=data.get("text", "")[:800]))
    return _valid_signals(signals)

def fetch_trends(max_per_source):
    from agents.agent2_research import RawSignal, _valid_signals
    try:
        from pytrends.request import TrendReq
    except ImportError as exc:
        raise RuntimeError("pytrends is not installed") from exc
    trend, signals = TrendReq(hl="en-US", tz=360), []
    for keyword in (x.strip() for x in os.getenv("TREND_KEYWORDS", "AI agents,LLM,NVIDIA,local AI").split(",")):
        if not keyword:
            continue
        trend.build_payload([keyword], timeframe="now 7-d")
        rising = trend.related_queries().get(keyword, {}).get("rising")
        if rising is not None:
            for _, row in rising.head(max_per_source).iterrows():
                query = str(row["query"])
                signals.append(RawSignal("google_trends", query, f"https://trends.google.com/trends/explore?q={quote_plus(query)}", datetime.now(timezone.utc).isoformat(), float(row["value"]), raw_evidence=f"Rising Google Trends query related to {keyword}"))
    return _valid_signals(signals)
