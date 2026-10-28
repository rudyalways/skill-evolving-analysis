from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .dashboard import build_dashboard
from matrix_sampler.run_config import default_run_config


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def discover_runs(runs_root: str | Path) -> list[dict[str, Any]]:
    """Discover standalone run workspaces without crossing their I/O boundaries."""
    root = Path(runs_root).resolve()
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for manifest_path in sorted(root.rglob("manifest.json")):
        run = manifest_path.parent
        if not (run / "input").is_dir() or not (run / "output").is_dir():
            continue
        manifest = _read_json(manifest_path)
        target_profile = _read_json(run / "input/target-profile.json")
        config = _read_json(run / "input/run-config.json") or default_run_config(target_profile)
        target = config.get("target") if isinstance(config.get("target"), dict) else {}
        harness = config.get("harness") if isinstance(config.get("harness"), dict) else {}
        sampling = config.get("sampling") if isinstance(config.get("sampling"), dict) else {}
        prompt_sets = [item for item in config.get("prompt_sets") or [] if isinstance(item, dict)]
        tree_path = run / "output/evolution/ood-tree.json"
        history_path = run / "output/evolution/history.jsonl"
        dashboard_path = run / "output/dashboard.html"
        tree = _read_json(tree_path) if tree_path.is_file() else {}
        summary = tree.get("summary") if isinstance(tree.get("summary"), dict) else {}
        steps = 0
        if history_path.is_file():
            steps = sum(1 for line in history_path.read_text().splitlines() if line.strip())
        if tree_path.is_file():
            build_dashboard(
                tree_path,
                dashboard_path,
                f"{manifest.get('run_name') or run.name} · evolution tree",
                history_path if history_path.is_file() else None,
            )
        rows.append(
            {
                "id": run.name,
                "name": str(manifest.get("run_name") or run.name),
                "created_at": str(manifest.get("created_at") or ""),
                "updated_at": str(manifest.get("updated_at") or ""),
                "status": str(manifest.get("status") or "unknown"),
                "run_path": str(run),
                "dashboard_path": dashboard_path if dashboard_path.is_file() else None,
                "has_tree": bool(tree),
                "steps": steps,
                "nodes": int(summary.get("total_nodes") or 0),
                "ood": int(summary.get("ood_count") or 0),
                "depth": int(summary.get("maximum_layer") or 0),
                "scope": str(config.get("evaluation_scope") or "both"),
                "target_model": str(target.get("model") or target.get("id") or "unspecified"),
                "target_adapter": str(target.get("adapter") or "unspecified"),
                "harness": str(harness.get("name") or "unspecified"),
                "harness_profile": str(harness.get("profile") or "default"),
                "samples_per_step": int(sampling.get("samples_per_step") or 0),
                "configured_steps": int(sampling.get("steps") or 0),
                "max_samples": int(sampling.get("max_samples") or 0),
                "prompt_sets": [str(item.get("name") or item.get("id")) for item in prompt_sets],
                "prompt_count": sum(len(item.get("prompts") or []) for item in prompt_sets),
            }
        )
    return sorted(rows, key=lambda row: (row["created_at"], row["id"]), reverse=True)


def build_runs_dashboard(
    runs_root: str | Path,
    output: str | Path | None = None,
    title: str = "Matrix Evolver · runs",
) -> Path:
    """Build a cross-run index whose selected panel is each run's own dashboard."""
    root = Path(runs_root).resolve()
    output_path = Path(output).resolve() if output else root / "runs-dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runs = discover_runs(root)
    encoded = []
    for row in runs:
        item = dict(row)
        dashboard_path = item.pop("dashboard_path")
        item["dashboard_url"] = (
            Path(dashboard_path).resolve().relative_to(output_path.parent).as_posix()
            if dashboard_path and Path(dashboard_path).resolve().is_relative_to(output_path.parent)
            else Path(dashboard_path).resolve().as_uri() if dashboard_path else None
        )
        if item["dashboard_url"] and dashboard_path:
            item["dashboard_url"] += f"?v={Path(dashboard_path).stat().st_mtime_ns}"
        encoded.append(item)
    payload = json.dumps(encoded, separators=(",", ":")).replace("</", "<\\/")
    document = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
:root{--bg:#f4f7fb;--paper:#fff;--ink:#17212b;--muted:#64748b;--line:#d9e2ec;--blue:#2563eb;--green:#159570}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,ui-sans-serif,system-ui,sans-serif}header{padding:22px 28px 17px;background:#fff;border-bottom:1px solid var(--line)}h1{font-size:24px;margin:0 0 4px}.muted{color:var(--muted)}main{display:grid;grid-template-columns:330px minmax(0,1fr);gap:14px;padding:16px 28px 30px}.sidebar,.viewer{background:var(--paper);border:1px solid var(--line);border-radius:13px;box-shadow:0 8px 26px #24364b12}.sidebar{padding:13px;height:calc(100vh - 116px);overflow:auto}.toolbar{display:grid;gap:9px;position:sticky;top:-13px;background:#fff;padding:2px 0 11px;z-index:2}.toolbar input{width:100%;padding:9px 11px;border:1px solid #cbd7e3;border-radius:8px}.run{width:100%;text-align:left;border:1px solid #dce5ee;background:#fff;border-radius:10px;padding:11px;margin:0 0 8px;cursor:pointer;color:var(--ink)}.run:hover,.run.active{border-color:#7da8ed;background:#f3f7ff}.run b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;gap:7px;flex-wrap:wrap;color:var(--muted);font-size:11px;margin-top:6px}.tag{background:#eef2f7;border-radius:999px;padding:2px 6px}.tag.ready{background:#e7f7f0;color:#087458}.viewer{min-width:0;overflow:hidden;height:calc(100vh - 116px)}.viewer-head{height:58px;padding:10px 15px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between}.viewer-head b{display:block}.viewer iframe{border:0;width:100%;height:calc(100% - 58px);background:#fff}.empty{display:grid;place-items:center;height:calc(100% - 58px);padding:28px;color:var(--muted);text-align:center}@media(max-width:900px){main{grid-template-columns:1fr;padding:12px}.sidebar{height:auto;max-height:310px}.viewer{height:760px}}
[hidden]{display:none!important}.viewer{display:flex;flex-direction:column}.viewer-head{height:auto;min-height:58px;gap:14px}.viewer-head>div{min-width:0}.viewer-head #selected-meta{display:block}.viewer iframe{height:auto;flex:1;min-height:0}.empty{height:auto;flex:1}</style></head><body><header><h1>__TITLE__</h1><div class=muted>Each run keeps standalone input/output artifacts and owns its evolution tree.</div></header><main><aside class=sidebar><div class=toolbar><b id=count></b><input id=search type=search placeholder="Search runs…"></div><div id=runs></div></aside><section class=viewer><div class=viewer-head><div><b id=selected-name>Select a run</b><span class=muted id=selected-meta></span></div><a id=open hidden target=_blank>Open tree ↗</a></div><div class=empty id=empty>Select a run to inspect its tree.</div><iframe id=frame title="Selected run evolution tree" hidden></iframe></section></main><script id=data type=application/json>__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent),$=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let selected=location.hash.slice(1)||data.find(x=>x.has_tree)?.id||data[0]?.id||'';
function filtered(){let q=$('#search').value.toLowerCase();return data.filter(run=>JSON.stringify(run).toLowerCase().includes(q))}function cards(){let rows=filtered();$('#count').textContent=`${rows.length} run${rows.length===1?'':'s'}`;$('#runs').innerHTML=rows.map(run=>`<button class="run ${run.id===selected?'active':''}" data-id="${esc(run.id)}"><b>${esc(run.name)}</b><div class=meta><span class="tag ${run.has_tree?'ready':''}">${run.has_tree?'tree ready':'tree pending'}</span><span class=tag>${esc(run.scope)}</span><span>${esc(run.target_model)}</span><span>${esc(run.harness)}</span><span>${run.samples_per_step}×${run.configured_steps} samples</span><span>${run.prompt_count} discovery prompts</span><span>${Math.max(0,run.steps-1)} observed steps</span></div></button>`).join('')||'<p class=muted>No matching runs.</p>';document.querySelectorAll('.run').forEach(button=>button.onclick=()=>select(button.dataset.id))}function select(id){selected=id;location.hash=id;let run=data.find(item=>item.id===id);cards();if(!run)return;$('#selected-name').textContent=run.name;$('#selected-meta').textContent=`${run.scope} · target ${run.target_model} via ${run.target_adapter} · harness ${run.harness}/${run.harness_profile} · ${run.samples_per_step} samples × ${run.configured_steps} configured steps (${run.max_samples} max) · prompt sets: ${run.prompt_sets.join(', ')||'none'} (${run.prompt_count} prompts) · ${run.nodes} nodes · ${run.ood} OOD`;let ready=run.has_tree&&run.dashboard_url;$('#frame').hidden=!ready;$('#empty').hidden=!!ready;$('#open').hidden=!ready;if(ready){$('#frame').src=run.dashboard_url;$('#open').href=run.dashboard_url}else{$('#empty').textContent='This run has no evolution tree yet. Run sampler evolve and sampler dashboard for this run.'}}const uiKey='matrix-runs-ui';let saved={};try{saved=JSON.parse(sessionStorage.getItem(uiKey)||'{}')}catch(_){}$('#search').value=saved.search||'';$('#search').oninput=cards;cards();if(selected)select(selected);requestAnimationFrame(()=>{document.querySelector('.sidebar').scrollTop=saved.sidebarY||0;scrollTo(saved.pageX||0,saved.pageY||0)});addEventListener('beforeunload',()=>sessionStorage.setItem(uiKey,JSON.stringify({search:$('#search').value,sidebarY:document.querySelector('.sidebar').scrollTop,pageX:scrollX,pageY:scrollY})));
</script></body></html>'''
    output_path.write_text(
        document.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)
    )
    return output_path
