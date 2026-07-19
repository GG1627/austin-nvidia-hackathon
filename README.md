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
- Agent 1 & Agent 2: currently running as stand-ins (`agents/stubs.py`);
  swap points documented in the integration guide.

## Docs

- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) — phases & milestones
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — data contracts & folder layout
- [docs/AGENTS.md](docs/AGENTS.md) — per-agent specs
- [docs/RECURSIVE_LOOP.md](docs/RECURSIVE_LOOP.md) — the learning loop & demo script
- [docs/ROLES.md](docs/ROLES.md) — team responsibilities
- [docs/AGENT3_INTEGRATION.md](docs/AGENT3_INTEGRATION.md) — Agent 3 status, testing & integration
