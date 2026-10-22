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
        raise SystemExit(f"metrics database does not exist: {database}")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT * FROM pipeline_spans ORDER BY started_at_us"
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise SystemExit(
                f"{database} has no pipeline timing spans; run the pipeline again"
            ) from error
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
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    phases: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        runs[row["run_id"]].append(row)
        phases[(row["phase"], row["category"])].append(
            row["duration_us"] / 1_000_000
        )
    run_summaries: list[dict[str, Any]] = []
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
        timing = _METRICS.summarize_spans(spans)
        active = active_statuses(database, run_id)
        if active:
            end = max(end, int(datetime.now(UTC).timestamp() * 1_000_000))
        run_summaries.append(
            {
                "run_id": run_id,
                "wall_seconds": max((end - start) / 1_000_000, 0),
                "category_seconds": dict(sorted(totals.items())),
                "span_count": len(spans),
                "error_count": sum(row["status"] != "ok" for row in spans),
                "started_at": min(row["started_at"] for row in spans),
                "phases": timing["phases"],
                "spans": timing["spans"],
                "active": active,
                "progress": run_progress(database, run_id, spans),
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
    }


def render(database: Path, output: Path) -> Path:
    rows = load_rows(database)
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
const selectTab = id => {{
  selectedTab = id;
  document.querySelectorAll('.tab').forEach(node =>
    node.classList.toggle('active', node.dataset.tab === id));
  document.querySelectorAll('.panel').forEach(node =>
    node.classList.toggle('active', node.dataset.panel === id));
}};
const phaseTable = rows =>
  `<table><thead><tr><th>Phase</th><th>Category</th><th>Count</th>`+
  `<th>Average</th><th>P50</th><th>P95</th><th>Maximum</th></tr></thead><tbody>`+
  rows.map(row =>
    `<tr><td>${{esc(row.phase)}}</td><td>${{esc(row.category)}}</td><td>${{row.count}}</td>`+
    `<td>${{sec(row.average_seconds)}}</td><td>${{sec(row.p50_seconds)}}</td>`+
    `<td>${{sec(row.p95_seconds)}}</td><td>${{sec(row.maximum_seconds)}}</td></tr>`
  ).join('')+`</tbody></table>`;
const runPanel = run => {{
  const total = Math.max(Object.values(run.category_seconds).reduce((a,b)=>a+b,0), .001);
  const bars = Object.entries(run.category_seconds).map(([category,value]) =>
    `<div class="bar ${{esc(category)}}" style="width:${{Math.min(value/total*100,100)}}%">`+
    `${{esc(category)}} ${{Number(value).toFixed(1)}}s</div>`).join('');
  const active = (run.active || []).map(row =>
    `<div class="active-run"><b>Running now:</b> ${{esc(row.stage)}} · `+
    `${{esc(row.item)}} · <b>${{sec(row.elapsed_seconds)}}</b></div>`).join('');
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
    `<span>live wall <b>${{sec(run.wall_seconds)}}</b></span>`+
    `<span>completed agent sum <b>${{sec(run.category_seconds.llm_agent || 0)}}</b></span>`+
    `<span>deterministic <b>${{sec(run.category_seconds.deterministic || 0)}}</b></span>`+
    `<span>orchestration <b>${{sec(run.category_seconds.orchestration || 0)}}</b></span>`+
    `<span>completed spans <b>${{run.span_count}}</b></span><span>errors <b>${{run.error_count}}</b></span>`+
    `</div><div class="bars">${{bars}}</div>`+
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
        `Run ${{index + 1}}</button>`).join('');
    document.getElementById('panels').innerHTML =
      `<section class="panel" data-panel="total"><section class="card">`+
      `<h2>Total across runs</h2><div class="stats"><span>runs <b>${{data.run_count}}</b></span>`+
      `<span>completed spans <b>${{data.span_count}}</b></span></div>`+
      `<h3>Cross-run phase statistics</h3>${{phaseTable(data.phases)}}</section></section>`+
      data.runs.map((run,index) =>
        `<div class="panel" data-panel="run-${{index + 1}}">${{runPanel(run)}}</div>`
      ).join('');
    document.querySelectorAll('.tab').forEach(node =>
      node.addEventListener('click', () => selectTab(node.dataset.tab)));
    selectTab(selectedTab);
  }} catch (error) {{
    document.getElementById('status').className = 'error';
    document.getElementById('status').textContent = `Refresh failed: ${{error}}`;
  }}
}}
refresh(); setInterval(refresh, {refresh_ms});
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
