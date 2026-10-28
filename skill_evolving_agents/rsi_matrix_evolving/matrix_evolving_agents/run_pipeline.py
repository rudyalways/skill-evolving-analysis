#!/usr/bin/env python3
"""Run the seven-stage matrix-evolving agent pipeline over one isolated run."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path: sys.path.insert(0, str(ROOT / "src"))
if str(Path(__file__).resolve().parent) not in sys.path: sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.contracts import append_event, validate_hierarchy, validate_lineage, write_json, write_status
from matrix_sampler.evolution import AGENT_CATEGORY_INSTRUCTION, EvolutionConfig, OODTree, observations_from_store, parse_expansion_output
from matrix_sampler.reporting.dashboard import append_tree_history, build_dashboard
from matrix_sampler.scenarios.registry import load
from matrix_sampler.storage.sqlite import Store
from matrix_sampler.workspace import RunWorkspace


class Pipeline:
    def __init__(self, workspace: Path, max_layer: int, branch_factor: int, max_nodes: int):
        self.ws = RunWorkspace(workspace).require()
        self.store = Store(self.ws.database)
        self.config = EvolutionConfig(max_layer=max_layer, branch_factor=branch_factor, max_nodes=max_nodes)
        self.run = self.ws.output / "run"
        self.derived = self.ws.output / "traces" / "derived"
        self.tree_path = self.ws.output / "evolution" / "ood-tree.json"

    def stage(self, number, name, action):
        key = f"{number:02d}_{name}"
        append_event(self.ws.root, f"{number:02d}", name, "started")
        try:
            artifacts = action()
            write_status(self.ws.root, key, "done", [str(Path(p).relative_to(self.ws.root)) for p in artifacts])
            append_event(self.ws.root, f"{number:02d}", name, "done", {"artifacts": len(artifacts)})
        except Exception as exc:
            write_status(self.ws.root, key, "failed", [], f"{type(exc).__name__}: {exc}")
            append_event(self.ws.root, f"{number:02d}", name, "failed", {"error": type(exc).__name__})
            raise

    def preprocess(self):
        observations = observations_from_store(self.store)
        artifact = write_json(self.derived / "observable-evidence.json", {"schema_version": 1, "source": "run-local-sqlite", "hidden_reasoning_retained": False, "scenario_observations": observations})
        return [artifact]

    def diagnose(self):
        evidence = json.loads((self.derived / "observable-evidence.json").read_text())
        scenarios = load(self.ws.input / "scenarios.json")
        provisional = OODTree(scenarios, evidence["scenario_observations"])
        findings = []
        for node in provisional.roots():
            expand, reasons = provisional.should_expand(node, self.config)
            if expand:
                finding_id = "finding_" + hashlib.sha256(node["node_id"].encode()).hexdigest()[:12]
                findings.append({"finding_id": finding_id, "node_id": node["node_id"], "scenario_id": node["dimensions"]["scenario"], "classification": "ood_expansion_candidate", "reason_codes": reasons, "metrics": node["metrics"], "evidence_ref": "output/traces/derived/observable-evidence.json"})
        artifact = write_json(self.run / "diagnosis.json", {"schema_version": 1, "findings": findings})
        return [artifact]

    def goals(self):
        diagnosis = json.loads((self.run / "diagnosis.json").read_text())
        outputs = []
        for finding in diagnosis["findings"]:
            directory = self.run / finding["finding_id"]
            goal = {"schema_version": 1, "finding_id": finding["finding_id"], "objective": "Expand the sparse OOD matrix only along evidence-backed controlled shifts.", "parent_node_id": finding["node_id"], "maximum_layer": self.config.max_layer, "branch_factor": self.config.branch_factor, "acceptance": ["lineage_valid", "one_new_axis_per_layer", "bounded_node_count", "deterministic_verifier_precedence"]}
            outputs.append(write_json(directory / "evolve-goal.json", goal))
        outputs.append(write_json(self.run / "goal-reduction.json", {"schema_version": 1, "input_findings": len(diagnosis["findings"]), "unique_goals": len(outputs), "duplicate_goals_removed": 0}))
        outputs.append(write_json(self.run / "category-proposal-request.json", {"schema_version": 1, "instruction": AGENT_CATEGORY_INSTRUCTION, "maximum_category_depth": self.config.max_layer, "separator": "/"}))
        return outputs

    def sample(self):
        evidence = json.loads((self.derived / "observable-evidence.json").read_text())
        evolver = OODTree(load(self.ws.input / "scenarios.json"), evidence["scenario_observations"])
        proposal_path = self.run / "expansion-proposals.json"
        tree = evolver.build_from_category_proposals(parse_expansion_output(json.loads(proposal_path.read_text()), self.config.max_layer), self.config) if proposal_path.is_file() else evolver.build(self.config)
        self.tree_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.tree_path, tree); self.store.put_ood_tree(tree)
        append_tree_history(tree, self.tree_path.with_name("history.jsonl"), progressive=False)
        queue = [{"node_id": n["node_id"], "parent_id": n["parent_id"], "layer": n["layer"], "scenario_id": n["dimensions"]["scenario"], "shift_axes": n["shift_axes"], "mutation": n.get("mutation"), "priority": round(n["metrics"]["uncertainty"] * .6 + n["metrics"]["failure_rate"] * .4, 4)} for n in tree["nodes"] if n["layer"] > 0 and not n["child_ids"]]
        queue.sort(key=lambda row: (-row["priority"], row["node_id"]))
        return [self.tree_path, write_json(self.run / "sample-queue.json", {"schema_version": 1, "candidates": queue})]

    def verify(self):
        tree = json.loads(self.tree_path.read_text()); errors = validate_lineage(tree); hierarchy_errors = validate_hierarchy(tree)
        all_errors = errors + hierarchy_errors
        result = {"schema_version": 1, "overall_status": "pass" if not all_errors else "fail", "checks": {"lineage": {"passed": not errors, "errors": errors}, "single_root_hierarchy": {"passed": not hierarchy_errors, "errors": hierarchy_errors}, "bounded": {"passed": len(tree["nodes"]) <= self.config.max_nodes, "actual": len(tree["nodes"]), "limit": self.config.max_nodes}, "depth": {"passed": tree["summary"]["maximum_layer"] <= self.config.max_layer}}, "ood": [n["node_id"] for n in tree["nodes"] if n["layer"] > 0], "action": None}
        return [write_json(self.run / "verification.json", result)]

    def judge(self):
        verification = json.loads((self.run / "verification.json").read_text())
        passed = verification["overall_status"] == "pass" and all(c["passed"] for c in verification["checks"].values())
        result = {"schema_version": 1, "decision": "pass" if passed else "fail", "formula": "verification.overall_status == pass AND all deterministic checks pass", "model_used": False, "terminal": True}
        return [write_json(self.run / "judge.json", result)]

    def dashboard(self):
        output = build_dashboard(self.tree_path, self.ws.output / "dashboard.html", f"Matrix Evolver · {self.ws.root.name}", self.tree_path.with_name("history.jsonl"))
        return [output]

    def execute(self):
        self.stage(1, "preprocessing", self.preprocess)
        self.stage(2, "diagnosis", self.diagnose)
        self.stage(3, "goal", self.goals)
        self.stage(4, "sampling", self.sample)
        self.stage(5, "verification", self.verify)
        self.stage(6, "judge", self.judge)
        self.stage(7, "dashboard", self.dashboard)
        summary = {"schema_version": 1, "status": "completed", "stages": 7, "dashboard": "output/dashboard.html", "tree": "output/evolution/ood-tree.json", "judge": json.loads((self.run / "judge.json").read_text())}
        write_json(self.run / "pipeline-summary.json", summary)
        self.ws.update_status("agent_pipeline_completed", pipeline_summary="output/run/pipeline-summary.json", dashboard="output/dashboard.html")
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(prog="matrix-evolving-agents")
    parser.add_argument("--workspace", required=True); parser.add_argument("--max-layer", type=int, choices=[1,2,3], default=3); parser.add_argument("--branch-factor", type=int, default=2); parser.add_argument("--max-nodes", type=int, default=500)
    args = parser.parse_args(argv)
    print(json.dumps(Pipeline(Path(args.workspace), args.max_layer, args.branch_factor, args.max_nodes).execute(), indent=2))


if __name__ == "__main__": main()
