export type Opportunity = { id: string; topic: string; angle: string; score: number; freshness: string; sources: string[]; signal: string };
export type Move = { id: string; title: string; why: string; steps: string[]; confidence: number; feedbackGiven: boolean };
export type Dashboard = {
  creator: { name: string; niche: string; audience?: string; handle?: string };
  heartbeat: { status: string; lastRun: string; sources: string; stale?: boolean };
  opportunity: Opportunity | null;
  insights: string[];
  brain: { memories: number; patterns: number };
  move: Move | null;
  activity: string[];
  engine?: string;
  runCount?: number;
  live: boolean;
};

// Static fallback so the UI still renders when scripts/serve_dashboard.py isn't running.
export const fallback: Dashboard = {
  creator: { name: "Maya Chen", handle: "@mayabuilds", niche: "AI tools for creators" },
  heartbeat: { status: "Offline demo", lastRun: "—", sources: "start scripts/serve_dashboard.py for live data" },
  opportunity: { id: "opp_voice", topic: "Tiny voice AI is having a moment", angle: "Build a local voice assistant in under 500 KB", score: 92, freshness: "8 min ago", sources: ["Hacker News", "GitHub Trending", "YouTube"], signal: "Three live signals converged around on-device voice models." },
  insights: ["Benchmark-style videos retain 28% longer", "Your audience saves local-AI tutorials", "12-15 min videos are your sweet spot"],
  brain: { memories: 34, patterns: 8 },
  move: { id: "", title: "Build a local voice assistant in under 500 KB", why: "It matches the format your audience saves most, and the conversation is peaking right now.", steps: ["Outline the benchmark setup", "Record Thursday · 2:00 PM"], confidence: 0.9, feedbackGiven: false },
  activity: ["Agent 2 scanned Hacker News", "New opportunity scored 92 / 100", "Agent 1 linked this to 2 prior wins"],
  live: false,
};

async function post(path: string, body: unknown): Promise<boolean> {
  try {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return res.ok;
  } catch {
    return false;
  }
}

export const api = {
  getDashboard: async (): Promise<Dashboard> => {
    try {
      const res = await fetch("/api/dashboard");
      if (!res.ok) throw new Error(String(res.status));
      return { ...fallback, ...(await res.json()), live: true };
    } catch {
      return fallback;
    }
  },
  runCycle: () => post("/api/cycle", {}),
  sendFeedback: (recommendationId: string, action: "accepted" | "rejected" | "deferred", notes = "") =>
    post("/api/feedback", { recommendation_id: recommendationId, action, notes }),
};
