# 🤖 Agent Specifications

## Recursive Creator Intelligence System

---

## Agent 1 — Memory & Knowledge Layer

**Role:** Long-term memory brain  
**Owner:** Memory & Knowledge Engineer  
**Files:** `agents/models.py`, `db.py`, `embeddings.py`, `llm.py`, `consolidation.py`, `memory.py`, `onboarding.py`

### Purpose
Owns the persistent knowledge layer: an append-only episodic log, a
consolidation engine that turns episodes into confidence-scored insights,
and a plain-SQL entity graph — all in Supabase/pgvector. Does not scrape
sources, score opportunities, or talk to the creator; it learns from what
Agents 2 and 3 log, and serves them context back through two interfaces.

### What It Knows
- `episodes` — append-only, immutable raw log of every observation,
  recommendation, outcome, feedback item, research finding, and onboarding
  finding, each with an embedding
- `insights` — learned conclusions with category, confidence, lifecycle
  status (`hypothesis` → `validated` → `core`, or `deprecated`), evidence
  counters, and pointers to supporting episodes
- `nodes` / `edges` — a plain two-table entity graph (creator, topic,
  video, audience_segment, opportunity nodes; typed weighted edges)

### Public Interfaces (the only door into this layer)

```python
def log_episode(kind: str, payload: dict, run_id: int) -> int:
    """Embed, insert, return episode id. Called by Agents 2 and 3."""

def get_context(task: str, token_budget: int = 4000) -> dict:
    """Returns {creator_profile, core_insights, relevant_insights,
    related_entities, last_run}, assembled in priority order until the
    token budget is spent. Deprecated/expired-volatile insights are never
    returned; every insight carries its status so Agent 3 can hedge."""
```

Payload contracts for each `episodes.kind` value (including the
onboarding-only `onboarding_finding` shape) are frozen in
`agents/models.py` — build against those dataclasses, not raw dicts.

### Consolidation Engine (`consolidation.py`)

Runs whenever unconsolidated episodes exist (NemoClaw heartbeat), plus once
immediately after onboarding. One batch call to Nemotron (via vLLM)
proposes `new_hypotheses` / `evidence_updates` / `contradictions`; a second,
self-hosted vLLM model calibrates the same batch. All confidence math and
lifecycle promotion after that is deterministic code — the LLM proposes,
the code disposes:

- New hypothesis → confidence `0.30`, status `hypothesis`
- Support → `c = c + 0.15*(1-c)` (single model) or `+0.20*(1-c)` (both
  models agree)
- Contradict → `c = c * 0.60`
- Promotion: 3+ support & `c > 0.60` → `validated`; 5+ & `c > 0.85` →
  `core`; `c < 0.20` → `deprecated` (kept, never deleted)
- Dedup: pgvector cosine similarity ≥ 0.90 merges as evidence instead of
  inserting a duplicate

### Onboarding Bootstrap (`onboarding.py`)

One-time job at creator signup, distinct from Agent 2's ongoing trend
monitoring. Logs every past-upload finding as an `onboarding_finding`
episode, builds the initial entity graph (creator + video + topic nodes,
`performed_well`/`underperformed` edges), and runs consolidation
immediately rather than waiting for the next heartbeat. Promotion is
capped at `validated` during this pass — nothing reaches `core` on run 1,
so the run-1-vs-run-N improvement curve stays honest.

### Example Learning

**Raw input (onboarding catalog):**
> Video A: 120k views, format=benchmark, length=14min
> Video B: 38k views, format=opinion, length=18min
> Video C: 145k views, format=benchmark, length=12min

**Stored conclusion:**
> Insight: "Benchmark-format videos consistently outperform opinion-format videos"
> Status: `hypothesis` (capped — onboarding pass) | Confidence: 0.30 → climbs with live evidence

---

## Agent 2 — Research & Opportunity Agent

**Role:** Live world monitor  
**Owner:** Research & Data Engineer  
**File:** `agents/agent2_research.py`

### Purpose
Continuously scans the outside world and converts raw signals into structured, scored opportunities.

### Data Sources

| Source | Library/API | What It Provides |
|--------|------------|------------------|
| Reddit | PRAW | Trending posts in relevant subreddits |
| Hacker News | Public API | Top tech stories |
| Google Trends | pytrends | Rising search terms |
| GitHub Trending | Web scrape | Trending AI/ML repos |
| NVIDIA Newsroom | RSS | Official announcements |
| Tavily | Tavily API | General web search fallback |

### Core Methods

```python
class ResearchAgent:
    def get_opportunities(creator_context: CreatorContext) -> List[Opportunity]
    # Main entry point. Pulls from all sources, scores, deduplicates, returns top N.

    def fetch_reddit_signals(subreddits: List[str]) -> List[RawSignal]
    def fetch_hn_signals() -> List[RawSignal]
    def fetch_trends(keywords: List[str]) -> List[RawSignal]
    def fetch_github_trending() -> List[RawSignal]

    def score_opportunity(signal: RawSignal, creator: CreatorContext) -> Opportunity
    # Applies scoring model to raw signal

    def is_duplicate(opportunity: Opportunity, memory: MemoryStore) -> bool
    # Checks against previously surfaced topics
```

### Scoring Model

```
Composite Score = (
    trend_velocity     * 0.35 +
    niche_alignment    * 0.35 +
    competition_gap    * 0.20 +
    recency_bonus      * 0.10
)
```

### System Prompt Guidance

Agent 2 should be prompted to:
- Think like an opportunity hunter, not a news aggregator
- Always suggest a specific content angle, not just a topic
- Connect external signals to the creator's known strengths
- Flag if a topic contradicts creator's known failures

---

## Agent 3 — Strategist / Execution Agent

**Role:** Decision layer and creator interface  
**Owner:** Strategy & Integration Engineer  
**File:** `agents/agent3_strategist.py`

### Purpose
Acts as the strategic advisor. Combines creator knowledge from Agent 1 with live opportunities from Agent 2 to generate reasoned, prioritized recommendations.

### Core Methods

```python
class StrategistAgent:
    def run_cycle() -> CycleResult
    # Executes the full recursive loop:
    # 1. Get creator context (Agent 1)
    # 2. Get opportunities (Agent 2)
    # 3. Generate recommendations
    # 4. Present to creator
    # 5. Collect feedback
    # 6. Push learnings back to Agent 1

    def generate_recommendations(
        context: CreatorContext,
        opportunities: List[Opportunity]
    ) -> List[Recommendation]
    # Uses NVIDIA NIM to synthesize context + opportunities into recommendations

    def present_recommendations(recs: List[Recommendation]) -> None
    # Displays to creator via CLI or UI

    def collect_feedback(recs: List[Recommendation]) -> List[Feedback]
    # Accepts creator input: accept / reject / defer + notes

    def show_improvement_metrics() -> None
    # Displays run-over-run learning stats
```

### Recommendation Quality Standard

Every recommendation **must** include:
1. **What** — Specific video title/concept
2. **Why** — Reasoning tied to 1+ learned patterns from Agent 1
3. **Evidence** — Specific signals from Agent 2
4. **Confidence** — Numeric score (0.0 – 1.0)
5. **Action Steps** — 3+ concrete next steps

**Bad recommendation:**
> "You should make a video about NVIDIA Claw."

**Good recommendation:**
> "Create ‘Building Recursive Agents with NVIDIA Claw’ this week. Search interest is rising (trend score: 94). This matches your benchmark/tutorial format which outperforms your other formats by 3x (confidence: 0.87). You already have 80% of the research in your notes. Target 12 minutes based on your audience retention data."

### System Prompt Guidance

Agent 3 should be prompted to:
- Behave as a strategic advisor, not a chatbot
- Always cite specific patterns and evidence in recommendations
- Rank by composite opportunity
- Acknowledge uncertainty with lower confidence scores
- Never give vague recommendations
