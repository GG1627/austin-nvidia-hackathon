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
  /db
    schema.sql              # runs, episodes, insights, nodes, edges, insight_snapshots
  /agents
    models.py                # Agent 1: frozen payload contracts + table dataclasses
    db.py                    # Agent 1: Supabase REST client
    embeddings.py            # Agent 1: vLLM embeddings + cosine helpers
    llm.py                   # Agent 1: Nemotron proposer + vLLM calibration
    consolidation.py         # Agent 1: batch consolidation engine
    memory.py                # Agent 1: log_episode() / get_context()
    onboarding.py            # Agent 1: onboarding bootstrap
    agent2_research.py
    agent3_strategist.py
  /scripts
    seed_onboarding.py       # Agent 1: end-to-end onboarding proof
  /tools
    reddit_tool.py
    trends_tool.py
    youtube_tool.py
  /prompts
    agent2_system.txt
    agent3_system.txt
  main.py
  requirements.txt
  .env.example
  ```

---

### Phase 1 — Agent 1: Memory & Knowledge Layer (Hours 2–8)
**Owner: Memory & Knowledge Engineer**

#### Milestone 1.1 — Supabase Schema Foundation
- [x] Design schema (`db/schema.sql`): `runs`, `episodes`, `insights`, `nodes`,
  `edges`, `insight_snapshots` + pgvector HNSW indexes + `match_insights` RPC
- [x] Implement `SupabaseClient` (`agents/db.py`) — thin REST wrapper, no SDK dependency
- [x] Freeze payload contracts + table-mirroring dataclasses (`agents/models.py`)

#### Milestone 1.2 — Consolidation Engine
- [x] Implement `run_consolidation()` — one batch Nemotron call proposes
  `new_hypotheses` / `evidence_updates` / `contradictions`; deterministic code
  applies confidence math and lifecycle promotion (`agents/consolidation.py`)
- [x] Implement pgvector dedup (merge as evidence above ~0.90 cosine similarity)
- [x] Implement self-hosted vLLM dual-model calibration for the faster support factor
- [x] Implement volatility-based expiry for trend-derived insights
- [x] Unit test: math + onboarding + dedup, offline (`tests/test_memory_layer.py`)

#### Milestone 1.3 — Public Interfaces & Onboarding
- [x] Expose `log_episode(kind, payload, run_id)` and `get_context(task, token_budget)`
  (`agents/memory.py`) — the only door into the memory layer
- [x] Implement onboarding bootstrap (`agents/onboarding.py`): seeds the entity
  graph and runs consolidation immediately at signup, capped at `validated`
- [x] End-to-end proof script (`scripts/seed_onboarding.py`)

---

### Phase 2 — Agent 2: Research & Opportunity Monitor (Hours 2–8)
**Owner: Research & Data Engineer**

#### Milestone 2.1 — Data Source Connectors
- [x] Reddit connector — pull top posts from relevant subreddits (`tools/reddit_tool.py`)
- [x] Hacker News connector — top stories via public API (`tools/trends_tool.py`)
- [x] Google Trends connector (`tools/trends_tool.py`)
- [x] GitHub Trending connector — trending repos related to AI/NVIDIA (`tools/world_sources.py`)
- [x] NVIDIA newsroom RSS connector (`tools/world_sources.py`)
- [x] YouTube Data API connector (`tools/social_sources.py`)
- [x] Optional: X/Twitter connector, disabled by default (`ENABLE_X=false`, paid API credits — see sprint2.md Workstream A3)

#### Milestone 2.2 — Opportunity Scoring Engine
- [x] Implement composite opportunity scoring in `ResearchAgent._build_opportunities` / `_scores`:
  - `trend_velocity` — how fast is topic growing?
  - `niche_alignment` — does it match creator's topics? (compare against Agent 1 profile, including learned insights)
  - `competition_gap` — is this underexplored?
  - `recency_bonus` — is this fresh?
- [x] Score each discovered topic 0–100, composite = `0.35*trend + 0.35*alignment + 0.20*gap + 0.10*recency`
- [x] Output structured `Opportunity` objects (`agents/agent2_research.py`):
  ```json
  {
    "id": "opp_...",
    "topic": "NVIDIA Claw Agents",
    "suggested_angle": "Building Recursive Agents with NVIDIA Claw",
    "reasoning": "Rapidly growing, matches creator's AI tool videos",
    "trend_velocity": 94,
    "niche_alignment": 88,
    "competition_gap": 60,
    "recency_bonus": 90,
    "composite_score": 84.9,
    "sources": [{"name": "reddit", "url": "..."}],
    "freshness": "2026-07-18T12:00:00+00:00"
  }
  ```

#### Milestone 2.3 — Agent 2 Prompt & API
- [x] Write Agent 2 system prompt emphasizing opportunity detection over news aggregation (`prompts/agent2_system.txt`)
- [x] Expose `get_opportunities(creator_context, top_n)` — accepts Agent 1 context, returns ranked opportunities
- [x] Deduplicate against previously surfaced topics via an injected `memory_store` adapter (`was_opportunity_surfaced` / `mark_opportunity_surfaced`)
- [x] Versioned handoff artifact for Agent 3 (`agents/agent2_handoff.py`, `docs/AGENT2_HANDOFF.md`) plus a heartbeat runner (`agents/agent2_heartbeat.py`, `scripts/run_agent2_heartbeat.py`)

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
| Persistent creator memory survives restarts | Memory Engineer | ✅ (verified live 2026-07-18, sprint2.md A1) |
| Agent 2 pulls live data from ≥2 sources | Research Engineer | ⏳ |
| Agent 3 generates reasoned recommendations | Strategy Engineer | ⏳ |
| System measurably improves over 3+ runs | All | ⏳ |
| Clear reasoning shown for every recommendation | Strategy Engineer | ⏳ |
| Demo clearly shows Run 1 vs Run N improvement | Strategy Engineer | ⏳ |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Consolidation LLM | Nemotron via NVIDIA NIM / self-hosted vLLM, OpenAI-compatible (`agents/llm.py`) |
| Calibration LLM | Second, independently-hosted self-hosted vLLM model (`Qwen2.5-7B-Instruct`) for dual-model agreement |
| Embeddings | Self-hosted vLLM embedding server (`Qwen3-Embedding-0.6B`, 1024-dim, `agents/embeddings.py`) |
| Agent Orchestration | Python + custom heartbeat loop (`agents/agent2_heartbeat.py`) — no LangGraph |
| Persistent Memory | Supabase (Postgres) + pgvector, accessed via a thin REST client (`agents/db.py`, `db/schema.sql`) — not JSON files or ChromaDB |
| Vector Search | pgvector HNSW index + `match_insights` RPC (with a local cosine fallback when the RPC is unreachable) |
| Agent 2 research runtime | NemoClaw / Ollama-compatible inference route (`OLLAMA_MODEL`, `INFERENCE_BASE_URL`) |
| Web / Signal Sources | Hacker News, Reddit, Google Trends, GitHub Trending, NVIDIA RSS, YouTube Data API, X (optional, disabled by default) |
| UI | None yet — Agent 3's CLI is out of scope for this sprint (see sprint2.md) |
| Environment | Python 3.11+, `python-dotenv`, `httpx` |

---

## 🔑 API Keys Needed

Source of truth: `.env.example`.

| Key | Used By |
|-----|---------|
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Agent 1 (Supabase REST client) |
| `NVIDIA_API_KEY` | Agent 1 consolidation proposer (Nemotron via NIM/vLLM) |
| `VLLM_CALIBRATE_BASE_URL` (+ `_MODEL` / `_API_KEY`) | Agent 1 dual-model calibration (self-hosted vLLM) |
| `VLLM_EMBEDDING_BASE_URL` (+ `_MODEL` / `_API_KEY`) | Agent 1 embeddings (self-hosted vLLM) |
| `OLLAMA_URL` / `OLLAMA_MODEL` / `INFERENCE_BASE_URL` | Agent 2 opportunity analysis (NemoClaw/Ollama-compatible route) |
| `YOUTUBE_API_KEY` | Agent 2 YouTube connector |
| `X_BEARER_TOKEN` (+ `ENABLE_X`) | Agent 2 X connector, optional/disabled by default (paid API credits) |
| `AGENT_RUN_ID` | Agent 2 heartbeat — owned by Agent 3, Agent 2 only reads it |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, `TAVILY_API_KEY` | Agent-3-owned (not required for Agents 1 & 2 this sprint) |
