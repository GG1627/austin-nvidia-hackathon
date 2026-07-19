# Recursive Creator Intelligence System

Three-agent system that gets smarter every run: Agent 1 (persistent creator
memory), Agent 2 (live opportunity research), Agent 3 (strategist that
generates reasoned recommendations, collects feedback, and pushes learnings
back into memory). Built for the NVIDIA Claw Agent Hackathon — Austin 2026.

## Quickstart (no installs, no API keys required)

```bash
python3 main.py                       # one interactive cycle
python3 main.py --cycles 4 --simulate # scripted 4-run demo showing learning
python3 main.py --metrics             # run-over-run improvement dashboard
python3 main.py --reset               # wipe memory back to cold start
python3 -m unittest -v                # test suite (16 tests, all offline)
```

Add `NVIDIA_API_KEY` to `.env` (see `.env.example`) to generate
recommendations with NVIDIA NIM; without it a deterministic engine keeps
everything fully functional.

## Status

- **Agent 3 (strategist, orchestration, CLI, metrics): complete** — see
  [docs/AGENT3_INTEGRATION.md](docs/AGENT3_INTEGRATION.md)
- **Real agents auto-wire when available** (`agents/bridges.py`):
  - Agent 1: set `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` to use the real
    memory layer (episodes + consolidation run after every cycle);
    otherwise the JSON-file mock is used.
  - Agent 2: `python3 scripts/run_agent2_heartbeat.py` writes
    `memory/agent2/latest.json`; `main.py` consumes it automatically.
  - `python3 main.py --mock` forces the stubs for a deterministic demo.
- **Dashboard**: `python3 scripts/serve_dashboard.py` (stdlib, port 8787)
  serves live agent state to the React app in `frontend/`
  (`npm run dev` proxies `/api`); "Run cycle" and the feedback buttons hit
  the real system.

## Docs

- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — phases & milestones
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — data contracts & folder layout
- [docs/AGENTS.md](docs/AGENTS.md) — per-agent specs
- [docs/RECURSIVE_LOOP.md](docs/RECURSIVE_LOOP.md) — the learning loop & demo script
- [docs/ROLES.md](docs/ROLES.md) — team responsibilities
- [docs/AGENT3_INTEGRATION.md](docs/AGENT3_INTEGRATION.md) — Agent 3 status, testing & integration
- [docs/VLLM_NEMOCLAW_DEMO.md](docs/VLLM_NEMOCLAW_DEMO.md) — vLLM + NemoClaw hackathon deployment validation
