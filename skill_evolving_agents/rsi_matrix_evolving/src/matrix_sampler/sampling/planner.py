from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from typing import Any

from matrix_sampler.models import stable_id


def beta_ci90(alpha: float, beta: float) -> tuple[float, float]:
    mean = alpha / (alpha + beta)
    sd = math.sqrt(alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1)))
    return max(0.0, mean - 1.645 * sd), min(1.0, mean + 1.645 * sd)


def should_stop(alpha: float, beta: float, attempts: int, max_width: float = .20) -> bool:
    lo, hi = beta_ci90(alpha, beta)
    return attempts >= 4 and hi - lo <= max_width


def select_uncertain(cells: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    """Thompson-style resampling: wide intervals win, with seeded tie breaking."""
    rng = random.Random(seed)
    eligible = [c for c in cells if not should_stop(c.get("alpha", 1), c.get("beta", 1), c.get("attempts", 0))]
    def score(c):
        lo, hi = beta_ci90(c.get("alpha", 1), c.get("beta", 1))
        draw = rng.betavariate(c.get("alpha", 1), c.get("beta", 1))
        return (hi - lo) * .7 + (1 - draw) * .3
    return sorted(eligible, key=score, reverse=True)[:limit]


def priority(components: dict[str, float]) -> float:
    weights = {"coverage_gap": .24, "posterior_uncertainty": .20, "expected_failure_probability": .16, "semantic_novelty": .14, "verifier_disagreement": .10, "production_frequency": .08, "recency_or_regression_risk": .08, "normalized_expected_cost": -.12, "redundancy": -.08, "safety_risk": -.20}
    return sum(weights[k] * components.get(k, 0.0) for k in weights)


def plan(scenarios: list[dict[str, Any]], max_samples: int, seed: int, target_hash: str, strategy: str = "greedy-covering") -> dict[str, Any]:
    rng = random.Random(seed)
    candidates = []
    seen_prompts: set[str] = set()
    for scenario in scenarios:
        for difficulty in ("easy", "medium", "hard"):
            interface = scenario["interface_requirements"][0]
            capability = scenario["capabilities"]["required"][0]
            prompt = scenario["generator"]["prompt"].format(difficulty=difficulty)
            ph = hashlib.sha256(" ".join(prompt.lower().split()).encode()).hexdigest()
            if ph in seen_prompts:
                continue
            seen_prompts.add(ph)
            cell = {"domain": "/".join(scenario["domain"]), "scenario": scenario["scenario_id"].split(".")[1], "capability": capability, "interface": interface, "difficulty_band": difficulty, "distribution_axis": scenario["distribution"].get("axis", "none")}
            components = {"coverage_gap": 1, "posterior_uncertainty": 1, "expected_failure_probability": .5, "semantic_novelty": rng.random(), "verifier_disagreement": 0, "production_frequency": .2, "recency_or_regression_risk": .5, "normalized_expected_cost": .1, "redundancy": 0, "safety_risk": .1 if scenario["risk"]["level"] == "low" else .5}
            sample = {"schema_version": 1, "scenario_id": scenario["scenario_id"], "seed": rng.randrange(2**31), "cell": cell, "messages": [{"role": "user", "content": prompt}], "environment_ref": None, "expected": scenario["oracle"], "provenance": {"generator": scenario["generator"]["template_id"], "parent_sample_ids": [], "trace_finding_ids": []}, "priority_components": components}
            sample["sample_id"] = stable_id("smp", sample)
            sample["priority"] = priority(components)
            candidates.append(sample)
    # Greedy approximation: shuffle ties, then maximize new dimension pairs.
    rng.shuffle(candidates)
    chosen, covered = [], set()
    dims = ("domain", "scenario", "capability", "interface", "difficulty_band", "distribution_axis")
    while candidates and len(chosen) < max_samples:
        def gain(c):
            pairs = {(a, c["cell"][a], b, c["cell"][b]) for a, b in itertools.combinations(dims, 2)}
            return (len(pairs - covered), c["priority"])
        best = max(candidates, key=gain)
        candidates.remove(best)
        chosen.append(best)
        covered |= {(a, best["cell"][a], b, best["cell"][b]) for a, b in itertools.combinations(dims, 2)}
    return {"schema_version": 1, "plan_id": stable_id("plan", [seed, target_hash, [x["sample_id"] for x in chosen]]), "seed": seed, "strategy": strategy, "target_profile_hash": target_hash, "taxonomy_version": 1, "generator_version": 1, "samples": chosen, "coverage_pairs": len(covered)}

