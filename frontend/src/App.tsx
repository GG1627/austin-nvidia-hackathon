import { useMemo, useState } from "react"; import { Home, ConnectWorld, BuildMemory } from "./Flow";
import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, dashboard } from "./lib/api";
import { Bell, Calendar, ChevronRight, CircleDot, Command, Database, Heart, Play, Sparkles, Zap } from "lucide-react";

const nodes: Node[] = [
  { id: "creator", position: { x: 170, y: 120 }, data: { label: "Maya / Creator" }, className: "graph-node creator" },
  { id: "local", position: { x: 420, y: 30 }, data: { label: "Local AI" }, className: "graph-node" },
  { id: "bench", position: { x: 450, y: 200 }, data: { label: "Benchmarks" }, className: "graph-node purple" },
  { id: "voice", position: { x: 120, y: 300 }, data: { label: "Tiny voice AI" }, className: "graph-node lime" },
];
const edges: Edge[] = [
  { id: "a", source: "creator", target: "local", animated: true },
  { id: "b", source: "creator", target: "bench" },
  { id: "c", source: "creator", target: "voice", animated: true },
];

function Sidebar({ page, setPage }: { page: string; setPage: (page: string) => void }) {
  const links = [{ label: "Command center", icon: Command }, { label: "Creator brain", icon: Database }, { label: "Opportunities", icon: Zap }, { label: "Content plan", icon: Calendar }];
  return <aside className="sidebar"><div className="brand"><span className="brand-mark">l</span><span>lore</span></div><nav>{links.map((item) => { const Icon = item.icon; return <button key={item.label} className={page === item.label ? "nav active" : "nav"} onClick={() => setPage(item.label)}><Icon size={18}/>{item.label}</button> })}</nav><div className="sidebar-bottom"><div className="mini-status"><span className="pulse" /> Agent system online</div><button className="avatar">MC</button></div></aside>
}
function Dashboard() {
  const [running, setRunning] = useState(false);
  const [liked, setLiked] = useState(false);
  const run = async () => { setRunning(true); await api.runHeartbeat(); setRunning(false); };
  const feed = useMemo(() => dashboard.activity, []);
  return <div className="app-shell"><Sidebar page="Command center" setPage={() => {}}/><main className="workspace"><header className="topbar"><div><p className="muted">Monday, July 18</p><h2>Good morning, Maya <span>*</span></h2></div><div className="top-actions"><button className="icon-button"><Bell size={19}/></button><button className="run-button" onClick={run}><Play size={15} fill="currentColor"/>{running ? "Scanning..." : "Run heartbeat"}</button></div></header><section className="signal-strip"><span className="pulse"/><b>Agent system is live</b><span>"</span><span>Last scan {dashboard.heartbeat.lastRun}</span><span>"</span><span>{dashboard.heartbeat.sources}</span><button>View activity <ChevronRight size={14}/></button></section><div className="dashboard-grid"><section className="feature-card"><div className="card-label"><span><Zap size={15}/> THE SIGNAL</span><span className="fresh">FRESH ? {dashboard.opportunity.freshness}</span></div><h1>{dashboard.opportunity.topic}</h1><p>{dashboard.opportunity.signal}</p><div className="source-row">{dashboard.opportunity.sources.map((source, i) => <span key={source} className={"source s"+i}>{source}</span>)}</div><div className="feature-footer"><div><span className="score">92</span><small>opportunity score</small></div><button className="outline">Open research <ChevronRight size={16}/></button></div></section><section className="brain-card"><div className="card-label"><span><Database size={15}/> YOUR CREATOR BRAIN</span><button className="tiny-link">Explore graph</button></div><div className="flow"><ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}><Background gap={18} size={1}/><Controls showInteractive={false}/></ReactFlow></div><div className="brain-stats"><span><b>34</b> memories</span><span><b>8</b> learned patterns</span><span><b>+3</b> this week</span></div></section><section className="strategy-card"><div className="card-label"><span><Sparkles size={15}/> TODAY'S MOVE</span><span className="agent-pill">Agent 3</span></div><h3>Make this next:</h3><h2>Build a local voice assistant in under 500 KB</h2><p>It matches the format your audience saves most, and the conversation is peaking right now.</p><div className="steps"><span><i>1</i> Outline the benchmark setup</span><span><i>2</i> Record Thursday ? 2:00 PM</span></div><div className="feedback"><button className={liked ? "feedback-btn selected" : "feedback-btn"} onClick={() => setLiked(!liked)}><Heart size={16} fill={liked ? "currentColor" : "none"}/> Love it</button><button className="feedback-btn">Not for me</button></div></section><section className="activity-card"><div className="card-label"><span><CircleDot size={15}/> AGENT ACTIVITY</span><button className="tiny-link">All activity</button></div><div className="activity-list">{feed.map((item, index) => <div className="activity" key={item}><span className={"activity-dot d"+index}/><span>{item}</span><small>{index === 0 ? "42s" : index === 1 ? "1m" : "2m"}</small></div>)}</div></section></div></main></div>
}

function App() { const [stage, setStage] = useState<"home" | "connect" | "build" | "dashboard">("home"); if (stage === "home") return <Home onConnect={() => setStage("connect")} />; if (stage === "connect") return <ConnectWorld onBack={() => setStage("home")} onBuild={() => setStage("build")} />; if (stage === "build") return <BuildMemory onDone={() => setStage("dashboard")} />; return <Dashboard />; } export default App;
