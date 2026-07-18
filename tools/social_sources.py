"""YouTube and X connectors for Agent 2."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
X_RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


def fetch_youtube_signals(client: Any, max_per_source: int, api_key: str):
    from agents.agent2_research import RawSignal, _valid_signals
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    limit = min(max(1, max_per_source), 50)
    lookback_hours = max(1, int(os.getenv("YOUTUBE_LOOKBACK_HOURS", "168")))
    published_after = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat().replace("+00:00", "Z")
    response = client.get(YOUTUBE_SEARCH_URL, params={"key": api_key, "part": "snippet", "type": "video", "order": os.getenv("YOUTUBE_ORDER", "date"), "q": os.getenv("YOUTUBE_QUERY", "AI agents LLM NVIDIA developer tools"), "publishedAfter": published_after, "maxResults": limit})
    response.raise_for_status()
    items = response.json().get("items", [])
    ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]
    stats = {}
    if ids:
        response = client.get(YOUTUBE_VIDEOS_URL, params={"key": api_key, "part": "statistics", "id": ",".join(ids)})
        response.raise_for_status()
        stats = {item["id"]: item.get("statistics", {}) for item in response.json().get("items", [])}
    signals = []
    for item in items:
        video_id, snippet = item.get("id", {}).get("videoId"), item.get("snippet", {})
        if not video_id:
            continue
        metric = stats.get(video_id, {})
        engagement = float(metric.get("viewCount", 0)) + 5 * float(metric.get("likeCount", 0)) + 10 * float(metric.get("commentCount", 0))
        signals.append(RawSignal("youtube", snippet.get("title", ""), f"https://www.youtube.com/watch?v={video_id}", snippet.get("publishedAt"), engagement, raw_evidence=f"Channel: {snippet.get('channelTitle', '')}. {snippet.get('description', '')[:700]}"))
    return _valid_signals(signals)


def fetch_x_signals(client: Any, max_per_source: int, bearer_token: str):
    from agents.agent2_research import RawSignal, _valid_signals
    if not bearer_token:
        raise RuntimeError("X_BEARER_TOKEN is not configured")
    response = client.get(X_RECENT_SEARCH_URL, params={"query": os.getenv("X_QUERY", "(AI agents OR LLM OR NVIDIA OR \"developer tools\") lang:en -is:retweet"), "max_results": min(max(10, max_per_source), 100), "tweet.fields": "created_at,public_metrics"}, headers={"Authorization": f"Bearer {bearer_token}"})
    response.raise_for_status()
    signals = []
    for post in response.json().get("data", []):
        metrics, text = post.get("public_metrics", {}), post.get("text", "").replace("\n", " ")
        engagement = float(metrics.get("like_count", 0)) + 2 * float(metrics.get("reply_count", 0)) + 3 * float(metrics.get("retweet_count", 0)) + 3 * float(metrics.get("quote_count", 0))
        signals.append(RawSignal("x", text[:280], f"https://x.com/i/web/status/{post.get('id', '')}", post.get("created_at"), engagement, raw_evidence=text[:800]))
    return _valid_signals(signals)
