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

### Creator Context (Agent 1 → Agent 3)

```json
{
  "creator_profile": {
    "niche": "AI tools for developers",
    "audience": "engineers, 25-40",
    "preferred_length": "10-15 minutes",
    "posting_frequency": "weekly"
  },
  "learned_patterns": [
    {
      "id": "p_001",
      "pattern": "Benchmark videos outperform opinion pieces",
      "confidence": 0.87,
      "evidence_count": 6,
      "last_updated": "2026-07-18"
    }
  ],
  "top_performing_topics": ["LLM benchmarks", "local AI", "NVIDIA tools"],
  "avoid_topics": ["crypto", "politics"],
  "pending_ideas": [
    {
      "title": "NVIDIA Claw Deep Dive",
      "research_complete": 0.8
    }
  ]
}
```

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

## Knowledge Graph Schema

```json
{
  "version": 1,
  "last_updated": "2026-07-18T04:00:00Z",
  "run_count": 4,
  "creator_profile": { },
  "content_items": [
    {
      "id": "ci_001",
      "title": "...",
      "views": 120000,
      "retention_pct": 62,
      "topics": ["LLM", "benchmark"],
      "format": "tutorial",
      "length_min": 14
    }
  ],
  "learned_patterns": [
    {
      "id": "p_001",
      "pattern": "Benchmark videos outperform opinion pieces",
      "confidence": 0.87,
      "evidence_count": 6,
      "supporting_items": ["ci_001", "ci_004"],
      "created": "2026-07-15",
      "last_updated": "2026-07-18"
    }
  ],
  "surfaced_opportunities": ["opp_20260718_001"],
  "acceptance_history": [],
  "metrics": {
    "total_patterns": 7,
    "acceptance_rate": 0.75,
    "avg_confidence_run1": 0.42,
    "avg_confidence_current": 0.81
  }
}
```

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|----------|
| LLM Inference | NVIDIA NIM | Hackathon requirement, fast inference |
| Orchestration | Python 3.11 | Simple, fast to build |
| Memory Store | JSON → ChromaDB | Start simple, upgrade if time allows |
| Reddit | PRAW | Official Python Reddit API wrapper |
| Trends | pytrends | Google Trends Python client |
| Web Search | Tavily API | Fast structured search results |
| UI | Streamlit (optional) | Rapid prototyping |
| Environment | python-dotenv | Standard .env management |

---

## Folder Structure

```
auston-nvidia-hackathon/
├── main.py                    # Entry point
├── requirements.txt
├── .env.example
├── agents/
│   ├── agent1_memory.py       # Creator Intelligence Agent
│   ├── agent2_research.py     # Research & Opportunity Agent
│   └── agent3_strategist.py   # Strategist / Execution Agent
├── memory/
│   ├── knowledge_graph.json   # Persistent store (grows each run)
│   └── creator_profile.json   # Creator onboarding data
├── tools/
│   ├── memory_tool.py         # Read/write knowledge graph
│   ├── reddit_tool.py         # Reddit connector
│   ├── trends_tool.py         # Google Trends + HN
│   └── youtube_tool.py        # YouTube trending
├── prompts/
│   ├── agent1_system.txt
│   ├── agent2_system.txt
│   └── agent3_system.txt
└── docs/
    ├── IMPLEMENTATION_PLAN.md
    ├── ROLES.md
    ├── ARCHITECTURE.md
    ├── AGENTS.md
    └── RECURSIVE_LOOP.md
```
