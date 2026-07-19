import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import { Calendar, Database, Zap } from "lucide-react";
import type { Dashboard as DashboardData } from "./lib/api";

export const shorten = (text: string, max = 30) => (text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text);

// Build the knowledge graph from live data: the creator at the center, top
// learned patterns and the current opportunity as spokes.
export function buildGraph(data: DashboardData): { nodes: Node[]; edges: Edge[] } {
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

const pct = (value: number) => Math.round(value * 100) + "%";

export function BrainPage({ data }: { data: DashboardData }) {
  const graph = buildGraph(data);
  return <div className="page-stack">
    <section className="brain-card">
      <div className="card-label"><span><Database size={15}/> KNOWLEDGE GRAPH</span><span className="fresh">{data.brain.patterns} patterns</span></div>
      <div className="flow tall"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}><Background gap={18} size={1}/><Controls showInteractive={false}/></ReactFlow></div>
      <div className="brain-stats"><span><b>{data.brain.memories}</b> memories</span><span><b>{data.brain.patterns}</b> learned patterns</span><span><b>{data.runCount ?? 0}</b> cycles run</span><span><b>{data.acceptanceRate == null ? "—" : pct(data.acceptanceRate)}</b> acceptance</span></div>
    </section>
    <section className="panel">
      <div className="card-label"><span><Database size={15}/> LEARNED PATTERNS</span><span className="fresh">sorted by confidence</span></div>
      {data.patterns.length ? <div className="pattern-list">{data.patterns.map((p) =>
        <div className="pattern-row" key={p.id}>
          <div className="pattern-text"><b>{p.text}</b><small>{p.id} · {p.evidence} evidence item{p.evidence === 1 ? "" : "s"}</small></div>
          <div className="conf"><span className="conf-track"><i style={{ width: pct(p.confidence) }}/></span><b>{pct(p.confidence)}</b></div>
        </div>)}
      </div> : <p className="empty-note">No learned patterns yet — run a cycle and give feedback to start teaching the brain.</p>}
    </section>
  </div>;
}

export function OpportunitiesPage({ data }: { data: DashboardData }) {
  const opportunities = data.opportunities?.length ? data.opportunities : (data.opportunity ? [data.opportunity] : []);
  return <div className="page-stack">
    {opportunities.length ? opportunities.map((opp, index) =>
      <section className="panel opp-row" key={opp.id || index}>
        <div className="opp-score"><span className="score">{opp.score}</span><small>score</small></div>
        <div className="opp-body">
          <b>{opp.topic}</b>
          <p>{opp.angle}</p>
          <p className="opp-signal">{opp.signal}</p>
          <div className="source-row">{opp.sources.map((source, i) => <span key={source} className={"source s" + i}>{source}</span>)}</div>
        </div>
        <span className="fresh">FRESH · {opp.freshness || "—"}</span>
      </section>)
    : <section className="panel">
        <div className="card-label"><span><Zap size={15}/> OPPORTUNITIES</span></div>
        <p className="empty-note">No live opportunities yet. Start the Agent 2 heartbeat (python3 scripts/run_agent2_heartbeat.py) to scan sources.</p>
      </section>}
  </div>;
}

export function PlanPage({ data }: { data: DashboardData }) {
  const plan = data.plan ?? { committed: [], later: [] };
  return <div className="page-stack">
    <section className="panel">
      <div className="card-label"><span><Calendar size={15}/> COMMITTED</span><span className="fresh">{plan.committed.length} item{plan.committed.length === 1 ? "" : "s"}</span></div>
      {plan.committed.length ? plan.committed.map((item, index) =>
        <div className="plan-item" key={index}>
          <b>{item.title}</b>
          <small>accepted in run {item.run}{item.notes ? ` · “${item.notes}”` : ""}</small>
          <div className="steps">{item.steps.map((step, j) => <span key={j}><i>{j + 1}</i> {step}</span>)}</div>
        </div>)
      : <p className="empty-note">Nothing committed yet — accept a recommendation on the command center and it lands here with its action steps.</p>}
    </section>
    <section className="panel">
      <div className="card-label"><span><Calendar size={15}/> MAYBE LATER</span></div>
      {plan.later.length ? <div className="later-list">{plan.later.map((item, index) => <span key={index} className="later-chip">{item.title} <small>run {item.run}</small></span>)}</div>
      : <p className="empty-note">Deferred recommendations queue up here.</p>}
    </section>
  </div>;
}
