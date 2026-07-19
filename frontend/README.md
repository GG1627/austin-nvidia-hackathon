# Lore frontend

A React + TypeScript product shell for the Creator Intelligence agents.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

## Current state

The app deliberately uses the typed mock data in `src/lib/api.ts`. This lets the
team demo the intended onboarding and dashboard experience before every backend
integration is complete.

Replace the functions in that file with the future API calls:

- `GET /api/creator-context` -> Agent 1 context and memory graph
- `GET /api/opportunities` -> `memory/agent2/latest.json` or backend adapter
- `POST /api/heartbeat/run` -> Agent 2 heartbeat trigger
- `GET /api/recommendation` -> Agent 3 result
- `POST /api/feedback` -> Agent 3 -> Agent 1 feedback/outcome flow

## Product flow

1. Creator connects Notion, channel/profile data, and calendar.
2. Agent 1 turns onboarding into persistent creator context.
3. Agent 2 refreshes live opportunities on its heartbeat.
4. Agent 3 recommends the best feasible next move.
5. Creator feedback appears in Agent 1's next context, improving later runs.

`npm run build` verifies the production bundle.
