# 🏗️ Technical Architecture

## Recursive Creator Intelligence System

---

## System Overview

The system is composed of three specialized AI agents that communicate through structured JSON contracts, share a persistent memory layer, and execute a continuous improvement loop.

```
                    ┌───────────────────┐
                    │   Creator Input     │
                    └──────────┴────────┘
                               │
                               ▼
         ┌────────────────────────────────────┐
         │         Agent 3: Strategist           │
         │  ────────────────────────────────  │
         │  orchestrates the full loop           │
         │  generates recommendations            │
         │  explains reasoning                   │
         │  collects feedback                    │
         └───────┬─────────────────┬────────┘
                  │                 │
         reads context       reads opportunities
                  │                 │
                  ▼                 ▼
  ┌────────────────┐  ┌────────────────┐
  │ Agent 1        │  │ Agent 2        │
  │ Memory Brain   │  │ Research &     │
  │                │◄─│ Opportunity    │
  │ knowledge      │  │ (uses creator  │
  │ patterns       │  │  profile to     │
  │ conclusions    │  │  score topics)  │
  └───────┬────────┘  └───────┬────────┘
          │                       │
          ▼                       ▼
  ┌────────────────┐  ┌────────────────┐
  │ knowledge_     │  │ External       │
  │ graph.json     │  │ Sources:       │
  │ (persistent)   │  │ Reddit, HN,    │
  └────────────────┘  │ Trends, NVIDIA │
                      └────────────────┘
```

---

## Data Contracts

### get_context() (Agent 1 → Agent 3)

The only read interface into the memory layer. See `agents/memory.py` and
Agent 1's spec section 7 for the authoritative contract.

```json
{
  "creator_profile": {"niche": "AI tools for developers", "audience_description": "engineers, 25-40"},
  "core_insights": [
    {"id": 3, "statement": "Benchmark-format videos outperform opinion pieces", "status": "core", "confidence": 0.91}
  ],
  "relevant_insights": [
    {"id": 12, "statement": "Videos over 20 minutes underperform in this creator's catalog", "status": "hypothesis", "confidence": 0.30}
  ],
  "related_entities": [
    {"type": "video", "name": "LLM Benchmark Showdown", "edges": [{"relation": "performed_well", "weight": 1.4}]}
  ],
  "last_run": {"run_id": 4, "recommendations": [], "outcomes": []}
}
```

Deprecated insights and expired volatile insights are never returned;
every insight carries its `status` so Agent 3 can hedge on hypotheses.

### Opportunity Object (Agent 2 → Agent 3)

```json
{
  "id": "opp_20260718_001",
  "topic": "NVIDIA Claw Recursive Agents",
  "trend_score": 94,
  "niche_alignment": 91,
  "competition_gap": 78,
  "composite_score": 88,
  "reason": "Rapidly trending, matches creator's top performing category, low saturation",
  "suggested_angle": "Building Recursive Agents with NVIDIA Claw",
  "sources": [
    {"name": "Reddit r/LocalLLaMA", "url": "...", "upvotes": 1840},
    {"name": "Hacker News", "url": "...", "points": 312}
  ],
  "freshness": "2026-07-18",
  "already_surfaced": false
}
```

### Recommendation Object (Agent 3 → Creator)

```json
{
  "rank": 1,
  "title": "Building Recursive Agents with NVIDIA Claw",
  "why": "Search interest is rising 94/100. Aligns with your strongest-performing category (benchmark/tutorial videos at 87% confidence). You already have 80% of the research completed.",
  "supporting_patterns": ["p_001", "p_003"],
  "opportunity_id": "opp_20260718_001",
  "confidence": 0.91,
  "action_steps": [
    "Review existing NVIDIA Claw notes",
    "Record benchmark section first (highest retention)",
    "Target 12-minute runtime based on audience retention patterns"
  ]
}
```

### Feedback Object (Creator → Agent 1)

```json
{
  "recommendation_id": "rec_001",
  "action": "accepted",
  "notes": "Already started outline",
  "outcome": null,
  "outcome_date": null
}
```

---

## Memory Layer Schema

Persisted in Supabase/Postgres + pgvector, not JSON files. Full DDL lives
in `db/schema.sql`: `runs`, `episodes` (append-only, embedded), `insights`
(lifecycle-tracked conclusions), `nodes`/`edges` (entity graph),
`insight_snapshots` (per-run diffing for the run-1-vs-run-N demo). Agent 1
is the only code that touches these tables directly — everything else
goes through `log_episode()` / `get_context()`.

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|----------|
| LLM Inference | NVIDIA NIM (Nemotron) | Hackathon requirement, fast inference |
| Orchestration | Python 3.11 | Simple, fast to build |
| Memory Store | Supabase (Postgres + pgvector) | Durable, Realtime dashboard, native vector search |
| Reddit | PRAW | Official Python Reddit API wrapper |
| Trends | pytrends | Google Trends Python client |
| Web Search | Tavily API | Fast structured search results |
| UI | Streamlit (optional) | Rapid prototyping |
| Environment | python-dotenv | Standard .env management |

---

## Folder Structure

```
austin-nvidia-hackathon/
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
├── db/
│   └── schema.sql             # Supabase/pgvector schema + match_insights RPC
├── agents/
│   ├── models.py               # Agent 1: frozen payload contracts + table dataclasses
│   ├── db.py                   # Agent 1: Supabase REST client
│   ├── embeddings.py           # Agent 1: Featherless embeddings + cosine helpers
│   ├── llm.py                  # Agent 1: Nemotron proposer + Featherless calibration
│   ├── consolidation.py        # Agent 1: batch consolidation engine
│   ├── memory.py               # Agent 1: log_episode() / get_context()
│   ├── onboarding.py           # Agent 1: onboarding bootstrap
│   ├── agent2_research.py      # Research & Opportunity Agent
│   └── agent3_strategist.py    # Strategist / Execution Agent
├── scripts/
│   └── seed_onboarding.py     # Agent 1: end-to-end onboarding proof
├── tools/
│   ├── reddit_tool.py          # Reddit connector
│   ├── trends_tool.py          # Google Trends + HN
│   └── youtube_tool.py         # YouTube trending
├── prompts/
│   ├── agent2_system.txt
│   └── agent3_system.txt
├── tests/
│   ├── fakes.py                # In-memory Supabase fake for offline tests
│   └── test_memory_layer.py    # Agent 1 unit tests
└── docs/
    ├── IMPLEMENTATION_PLAN.md
    ├── ROLES.md
    ├── ARCHITECTURE.md
    ├── AGENTS.md
    └── RECURSIVE_LOOP.md
```
