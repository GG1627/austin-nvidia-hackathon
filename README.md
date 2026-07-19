# Creator Intelligence

An autonomous creator-research system. Agent 1 is a persistent memory/knowledge
layer (Supabase + pgvector); Agent 2 monitors live technical and creator
signals, scores emerging opportunities, and turns grounded evidence into
useful content angles; Agent 3 (strategist/CLI) is being built separately and
integrates through the versioned handoff artifact described in
[`docs/AGENT2_HANDOFF.md`](docs/AGENT2_HANDOFF.md).

For the hackathon deployment, see [vLLM + NemoClaw validation](docs/VLLM_NEMOCLAW_DEMO.md).
For current sprint status and what's proven live vs. offline, see
[`docs/sprint2.md`](docs/sprint2.md).

## Quickstart (5 minutes)

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Fill in at minimum `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Everything
   else (`NVIDIA_API_KEY`, `VLLM_CALIBRATE_BASE_URL`, `VLLM_EMBEDDING_BASE_URL`,
   `YOUTUBE_API_KEY`, ...) is optional — the memory layer's deterministic
   plumbing (episodes, entity graph, `get_context()`) works end to end even
   before every model/API key is wired up; missing ones just degrade
   gracefully (e.g. single-model support factors instead of dual-model
   calibration, or fewer live research sources).

3. **Apply the schema** to your Supabase project (creates `runs`, `episodes`,
   `insights`, `nodes`, `edges`, `insight_snapshots`, the pgvector HNSW index,
   and the `match_insights` RPC):

   ```bash
   psql "$SUPABASE_DB_URL" -f db/schema.sql
   # or paste db/schema.sql into the Supabase SQL editor
   ```

4. **Seed onboarding** — proves the Agent 1 memory layer end to end against
   the live project (episodes logged, entity graph populated, a first
   hypothesis surfaced via `get_context()`):

   ```bash
   python scripts/seed_onboarding.py
   ```

5. **Run the Agent 2 heartbeat** — once an Agent 1 run exists (Agent 3 owns
   `AGENT_RUN_ID` in normal operation; for a standalone smoke test, create a
   run row in Supabase yourself and export its id):

   ```bash
   AGENT_RUN_ID=<run-id> python scripts/run_agent2_heartbeat.py
   ```

   Each heartbeat logs `research_finding` episodes back into Agent 1 and
   writes `memory/agent2/latest.json` + `memory/agent2/history/<run_id>.json`
   — the `agent2-handoff/v1` artifact Agent 3 reads.

6. **Run the tests**

   ```bash
   pytest              # offline suite, no live services required
   pytest -m live      # opt-in tests against your real Supabase project
   ```
