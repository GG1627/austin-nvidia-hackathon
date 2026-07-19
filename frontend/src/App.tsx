import { useCallback, useEffect, useMemo, useRef, useState } from "react"; import { Home, ConnectWorld, BuildMemory } from "./Flow";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api, fallback, type Dashboard as DashboardData, type FeedbackAction, type Profile } from "./lib/api";
import { Bell, Calendar, ChevronRight, CircleDot, Command, Database, Heart, Play, Sparkles, Zap } from "lucide-react";
import { BrainPage, OpportunitiesPage, PlanPage, buildGraph } from "./Pages";

const PAGES = [
  { label: "Command center", icon: Command },
  { label: "Creator brain", icon: Database },
  { label: "Opportunities", icon: Zap },
  { label: "Content plan", icon: Calendar },
];

function Sidebar({ page, setPage, initials }: { page: string; setPage: (page: string) => void; initials: string }) {
  return <aside className="sidebar"><div className="brand"><span className="brand-mark">l</span><span>lore</span></div><nav>{PAGES.map((item) => { const Icon = item.icon; return <button key={item.label} className={page === item.label ? "nav active" : "nav"} onClick={() => setPage(item.label)}><Icon size={18}/>{item.label}</button> })}</nav><div className="sidebar-bottom"><div className="mini-status"><span className="pulse" /> Agent system online</div><button className="avatar">{initials}</button></div></aside>
}

function Dashboard() {
  const [page, setPage] = useState("Command center");
  const [running, setRunning] = useState(false);
  const [voted, setVoted] = useState<FeedbackAction | null>(null);
  const [notes, setNotes] = useState("");
  const [showAllActivity, setShowAllActivity] = useState(false);
  const [activityFocus, setActivityFocus] = useState(0);
  const activityRef = useRef<HTMLElement | null>(null);
  const [data, setData] = useState<DashboardData>(fallback);
  const load = useCallback(async () => { setData(await api.getDashboard()); }, []);
  useEffect(() => { load(); const poll = setInterval(load, 15000); return () => clearInterval(poll); }, [load]);
  useEffect(() => { setVoted(null); setNotes(""); }, [data.move?.id]);
  // Runs after the Command center (and the activity card) has rendered, so
  // "View activity" lands the eye on the list even from another page.
  useEffect(() => { if (activityFocus) activityRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [activityFocus]);
  const graph = useMemo(() => buildGraph(data), [data]);
  const run = async () => { setRunning(true); await api.runCycle(); await load(); setVoted(null); setRunning(false); };
  const vote = async (action: FeedbackAction) => {
    if (!data.move || voted || data.move.feedbackGiven) return;
    setVoted(action);
    await api.sendFeedback(data.move.id, action, notes.trim());
    await load();
  };
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const opp = data.opportunity; const move = data.move;
  const settled = !!voted || !!move?.feedbackGiven;
  const initials = (data.creator.name || "C").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const activity = showAllActivity ? data.activity : data.activity.slice(0, 4);
  const commandCenter = <div className="dashboard-grid"><section className="feature-card"><div className="card-label"><span><Zap size={15}/> THE SIGNAL</span><span className="fresh">FRESH · {opp?.freshness ?? "—"}</span></div>{opp ? <><h1>{opp.topic}</h1><p>{opp.signal}</p><div className="source-row">{opp.sources.map((source, i) => <span key={source} className={"source s"+i}>{source}</span>)}</div><div className="feature-footer"><div><span className="score">{opp.score}</span><small>opportunity score</small></div><button className="outline" onClick={() => setPage("Opportunities")}>Open research <ChevronRight size={16}/></button></div></> : <><h1>No opportunities yet</h1><p>Run the Agent 2 heartbeat to scan live sources.</p></>}</section><section className="brain-card"><div className="card-label"><span><Database size={15}/> YOUR CREATOR BRAIN</span><button className="tiny-link" onClick={() => setPage("Creator brain")}>Explore graph</button></div><div className="flow"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}><Background gap={18} size={1}/><Controls showInteractive={false}/></ReactFlow></div><div className="brain-stats"><span><b>{data.brain.memories}</b> memories</span><span><b>{data.brain.patterns}</b> learned patterns</span><span><b>{data.runCount ?? 0}</b> cycles run</span></div></section><section className="strategy-card"><div className="card-label"><span><Sparkles size={15}/> TODAY'S MOVE</span><span className="agent-pill">Agent 3</span></div>{move ? <><h3>Make this next:</h3><h2>{move.title}</h2><p>{move.why}</p><div className="steps">{move.steps.slice(0, 2).map((step, i) => <span key={step}><i>{i + 1}</i> {step}</span>)}</div><div className="feedback-notes"><input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add a note for the brain (optional)" disabled={settled}/></div><div className="feedback"><button className={voted === "accepted" ? "feedback-btn selected" : "feedback-btn"} disabled={settled} onClick={() => vote("accepted")}><Heart size={16} fill={voted === "accepted" ? "currentColor" : "none"}/> Love it</button><button className={voted === "rejected" ? "feedback-btn selected" : "feedback-btn"} disabled={settled} onClick={() => vote("rejected")}>Not for me</button><button className={voted === "deferred" ? "feedback-btn selected" : "feedback-btn"} disabled={settled} onClick={() => vote("deferred")}>Later</button></div></> : <><h3>No recommendation yet</h3><p>Hit "Run cycle" to have Agent 3 pick your next move.</p></>}</section><section className="activity-card" ref={activityRef}><div className="card-label"><span><CircleDot size={15}/> AGENT ACTIVITY</span><button className="tiny-link" onClick={() => setShowAllActivity(v => !v)}>{showAllActivity ? "Show less" : "All activity"}</button></div><div className="activity-list">{activity.map((item, index) => <div className="activity" key={item + index}><span className={"activity-dot d"+(index % 3)}/><span>{item}</span></div>)}</div></section></div>;
  return <div className="app-shell"><Sidebar page={page} setPage={setPage} initials={initials}/><main className="workspace"><header className="topbar"><div><p className="muted">{today}</p><h2>{page === "Command center" ? <>Good morning, {data.creator.name} <span>*</span></> : page}</h2></div><div className="top-actions"><button className="icon-button"><Bell size={19}/></button><button className="run-button" onClick={run} disabled={running}><Play size={15} fill="currentColor"/>{running ? "Scanning..." : "Run cycle"}</button></div></header><section className="signal-strip"><span className="pulse"/><b>{data.live ? "Agent system is live" : "Offline demo data"}</b><span>·</span><span>Last scan {data.heartbeat.lastRun}</span><span>·</span><span>{data.heartbeat.sources}{data.heartbeat.stale ? " (stale snapshot)" : ""}</span><button onClick={() => { setPage("Command center"); setShowAllActivity(true); setActivityFocus((n) => n + 1); }}>View activity <ChevronRight size={14}/></button></section>{page === "Command center" ? commandCenter : page === "Creator brain" ? <BrainPage data={data}/> : page === "Opportunities" ? <OpportunitiesPage data={data}/> : <PlanPage data={data}/>}</main></div>
}

function App() {
  const [stage, setStage] = useState<"home" | "connect" | "build" | "dashboard">("home");
  const [profile, setProfile] = useState<Profile>({ name: "", niche: "", audience: "" });
  if (stage === "home") return <Home onConnect={() => setStage("connect")} onSignIn={() => setStage("dashboard")} />;
  if (stage === "connect") return <ConnectWorld onBack={() => setStage("home")} onBuild={(p) => { setProfile(p); setStage("build"); }} />;
  if (stage === "build") return <BuildMemory profile={profile} onDone={() => setStage("dashboard")} />;
  return <Dashboard />;
}
export default App;
