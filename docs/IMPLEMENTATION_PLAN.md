# 📋 Implementation Plan — Recursive Creator Intelligence System

## Project Overview

**Hackathon Track:** Recursive Intelligence  
**Team Size:** 3 Engineers  
**Timeline:** Hackathon sprint (estimated 24–48 hours)

---

## 🚦 Phases

### Phase 0 — Setup & Scaffolding (Hours 0–2)
**All team members**

- [ ] Clone repo and set up dev environment
- [ ] Configure shared `.env` with NVIDIA NIM, OpenAI, Reddit, and Tavily API keys
- [ ] Agree on data schema for knowledge graph nodes
- [ ] Agree on inter-agent message format (structured JSON)
- [ ] Create folder structure:
  ```
  /agents
    agent1_memory.py
    agent2_research.py
    agent3_strategist.py
  /memory
    knowledge_graph.json   # persisted between runs
    creator_profile.json
  /tools
    reddit_tool.py
    trends_tool.py
    youtube_tool.py
    memory_tool.py
  /prompts
    agent1_system.txt
    agent2_system.txt
    agent3_system.txt
  main.py
  requirements.txt
  .env.example
  ```

---

### Phase 1 — Agent 1: Creator Memory Brain (Hours 2–8)
**Owner: Memory & Knowledge Engineer**

#### Milestone 1.1 — Knowledge Graph Foundation
- [ ] Design schema for persistent memory nodes:
  - `CreatorProfile` (niche, audience, style, goals)
  - `ContentItem` (title, views, retention, topics, outcome)
  - `LearnedPattern` (observation → conclusion)
  - `ContentIdea` (title, angle, research_status, priority)
  - `FailedTopic` (topic, reason, date)
- [ ] Implement `MemoryStore` class with JSON persistence
- [ ] Implement `read_memory()`, `write_memory()`, `update_pattern()` methods

#### Milestone 1.2 — Learning Engine
- [ ] Implement `extract_patterns()` — convert raw performance data into conclusions
  - e.g., "Benchmark videos outperform opinion pieces" stored as a `LearnedPattern`
- [ ] Implement `confidence_score()` — track how confident the system is in each pattern
- [ ] Implement `decay_unused_patterns()` — de-prioritize stale learnings
- [ ] Unit test: load memory, add 3 content items, assert patterns are extracted

#### Milestone 1.3 — Agent 1 Prompt & API
- [ ] Write Agent 1 system prompt emphasizing memory synthesis over raw storage
- [ ] Expose `get_creator_context()` — returns structured brief for Agent 3
- [ ] Expose `ingest_feedback(result)` — ingests post-action results and updates patterns

---

### Phase 2 — Agent 2: Research & Opportunity Monitor (Hours 2–8)
**Owner: Research & Data Engineer**

#### Milestone 2.1 — Data Source Connectors
- [ ] Reddit connector — pull top posts from relevant subreddits
- [ ] Hacker News connector — top stories via public API
- [ ] Google Trends connector (via `pytrends`)
- [ ] GitHub Trending connector — trending repos related to AI/NVIDIA
- [ ] NVIDIA newsroom RSS connector
- [ ] Optional: X/Twitter via Tavily search fallback

#### Milestone 2.2 — Opportunity Scoring Engine
- [ ] Implement `OpportunityScorer`:
  - `trend_velocity` — how fast is topic growing?
  - `niche_alignment` — does it match creator's topics? (compare against Agent 1 profile)
  - `competition_gap` — is this underexplored?
  - `recency` — is this fresh?
- [ ] Score each discovered topic 0–100
- [ ] Output structured `Opportunity` objects:
  ```json
  {
    "topic": "NVIDIA Claw Agents",
    "trend_score": 94,
    "niche_alignment": 88,
    "reason": "Rapidly growing, matches creator's AI tool videos",
    "suggested_angle": "Building Recursive Agents with NVIDIA Claw",
    "sources": ["reddit.com/r/LocalLLaMA", "news.ycombinator.com"]
  }
  ```

#### Milestone 2.3 — Agent 2 Prompt & API
- [ ] Write Agent 2 system prompt emphasizing opportunity detection over news aggregation
- [ ] Expose `get_opportunities(creator_context)` — accepts creator profile, returns ranked opportunities
- [ ] Deduplicate against previously surfaced topics (compare against Agent 1 memory)

---

### Phase 3 — Agent 3: Strategist & Execution Layer (Hours 2–10)
**Owner: Strategy & Integration Engineer**

#### Milestone 3.1 — Orchestration Core
- [ ] Build `run_cycle()` — main execution loop:
  1. Call Agent 1 → get creator context
  2. Call Agent 2 → get ranked opportunities
  3. Synthesize into recommendations
  4. Present to creator
  5. Collect feedback
  6. Call Agent 1 to ingest feedback
- [ ] Log each cycle run with timestamp and recommendation set

#### Milestone 3.2 — Recommendation Engine
- [ ] Implement `generate_recommendation(context, opportunities)` using NVIDIA NIM inference
- [ ] Each recommendation must include:
  - **What** to create
  - **Why** (tied to specific patterns from Agent 1)
  - **Supporting evidence** from Agent 2
  - **Confidence score**
  - **Action steps**
- [ ] Rank recommendations by composite score

#### Milestone 3.3 — Creator Interface
- [ ] Build simple CLI interface for demo:
  - Show top 3 recommendations
  - Accept creator feedback (accept / reject / defer + notes)
  - Show "what I learned" summary after each cycle
- [ ] Optional: simple web UI with Streamlit or Gradio

#### Milestone 3.4 — Improvement Metrics Dashboard
- [ ] Track and display per-cycle metrics:
  - Number of learned patterns
  - Creator acceptance rate
  - Recommendation confidence over time
  - Duplicate research avoided
- [ ] Show delta between Run 1 and current run to prove improvement

---

### Phase 4 — Integration & Testing (Hours 10–16)
**All team members**

- [ ] End-to-end integration test: run full cycle from cold start
- [ ] Run 3 cycles with simulated feedback to demonstrate learning
- [ ] Verify memory persists across process restarts
- [ ] Stress test: 10 opportunities input, verify correct ranking
- [ ] Fix inter-agent data contract mismatches
- [ ] Polish CLI output / UI

---

### Phase 5 — Demo Preparation (Hours 16–24)
**Lead: Strategy & Integration Engineer | Support: All**

- [ ] Prepare demo script:
  1. Show Run 1 — cold start, minimal knowledge
  2. Feed in 3 rounds of simulated creator feedback
  3. Show Run 4 — clearly improved, personalized recommendations
  4. Show knowledge graph growth (number of patterns learned)
- [ ] Prepare 2-minute pitch covering:
  - The problem (content creators drown in choices)
  - Our differentiator (recursive intelligence, not just a chatbot)
  - Architecture walkthrough
  - Live demo
  - Metrics showing improvement
- [ ] Record backup demo video in case of live failure
- [ ] Push all final code to GitHub

---

## ✅ Success Criteria Checklist

| Criterion | Owner | Status |
|-----------|-------|--------|
| Persistent creator memory survives restarts | Memory Engineer | ⏳ |
| Agent 2 pulls live data from ≥2 sources | Research Engineer | ⏳ |
| Agent 3 generates reasoned recommendations | Strategy Engineer | ⏳ |
| System measurably improves over 3+ runs | All | ⏳ |
| Clear reasoning shown for every recommendation | Strategy Engineer | ⏳ |
| Demo clearly shows Run 1 vs Run N improvement | Strategy Engineer | ⏳ |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| LLM Inference | NVIDIA NIM (llama-3.1-70b-instruct or nemotron) |
| Agent Orchestration | Python + custom loop (or LangGraph) |
| Persistent Memory | JSON files → upgrade to SQLite/ChromaDB if time allows |
| Vector Search | ChromaDB (for semantic memory retrieval) |
| Web Scraping / Search | Tavily API, PRAW (Reddit), `requests` |
| Trend Data | `pytrends` (Google Trends) |
| UI | Streamlit or Gradio (optional) |
| Environment | Python 3.11+, `python-dotenv` |

---

## 🔑 API Keys Needed

| Key | Used By |
|-----|---------|
| `NVIDIA_API_KEY` | All agents (NIM inference) |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | Agent 2 |
| `TAVILY_API_KEY` | Agent 2 (web search fallback) |
| `OPENAI_API_KEY` | Optional fallback |
