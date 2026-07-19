"""CLI presentation layer for Agent 3.

Pure rendering and prompting: every function takes its data plus print/input
callables, so the strategist stays testable with captured IO and this module
never touches memory, research, or history state.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from agents.contracts import CycleResult, Feedback, Opportunity, Recommendation


def present_recommendations(
    recommendations: List[Recommendation],
    opportunities: Optional[List[Opportunity]],
    print_fn: Callable[[str], None],
) -> None:
    if not recommendations:
        print_fn("\n  No recommendations this cycle (no eligible opportunities).")
        return
    opps = {o.id: o for o in (opportunities or [])}
    print_fn("\n  ── TOP RECOMMENDATIONS " + "─" * 38)
    for rec in recommendations:
        bar = "█" * round(rec.confidence * 10) + "░" * (10 - round(rec.confidence * 10))
        print_fn(f"\n  #{rec.rank}  {rec.title}")
        print_fn(f"      confidence {rec.confidence:.2f} [{bar}]")
        print_fn(f"      WHY: {rec.why}")
        if rec.supporting_patterns:
            print_fn(
                f"      PATTERNS CITED: {', '.join(rec.supporting_patterns)}"
            )
        opp = opps.get(rec.opportunity_id)
        if opp and opp.sources:
            for s in opp.sources:
                detail = f" — {s.detail}" if s.detail else ""
                print_fn(f"      SOURCE: {s.name}{detail} ({s.url})")
        print_fn("      ACTION STEPS:")
        for j, step in enumerate(rec.action_steps, 1):
            print_fn(f"        {j}. {step}")
    print_fn("\n  " + "─" * 60)


def interactive_feedback(
    rec: Recommendation,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> Feedback:
    print_fn(f"\n  Feedback for #{rec.rank} \"{rec.title}\"")
    while True:
        raw = input_fn(
            "    [a]ccept / [r]eject / [d]efer (default d): "
        ).strip().lower()
        action = {
            "a": "accepted", "accept": "accepted", "accepted": "accepted",
            "r": "rejected", "reject": "rejected", "rejected": "rejected",
            "d": "deferred", "defer": "deferred", "deferred": "deferred",
            "": "deferred",
        }.get(raw)
        if action:
            break
        print_fn("    Please enter a, r, or d.")
    notes = input_fn("    Notes (optional): ").strip()
    return Feedback(recommendation_id=rec.id, action=action, notes=notes)


def show_learning_summary(
    patterns_before: Dict[str, float],
    patterns_after: Dict[str, object],
    print_fn: Callable[[str], None],
) -> None:
    """'What I learned' summary shown after each cycle."""
    new = [p for pid, p in patterns_after.items() if pid not in patterns_before]
    changed = [
        (p, patterns_before[pid])
        for pid, p in patterns_after.items()
        if pid in patterns_before and abs(p.confidence - patterns_before[pid]) > 1e-9
    ]
    print_fn("\n  ── WHAT I LEARNED THIS CYCLE " + "─" * 32)
    if not new and not changed:
        print_fn("    Nothing new — no feedback moved any conclusions.")
    for p in new:
        print_fn(
            f"    NEW  {p.id}: \"{p.pattern}\" (confidence {p.confidence:.2f})"
        )
    for p, old in changed:
        arrow = "↑" if p.confidence > old else "↓"
        print_fn(
            f"    {arrow}    {p.id}: confidence {old:.2f} → {p.confidence:.2f} "
            f"({p.evidence_count} evidence items)"
        )
    print_fn("  " + "─" * 60)


def render_improvement_metrics(
    history: List[CycleResult],
    print_fn: Callable[[str], None],
) -> None:
    """Run-over-run dashboard proving the system is getting smarter."""
    print_fn("\n  ── IMPROVEMENT METRICS " + "─" * 38)
    if not history:
        print_fn("    No cycles logged yet. Run a cycle first.")
        print_fn("  " + "─" * 60)
        return

    headers = ["metric"] + [f"Run {r.run_number}" for r in history]
    rows = [
        ("Learned patterns", [r.metrics.get("learned_patterns", 0) for r in history]),
        ("Avg confidence", [f"{r.metrics.get('avg_confidence', 0):.2f}" for r in history]),
        (
            "Acceptance rate",
            [
                "—" if r.metrics.get("acceptance_rate") is None
                else f"{r.metrics['acceptance_rate']:.0%}"
                for r in history
            ],
        ),
        ("Duplicates filtered", [r.metrics.get("duplicates_filtered", 0) for r in history]),
        ("Action steps / rec", [r.metrics.get("avg_action_steps", 0) for r in history]),
    ]
    widths = [max(len(headers[0]), max(len(name) for name, _ in rows))] + [
        max(8, len(h)) for h in headers[1:]
    ]
    line = "    " + "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print_fn(line)
    print_fn("    " + "  ".join("-" * w for w in widths))
    for name, values in rows:
        cells = [name.ljust(widths[0])] + [
            str(v).ljust(w) for v, w in zip(values, widths[1:])
        ]
        print_fn("    " + "  ".join(cells))

    first, last = history[0], history[-1]
    if len(history) > 1:
        d_patterns = last.metrics.get("learned_patterns", 0) - first.metrics.get("learned_patterns", 0)
        d_conf = last.metrics.get("avg_confidence", 0) - first.metrics.get("avg_confidence", 0)
        print_fn(
            f"\n    Run {first.run_number} → Run {last.run_number}: "
            f"{d_patterns:+d} patterns, "
            f"{d_conf:+.2f} avg confidence"
        )
    print_fn("  " + "─" * 60)
