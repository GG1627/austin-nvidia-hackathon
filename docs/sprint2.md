# Sprint 2 Plan — Hardening Agents 1 & 2 (Agent 3 excluded)

Agent 3 is being built separately and is not yet in the repo. This sprint closes
every gap that does **not** depend on Agent 3 landing, so that when its code is
pushed, integration is a plug-in exercise rather than a debugging session.

Current baseline: `main` is clean, all branches merged, 27/27 tests passing —
but every test is offline with fakes. Nothing has been proven against live
services yet.

---

## Workstream A — Live-service verification (highest priority)

All success criteria in the implementation plan require live behavior; today we
have only offline proof.

### A1. Supabase end-to-end — ✅ done 2026-07-18
- [x] Apply `db/schema.sql` to the team Supabase project (runs, episodes,
      insights, nodes, edges, insight_snapshots + pgvector HNSW + `match_insights` RPC)
- [x] Run `scripts/seed_onboarding.py` against the real project; confirm it
      seeds the entity graph and consolidation promotes at most to `validated`
      — entity graph confirmed (9 related entities across 3 runs); no
      hypotheses were proposed because `NVIDIA_API_KEY` is present in `.env`
      but **empty**, so `propose_consolidation()` degrades to a no-op
      (documented, graceful behavior — not a bug). Re-run once a real key is
      set to actually exercise the promotion-cap path.
- [x] **Persistence check (success criterion):** ran `get_context()` in a
      genuinely separate `python3` process after seeding (run_id 3) and
      confirmed the creator profile and all 9 entity-graph nodes survived —
      proven against the live project, not a fake.

### A2. Self-hosted vLLM endpoints
`.env.example` leaves `VLLM_CALIBRATE_BASE_URL` and `VLLM_EMBEDDING_BASE_URL`
empty; calibration currently degrades to single-model support factors.
- [ ] Stand up the two vLLM servers (`Qwen2.5-7B-Instruct` on :8001,
      `Qwen3-Embedding-0.6B` on :8002 with `--task embed`)
- [ ] Verify embeddings return 1024-dim vectors (must match `vector(1024)` in schema)
- [ ] Verify dual-model calibration actually produces the faster support factor
      (compare promotion speed vs. single-model fallback)
- [ ] Confirm graceful degradation still works when the servers are down
      (kill them mid-run once — this is a demo-day insurance test)

### A3. Agent 2 live sources — mostly done 2026-07-19
- [x] Smoke-run `ResearchAgent` with real network: confirmed **3** live sources
      returning real data (`hacker_news`, `nvidia_rss`, `github`) — above the
      ≥2 success criterion. `reddit` is 403-blocked from this network/UA and
      `google_trends` fails because `pytrends` isn't in `requirements.txt`
      (both recorded cleanly in `source_errors`, see below — not blockers,
      not in scope to fix this pass).
- [ ] Provision `YOUTUBE_API_KEY` and verify the YouTube connector live —
      **outstanding**, blocked on creating a key in Google Cloud Console
      (connector itself is implemented and unit-tested).
- [x] Decide on X: **formally dropped from demo scope** (paid API credits).
      Stays disabled by default (`ENABLE_X=false`); not revisited this sprint.
- [x] Confirm `source_errors` is populated (not a crash) when one source fails
      live — confirmed for `reddit` (403), `google_trends` (missing dep),
      `tavily`/`youtube` (missing keys); `get_opportunities()` still returned
      results from the sources that succeeded.
- [x] Verify Nemotron inference route end-to-end (`OLLAMA_MODEL` /
      `INFERENCE_BASE_URL`) — found and fixed a real bug: the Ollama branch of
      `ResearchAgent._analyse_group` used `/api/generate` (flat prompt), which
      silently discards a reasoning model's answer into an unused `thinking`
      field instead of `response` — every live call was hitting the
      (correctly, already-offline-tested) fallback path even with the model
      available. Switched it to `/api/chat` (message-role framing, matching
      the existing `inference_base_url`/NemoClaw branch) and confirmed live
      against a freshly-pulled `nemotron-3-nano:4b`: real grounded
      topic/angle/reasoning now comes through instead of the fallback
      template. Also caught and fixed three offline tests
      (`test_source_failure_does_not_stop_run`,
      `test_optional_social_source_failures_are_recorded`,
      `test_x_is_disabled_by_default`) that never mocked `_analyse_group` and
      were only "offline" by accident of the model 404ing quickly before this
      fix — they now explicitly mock it like the rest of the suite.

### A4. Heartbeat + handoff, pre-staged without Agent 3
Agent 3 will own `AGENT_RUN_ID`, but nothing stops us proving the pipe now.
- [ ] Manually create a run row in Supabase, export `AGENT_RUN_ID`, and run
      `scripts/run_agent2_heartbeat.py` for 2–3 intervals
- [ ] Confirm `memory/agent2/latest.json` and `history/<run_id>.json` are written
      and conform to `agent2-handoff/v1` (see `docs/AGENT2_HANDOFF.md`)
- [ ] Confirm each opportunity is also logged as a `research_finding` episode
      through `log_episode()` (Agent 1 side visible in Supabase)
- [ ] Confirm the failure path writes an error snapshot instead of killing the
      loop (already unit-covered; verify once live)

---

## Workstream B — Test gaps that don't need Agent 3

- [ ] **Stress test (Phase 4 item):** feed 10+ candidate opportunities and
      assert composite ranking is correct and stable
- [ ] Add a handoff-schema validator test: reject unknown `schema_version`
      majors (the contract doc mandates this for consumers — encode it now so
      Agent 3 can reuse the validator)
- [ ] Add a persistence regression test for A1's restart check (can run against
      a fake, but keep one opt-in live marker, e.g. `pytest -m live`, skipped in CI)
- [ ] Multi-cycle memory test: run consolidation across 3 simulated cycles of
      feedback and assert confidence/promotion trends upward — this is the
      "system measurably improves" criterion, provable without Agent 3 by
      logging `FeedbackPayload`s directly

---

## Workstream C — Documentation truth-up

`docs/IMPLEMENTATION_PLAN.md` misleads anyone who reads it today.
- [ ] Check off Phase 2 (Milestones 2.1–2.3 are built and merged)
- [ ] Fix the tech-stack table: JSON/ChromaDB/LangGraph → Supabase + pgvector,
      self-hosted vLLM, custom heartbeat loop
- [ ] Fix the API-keys table to match `.env.example` (NVIDIA + Supabase + vLLM
      + YouTube; Reddit/Tavily are marked Agent-3-owned)
- [ ] Update the success-criteria table as Workstream A items land
- [ ] Expand `README.md` with a 5-minute quickstart: env setup → schema apply →
      seed onboarding → heartbeat run (judges and Agent 3's author both need this)

---

## Workstream D — Demo pre-staging (Agent-3-independent)

- [ ] Capture a known-good `latest.json` snapshot and Supabase seed state as
      demo fixtures / backup data in case live sources rate-limit on demo day
- [ ] Record Run-1 baseline metrics from onboarding (`run1_metrics` already
      exists in the memory layer) — this becomes the "before" in the
      Run 1 vs. Run N comparison
- [ ] Write down the exact env/edge cases we've verified (which sources are
      live, which model routes work) so demo setup isn't rediscovery

---

## Explicitly out of scope this sprint

- Agent 3 strategist, `run_cycle()`, recommendation engine, CLI, metrics
  dashboard — arrives via separate push
- Full Phase 4 end-to-end cycle and Phase 5 demo script — blocked on Agent 3

## Suggested order

1. A1 → A2 (memory layer live) — everything else reads through it
2. A3 → A4 (research layer live, handoff proven)
3. B in parallel with A (offline, no env dependencies)
4. C once A confirms what's actually true
5. D last, using artifacts produced by A

## Definition of done

- One command sequence, documented in README, takes a fresh clone to a live
  heartbeat writing valid `agent2-handoff/v1` snapshots backed by real Supabase
- `pytest` green, plus an opt-in `-m live` suite green against real services
- Implementation plan and README reflect reality
- Demo fixtures captured and stored
