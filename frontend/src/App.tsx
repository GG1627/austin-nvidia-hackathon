import { useCallback, useEffect, useMemo, useState } from "react"; import { Home, ConnectWorld, BuildMemory } from "./Flow";
import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, fallback, type Dashboard as DashboardData } from "./lib/api";
import { Bell, Calendar, ChevronRight, CircleDot, Command, Database, Heart, Play, Sparkles, Zap } from "lucide-react";

const shorten = (text: string, max = 30) => (text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text);

// Build the knowledge graph from live data: the creator at the center, top
// learned patterns and the current opportunity as spokes.
function buildGraph(data: DashboardData): { nodes: Node[]; edges: Edge[] } {
  const spokeStyles = ["graph-node", "graph-node purple", "graph-node", "graph-node purple"];
  const positions = [{ x: 420, y: 30 }, { x: 450, y: 200 }, { x: 120, y: 300 }, { x: 390, y: 330 }];
  const spokes = [
    ...data.insights.slice(0, 3).map((text, i) => ({ id: `insight-${i}`, label: shorten(text), className: spokeStyles[i], animated: i === 0 })),
    ...(data.opportunity ? [{ id: "opportunity", label: shorten(data.opportunity.topic), className: "graph-node lime", animated: true }] : []),
  ];
  return {
    nodes: [
      { id: "creator", position: { x: 170, y: 140 }, data: { label: data.creator.name }, className: "graph-node creator" },
      ...spokes.map((s, i) => ({ id: s.id, position: positions[i % positions.length], data: { label: s.label }, className: s.className })),
    ],
    edges: spokes.map((s) => ({ id: `e-${s.id}`, source: "creator", target: s.id, animated: s.animated })),
  };
}

function Sidebar({ page, setPage }: { page: string; setPage: (page: string) => void }) {
  const links = [{ label: "Command center", icon: Command }, { label: "Creator brain", icon: Database }, { label: "Opportunities", icon: Zap }, { label: "Content plan", icon: Calendar }];
  return <aside className="sidebar"><div className="brand"><span className="brand-mark">l</span><span>lore</span></div><nav>{links.map((item) => { const Icon = item.icon; return <button key={item.label} className={page === item.label ? "nav active" : "nav"} onClick={() => setPage(item.label)}><Icon size={18}/>{item.label}</button> })}</nav><div className="sidebar-bottom"><div className="mini-status"><span className="pulse" /> Agent system online</div><button className="avatar">MC</button></div></aside>
}
function Dashboard() {
  const [running, setRunning] = useState(false);
  const [voted, setVoted] = useState<"accepted" | "rejected" | null>(null);
  const [data, setData] = useState<DashboardData>(fallback);
  const load = useCallback(async () => { setData(await api.getDashboard()); }, []);
  useEffect(() => { load(); const poll = setInterval(load, 15000); return () => clearInterval(poll); }, [load]);
  useEffect(() => { setVoted(null); }, [data.move?.id]);
  const graph = useMemo(() => buildGraph(data), [data]);
  const run = async () => { setRunning(true); await api.runCycle(); await load(); setVoted(null); setRunning(false); };
  const vote = async (action: "accepted" | "rejected") => {
    if (!data.move || voted) return;
    setVoted(action);
    await api.sendFeedback(data.move.id, action, action === "rejected" ? "Not for me (dashboard)" : "Love it (dashboard)");
    await load();
  };
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const opp = data.opportunity; const move = data.move;
  return <div className="app-shell"><Sidebar page="Command center" setPage={() => {}}/><main className="workspace"><header className="topbar"><div><p className="muted">{today}</p><h2>Good morning, {data.creator.name} <span>*</span></h2></div><div className="top-actions"><button className="icon-button"><Bell size={19}/></button><button className="run-button" onClick={run} disabled={running}><Play size={15} fill="currentColor"/>{running ? "Scanning..." : "Run cycle"}</button></div></header><section className="signal-strip"><span className="pulse"/><b>{data.live ? "Agent system is live" : "Offline demo data"}</b><span>·</span><span>Last scan {data.heartbeat.lastRun}</span><span>·</span><span>{data.heartbeat.sources}{data.heartbeat.stale ? " (stale snapshot)" : ""}</span><button>View activity <ChevronRight size={14}/></button></section><div className="dashboard-grid"><section className="feature-card"><div className="card-label"><span><Zap size={15}/> THE SIGNAL</span><span className="fresh">FRESH · {opp?.freshness ?? "—"}</span></div>{opp ? <><h1>{opp.topic}</h1><p>{opp.signal}</p><div className="source-row">{opp.sources.map((source, i) => <span key={source} className={"source s"+i}>{source}</span>)}</div><div className="feature-footer"><div><span className="score">{opp.score}</span><small>opportunity score</small></div><button className="outline">Open research <ChevronRight size={16}/></button></div></> : <><h1>No opportunities yet</h1><p>Run the Agent 2 heartbeat to scan live sources.</p></>}</section><section className="brain-card"><div className="card-label"><span><Database size={15}/> YOUR CREATOR BRAIN</span><button className="tiny-link">Explore graph</button></div><div className="flow"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}><Background gap={18} size={1}/><Controls showInteractive={false}/></ReactFlow></div><div className="brain-stats"><span><b>{data.brain.memories}</b> memories</span><span><b>{data.brain.patterns}</b> learned patterns</span><span><b>{data.runCount ?? 0}</b> cycles run</span></div></section><section className="strategy-card"><div className="card-label"><span><Sparkles size={15}/> TODAY'S MOVE</span><span className="agent-pill">Agent 3</span></div>{move ? <><h3>Make this next:</h3><h2>{move.title}</h2><p>{move.why}</p><div className="steps">{move.steps.slice(0, 2).map((step, i) => <span key={step}><i>{i + 1}</i> {step}</span>)}</div><div className="feedback"><button className={voted === "accepted" ? "feedback-btn selected" : "feedback-btn"} disabled={!!voted || move.feedbackGiven} onClick={() => vote("accepted")}><Heart size={16} fill={voted === "accepted" ? "currentColor" : "none"}/> Love it</button><button className={voted === "rejected" ? "feedback-btn selected" : "feedback-btn"} disabled={!!voted || move.feedbackGiven} onClick={() => vote("rejected")}>Not for me</button></div></> : <><h3>No recommendation yet</h3><p>Hit "Run cycle" to have Agent 3 pick your next move.</p></>}</section><section className="activity-card"><div className="card-label"><span><CircleDot size={15}/> AGENT ACTIVITY</span><button className="tiny-link">All activity</button></div><div className="activity-list">{data.activity.map((item, index) => <div className="activity" key={item}><span className={"activity-dot d"+index}/><span>{item}</span></div>)}</div></section></div></main></div>
}

function App() { const [stage, setStage] = useState<"home" | "connect" | "build" | "dashboard">("home"); if (stage === "home") return <Home onConnect={() => setStage("connect")} />; if (stage === "connect") return <ConnectWorld onBack={() => setStage("home")} onBuild={() => setStage("build")} />; if (stage === "build") return <BuildMemory onDone={() => setStage("dashboard")} />; return <Dashboard />; } export default App;
