"""Hacker News and Google Trends connectors for Agent 2."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import os
import re
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree
HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"
TRENDS_NS = {"ht": "https://trends.google.com/trending/rss"}

def fetch_hn_signals(client, max_per_source):
    from agents.agent2_research import RawSignal, _unix_iso, _valid_signals
    response = client.get(HN_TOP_URL); response.raise_for_status()
    story_ids = response.json()[:max_per_source]

    def fetch_item(story_id):
        r = client.get(HN_ITEM_URL.format(id=story_id)); r.raise_for_status()
        return r.json()

    # The item endpoint only serves one story per request; fetch them
    # concurrently (httpx.Client is thread-safe) but keep top-story order.
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(story_ids)))) as pool:
        items = list(pool.map(fetch_item, story_ids))

    signals = []
    for story_id, data in zip(story_ids, items):
        if data and data.get("type") == "story":
            signals.append(RawSignal("hacker_news", data.get("title", ""), data.get("url") or f"https://news.ycombinator.com/item?id={story_id}", _unix_iso(data.get("time")), float(data.get("score", 0)) + float(data.get("descendants", 0)), raw_evidence=data.get("text", "")[:800]))
    return _valid_signals(signals)

def fetch_trends(client, max_per_source):
    """Daily trending searches from Google Trends' public RSS feed — no
    pytrends (or any extra dependency) required. The feed is general-interest
    (sports, celebrities, outages), so entries are kept only when they match
    a TREND_KEYWORDS token — otherwise high trend velocity would let
    off-niche topics crowd out real opportunities."""
    from agents.agent2_research import RawSignal, _valid_signals
    keywords = {
        word
        for phrase in os.getenv("TREND_KEYWORDS", "AI agents,LLM,NVIDIA,local AI").lower().split(",")
        for word in phrase.split()
        if len(word) > 1
    }
    response = client.get(TRENDS_RSS_URL.format(geo=os.getenv("TRENDS_GEO", "US")))
    response.raise_for_status()
    signals = []
    for item in ElementTree.fromstring(response.text).findall(".//item"):
        if len(signals) >= max_per_source:
            break
        title = (item.findtext("title") or "").strip()
        traffic = (item.findtext("ht:approx_traffic", default="", namespaces=TRENDS_NS) or "").rstrip("+").replace(",", "")
        news = item.find("ht:news_item", TRENDS_NS)
        news_url = news.findtext("ht:news_item_url", default="", namespaces=TRENDS_NS) if news is not None else ""
        news_title = news.findtext("ht:news_item_title", default="", namespaces=TRENDS_NS) if news is not None else ""
        words = set(re.findall(r"[a-z0-9]+", f"{title} {news_title}".lower()))
        if not words & keywords:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").isoformat()
        except (TypeError, ValueError):
            published = None
        url = news_url or f"https://trends.google.com/trends/explore?q={quote_plus(title)}"
        signals.append(RawSignal("google_trends", title, url, published, float(traffic) if traffic.isdigit() else 0.0, raw_evidence=news_title[:800]))
    return _valid_signals(signals)
