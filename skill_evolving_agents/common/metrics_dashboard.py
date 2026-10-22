#!/usr/bin/env python3
"""Render a dependency-free cross-run pipeline timing dashboard."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _load_metrics():
    path = Path(__file__).with_name("pipeline_metrics.py")
    spec = importlib.util.spec_from_file_location(
        "pipeline_metrics_for_dashboard", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


_METRICS = _load_metrics()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def load_rows(database: Path) -> list[dict[str, Any]]:
    if not database.is_file():
        return []
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM pipeline_spans ORDER BY started_at_us"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]


def active_statuses(database: Path, run_id: str) -> list[dict[str, Any]]:
    """Return currently started items with a live elapsed duration."""
    root = database.parent / "runs" / run_id / "run/status"
    if not root.is_dir():
        return []
    now = datetime.now(UTC)
    active: list[dict[str, Any]] = []
    for path in root.glob("*/*.json"):
        try:
            row = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("state") != "started":
            continue
        raw_started = row.get("started_at") or row.get("at")
        try:
            started = datetime.fromisoformat(str(raw_started).replace("Z", "+00:00"))
        except ValueError:
            continue
        active.append(
            {
                "stage": row.get("stage"),
                "item": row.get("item"),
                "started_at": started.isoformat(),
                "elapsed_seconds": max((now - started).total_seconds(), 0),
            }
        )
    return sorted(active, key=lambda row: row["started_at"])


def run_progress(
    database: Path, run_id: str, spans: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build a concise live checklist from runner-owned status records."""
    workspace = database.parent / "runs" / run_id
    status_root = workspace / "run/status"
    documents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if status_root.is_dir():
        for path in status_root.glob("*/*.json"):
            try:
                row = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(row, dict) and isinstance(row.get("stage"), str):
                documents[row["stage"]].append(row)
    queue_phases = {
        "label-traces-cluster": "diagnosis-queue",
        "goal": "goal-queue",
        "optimize": "operation-queue",
    }
    display = [
        ("preprocessing", "Preprocessing"),
        ("label-skills", "LabelSkills"),
        ("label-traces-cluster", "Diagnosis"),
        ("goal", "Goal"),
        ("optimize", "Optimize"),
        ("verifiter", "Verifiter"),
        ("judge", "Judge"),
    ]
    goals = []
    for path in (workspace / "run").glob("*/evolve-goal.json"):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            goals.append(value)
    goal_done = bool(documents.get("goal")) and all(
        row.get("state") == "done" for row in documents["goal"]
    )
    operations_skipped = goal_done and bool(goals) and all(
        not ((value.get("action") or {}).get("ops") or []) for value in goals
    )
    now = datetime.now(UTC)
    stages: list[dict[str, Any]] = []
    for stage, label in display:
        rows = documents.get(stage, [])
        states = [row.get("state") for row in rows]
        if "failed" in states:
            state = "failed"
        elif "started" in states:
            state = "running"
        elif rows and all(value == "done" for value in states):
            state = "done"
        elif operations_skipped and stage in {"optimize", "verifiter", "judge"}:
            state = "skipped"
        else:
            state = "pending"
        completed_ms = sum(
            float(row.get("duration_ms") or 0)
            for row in rows
            if row.get("state") == "done"
        )
        running_seconds = 0.0
        for row in rows:
            if row.get("state") != "started":
                continue
            raw = row.get("started_at") or row.get("at")
            try:
                started = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            running_seconds = max(running_seconds, (now - started).total_seconds())
        queue_phase = queue_phases.get(stage)
        queue_wait_ms = None
        if queue_phase:
            waits = []
            for span in spans:
                if span.get("phase") != queue_phase:
                    continue
                metadata = _METRICS._metadata(span)
                value = metadata.get("queue_wait_ms")
                if isinstance(value, (int, float)):
                    waits.append(float(value))
            if waits:
                queue_wait_ms = round(sum(waits), 3)
        stages.append(
            {
                "stage": stage,
                "label": label,
                "state": state,
                "duration_seconds": round(
                    running_seconds if state == "running" else completed_ms / 1000,
                    3,
                ),
                "items_done": sum(value == "done" for value in states),
                "items_total": len(rows),
                "queue_wait_ms": queue_wait_ms,
            }
        )
    findings = workspace / "traces/derived/findings"
    selected_findings = (
        sum(1 for path in findings.iterdir() if path.is_dir())
        if findings.is_dir()
        else 0
    )
    return {"selected_findings": selected_findings, "stages": stages}


def metrics_payload(database: Path) -> dict[str, Any]:
    rows = load_rows(database)
    runs_root = database.parent / "runs"
    active_by_run = {
        path.name: active
        for path in runs_root.iterdir()
        if path.is_dir() and (active := active_statuses(database, path.name))
    } if runs_root.is_dir() else {}
    excluded_run_ids = sorted(
        {
            str(row["run_id"])
            for row in rows
            if not (runs_root / str(row["run_id"])).is_dir()
        }
    )
    rows = [
        row
        for row in rows
        if (runs_root / str(row["run_id"])).is_dir()
    ]
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phases: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        runs[row["run_id"]].append(row)
        phases[(row["phase"], row["category"])].append(
            row["duration_us"] / 1_000_000
        )
    for run_id in active_by_run:
        runs.setdefault(run_id, [])

    def run_start(item: tuple[str, list[dict[str, Any]]]) -> float:
        run_id, spans = item
        if spans:
            return min(row["started_at_us"] for row in spans)
        return datetime.fromisoformat(
            active_by_run[run_id][0]["started_at"]
        ).timestamp() * 1_000_000

    run_summaries: list[dict[str, Any]] = []
    for run_id, spans in sorted(
        runs.items(),
        key=run_start,
        reverse=True,
    ):
        totals: dict[str, float] = defaultdict(float)
        for row in spans:
            totals[row["category"]] += row["duration_us"] / 1_000_000
        active = active_by_run.get(run_id, [])
        if spans:
            start = min(row["started_at_us"] for row in spans)
            end = max(row["started_at_us"] + row["duration_us"] for row in spans)
            started_at = min(row["started_at"] for row in spans)
        else:
            started_at = active[0]["started_at"]
            start = int(datetime.fromisoformat(started_at).timestamp() * 1_000_000)
            end = start
        timing = _METRICS.summarize_spans(spans)
        if active:
            end = max(end, int(datetime.now(UTC).timestamp() * 1_000_000))
        run_summaries.append(
            {
                "run_id": run_id,
                "wall_seconds": max((end - start) / 1_000_000, 0),
                "category_seconds": dict(sorted(totals.items())),
                "span_count": len(spans),
                "error_count": sum(row["status"] != "ok" for row in spans),
                "started_at": started_at,
                "phases": timing["phases"],
                "spans": timing["spans"],
                "active": active,
                "progress": run_progress(database, run_id, spans),
                "phase_metrics": _METRICS._read_json(
                    runs_root / run_id / "logs/phase-metrics.json"
                ),
            }
        )
    phase_summaries = [
        {
            "phase": phase,
            "category": category,
            "count": len(values),
            "average_seconds": statistics.mean(values),
            "p50_seconds": percentile(values, 0.5),
            "p95_seconds": percentile(values, 0.95),
            "maximum_seconds": max(values),
        }
        for (phase, category), values in sorted(phases.items())
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": str(database),
        "run_count": len(runs),
        "span_count": len(rows),
        "runs": run_summaries,
        "phases": phase_summaries,
        "phase_metrics": _METRICS.aggregate_phase_metrics(runs_root),
        "excluded_database_run_ids": excluded_run_ids,
    }


def render(database: Path, output: Path) -> Path:
    rows = load_rows(database)
    runs_root = database.parent / "runs"
    rows = [
        row
        for row in rows
        if (runs_root / str(row["run_id"])).is_dir()
    ]
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phases: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        runs[row["run_id"]].append(row)
        phases[(row["phase"], row["category"])].append(
            row["duration_us"] / 1_000_000
        )

    run_cards: list[str] = []
    for run_id, spans in sorted(
        runs.items(),
        key=lambda item: min(row["started_at_us"] for row in item[1]),
        reverse=True,
    ):
        totals: dict[str, float] = defaultdict(float)
        for row in spans:
            totals[row["category"]] += row["duration_us"] / 1_000_000
        start = min(row["started_at_us"] for row in spans)
        end = max(row["started_at_us"] + row["duration_us"] for row in spans)
        wall = max((end - start) / 1_000_000, 0.001)
        bars = "".join(
            (
                f'<div class="bar {html.escape(category)}" '
                f'style="width:{min(seconds / max(sum(totals.values()), 0.001) * 100, 100):.2f}%">'
                f"{html.escape(category)} {seconds:.1f}s</div>"
            )
            for category, seconds in sorted(totals.items())
        )
        failures = sum(row["status"] != "ok" for row in spans)
        timing = _METRICS.summarize_spans(spans)
        phase_rows_run = "".join(
            "<tr>"
            f"<td>{html.escape(str(row['phase']))}</td>"
            f"<td>{row['count']}</td>"
            f"<td>{row['sum_seconds']:.3f}s</td>"
            f"<td>{row['wall_seconds']:.3f}s</td>"
            f"<td>{row['peak_concurrency']}</td>"
            f"<td>{row['p50_seconds']:.3f}s</td>"
            f"<td>{row['max_seconds']:.3f}s</td>"
            "</tr>"
            for row in timing["phases"]
        )
        span_rows_run = "".join(
            "<tr>"
            f"<td>{html.escape(str(row['phase']))}</td>"
            f"<td>{html.escape(str(row['item']))}</td>"
            f"<td>{row['duration_ms']:.1f}</td>"
            f"<td>{html.escape(str(row['queue_wait_ms']))}</td>"
            f"<td>{html.escape(str(row['slice_tokens']))}</td>"
            f"<td>{html.escape(str(row['slice_user_turns']))}</td>"
            f"<td>{html.escape(str(row['tool_events']))}</td>"
            f"<td>{html.escape(str(row['decision']))}</td>"
            f"<td>{html.escape(str(row['super_score']))}</td>"
            f"<td>{html.escape(str(row['judge_action']))}</td>"
            f"<td>{html.escape(str(row['status']))}</td>"
            "</tr>"
            for row in timing["spans"]
        )
        run_cards.append(
            f"""
            <section class="card">
              <h2>{html.escape(run_id)}</h2>
              <div class="stats">
                <span>wall <b>{wall:.1f}s</b></span>
                <span>agent sum <b>{totals.get("llm_agent", 0):.1f}s</b></span>
                <span>deterministic <b>{totals.get("deterministic", 0):.3f}s</b></span>
                <span>orchestration <b>{totals.get("orchestration", 0):.3f}s</b></span>
                <span>spans <b>{len(spans)}</b></span>
                <span>errors <b>{failures}</b></span>
              </div>
              <div class="bars">{bars}</div>
              <h3>Phase wall</h3>
              <table><thead><tr><th>Phase</th><th>Count</th><th>Sum</th>
              <th>Wall</th><th>Peak</th><th>P50</th><th>Max</th></tr></thead>
              <tbody>{phase_rows_run}</tbody></table>
              <h3>Spans</h3>
              <table><thead><tr><th>Phase</th><th>Item</th><th>ms</th>
              <th>Queue ms</th><th>Slice tokens</th><th>User turns</th>
              <th>Tool events</th><th>Decision</th><th>Super score</th>
              <th>Judge</th><th>Status</th></tr></thead>
              <tbody>{span_rows_run}</tbody></table>
            </section>
            """
        )

    phase_rows: list[str] = []
    for (phase, category), values in sorted(phases.items()):
        phase_rows.append(
            "<tr>"
            f"<td>{html.escape(phase)}</td>"
            f"<td>{html.escape(category)}</td>"
            f"<td>{len(values)}</td>"
            f"<td>{statistics.mean(values):.3f}s</td>"
            f"<td>{percentile(values, 0.5):.3f}s</td>"
            f"<td>{percentile(values, 0.95):.3f}s</td>"
            f"<td>{max(values):.3f}s</td>"
            "</tr>"
        )

    payload = {
        "database": str(database),
        "run_count": len(runs),
        "span_count": len(rows),
    }
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skill Evolver Pipeline Metrics</title>
<style>
:root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui; }}
body {{ margin: 0; padding: 28px; background: #0b1020; color: #e7eaf0; }}
main {{ max-width: 1200px; margin: auto; }}
h1 {{ margin-bottom: 4px; }} .muted {{ color: #9aa4b8; }}
.card {{ background: #151c30; border: 1px solid #29334d; border-radius: 12px;
  padding: 18px; margin: 16px 0; }}
.stats {{ display: flex; flex-wrap: wrap; gap: 18px; margin-bottom: 12px; }}
.bars {{ display: flex; overflow: hidden; border-radius: 7px; min-height: 32px; }}
.bar {{ min-width: 5px; padding: 7px; white-space: nowrap; overflow: hidden;
  box-sizing: border-box; font-size: 12px; }}
.llm_agent {{ background: #7c5cff; }} .deterministic {{ background: #19a974; }}
.orchestration {{ background: #ec9f05; }}
table {{ width: 100%; border-collapse: collapse; background: #151c30; }}
th, td {{ padding: 10px; border-bottom: 1px solid #29334d; text-align: left; }}
th {{ position: sticky; top: 0; background: #202943; }}
code {{ color: #9fd3ff; }}
</style>
</head>
<body><main>
<h1>Skill Evolver Pipeline Metrics</h1>
<p class="muted">{len(runs)} runs · {len(rows)} spans · <code>{html.escape(str(database))}</code></p>
{''.join(run_cards) or '<p>No spans recorded.</p>'}
<section class="card">
<h2>Cross-run phase statistics</h2>
<table><thead><tr><th>Phase</th><th>Category</th><th>Count</th>
<th>Average</th><th>P50</th><th>P95</th><th>Maximum</th></tr></thead>
<tbody>{''.join(phase_rows)}</tbody></table>
</section>
<script type="application/json" id="dashboard-metadata">{html.escape(json.dumps(payload))}</script>
</main></body></html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document)
    return output


def live_document(refresh_seconds: float) -> str:
    refresh_ms = max(250, round(refresh_seconds * 1000))
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skill Evolver Live Metrics</title>
<style>
:root {{ color-scheme: dark; font-family: ui-sans-serif, system-ui; }}
body {{ margin:0; padding:28px; background:#0b1020; color:#e7eaf0; }}
main {{ max-width:1200px; margin:auto; }}
.muted {{ color:#9aa4b8 }} .error {{ color:#ff8080 }}
.card {{ background:#151c30; border:1px solid #29334d; border-radius:12px;
padding:18px; margin:16px 0; }}
.stats {{ display:flex; flex-wrap:wrap; gap:18px; margin-bottom:12px; }}
.bars {{ display:flex; overflow:hidden; border-radius:7px; min-height:32px; }}
.bar {{ min-width:5px; padding:7px; white-space:nowrap; overflow:hidden;
box-sizing:border-box; font-size:12px; }}
.llm_agent {{ background:#7c5cff }} .deterministic {{ background:#19a974 }}
.orchestration {{ background:#ec9f05 }}
table {{ width:100%; border-collapse:collapse; background:#151c30 }}
th,td {{ padding:10px; border-bottom:1px solid #29334d; text-align:left }}
th {{ background:#202943 }} code {{ color:#9fd3ff }}
.tabs {{ display:flex; gap:8px; flex-wrap:wrap; margin:18px 0 8px }}
.tab {{ border:1px solid #36415f; background:#151c30; color:#cbd3e5;
padding:9px 14px; border-radius:9px; cursor:pointer }}
.tab.active {{ background:#7c5cff; border-color:#9a85ff; color:white }}
.panel {{ display:none }} .panel.active {{ display:block }}
.active-run {{ margin:12px 0; padding:12px; border-radius:8px;
background:#112d29; border:1px solid #1d7668; color:#95eadb }}
.progress {{ margin:14px 0; padding:14px; border-radius:10px; background:#10172a }}
.progress-grid {{ display:grid; grid-template-columns:minmax(150px,1fr) 110px 110px 130px;
gap:7px 16px; align-items:center }}
.state {{ font-weight:700 }} .state.done {{ color:#62d8a8 }}
.state.running {{ color:#f4c15d }} .state.failed {{ color:#ff8080 }}
.state.pending,.state.skipped {{ color:#8f9ab0 }}
.trace-tools {{ position:relative; z-index:31; display:flex; justify-content:space-between; align-items:center; gap:12px }}
.trace-expand {{ border:1px solid #36415f; background:#151c30; color:#cbd3e5;
padding:7px 12px; border-radius:8px; cursor:pointer }}
.trace-shell {{ margin:18px 0; border:1px solid #29334d; border-radius:10px;
overflow:auto; max-height:640px; background:#0c1222 }}
.trace-shell.expanded {{ position:fixed; inset:20px; z-index:30; max-height:none;
margin:0; box-shadow:0 0 0 100vmax #070b16cc }}
.trace-view {{ position:relative; min-width:1100px; padding:8px 0 12px }}
.trace-ruler,.trace-row {{ display:grid; grid-template-columns:128px minmax(860px,1fr);
align-items:stretch }}
.trace-label {{ position:sticky; left:0; z-index:4; overflow:hidden; padding:6px 10px;
background:#0c1222; color:#aeb8cc; font:12px ui-monospace,monospace;
white-space:nowrap; text-overflow:ellipsis }}
.trace-group {{ padding:8px 10px 2px; color:#d7deef; font-size:12px; font-weight:700 }}
.trace-track {{ position:relative; min-height:54px;
background:repeating-linear-gradient(90deg,#243049 0,#243049 1px,transparent 1px,transparent 20%) }}
.trace-time {{ position:absolute; top:1px; color:#9eb0cc; font:10px ui-monospace,monospace;
white-space:nowrap; pointer-events:none; z-index:3 }}
.trace-ticks {{ position:relative; height:22px; color:#8390aa;
font:11px ui-monospace,monospace }}
.trace-tick {{ position:absolute; transform:translateX(-50%); white-space:nowrap }}
.trace-tick:first-child {{ transform:none }}
.trace-tick:last-child {{ transform:translateX(-100%) }}
.trace-block {{ position:absolute; height:22px; min-width:2px; border-radius:5px;
overflow:hidden; padding:1px 5px; box-sizing:border-box; color:white;
font:11px ui-monospace,monospace; white-space:nowrap; z-index:1;
box-shadow:0 0 0 1px #ffffff18 }}
.trace-block.llm_agent {{ background:#7055de }} .trace-block.deterministic {{ background:#15855c }}
.trace-block.orchestration {{ background:#bb7900 }} .trace-block.audit {{ background:#3f8db8 }}
.trace-block.fanout-parent {{ box-shadow:0 0 0 2px #ff8a3d,0 0 10px #ff8a3d66 }}
.trace-block.fanout-parent::after {{ content:''; position:absolute; right:1px; top:8px;
width:6px; height:6px; border-radius:50%; background:#ffd0ad }}
.trace-block.instant {{ width:9px; min-width:9px; height:9px; padding:0; border-radius:1px;
transform:rotate(45deg); transform-origin:center }}
.trace-block.live {{ background:#d39422; box-shadow:0 0 8px #f4c15d;
background-image:linear-gradient(110deg,transparent 25%,#f4c15d88 45%,transparent 65%);
background-size:200% 100%; animation:trace-pulse 1.4s linear infinite }}
.trace-arrows {{ position:absolute; inset:0; width:100%; height:100%;
pointer-events:none; z-index:2; overflow:visible }}
.trace-legend {{ display:flex; gap:16px; color:#9aa4b8; font-size:12px; margin:0 0 8px }}
.trace-legend i {{ display:inline-block; width:28px; height:4px; margin-right:6px; vertical-align:middle; border-radius:2px }}
.trace-legend .chain {{ background:#f4f7ff }} .trace-legend .fanout {{ background:#ff8a3d }}
.trace-legend .merge {{ background:#3dffa8 }}
@keyframes trace-pulse {{ to {{ background-position:-200% 0 }} }}
@media (max-width:700px) {{ .progress-grid {{ grid-template-columns:1fr 90px }} }}
</style></head><body><main>
<h1>Skill Evolver Live Metrics</h1>
<p id="status" class="muted">Connecting…</p>
<nav id="tabs" class="tabs"></nav>
<div id="panels"></div>
<script>
const esc = value => String(value).replace(/[&<>"']/g, c =>
  ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c]);
const sec = value => `${{Number(value).toFixed(3)}}s`;
let selectedTab = 'total';
let expandedRun = '';
const applyExpandedTrace = () => {{
  document.querySelectorAll('.trace-shell').forEach(shell =>
    shell.classList.toggle('expanded', shell.dataset.run === expandedRun));
  document.querySelectorAll('[data-trace-expand]').forEach(button => {{
    button.textContent = button.dataset.traceExpand === expandedRun ? 'Close' : 'Expand';
  }});
}};
document.addEventListener('click', event => {{
  const button = event.target.closest('[data-trace-expand]');
  if (!button) return;
  expandedRun = expandedRun === button.dataset.traceExpand ? '' : button.dataset.traceExpand;
  applyExpandedTrace();
  tickTraces();
}});
const selectTab = id => {{
  selectedTab = id;
  document.querySelectorAll('.tab').forEach(node =>
    node.classList.toggle('active', node.dataset.tab === id));
  document.querySelectorAll('.panel').forEach(node =>
    node.classList.toggle('active', node.dataset.panel === id));
  if (typeof tickTraces === 'function') tickTraces();
}};
const phaseTable = rows =>
  `<table><thead><tr><th>Phase</th><th>Category</th><th>Count</th>`+
  `<th>Average</th><th>P50</th><th>P95</th><th>Maximum</th></tr></thead><tbody>`+
  rows.map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{esc(row.category)}}</td><td>${{row.count}}</td>`+
    `<td>${{sec(row.average_seconds)}}</td><td>${{sec(row.p50_seconds)}}</td>`+
    `<td>${{sec(row.p95_seconds)}}</td><td>${{sec(row.maximum_seconds)}}</td></tr>`
  ).join('')+`</tbody></table>`;
const TRUNK = ['normalize-traces','detect-signals','deduplicate-and-cluster',
  'validate-preprocessing','label-skills','validate-skill-labels'];
const GRAPH = new Set([...TRUNK, 'label-traces-cluster','goal','reduce-goals',
  'optimize','verifiter','judge']);
const PHASE_COLORS = {{
  'normalize-traces':'#167d68', 'detect-signals':'#198b72',
  'deduplicate-and-cluster':'#1d997e', 'validate-preprocessing':'#25a889',
  'label-skills':'#377bd6', 'validate-skill-labels':'#4c8de0',
  'label-traces-cluster':'#7055de', 'goal':'#9b5de5',
  'reduce-goals':'#c58a18', 'optimize':'#df6f32',
  'verifiter':'#d84f8b', 'judge':'#2ca56f'
}};
const phaseColor = phase => PHASE_COLORS[phase] || '';
const traceLane = (phase, item, runId) => {{
  if (TRUNK.includes(phase) || phase === 'reduce-goals' || item === runId ||
      phase === 'preprocessing' || phase === 'label-skills')
    return {{id:'pipeline', kind:'pipeline', title:'pipeline', sortKey:'0'}};
  const rest = item.startsWith(`${{runId}}-`) ? item.slice(runId.length + 1) : item;
  const match = rest.match(/(sig-[0-9a-f]+)(?:-op-(\\d+))?/);
  if (!match) return {{id:'pipeline', kind:'pipeline', title:'pipeline', sortKey:'0'}};
  const short = match[1].slice(4, 12);
  const opPhases = ['edit-decision','operation-queue','optimize','verifiter',
    'judge','judge-decision','merge-operation'];
  if (match[2] || opPhases.includes(phase)) {{
    const op = match[2] || '1';
    return {{id:`op:${{match[1]}}:${{op}}`, kind:'op', title:`${{short}}/op-${{op}}`,
      sortKey:`1/${{match[1]}}/op-${{op.padStart(4, '0')}}`}};
  }}
  return {{id:`finding:${{match[1]}}`, kind:'finding', title:short,
    sortKey:`1/${{match[1]}}`}};
}};
const tracePanel = run => {{
  const markerId = `trace-arrow-${{run.run_id.replace(/[^A-Za-z0-9_-]/g, '')}}`;
  const seen = new Set();
  const slices = [];
  (run.spans || []).forEach(row => {{
    const start = Date.parse(row.started_at);
    if (!Number.isFinite(start)) return;
    const lane = traceLane(row.phase, String(row.item), run.run_id);
    const instant = row.category === 'audit' || Number(row.duration_ms) === 0;
    const slice = {{id:`${{markerId}}-${{slices.length}}`, phase:row.phase, item:String(row.item),
      category:row.category, start, end:start + Number(row.duration_ms),
      live:false, instant, lane}};
    seen.add(`${{slice.phase}}|${{slice.item}}`);
    slices.push(slice);
  }});
  (run.active || []).forEach(row => {{
    const start = Date.parse(row.started_at);
    const phase = String(row.stage);
    const item = String(row.item);
    if (!Number.isFinite(start) || seen.has(`${{phase}}|${{item}}`)) return;
    slices.push({{id:`${{markerId}}-${{slices.length}}`, phase, item, category:'live', start,
      end:null, live:true, instant:false, lane:traceLane(phase, item, run.run_id)}});
  }});
  if (!slices.length) return '';
  const lanes = new Map();
  slices.forEach(slice => {{
    if (!lanes.has(slice.lane.id)) lanes.set(slice.lane.id, {{...slice.lane, slices:[]}});
    lanes.get(slice.lane.id).slices.push(slice);
  }});
  const ordered = [...lanes.values()];
  const byKind = kind => ordered.filter(lane => lane.kind === kind);
  const edges = [];
  const link = (source, target, kind) => {{
    if (source && target && source.id !== target.id)
      edges.push({{from:source.id, to:target.id, kind}});
  }};
  const graphNodes = rows => rows.filter(slice => GRAPH.has(slice.phase) || slice.live);
  const durationOf = slice => (slice.end ?? slice.start) - slice.start;
  const shown = rows => graphNodes(rows).filter(slice =>
    slice.live || durationOf(slice) >= 800);
  const chain = rows => {{
    const nodes = shown(rows);
    nodes.forEach((row, index) => link(row, nodes[index + 1], 'depends'));
  }};
  const pipeline = byKind('pipeline')[0];
  const trunk = (pipeline?.slices || []).filter(slice => TRUNK.includes(slice.phase))
    .sort((a, b) => a.start - b.start);
  const reduce = (pipeline?.slices || []).find(slice => slice.phase === 'reduce-goals');
  ordered.forEach(lane => lane.slices.sort((a, b) =>
    a.start - b.start || String(a.item).localeCompare(String(b.item))));
  chain(trunk);
  const displayLanes = [...ordered].sort((a, b) =>
    (a.sortKey || a.id).localeCompare(b.sortKey || b.id) || a.id.localeCompare(b.id));
  const findings = displayLanes.filter(lane => lane.kind === 'finding');
  const ops = displayLanes.filter(lane => lane.kind === 'op');
  displayLanes.forEach((lane, row) =>
    lane.slices.forEach(slice => {{ slice.row = row; }}));
  findings.forEach(lane => chain(lane.slices));
  ops.forEach(lane => chain(lane.slices));
  const fork = shown(trunk).at(-1);
  const firstShown = lane => shown(lane.slices)[0];
  const lastShown = lane => shown(lane.slices).at(-1);
  const reduceShown = reduce && durationOf(reduce) >= 800 ? reduce : null;
  findings.forEach(lane =>
    link(fork, firstShown(lane), findings.length > 1 ? 'fanout' : 'depends'));
  if (reduceShown) {{
    findings.forEach(lane =>
      link(lastShown(lane), reduceShown, findings.length > 1 ? 'merge' : 'depends'));
    ops.forEach(lane =>
      link(reduceShown, firstShown(lane), ops.length > 1 ? 'fanout' : 'depends'));
  }} else {{
    findings.forEach(lane => {{
      const sig = lane.id.replace(/^finding:/, '');
      ops.filter(op => op.id.startsWith(`op:${{sig}}:`)).forEach(op =>
        link(lastShown(lane), firstShown(op), 'merge'));
    }});
  }}
  const fanoutSources = new Set(
    edges.filter(edge => edge.kind === 'fanout').map(edge => edge.from)
  );
  const origin = Math.min(...slices.map(slice => slice.start));
  const completedEnds = slices.filter(slice => slice.end != null).map(slice => slice.end);
  const staticEnd = Math.max(origin + 1, ...completedEnds);
  const renderRow = (lane, row) => {{
    const rowSlices = lane.slices;
    const title = lane.kind === 'pipeline' ? 'pipeline' : lane.title;
    const blocks = rowSlices.map(slice =>
      `<div id="${{slice.id}}" class="trace-block ${{esc(slice.category)}}${{slice.live ? ' live' : ''}}${{slice.instant ? ' instant' : ''}}${{fanoutSources.has(slice.id) ? ' fanout-parent' : ''}}" `+
      `data-start="${{slice.start}}" data-end="${{slice.end == null ? '' : slice.end}}" `+
      `data-phase="${{esc(slice.phase)}}" data-item="${{esc(slice.item)}}" `+
      `data-sub="0" data-instant="${{slice.instant ? '1' : '0'}}" `+
      `data-graph="${{GRAPH.has(slice.phase) || slice.live ? '1' : '0'}}" `+
      `${{!slice.live && phaseColor(slice.phase) ? `style="background:${{phaseColor(slice.phase)}}"` : ''}} `+
      `title="${{esc(slice.phase)}}">${{esc(slice.phase)}}</div>`
    ).join('');
    const times = rowSlices.filter(slice =>
      (GRAPH.has(slice.phase) || slice.live) && !slice.instant).map(slice =>
      `<div class="trace-time" data-for="${{slice.id}}"></div>`).join('');
    return `<div class="trace-row"><div class="trace-label" title="${{esc(title)}}">`+
      `${{esc(title)}}</div><div class="trace-track">${{times}}${{blocks}}</div></div>`;
  }};
  const arrowColor = kind => kind === 'merge' ? '#3dffa8' : kind === 'fanout' ? '#ff8a3d' : '#f4f7ff';
  const arrowWidth = kind => kind === 'depends' ? 2.6 : 3.25;
  const arrows = edges.map(edge =>
    `<path data-from="${{edge.from}}" data-to="${{edge.to}}" data-kind="${{edge.kind}}" `+
    `fill="none" stroke="${{arrowColor(edge.kind)}}" stroke-width="${{arrowWidth(edge.kind)}}" `+
    `stroke-linecap="round" stroke-linejoin="round" `+
    `marker-end="url(#${{markerId}}-${{edge.kind}})"/>`
  ).join('');
  const markers = ['depends', 'fanout', 'merge'].map(kind =>
    `<marker id="${{markerId}}-${{kind}}" viewBox="0 0 10 10" refX="10" refY="5" `+
    `markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" orient="auto">`+
    `<path d="M 0 1 L 10 5 L 0 9 z" fill="${{arrowColor(kind)}}"/></marker>`
  ).join('');
  return `<div class="trace-tools"><h3>Live trace</h3><div class="trace-legend">`+
    `<span><i class="chain"></i>depends</span><span><i class="fanout"></i>fanout</span>`+
    `<span><i class="merge"></i>merge</span>`+
    `<button type="button" class="trace-expand" data-trace-expand="${{esc(run.run_id)}}">Expand</button>`+
    `</div></div>`+
    `<div class="trace-shell" data-run="${{esc(run.run_id)}}"><div class="trace-view" data-trace-origin="${{origin}}" `+
    `data-trace-static-end="${{staticEnd}}" data-trace-active="${{slices.some(slice => slice.live) ? '1' : '0'}}">`+
    `<div class="trace-ruler"><div class="trace-label">start →</div><div class="trace-ticks">`+
    `${{[0,20,40,60,80,100].map(value =>
      `<span class="trace-tick" data-fraction="${{value/100}}" style="left:${{value}}%"></span>`
    ).join('')}}</div></div>`+
    `${{displayLanes.map((lane, row) => renderRow(lane, row)).join('')}}`+
    `<svg class="trace-arrows"><defs>${{markers}}</defs>${{arrows}}</svg>`+
    `</div></div>`;
}};
const tickTraces = () => {{
  const now = Date.now();
  document.querySelectorAll('[data-live-elapsed-start]').forEach(node => {{
    node.textContent = sec(Math.max(0, now-Number(node.dataset.liveElapsedStart))/1000);
  }});
  document.querySelectorAll('[data-live-wall-start]').forEach(node => {{
    node.textContent = sec(Math.max(0, now-Number(node.dataset.liveWallStart))/1000);
  }});
  document.querySelectorAll('[data-trace-origin]').forEach(view => {{
    const origin = Number(view.dataset.traceOrigin);
    const end = view.dataset.traceActive === '1'
      ? Math.max(now, Number(view.dataset.traceStaticEnd))
      : Number(view.dataset.traceStaticEnd);
    const range = Math.max(end-origin, 1);
    view.querySelectorAll('.trace-tick').forEach(tick => {{
      tick.textContent = sec(range * Number(tick.dataset.fraction) / 1000);
    }});
    view.querySelectorAll('.trace-block').forEach(block => {{
      const start = Number(block.dataset.start);
      const blockEnd = block.dataset.end ? Number(block.dataset.end) : now;
      const track = block.parentElement.getBoundingClientRect().width || 1;
      const graph = block.dataset.graph !== '0';
      block.style.top = graph ? '16px' : '4px';
      const rawLeft = Math.max(0, (start - origin) / range) * track;
      const started = Math.max(0, (start - origin) / 1000);
      const duration = Math.max(0, (blockEnd - start) / 1000);
      const phase = block.dataset.phase || '';
      const clock = new Date(start).toLocaleTimeString([], {{
        hour:'2-digit', minute:'2-digit', second:'2-digit'}});
      block.title = `${{phase}} · start +${{sec(started)}} (${{clock}}) · ${{sec(duration)}}`+
        (block.dataset.item ? ` · ${{block.dataset.item}}` : '');
      if (block.dataset.instant === '1') {{
        block.style.left = `${{rawLeft}}px`;
        block.style.width = '9px';
      }} else {{
        const rawWidth = Math.max(2, (blockEnd - start) / range * track);
        const trim = graph && rawWidth >= 36 ? 8 : 0;
        block.style.left = `${{rawLeft}}px`;
        block.style.width = `${{Math.max(2, rawWidth - trim)}}px`;
        if (!block.dataset.end) block.textContent =
          `${{phase}} +${{started.toFixed(1)}}s · ${{sec(duration)}}`;
      }}
    }});
    view.querySelectorAll('.trace-time').forEach(label => {{
      const block = view.querySelector(`#${{label.dataset.for}}`);
      if (!block) return;
      const start = Number(block.dataset.start);
      label.style.left = block.style.left;
      label.textContent = `+${{Math.max(0, (start - origin) / 1000).toFixed(1)}}s`;
    }});
    view.querySelectorAll('.trace-track').forEach(track => {{
      let last = -Infinity;
      [...track.querySelectorAll('.trace-time')]
        .sort((a, b) => parseFloat(a.style.left) - parseFloat(b.style.left))
        .forEach(label => {{
          const x = parseFloat(label.style.left);
          const hide = x < last + 46;
          label.style.visibility = hide ? 'hidden' : 'visible';
          if (!hide) last = x;
        }});
    }});
    const root = view.getBoundingClientRect();
    if (!root.width) return;
    view.querySelectorAll('.trace-arrows path').forEach(path => {{
      const source = view.querySelector(`#${{path.dataset.from}}`);
      const target = view.querySelector(`#${{path.dataset.to}}`);
      if (!source || !target) return;
      const from = source.getBoundingClientRect();
      const to = target.getBoundingClientRect();
      const x1 = from.right - root.left + 2;
      const y1 = from.top + from.height / 2 - root.top;
      const x2 = to.left - root.left - 3;
      const y2 = to.top + to.height / 2 - root.top;
      const room = x2 - x1;
      if (room < 10 && Math.abs(y1 - y2) < 8) {{
        path.setAttribute('d', '');
        return;
      }}
      if (room < 10) {{
        const knee = x1 + Math.max(4, Math.min(room, 8));
        path.setAttribute('d', `M ${{x1}} ${{y1}} H ${{knee}} V ${{y2}} H ${{Math.max(x2, knee)}}`);
        return;
      }}
      const rail = x1 + Math.min(room * 0.5, 36);
      path.setAttribute('d', Math.abs(y1 - y2) < 8
        ? `M ${{x1}} ${{y1}} H ${{x2}}`
        : `M ${{x1}} ${{y1}} H ${{rail}} V ${{y2}} H ${{x2}}`);
    }});
  }});
}};
const runPanel = run => {{
  const total = Math.max(Object.values(run.category_seconds).reduce((a,b)=>a+b,0), .001);
  const bars = Object.entries(run.category_seconds).map(([category,value]) =>
    `<div class="bar ${{esc(category)}}" style="width:${{Math.min(value/total*100,100)}}%">`+
    `${{esc(category)}} ${{Number(value).toFixed(1)}}s</div>`).join('');
  const active = (run.active || []).map(row =>
    `<div class="active-run"><b>Running now:</b> ${{esc(row.stage)}} · `+
    `${{esc(row.item)}} · <b data-live-elapsed-start="${{Date.parse(row.started_at)}}">`+
    `${{sec(row.elapsed_seconds)}}</b></div>`).join('');
  const progress = run.progress || {{selected_findings:0, stages:[]}};
  const progressRows = (progress.stages || []).map(row => {{
    const duration = row.state === 'pending' || row.state === 'skipped'
      ? '—' : sec(row.duration_seconds);
    const queue = row.queue_wait_ms == null ? '—' : `${{Number(row.queue_wait_ms).toFixed(2)}}ms`;
    const items = row.items_total ? `${{row.items_done}}/${{row.items_total}} items` : '—';
    return `<span>${{esc(row.label)}}</span>`+
      `<span class="state ${{esc(row.state)}}">${{esc(row.state)}}</span>`+
      `<span>${{duration}}</span><span>${{items}} · queue ${{queue}}</span>`;
  }}).join('');
  const phaseRows = (run.phases || []).map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{row.count}}</td>`+
    `<td>${{sec(row.sum_seconds)}}</td><td>${{sec(row.wall_seconds)}}</td>`+
    `<td>${{row.peak_concurrency}}</td><td>${{sec(row.p50_seconds)}}</td>`+
    `<td>${{sec(row.max_seconds)}}</td></tr>`).join('');
  const spanRows = (run.spans || []).map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{esc(row.item)}}</td>`+
    `<td>${{Number(row.duration_ms).toFixed(1)}}</td>`+
    `<td>${{esc(row.queue_wait_ms)}}</td><td>${{esc(row.slice_tokens)}}</td>`+
    `<td>${{esc(row.slice_user_turns)}}</td><td>${{esc(row.tool_events)}}</td>`+
    `<td>${{esc(row.decision)}}</td><td>${{esc(row.super_score)}}</td>`+
    `<td>${{esc(row.judge_action)}}</td><td>${{esc(row.status)}}</td></tr>`).join('');
  return `<section class="card"><h2>${{esc(run.run_id)}}</h2>${{active}}`+
    `<section class="progress"><h3>Current progress</h3>`+
    `<p>Selected findings: <b>${{progress.selected_findings}}</b></p>`+
    `<div class="progress-grid">${{progressRows}}</div></section><div class="stats">`+
    `<span>live wall <b${{(run.active || []).length ? ` data-live-wall-start="${{Date.parse(run.started_at)}}"` : ''}}>`+
    `${{sec(run.wall_seconds)}}</b></span>`+
    `<span>completed agent sum <b>${{sec(run.category_seconds.llm_agent || 0)}}</b></span>`+
    `<span>deterministic <b>${{sec(run.category_seconds.deterministic || 0)}}</b></span>`+
    `<span>orchestration <b>${{sec(run.category_seconds.orchestration || 0)}}</b></span>`+
    `<span>completed spans <b>${{run.span_count}}</b></span><span>errors <b>${{run.error_count}}</b></span>`+
    `</div><div class="bars">${{bars}}</div>`+
    tracePanel(run)+
    `<h3>Completed phase spans</h3><table><thead><tr><th>Phase</th><th>Count</th><th>Sum</th>`+
    `<th>Wall</th><th>Peak</th><th>P50</th><th>Max</th></tr></thead>`+
    `<tbody>${{phaseRows}}</tbody></table>`+
    `<h3>Completed spans</h3><table><thead><tr><th>Phase</th><th>Item</th><th>ms</th>`+
    `<th>Queue ms</th><th>Slice tokens</th><th>User turns</th>`+
    `<th>Tool events</th><th>Decision</th><th>Super score</th>`+
    `<th>Judge</th><th>Status</th></tr></thead>`+
    `<tbody>${{spanRows}}</tbody></table></section>`;
}};
async function refresh() {{
  try {{
    const response = await fetch('/api/metrics', {{cache:'no-store'}});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    const data = await response.json();
    document.getElementById('status').className = 'muted';
    document.getElementById('status').innerHTML =
      `${{data.run_count}} runs · ${{data.span_count}} spans · refreshed ${{esc(data.generated_at)}} · <code>${{esc(data.database)}}</code>`;
    const ids = ['total', ...data.runs.map((_, index) => `run-${{index + 1}}`)];
    if (!ids.includes(selectedTab)) selectedTab = 'total';
    document.getElementById('tabs').innerHTML =
      `<button class="tab" data-tab="total">Total</button>`+
      data.runs.map((run,index) =>
        `<button class="tab" data-tab="run-${{index + 1}}" title="${{esc(run.run_id)}}">`+
        `${{esc(run.run_id)}}</button>`).join('');
    const empty = data.run_count ? '' : `<p class="muted">No runs recorded.</p>`;
    document.getElementById('panels').innerHTML =
      `<section class="panel" data-panel="total"><section class="card">`+
      `<h2>Total across runs</h2>${{empty}}<div class="stats"><span>runs <b>${{data.run_count}}</b></span>`+
      `<span>completed spans <b>${{data.span_count}}</b></span></div>`+
      `<h3>Cross-run phase statistics</h3>${{phaseTable(data.phases)}}</section></section>`+
      data.runs.map((run,index) =>
        `<div class="panel" data-panel="run-${{index + 1}}">${{runPanel(run)}}</div>`
      ).join('');
    document.querySelectorAll('.tab').forEach(node =>
      node.addEventListener('click', () => selectTab(node.dataset.tab)));
    selectTab(selectedTab);
    applyExpandedTrace();
    tickTraces();
  }} catch (error) {{
    document.getElementById('status').className = 'error';
    document.getElementById('status').textContent = `Refresh failed: ${{error}}`;
  }}
}}
refresh(); setInterval(refresh, {refresh_ms}); setInterval(tickTraces, 100);
</script></main></body></html>"""


def make_server(
    database: Path,
    host: str,
    port: int,
    refresh_seconds: float = 2.0,
) -> ThreadingHTTPServer:
    document = live_document(refresh_seconds).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/" or self.path.startswith("/index.html"):
                self._reply(200, "text/html; charset=utf-8", document)
                return
            if self.path.startswith("/api/metrics"):
                try:
                    payload = json.dumps(
                        metrics_payload(database), ensure_ascii=False
                    ).encode()
                except (OSError, sqlite3.Error, SystemExit) as error:
                    self._reply(
                        500,
                        "application/json",
                        json.dumps({"error": str(error)}).encode(),
                    )
                    return
                self._reply(200, "application/json", payload)
                return
            if self.path == "/health":
                self._reply(200, "application/json", b'{"status":"ok"}')
                return
            self._reply(404, "text/plain; charset=utf-8", b"not found")

        def _reply(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=root / "workspace/metrics.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "workspace/metrics-dashboard.html",
    )
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-seconds", type=float, default=2.0)
    args = parser.parse_args()
    database = args.database.resolve()
    if args.snapshot:
        print(render(database, args.output.resolve()))
        return
    server = make_server(
        database, args.host, args.port, args.refresh_seconds
    )
    print(f"http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
