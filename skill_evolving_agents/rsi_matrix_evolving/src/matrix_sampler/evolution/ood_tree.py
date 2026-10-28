from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OOD_AXES = (
    "domain_shift", "task_scenario_shift", "capability_composition_shift",
    "interface_tool_shift", "language_locale_shift", "format_schema_shift",
    "difficulty_length_shift", "ambiguity_missing_information_shift",
    "adversarial_instruction_conflict_shift", "temporal_version_shift",
    "environment_state_shift", "failure_mechanism_shift",
    "user_persona_accessibility_shift",
)

AXIS_NAMES = {
    "domain_shift": "New-domain transfer",
    "task_scenario_shift": "Adjacent-task transfer",
    "capability_composition_shift": "Composed capabilities",
    "interface_tool_shift": "New tool surface",
    "language_locale_shift": "Locale and language variation",
    "format_schema_shift": "Schema and format variation",
    "difficulty_length_shift": "Scale and length stress",
    "ambiguity_missing_information_shift": "Missing-information boundary",
    "adversarial_instruction_conflict_shift": "Instruction-conflict defense",
    "temporal_version_shift": "Version-drift handling",
    "environment_state_shift": "Environment-state recovery",
    "failure_mechanism_shift": "Novel failure mechanism",
    "user_persona_accessibility_shift": "Accessibility and persona variation",
}

LAYER_POLICIES = {
    1: {"name": "single_axis_boundary", "axes_per_child": 1, "description": "One controlled shift from an ID or declared parent."},
    2: {"name": "composed_ood", "axes_per_child": 2, "description": "A pair of evidenced shifts composed from a weak layer-1 branch."},
    3: {"name": "failure_neighborhood", "axes_per_child": 3, "description": "A bounded hard case around a verified failure or disagreement."},
}


def _id(prefix: str, value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _ci(alpha: float, beta: float) -> list[float]:
    mean = alpha / (alpha + beta)
    sd = math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1)))
    return [round(max(0, mean - 1.645 * sd), 4), round(min(1, mean + 1.645 * sd), 4)]


def _axis_for(scenario: dict, offset: int = 0) -> str:
    key = scenario["scenario_id"] + scenario["capabilities"]["required"][0]
    return OOD_AXES[(int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) + offset) % len(OOD_AXES)]


@dataclass
class EvolutionConfig:
    max_layer: int = 3
    branch_factor: int = 2
    min_parent_attempts: int = 0
    expand_failure_below: float = .8
    expand_ci_width_above: float = .2
    max_nodes: int = 500


class OODTree:
    """Deterministic evolving-agent policy over a sparse hierarchical OOD tree."""

    def __init__(self, scenarios: list[dict], observations: dict[str, dict] | None = None):
        self.scenarios = scenarios
        self.observations = observations or {}

    def roots(self) -> list[dict]:
        roots = []
        for scenario in self.scenarios:
            scenario_id = scenario["scenario_id"]
            observed = self.observations.get(scenario_id, {})
            attempts, successes = int(observed.get("attempts", 0)), int(observed.get("successes", 0))
            alpha, beta = successes + 1, attempts - successes + 1
            roots.append(self._node(scenario, 0, None, [], attempts, successes, alpha, beta, "declared_root", ["bootstrap_contract"]))
        return roots

    def _node(self, scenario, layer, parent_id, axes, attempts, successes, alpha, beta, policy, evidence):
        display_name = self._display_name(scenario, layer, axes)
        dimensions = {"domain": "/".join(scenario["domain"]), "scenario": scenario["scenario_id"], "scenario_variant": display_name, "capability": scenario["capabilities"]["required"][0], "interface": scenario["interface_requirements"][0]}
        node_id = _id("ood", [parent_id, layer, dimensions, axes])
        mean = alpha / (alpha + beta)
        ci = _ci(alpha, beta)
        return {"schema_version": 1, "node_id": node_id, "parent_id": parent_id, "display_name": display_name, "layer": layer, "status": "id_declared" if layer == 0 else "ood_candidate", "dimensions": dimensions, "shift_axes": axes, "expansion_policy": policy, "evidence": evidence, "metrics": {"attempts": attempts, "successes": successes, "posterior_alpha": alpha, "posterior_beta": beta, "success_mean": round(mean, 4), "success_ci90": ci, "uncertainty": round(ci[1] - ci[0], 4), "failure_rate": round(1 - mean, 4), "novel_failures": int(self.observations.get(scenario["scenario_id"], {}).get("novel_failures", 0)), "cost_usd": float(self.observations.get(scenario["scenario_id"], {}).get("cost_usd", 0))}}

    def _display_name(self, scenario: dict, layer: int, axes: list[str]) -> str:
        if layer == 0:
            return scenario["title"]
        names = [AXIS_NAMES[axis] for axis in axes]
        if layer == 1:
            return names[-1]
        if layer == 2:
            return f"{names[-1]} + {names[-2]}"
        return "Stress case: " + " + ".join(names[-3:])

    def should_expand(self, node: dict, config: EvolutionConfig) -> tuple[bool, list[str]]:
        if node["layer"] >= config.max_layer: return False, ["maximum_layer"]
        metrics = node["metrics"]
        reasons = []
        if metrics["attempts"] < config.min_parent_attempts: return False, ["insufficient_parent_evidence"]
        if metrics["success_mean"] < config.expand_failure_below: reasons.append("elevated_failure_probability")
        if metrics["uncertainty"] > config.expand_ci_width_above: reasons.append("posterior_uncertainty")
        if metrics["novel_failures"] > 0: reasons.append("novel_failure_signature")
        if node["layer"] == 0 and metrics["attempts"] == 0: reasons.append("declared_but_unobserved")
        return bool(reasons), reasons

    def build(self, config: EvolutionConfig) -> dict:
        nodes, frontier = [], self.roots()
        nodes.extend(frontier)
        while frontier and len(nodes) < config.max_nodes:
            parent = frontier.pop(0)
            expand, reasons = self.should_expand(parent, config)
            if not expand: continue
            child_layer = parent["layer"] + 1
            scenario = next(s for s in self.scenarios if s["scenario_id"] == parent["dimensions"]["scenario"])
            for branch in range(config.branch_factor):
                axes = list(parent["shift_axes"])
                offset = child_layer + branch
                candidate_axis = _axis_for(scenario, offset)
                while candidate_axis in axes:
                    offset += config.branch_factor
                    candidate_axis = _axis_for(scenario, offset)
                axes.append(candidate_axis)
                while len(axes) < LAYER_POLICIES[child_layer]["axes_per_child"]:
                    extra = OOD_AXES[(OOD_AXES.index(candidate_axis) + len(axes)) % len(OOD_AXES)]
                    if extra not in axes: axes.append(extra)
                child = self._node(scenario, child_layer, parent["node_id"], axes, 0, 0, 1, 1, LAYER_POLICIES[child_layer]["name"], reasons)
                child["branch_index"] = branch
                child["mutation"] = self._mutation(child)
                nodes.append(child); frontier.append(child)
                if len(nodes) >= config.max_nodes: break
        return self._finalize(nodes, config)

    def build_from_category_proposals(self, proposals, config: EvolutionConfig) -> dict:
        """Apply parsed slash-path proposals; proposal paths, not cycle number, set depth."""
        nodes = self.roots()
        roots = {node["dimensions"]["scenario"]: node for node in nodes}
        path_nodes: dict[tuple[str, str], dict] = {}
        ordered = sorted(proposals, key=lambda proposal: (len(proposal.segments), proposal.scenario_id, proposal.category_path))
        for proposal in ordered:
            if len(nodes) >= config.max_nodes:
                break
            layer = len(proposal.segments)
            if layer > config.max_layer:
                raise ValueError(f"category path exceeds configured maximum depth {config.max_layer}")
            scenario = next((item for item in self.scenarios if item["scenario_id"] == proposal.scenario_id), None)
            if scenario is None:
                raise ValueError(f"unknown scenario_id: {proposal.scenario_id}")
            parent = roots[proposal.scenario_id] if layer == 1 else path_nodes.get((proposal.scenario_id, "/".join(proposal.segments[:-1])))
            if parent is None:
                raise ValueError(f"missing category prefix for {proposal.category_path}")
            key = (proposal.scenario_id, proposal.category_path)
            if key in path_nodes:
                continue
            axes = list(OOD_AXES[:layer])
            node = self._node(scenario, layer, parent["node_id"], axes, 0, 0, 1, 1, "agent_category_path", list(proposal.evidence))
            node["node_id"] = _id("ood_category", [proposal.scenario_id, proposal.category_path])
            node["display_name"] = proposal.display_name
            node["dimensions"]["scenario_variant"] = proposal.display_name
            node["dimensions"]["category_path"] = proposal.category_path
            node["shift_axes"] = list(proposal.segments)
            node["mutation"] = {"kind": "agent_category_proposal", "category_path": proposal.category_path, "requires_parent_comparison": True}
            nodes.append(node)
            path_nodes[key] = node
        return self._finalize(nodes, config)

    def _finalize(self, nodes: list[dict], config: EvolutionConfig) -> dict:
        children = defaultdict(list)
        for node in nodes:
            if node["parent_id"]: children[node["parent_id"]].append(node["node_id"])
        for node in nodes: node["child_ids"] = children[node["node_id"]]
        layer_metrics = []
        for layer in range(config.max_layer + 1):
            rows = [n for n in nodes if n["layer"] == layer]
            layer_metrics.append({"layer": layer, "name": "id_roots" if layer == 0 else LAYER_POLICIES[layer]["name"], "nodes": len(rows), "sampled_nodes": sum(r["metrics"]["attempts"] > 0 for r in rows), "attempts": sum(r["metrics"]["attempts"] for r in rows), "mean_success": round(sum(r["metrics"]["success_mean"] for r in rows) / len(rows), 4) if rows else None, "mean_uncertainty": round(sum(r["metrics"]["uncertainty"] for r in rows) / len(rows), 4) if rows else None, "novel_failures": sum(r["metrics"]["novel_failures"] for r in rows), "cost_usd": round(sum(r["metrics"]["cost_usd"] for r in rows), 6)})
        hierarchy = self._hierarchy(nodes)
        return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "policy": {"layers": LAYER_POLICIES, "config": config.__dict__}, "nodes": nodes, "hierarchy": hierarchy, "layer_metrics": layer_metrics, "frontier": [n["node_id"] for n in nodes if n["status"] == "ood_candidate" and not n["child_ids"]], "summary": {"total_nodes": len(nodes), "maximum_layer": max(n["layer"] for n in nodes), "root_count": sum(n["layer"] == 0 for n in nodes), "ood_count": sum(n["layer"] > 0 for n in nodes), "hierarchy_nodes": len(hierarchy["nodes"]), "hierarchy_roots": 1}}

    def _hierarchy(self, nodes: list[dict]) -> dict:
        """Build a single-root taxonomy tree without changing sampling-node identity."""
        root_id = "tree_matrix_root"
        view = [{"node_id": root_id, "parent_id": None, "display_name": "Evaluation matrix", "kind": "matrix_root", "depth": 0, "source_node_id": None}]
        domains: dict[str, str] = {}
        for node in nodes:
            if node["layer"] != 0:
                continue
            domain = node["dimensions"]["domain"].split("/", 1)[0]
            if domain not in domains:
                domain_id = _id("tree_domain", domain)
                domains[domain] = domain_id
                domain_name = {"knowledge_work": "Knowledge", "capability_discovery": "Capability discovery"}.get(domain, domain.replace("_", " ").title())
                view.append({"node_id": domain_id, "parent_id": root_id, "display_name": domain_name, "kind": "domain", "depth": 1, "source_node_id": None})
            view.append({"node_id": node["node_id"], "parent_id": domains[domain], "display_name": node["display_name"], "kind": "scenario", "depth": 2, "source_node_id": node["node_id"]})
        for node in nodes:
            if node["layer"] > 0:
                view.append({"node_id": node["node_id"], "parent_id": node["parent_id"], "display_name": node["display_name"], "kind": "ood", "depth": node["layer"] + 2, "source_node_id": node["node_id"]})
        children = defaultdict(list)
        for node in view:
            if node["parent_id"]: children[node["parent_id"]].append(node["node_id"])
        for node in view: node["child_ids"] = children[node["node_id"]]
        return {"root_id": root_id, "nodes": view}

    def _mutation(self, node):
        return {"kind": "controlled_axis_shift", "instructions": [f"Vary {axis.replace('_', ' ')} while holding other parent dimensions fixed." for axis in node["shift_axes"]], "seed_material": node["node_id"], "requires_parent_comparison": True}


def observations_from_store(store) -> dict[str, dict]:
    rows = store.db.execute("""SELECT s.scenario_id, count(r.run_id), sum(CASE WHEN l.value_json='true' THEN 1 ELSE 0 END)
        FROM samples s LEFT JOIN runs r ON r.sample_id=s.sample_id AND r.status='completed'
        LEFT JOIN labels l ON l.run_id=r.run_id AND l.name='task_success' GROUP BY s.scenario_id""").fetchall()
    return {row[0]: {"attempts": row[1] or 0, "successes": row[2] or 0} for row in rows}


def write_tree(tree: dict, output: str | Path) -> Path:
    output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n")
    return output

