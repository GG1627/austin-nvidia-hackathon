export type Opportunity = { id: string; topic: string; angle: string; score: number; freshness: string; sources: string[]; signal: string };
export const dashboard = {
  creator: { name: "Maya Chen", handle: "@mayabuilds", niche: "AI tools for creators" },
  heartbeat: { status: "Scanning", lastRun: "42 sec ago", sources: "6 / 7 healthy" },
  opportunity: { id: "opp_voice", topic: "Tiny voice AI is having a moment", angle: "Build a local voice assistant in under 500 KB", score: 92, freshness: "8 min ago", sources: ["Hacker News", "GitHub Trending", "YouTube"], signal: "Three live signals converged around on-device voice models." } as Opportunity,
  insights: ["Benchmark-style videos retain 28% longer", "Your audience saves local-AI tutorials", "12-15 min videos are your sweet spot"],
  activity: ["Agent 2 scanned Hacker News", "New opportunity scored 92 / 100", "Agent 1 linked this to 2 prior wins"],
};
export const api = {
  getDashboard: async () => dashboard,
  runHeartbeat: async () => new Promise<typeof dashboard>((resolve) => setTimeout(() => resolve(dashboard), 700)),
};
