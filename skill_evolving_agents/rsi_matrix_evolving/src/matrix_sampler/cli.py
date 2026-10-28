from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from matrix_sampler.adapters.fake import FakeTargetAdapter
from matrix_sampler.adapters.replay import TraceReplayAdapter
from matrix_sampler.adapters.dsh import DSHAdapter
from matrix_sampler.mining.traces import ingest
from matrix_sampler.reporting.report import build_report
from matrix_sampler.reporting.dashboard import append_tree_history, build_dashboard
from matrix_sampler.reporting.run_dashboard import build_runs_dashboard
from matrix_sampler.runners.batch import run_plan
from matrix_sampler.sampling.planner import plan
from matrix_sampler.scenarios.registry import load, validate
from matrix_sampler.storage.sqlite import Store
from matrix_sampler.workspace import RunWorkspace
from matrix_sampler.run_config import builtin_prompt_sets, default_run_config, prompt_set_scenarios, validate_run_config
from matrix_sampler.evolution import EvolutionConfig, OODTree, observations_from_store, write_tree


def _json(path): return json.loads(Path(path).read_text())
def _hash(value): return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sampler")
    sub = parser.add_subparsers(dest="command", required=True)
    workspace = sub.add_parser("workspace").add_subparsers(dest="action", required=True)
    p = workspace.add_parser("init"); p.add_argument("name"); p.add_argument("--runs-root", default="runs"); p.add_argument("--scope", choices=["target", "harness", "both"], default="both"); p.add_argument("--target-model"); p.add_argument("--target-adapter"); p.add_argument("--harness", default="matrix-sampler"); p.add_argument("--harness-profile", default="default"); p.add_argument("--samples-per-step", type=int, default=25); p.add_argument("--steps", type=int, default=4); p.add_argument("--max-samples", type=int, default=100); p.add_argument("--prompt-set", action="append", choices=["capability-discovery", "limitations", "harness-awareness"]); p.add_argument("--no-prompt-sets", action="store_true", help="Use only the bootstrap scenario registry"); p.add_argument("--prompt-set-file", action="append", default=[]); p.add_argument("--scenarios", default="scenarios/bootstrap/scenarios.json", help="Bootstrap scenario registry copied into this run")
    p = workspace.add_parser("show"); p.add_argument("run_dir")
    target = sub.add_parser("target").add_subparsers(dest="action", required=True); target.add_parser("init")
    scenarios = sub.add_parser("scenarios").add_subparsers(dest="action", required=True); scenarios.add_parser("validate")
    traces = sub.add_parser("traces").add_subparsers(dest="action", required=True); p = traces.add_parser("ingest"); p.add_argument("path"); p.add_argument("--run-dir")
    sub.add_parser("matrix").add_subparsers(dest="action", required=True).add_parser("build")
    p = sub.add_parser("plan"); p.add_argument("--budget-usd", type=float, default=5); p.add_argument("--max-samples", type=int); p.add_argument("--strategy"); p.add_argument("--seed", type=int); p.add_argument("--output", default=None); p.add_argument("--run-dir")
    p = sub.add_parser("run"); p.add_argument("plan", nargs="?"); p.add_argument("--run-dir"); p.add_argument("--concurrency", type=int); p.add_argument("--adapter", choices=["fake", "replay", "dsh"]); p.add_argument("--trace"); p.add_argument("--dsh-patch")
    p = sub.add_parser("campaign"); p.add_argument("--run-dir", required=True); p.add_argument("--dsh-patch", required=True); p.add_argument("--concurrency", type=int); p.add_argument("--timeout", type=float, default=45)
    p = sub.add_parser("evaluate"); p.add_argument("run_or_batch_id")
    p = sub.add_parser("report"); p.add_argument("--target", default="draft-unknown-target"); p.add_argument("--output", default=None); p.add_argument("--run-dir")
    p = sub.add_parser("evolve"); p.add_argument("--run-dir", required=True); p.add_argument("--max-layer", type=int, choices=[1, 2, 3]); p.add_argument("--branch-factor", type=int); p.add_argument("--min-parent-attempts", type=int, default=0); p.add_argument("--max-nodes", type=int)
    p = sub.add_parser("dashboard"); dashboard_source = p.add_mutually_exclusive_group(required=True); dashboard_source.add_argument("--run-dir"); dashboard_source.add_argument("--runs-root"); p.add_argument("--output", default=None); p.add_argument("--title", default="Matrix Evolver")
    agents = sub.add_parser("agents").add_subparsers(dest="action", required=True)
    p = agents.add_parser("run"); p.add_argument("--run-dir", required=True); p.add_argument("--max-layer", type=int, choices=[1,2,3], default=3); p.add_argument("--branch-factor", type=int, default=2); p.add_argument("--max-nodes", type=int, default=500)
    args = parser.parse_args(argv)
    run_workspace = RunWorkspace(args.run_dir).require() if getattr(args, "run_dir", None) else None
    run_config = _json(run_workspace.input / "run-config.json") if run_workspace and (run_workspace.input / "run-config.json").is_file() else {}
    store = Store(run_workspace.database if run_workspace else ".sampler/sampler.db")
    if args.command == "workspace":
        if args.action == "init":
            config = default_run_config(_json("target-profile.json")); config["evaluation_scope"] = args.scope; config["target"]["model"] = args.target_model; config["target"]["adapter"] = args.target_adapter or config["target"]["adapter"]; config["harness"] = {"name": args.harness, "profile": args.harness_profile}; config["sampling"]["samples_per_step"] = args.samples_per_step; config["sampling"]["steps"] = args.steps; config["sampling"]["max_samples"] = args.max_samples; config["prompt_sets"] = [] if args.no_prompt_sets else builtin_prompt_sets(args.prompt_set)
            for prompt_file in args.prompt_set_file:
                custom = _json(prompt_file); config["prompt_sets"].extend(custom if isinstance(custom, list) else custom.get("prompt_sets", [custom]))
            created = RunWorkspace.create(args.runs_root, args.name, "target-profile.json", args.scenarios, ["configs/default.yaml", "configs/sampling-policy.yaml"], validate_run_config(config))
            print(created.root)
        else:
            selected = RunWorkspace(args.run_dir).require()
            print(selected.manifest.read_text(), end="")
    elif args.command == "target":
        profile = _json("target-profile.json"); store.put_json("targets", "target_id", profile["target_id"], "profile_json", profile); print("initialized", profile["target_id"])
    elif args.command == "scenarios":
        errors = validate("scenarios/bootstrap/scenarios.json"); print(f"validated {len(load())} scenarios" if not errors else "\n".join(errors)); raise SystemExit(bool(errors))
    elif args.command == "traces":
        source = run_workspace.snapshot_trace(args.path) if run_workspace else Path(args.path)
        summary = ingest(source, store); out = run_workspace.output / "trace-summary.json" if run_workspace else Path(".sampler/trace-summary.json"); out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(summary, indent=2));
        if run_workspace: run_workspace.update_status("inputs_ready", trace_summary=str(out.relative_to(run_workspace.root)))
        print(out)
    elif args.command == "matrix":
        print(json.dumps(store.counts(), indent=2))
    elif args.command == "plan":
        profile_path = run_workspace.input / "target-profile.json" if run_workspace else Path("target-profile.json")
        scenario_path = run_workspace.input / "scenarios.json" if run_workspace else Path("scenarios/bootstrap/scenarios.json")
        sampling_config = run_config.get("sampling", {}); max_samples = args.max_samples or sampling_config.get("max_samples") or 30; seed = args.seed or sampling_config.get("seed") or 184221; strategy = args.strategy or sampling_config.get("strategy") or "thompson-diverse"
        profile = _json(profile_path); planning_scenarios = load(scenario_path) + prompt_set_scenarios(run_config); result = plan(planning_scenarios, max_samples, seed, _hash(profile), strategy); result["budget_usd"] = args.budget_usd; result["prompt_sets"] = [item.get("id") for item in run_config.get("prompt_sets", [])]
        for sample in result["samples"]: store.add_sample(sample)
        out = Path(args.output) if args.output else (run_workspace.input / "plan.json" if run_workspace else Path(".sampler/plan.json")); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, indent=2));
        if run_workspace: run_workspace.update_status("planned", plan=str(out.relative_to(run_workspace.root)), plan_id=result["plan_id"], plan_sha256=hashlib.sha256(out.read_bytes()).hexdigest())
        print(out)
    elif args.command == "run":
        plan_path = Path(args.plan) if args.plan else (run_workspace.input / "plan.json" if run_workspace else None)
        if plan_path is None: parser.error("run requires PLAN or --run-dir")
        profile_path = run_workspace.input / "target-profile.json" if run_workspace else Path("target-profile.json")
        trace = run_workspace.snapshot_trace(args.trace) if run_workspace and args.trace else args.trace
        sampling_config = run_config.get("sampling", {}); target_config = run_config.get("target", {}); adapter_name = args.adapter or target_config.get("adapter") or "fake"; concurrency = args.concurrency or sampling_config.get("concurrency") or 4
        batch = _json(plan_path); profile = _json(profile_path)
        if adapter_name == "fake": adapter = FakeTargetAdapter()
        elif adapter_name == "replay": adapter = TraceReplayAdapter(trace)
        else:
            patch = args.dsh_patch or target_config.get("patch")
            if not patch: parser.error("DSH requires --dsh-patch or target.patch in run-config.json")
            adapter = DSHAdapter(patch, profile=run_config.get("harness", {}).get("profile", "headless"), cwd=run_workspace.artifacts if run_workspace else None)
        if run_workspace: run_workspace.update_status("running")
        result = asyncio.run(run_plan(store, adapter, batch, profile["target_id"], concurrency))
        if run_workspace:
            result_path = run_workspace.output / "batch-result.json"; result_path.write_text(json.dumps(result, indent=2)); run_workspace.update_status("completed", batch_result="output/batch-result.json")
        print(json.dumps(result, indent=2))
    elif args.command == "campaign":
        profile = _json(run_workspace.input / "target-profile.json")
        scenario_path = run_workspace.input / "scenarios.json"
        sampling = run_config["sampling"]
        planning_scenarios = load(scenario_path) + prompt_set_scenarios(run_config)
        evolution_scenarios = planning_scenarios
        full_plan = plan(planning_scenarios, sampling["max_samples"], sampling["seed"], _hash(profile), sampling["strategy"])
        (run_workspace.input / "plan.json").write_text(json.dumps(full_plan, indent=2))
        for sample in full_plan["samples"]: store.add_sample(sample)
        adapter = DSHAdapter(args.dsh_patch, profile=run_config.get("harness", {}).get("profile", "headless"), timeout=args.timeout, cwd=run_workspace.artifacts)
        health = asyncio.run(adapter.health())
        if not health.healthy: parser.error(f"DSH is unavailable: {health.detail}")
        steps, per_step = int(sampling["steps"]), int(sampling["samples_per_step"])
        aggregate = {"completed": 0, "skipped": 0, "adapter_errors": 0, "target_failures": 0, "steps": []}
        evolution = run_config["evolution"]
        config = EvolutionConfig(max_layer=evolution["max_depth"], branch_factor=evolution["branch_factor"], max_nodes=evolution["max_nodes"])
        tree = OODTree(evolution_scenarios, observations_from_store(store)).build(config)
        write_tree(tree, run_workspace.output / "evolution" / "ood-tree.json")
        append_tree_history(tree, run_workspace.output / "evolution" / "history.jsonl", progressive=False)
        build_dashboard(run_workspace.output / "evolution" / "ood-tree.json", run_workspace.output / "dashboard.html", "Matrix Evolver")
        build_runs_dashboard(run_workspace.root.parent, run_workspace.root.parent / "runs-dashboard.html", "Matrix Evolver runs")
        run_workspace.update_status("running", current_step=0, completed_samples=0, dashboard="output/dashboard.html")
        for index in range(steps):
            samples = full_plan["samples"][index * per_step:(index + 1) * per_step]
            step_plan = {**full_plan, "plan_id": f'{full_plan["plan_id"]}-step-{index + 1}', "samples": samples, "step": index + 1}
            step_path = run_workspace.input / f"plan-step-{index + 1}.json"
            step_path.write_text(json.dumps(step_plan, indent=2))
            def publish_live(partial):
                live_tree = OODTree(evolution_scenarios, observations_from_store(store)).build(config)
                write_tree(live_tree, run_workspace.output / "evolution" / "ood-tree.json")
                build_dashboard(run_workspace.output / "evolution" / "ood-tree.json", run_workspace.output / "dashboard.html", "Matrix Evolver")
                finished_before = aggregate["completed"]
                run_workspace.update_status("running", current_step=index + 1, step_completed=partial["completed"], step_errors=partial["adapter_errors"], completed_samples=finished_before + partial["completed"])
                build_runs_dashboard(run_workspace.root.parent, run_workspace.root.parent / "runs-dashboard.html", "Matrix Evolver runs")
            result = asyncio.run(run_plan(store, adapter, step_plan, profile["target_id"], args.concurrency or sampling.get("concurrency", 4), publish_live))
            aggregate["steps"].append({"step": index + 1, **result})
            for key in ("completed", "skipped", "adapter_errors", "target_failures"): aggregate[key] += result[key]
            tree = OODTree(evolution_scenarios, observations_from_store(store)).build(config)
            write_tree(tree, run_workspace.output / "evolution" / "ood-tree.json")
            append_tree_history(tree, run_workspace.output / "evolution" / "history.jsonl", progressive=False)
            store.put_ood_tree(tree)
            build_dashboard(run_workspace.output / "evolution" / "ood-tree.json", run_workspace.output / "dashboard.html", "Matrix Evolver")
            (run_workspace.output / f"step-{index + 1}-result.json").write_text(json.dumps(result, indent=2))
            run_workspace.update_status("running", current_step=index + 1, completed_samples=aggregate["completed"])
            build_runs_dashboard(run_workspace.root.parent, run_workspace.root.parent / "runs-dashboard.html", "Matrix Evolver runs")
            print(json.dumps({"step": index + 1, **result}), flush=True)
        result_path = run_workspace.output / "batch-result.json"
        result_path.write_text(json.dumps(aggregate, indent=2))
        build_dashboard(run_workspace.output / "evolution" / "ood-tree.json", run_workspace.output / "dashboard.html", "Matrix Evolver")
        run_workspace.update_status("completed", current_step=steps, completed_samples=aggregate["completed"], batch_result="output/batch-result.json", dashboard="output/dashboard.html")
        build_runs_dashboard(run_workspace.root.parent, run_workspace.root.parent / "runs-dashboard.html", "Matrix Evolver runs")
        print(json.dumps(aggregate, indent=2))
    elif args.command == "evaluate":
        print(json.dumps(store.counts(), indent=2))
    elif args.command == "report":
        output = Path(args.output) if args.output else (run_workspace.output / "report.md" if run_workspace else Path(".sampler/report.md"))
        print(build_report(store, args.target, output))
    elif args.command == "evolve":
        scenario_path = run_workspace.input / "scenarios.json"
        evolution_config = run_config.get("evolution", {}); config = EvolutionConfig(max_layer=args.max_layer or evolution_config.get("max_depth") or 3, branch_factor=args.branch_factor or evolution_config.get("branch_factor") or 2, min_parent_attempts=args.min_parent_attempts, max_nodes=args.max_nodes or evolution_config.get("max_nodes") or 500)
        tree = OODTree(load(scenario_path), observations_from_store(store)).build(config)
        output = write_tree(tree, run_workspace.output / "evolution" / "ood-tree.json")
        append_tree_history(tree, run_workspace.output / "evolution" / "history.jsonl", progressive=False)
        metrics = run_workspace.output / "evolution" / "layer-metrics.json"
        metrics.write_text(json.dumps({"summary": tree["summary"], "layers": tree["layer_metrics"]}, indent=2) + "\n")
        store.put_ood_tree(tree)
        run_workspace.update_status("evolved", ood_tree=str(output.relative_to(run_workspace.root)), maximum_ood_layer=tree["summary"]["maximum_layer"], ood_nodes=tree["summary"]["ood_count"])
        print(output)
    elif args.command == "dashboard":
        if args.runs_root:
            print(build_runs_dashboard(args.runs_root, args.output, args.title))
        else:
            tree_path = run_workspace.output / "evolution" / "ood-tree.json"
            if not tree_path.is_file(): parser.error("dashboard requires `sampler evolve --run-dir ...` first")
            output = Path(args.output) if args.output else run_workspace.output / "dashboard.html"
            print(build_dashboard(tree_path, output, args.title))
    elif args.command == "agents":
        script = Path(__file__).resolve().parents[2] / "matrix_evolving_agents" / "run_pipeline.py"
        command = [sys.executable, str(script), "--workspace", args.run_dir, "--max-layer", str(args.max_layer), "--branch-factor", str(args.branch_factor), "--max-nodes", str(args.max_nodes)]
        raise SystemExit(subprocess.run(command).returncode)


if __name__ == "__main__": main()

