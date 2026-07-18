"""GitHub, NVIDIA RSS, and Tavily connectors for Agent 2."""
from __future__ import annotations
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os, re
from xml.etree import ElementTree
GITHUB_TRENDING_URL = "https://github.com/trending?since=weekly"
NVIDIA_RSS_URL = "https://nvidianews.nvidia.com/releases.xml"

def fetch_github_trending(client, max_per_source):
    from agents.agent2_research import RawSignal
    response = client.get(GITHUB_TRENDING_URL, headers={"User-Agent": "creator-intelligence/0.1"}); response.raise_for_status()
    seen, signals = set(), []
    for repo in re.findall(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', response.text):
        if repo in seen:
            continue
        seen.add(repo)
        signals.append(RawSignal("github", repo, f"https://github.com/{repo}", datetime.now(timezone.utc).isoformat(), raw_evidence="GitHub weekly trending repository"))
        if len(signals) >= max_per_source:
            break
    return signals

def fetch_nvidia_news(client, max_per_source):
    from agents.agent2_research import RawSignal, _valid_signals
    response = client.get(NVIDIA_RSS_URL); response.raise_for_status()
    root, signals = ElementTree.fromstring(response.content), []
    for item in root.findall(".//item")[:max_per_source]:
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", "")).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = datetime.now(timezone.utc).isoformat()
        signals.append(RawSignal("nvidia_rss", item.findtext("title", ""), item.findtext("link", ""), published, raw_evidence=item.findtext("description", "")[:800]))
    return _valid_signals(signals)

def fetch_tavily_signals(client, max_per_source, api_key):
    from agents.agent2_research import RawSignal, _valid_signals
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    response = client.post("https://api.tavily.com/search", json={"api_key": api_key, "query": os.getenv("TAVILY_QUERY", "AI agents LLM developer tools NVIDIA"), "max_results": max_per_source, "search_depth": "basic"})
    response.raise_for_status()
    return _valid_signals([RawSignal("tavily", item.get("title", ""), item.get("url", ""), item.get("published_date"), float(item.get("score", 0)) * 100, raw_evidence=item.get("content", "")[:800]) for item in response.json().get("results", [])])
