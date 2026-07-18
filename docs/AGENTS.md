# 🤖 Agent Specifications

## Recursive Creator Intelligence System

---

## Agent 1 — Creator Intelligence Agent

**Role:** Long-term memory brain  
**Owner:** Memory & Knowledge Engineer  
**File:** `agents/agent1_memory.py`

### Purpose
Acts as the persistent knowledge layer of the system. Does not just store facts — it stores **conclusions**.

### What It Knows
- Creator profile (niche, audience, style, goals)
- Every content item ever analyzed (title, views, retention, topics)
- Learned patterns derived from performance data
- Content ideas and their research status
- Failed topics and why they failed
- Creator preferences and biases
- Historical acceptance/rejection of recommendations

### Core Methods

```python
class CreatorMemoryAgent:
    def get_creator_context() -> CreatorContext
    # Returns full structured profile for Agent 3

    def ingest_feedback(feedback: Feedback) -> None
    # Ingests creator response to a recommendation
    # This is where recursive learning happens

    def ingest_content_result(item: ContentItem) -> None
    # Ingests performance data from a published video

    def extract_patterns() -> List[LearnedPattern]
    # Derives conclusions from accumulated content items

    def update_pattern(pattern_id: str, new_evidence: dict) -> None
    # Updates confidence score and evidence count

    def get_patterns(min_confidence: float = 0.5) -> List[LearnedPattern]
    # Returns patterns above confidence threshold
```

### System Prompt Guidance

Agent 1 should be prompted to:
- Synthesize, not just store
- Express learnings as generalized rules, not specific facts
- Assign confidence scores (0.0 – 1.0) to every conclusion
- Update existing patterns rather than creating duplicates
- Flag contradictions in the knowledge base

### Example Learning

**Raw input:**
> Video A: 120k views, format=benchmark, length=14min
> Video B: 38k views, format=opinion, length=18min
> Video C: 145k views, format=benchmark, length=12min

**Stored conclusion:**
> Pattern: "Benchmark-format videos consistently outperform opinion-format videos"
> Confidence: 0.82 | Evidence: 3 items

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
