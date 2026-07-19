"""Focused tests for Agent 2; all network and Ollama calls are mocked."""
from dataclasses import asdict
from agents.agent2_research import Opportunity, RawSignal, ResearchAgent, _deduplicate


def signal(source, title, url, engagement=100):
    return RawSignal(source, title, url, "2026-07-18T12:00:00+00:00", engagement)


def context():
    return {"creator_profile": {"niche": "AI tools for developers", "avoid_topics": ["crypto"]}}


def test_deduplicates_same_title_and_url():
    assert len(_deduplicate([signal("hn", "AI Agents", "https://a"), signal("reddit", "AI agents!", "https://a")])) == 1


def test_ranking_and_memory_adapter(monkeypatch):
    agent = ResearchAgent()
    monkeypatch.setattr(agent, "fetch_reddit_signals", lambda: [signal("reddit", "NVIDIA AI agents", "https://reddit/a", 900)])
    monkeypatch.setattr(agent, "fetch_hn_signals", lambda: [signal("hacker_news", "NVIDIA AI agents", "https://hn/a", 500)])
    for name in ("fetch_trends", "fetch_github_trending", "fetch_nvidia_news", "fetch_tavily_signals"):
        monkeypatch.setattr(agent, name, lambda: [])
    monkeypatch.setattr(agent, "_analyse_group", lambda group, ctx: {"topic": "NVIDIA AI agents", "suggested_angle": "Benchmark agent tools", "reasoning": "Two sources", "niche_alignment": 90, "competition_gap": 60})
    opportunities = agent.get_opportunities(context())
    assert len(opportunities) == 1
    assert len(opportunities[0].sources) == 2
    finding = agent.to_research_finding(opportunities[0])
    assert finding.topic == "NVIDIA AI agents" and finding.raw_ref == "https://reddit/a"
    assert agent.to_research_episode(opportunities[0]).kind == "research_finding"


def test_source_failure_does_not_stop_run(monkeypatch):
    agent = ResearchAgent()
    monkeypatch.setattr(agent, "fetch_reddit_signals", lambda: (_ for _ in ()).throw(RuntimeError("rate limit")))
    monkeypatch.setattr(agent, "fetch_hn_signals", lambda: [signal("hacker_news", "Local LLM tools", "https://hn/a")])
    for name in ("fetch_trends", "fetch_github_trending", "fetch_nvidia_news", "fetch_tavily_signals"):
        monkeypatch.setattr(agent, name, lambda: [])
    results = agent.get_opportunities(context())
    assert results and "reddit" in agent.last_result.source_errors


def test_avoided_topic_is_filtered(monkeypatch):
    agent = ResearchAgent()
    monkeypatch.setattr(agent, "_analyse_group", lambda group, ctx: {"topic": "Crypto agents", "suggested_angle": "x", "reasoning": "x", "niche_alignment": 90, "competition_gap": 80})
    assert agent._build_opportunities([signal("hn", "Crypto agents", "https://hn/a")], context()) == []


def test_youtube_connector_uses_video_statistics():
    import httpx
    from tools.social_sources import fetch_youtube_signals

    def handler(request):
        if "search" in str(request.url):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "Agent benchmark", "publishedAt": "2026-07-18T12:00:00Z", "channelTitle": "AI Lab", "description": "Demo"}}]})
        return httpx.Response(200, json={"items": [{"id": "abc", "statistics": {"viewCount": "100", "likeCount": "5", "commentCount": "2"}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        signals = fetch_youtube_signals(client, 5, "key")
    assert signals[0].url.endswith("abc") and signals[0].engagement == 145


def test_x_connector_maps_metrics_and_requires_token():
    import httpx
    from tools.social_sources import fetch_x_signals

    def handler(request):
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json={"data": [{"id": "42", "text": "NVIDIA agent release", "created_at": "2026-07-18T12:00:00Z", "public_metrics": {"like_count": 10, "reply_count": 2, "retweet_count": 3, "quote_count": 1}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        signals = fetch_x_signals(client, 5, "token")
    assert signals[0].source == "x" and signals[0].engagement == 26
    try:
        fetch_x_signals(httpx.Client(), 5, "")
    except RuntimeError as exc:
        assert "X_BEARER_TOKEN" in str(exc)
    else:
        raise AssertionError("missing X token should fail clearly")


def test_optional_social_source_failures_are_recorded(monkeypatch):
    monkeypatch.setenv("ENABLE_X", "true")
    agent = ResearchAgent()
    monkeypatch.setattr(agent, "fetch_youtube_signals", lambda: (_ for _ in ()).throw(RuntimeError("YOUTUBE_API_KEY is not configured")))
    monkeypatch.setattr(agent, "fetch_x_signals", lambda: (_ for _ in ()).throw(RuntimeError("X_BEARER_TOKEN is not configured")))
    monkeypatch.setattr(agent, "fetch_hn_signals", lambda: [signal("hacker_news", "Local LLM tools", "https://hn/a")])
    for name in ("fetch_reddit_signals", "fetch_trends", "fetch_github_trending", "fetch_nvidia_news", "fetch_tavily_signals"):
        monkeypatch.setattr(agent, name, lambda: [])
    assert agent.get_opportunities(context())
    assert {"youtube", "x"} <= set(agent.last_result.source_errors)


def test_x_is_disabled_by_default(monkeypatch):
    agent = ResearchAgent()
    monkeypatch.delenv("ENABLE_X", raising=False)
    monkeypatch.setattr(agent, "fetch_x_signals", lambda: (_ for _ in ()).throw(AssertionError("X should not be called")))
    monkeypatch.setattr(agent, "fetch_hn_signals", lambda: [signal("hacker_news", "Local LLM tools", "https://hn/a")])
    for name in ("fetch_reddit_signals", "fetch_trends", "fetch_github_trending", "fetch_nvidia_news", "fetch_tavily_signals", "fetch_youtube_signals"):
        monkeypatch.setattr(agent, name, lambda: [])
    assert agent.get_opportunities(context())
    assert "x" not in agent.last_result.source_errors


def test_default_model_is_nemotron_not_nemoclaw(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert ResearchAgent().ollama_model == "nemotron-3-nano:4b"


def test_nemoclaw_openai_compatible_inference_route():
    import httpx

    def handler(request):
        assert str(request.url) == "https://inference.local/v1/chat/completions"
        assert request.json()["model"] == "nemotron-3-nano:30b"
        content = '{"topic":"AI agents","suggested_angle":"Benchmark agents","reasoning":"Live evidence","niche_alignment":90,"competition_gap":60}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        agent = ResearchAgent(http_client=client, inference_base_url="https://inference.local/v1", ollama_model="nemotron-3-nano:30b")
        analysis = agent._analyse_group([signal("hn", "AI agents", "https://hn/a")], context())
    assert analysis["topic"] == "AI agents"


def test_malformed_llm_json_uses_grounded_fallback(monkeypatch):
    agent = ResearchAgent()
    response = type("Response", (), {"raise_for_status": lambda self: None, "json": lambda self: {"response": "{}"}})()
    monkeypatch.setattr(agent._client, "post", lambda *args, **kwargs: response)
    analysis = agent._analyse_group([signal("hacker_news", "Local LLM tools", "https://hn/a")], context())
    assert analysis["topic"] == "Local LLM tools"
    assert "Grounded" in analysis["reasoning"]
