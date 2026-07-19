# Agent 2 handoff contract

Agent 2 produces a portable snapshot for Agent 3 at:

- `memory/agent2/latest.json`
- `memory/agent2/history/<run_id>.json`

The snapshot is a cache and handoff artifact, not a second learning database.
Agent 1 remains the authoritative owner of runs, episodes, feedback, and
consolidated insights.

## Version

`schema_version` is currently `agent2-handoff/v1`. Consumers must reject
unknown major versions rather than silently guessing field meanings.

## Top-level shape

```json
{
  "schema_version": "agent2-handoff/v1",
  "run_id": 42,
  "generated_at": "ISO-8601 UTC",
  "producer": {"agent": "agent2_research", "model": "nemotron-3-nano-4b"},
  "context_basis": {
    "creator_profile": {},
    "core_insight_ids": [1, 2],
    "relevant_insight_ids": [8]
  },
  "source_errors": {},
  "opportunities": []
}
```

Every opportunity uses the existing Agent 2 fields: `id`, `topic`,
`suggested_angle`, `reasoning`, `trend_velocity`, `niche_alignment`,
`competition_gap`, `recency_bonus`, `composite_score`, `sources`, and
`freshness`.

## Agent 3 integration

1. Create/own the Agent 1 run ID.
2. Invoke the Agent 2 heartbeat with that run ID.
3. Read `latest.json` and make recommendations from its opportunities.
4. Send creator feedback and outcomes to Agent 1 using its frozen
   `FeedbackPayload` / `OutcomePayload` contracts.
5. On the next heartbeat, pass Agent 1's `get_context()` result to Agent 2.
   Agent 2 uses the returned insights for analysis and alignment.

This keeps feedback and learning in one authoritative system while letting
Agent 3 integrate through a stable file contract.


## Heartbeat launcher

With Supabase configured, start Agent 2 (AGENT_RUN_ID is optional — set it to
pin episodes to an Agent 3-owned run, otherwise they carry run_id=null):

```bash
python scripts/run_agent2_heartbeat.py
```
