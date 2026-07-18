# 👥 Team Roles & Responsibilities

## Recursive Creator Intelligence System
### NVIDIA Claw Agent Hackathon — Austin 2026

---

## Position 1 — Memory & Knowledge Engineer

### Primary Owner
Agent 1 — Memory & Knowledge Layer (persistent memory brain: episodic log,
semantic insights, entity graph — Supabase/pgvector backed)

### Core Responsibilities

- Design and implement the **Supabase schema** (`db/schema.sql`): `runs`,
  `episodes`, `insights`, `nodes`, `edges`, `insight_snapshots`
- Build the **consolidation engine** that turns raw episodes into
  confidence-scored insights (Nemotron proposes, deterministic code
  disposes — `agents/consolidation.py`)
- Implement the two public interfaces — `log_episode()` and
  `get_context()` (`agents/memory.py`) — the *only* door into this layer
- Implement the **onboarding bootstrap** (`agents/onboarding.py`): one-time
  pass that seeds the entity graph and runs consolidation immediately at
  creator signup, so run 1 isn't a cold start
- Ensure memory **persists in Postgres**, not in-process state
- Implement pgvector **dedup** and volatility-based **expiry** for stale
  or trend-derived insights

### Key Deliverables

| Deliverable | Description |
|-------------|-------------|
| `db/schema.sql` | Supabase/pgvector schema + `match_insights` RPC |
| `agents/models.py` | Frozen payload contracts + table-mirroring dataclasses |
| `agents/consolidation.py` | Batch consolidation engine (confidence math, promotions, dedup) |
| `agents/memory.py` | `log_episode()` / `get_context()` |
| `agents/onboarding.py` | Onboarding bootstrap |
| `tests/test_memory_layer.py` | Unit tests: math, onboarding, dedup, `get_context` — offline, no live creds needed |
| `scripts/seed_onboarding.py` | End-to-end proof against a real Supabase project |

### Technical Skills Needed
- Python (dataclasses, REST/HTTP clients)
- Postgres + pgvector schema design
- LLM prompting for structured JSON extraction (Nemotron via vLLM)
- Deterministic state-machine thinking for confidence/lifecycle math

### What "Done" Looks Like
- `python scripts/seed_onboarding.py` seeds a fake catalog and prints a
  populated `get_context()` — not an empty shell
- Insights visibly promote across a few consolidation passes, capped at
  `validated` on the onboarding run and reaching `core` only afterward
- Memory persists in Supabase across process restarts by construction
- `tests/test_memory_layer.py` passes without any live API keys

---

## Position 2 — Research & Data Engineer

### Primary Owner
Agent 2 — Research & Opportunity Agent (World Monitor)

### Core Responsibilities

- Build and maintain **data source connectors**:
  - Reddit (via PRAW)
  - Hacker News (public API)
  - Google Trends (via `pytrends`)
  - GitHub Trending (web scrape or API)
  - NVIDIA newsroom RSS
  - Tavily web search (as fallback/catch-all)
- Implement the **OpportunityScorer** — rank raw signals into actionable opportunities
- Implement **trend velocity detection** — how fast is a topic accelerating?
- Implement **niche alignment scoring** — match external topics against creator's known profile
- Implement **deduplication** — never surface the same opportunity twice
- Output clean, structured `Opportunity` JSON objects
- Integrate with Agent 1's creator profile to personalize opportunity relevance

### Key Deliverables

| Deliverable | Description |
|-------------|-------------|
| `agents/agent2_research.py` | Core research agent |
| `tools/reddit_tool.py` | Reddit connector |
| `tools/trends_tool.py` | Google Trends + HN connector |
| `tools/youtube_tool.py` | YouTube trending connector |
| `prompts/agent2_system.txt` | Agent 2 system prompt |
| Sample opportunity output | JSON examples for testing |

### Technical Skills Needed
- Python (REST APIs, web scraping, `requests`)
- PRAW (Reddit API library)
- `pytrends` or similar
- JSON data modeling
- Optional: async Python for parallel source fetching

### What "Done" Looks Like
- Agent 2 pulls live data from at least 2 real sources
- Each opportunity has a numeric score and clear reasoning
- Opportunities are personalized based on creator profile from Agent 1
- Duplicate topics across runs are filtered out

---

## Position 3 — Strategy & Integration Engineer

### Primary Owner
Agent 3 — Strategist / Execution Agent + System Orchestration

### Core Responsibilities

- Build the **main orchestration loop** (`run_cycle()`) that connects all three agents
- Implement the **recommendation engine** using NVIDIA NIM inference
- Ensure every recommendation includes clear reasoning tied to Agent 1 patterns and Agent 2 signals
- Build the **creator interface** (CLI minimum, Streamlit/Gradio optional)
- Implement **feedback collection** — accept/reject/defer with notes
- Implement the **improvement metrics dashboard** — show system getting smarter over runs
- Manage the **demo script** and integration testing
- Own the **`.env.example`**, `requirements.txt`, and project scaffolding
- Drive **Phase 4 integration** and **Phase 5 demo prep**

### Key Deliverables

| Deliverable | Description |
|-------------|-------------|
| `agents/agent3_strategist.py` | Core strategist agent |
| `main.py` | Entry point + run loop |
| `prompts/agent3_system.txt` | Agent 3 system prompt |
| CLI or UI | Creator-facing interface |
| Metrics display | Run-over-run improvement tracker |
| Demo script | Written walkthrough for judges |
| `requirements.txt` + `.env.example` | Project setup files |

### Technical Skills Needed
- Python (orchestration, control flow)
- NVIDIA NIM API (REST or SDK)
- LLM prompting for strategic reasoning
- CLI design or Streamlit/Gradio
- System integration and debugging

### What "Done" Looks Like
- `python main.py` runs the full cycle end-to-end
- Recommendations clearly explain *why* each piece of content is the best choice
- After 3 cycles, the system demonstrably gives better, more personalized recommendations
- The improvement is visible and explainable to judges in 2 minutes

---

## 🔄 Shared Responsibilities (All 3)

| Task | When |
|------|------|
| Agree on inter-agent data contracts (JSON schemas) | Phase 0 |
| Review each other's agent prompts | Phase 1–2 |
| End-to-end integration testing | Phase 4 |
| Demo rehearsal | Phase 5 |
| Push final code to GitHub | Phase 5 |

---

## 📊 Responsibility Matrix (RACI)

| Task | Mem Eng | Research Eng | Strategy Eng |
|------|---------|--------------|---------------|
| Knowledge graph design | **R** | C | C |
| Pattern learning engine | **R** | I | C |
| Reddit / trend connectors | C | **R** | I |
| Opportunity scoring | I | **R** | C |
| Orchestration loop | C | I | **R** |
| Recommendation engine | C | I | **R** |
| Creator UI / CLI | I | I | **R** |
| Demo preparation | C | C | **R** |
| Integration testing | **A** | **A** | **A** |

*R = Responsible | A = Accountable | C = Consulted | I = Informed*
