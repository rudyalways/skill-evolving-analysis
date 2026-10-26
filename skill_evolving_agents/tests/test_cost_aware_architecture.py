from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


AGENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENTS))

from core.adapters import band_decision, execute_adapter
from core.phase_envelope import artifact_ref, build_envelope, validate_envelope, write_envelope
from core.profile import ProfileError, load_profile, validate_profile
from core.super_config import SuperConfigError, load_super_config, resolve_execution_config
from core.service_tiers import load_service_tiers
from core.optimization import (
    OptimizationError,
    evaluate_candidate,
    generate_grid,
    load_spec,
    materialize_candidate,
    summarize_observations,
    validate_knob_registry,
    validate_metric_spec,
)
from core.online_learning import StudyStore, mcts_search, random_search, wide_deep_search
from core.state_machine import (
    StateMachineError,
    StateMachineRuntime,
    TransitionDecision,
    load_machine,
)
from policy import (
    CandidatePolicy,
    FixedPolicy,
    ModelPolicy,
    PolicyCompiler,
    PolicyStore,
    extract_policy_features,
)
from policy.heads import build_head_specs
from services.embedding_api.client import EmbeddingClient
from services.embedding_api.server import Handler, configure_framework_environment
from services.embedding_api import server as embedding_server
from services.embedding_api.provider import EmbeddingProvider
from services.generation_api.client import GenerationClient
from services.generation_api.server import Handler as GenerationHandler
import run_pipeline as runner


class CostAwareArchitectureTests(unittest.TestCase):
    def test_embedding_ranking_batches_candidates_and_queries(self) -> None:
        class BatchBackend:
            def __init__(self) -> None:
                self.calls: list[tuple[str, list[str]]] = []

            def embed_many(self, texts: list[str]) -> list[list[float]]:
                self.calls.append(("candidates", texts))
                return [[1.0, 0.0], [0.0, 1.0]]

            def embed_query_many(self, texts: list[str]) -> list[list[float]]:
                self.calls.append(("queries", texts))
                return [[1.0, 0.0] for _ in texts]

        backend = BatchBackend()
        with patch.object(embedding_server, "BACKEND", backend):
            rows = embedding_server.ranked(
                ["first", "second"],
                {"left": "alpha", "right": "beta"},
                1,
            )
        self.assertEqual(
            backend.calls,
            [
                ("candidates", ["alpha", "beta"]),
                ("queries", ["first", "second"]),
            ],
        )
        self.assertEqual(rows, [{"matches": [{"id": "left", "score": 1.0}]}] * 2)

    def test_optimization_specs_validate_and_grid_respects_constraints(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        validate_metric_spec(load_spec(AGENTS / "config/metric-spec.json", "metrics"))
        rows = generate_grid(
            registry,
            ["semantic.accept_at", "semantic.noise_accept_at"],
            max_candidates=100,
        )
        self.assertTrue(rows)
        self.assertTrue(
            all(
                row["overrides"]["semantic.accept_at"]
                <= row["overrides"]["semantic.noise_accept_at"]
                for row in rows
            )
        )
        with self.assertRaisesRegex(OptimizationError, "locked"):
            generate_grid(registry, ["publish.atomic"])

    def test_candidate_materialization_only_changes_registered_path(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        profile = json.loads((AGENTS / "profiles/low-cost.json").read_text())
        result = materialize_candidate(
            {"profile": profile},
            registry,
            {"overrides": {"semantic.accept_at": 0.8}},
        )
        self.assertEqual(result["profile"]["phases"]["semantic_prefilter"]["accept_at"], 0.8)
        self.assertEqual(profile["phases"]["semantic_prefilter"]["accept_at"], 0.7)

    def test_promotion_is_constraint_first_and_pareto_safe(self) -> None:
        spec = validate_metric_spec(
            load_spec(AGENTS / "config/metric-spec.json", "metrics")
        )
        baseline = {
            "critical_finding_recall": {"value": 1.0, "samples": 10},
            "high_finding_recall": {"value": 0.97, "samples": 30},
            "noise_rejection_precision": {"value": 0.99, "samples": 20},
            "activation_false_positive_rate": {"value": 0.08, "samples": 30},
            "held_out_pass_rate": {"value": 0.85, "samples": 20},
            "skill_recall_at_5": {"value": 0.8, "samples": 30},
            "agent_calls_per_finding": {"value": 4.0, "samples": 30},
            "wall_ms_per_finding": {"value": 1000, "samples": 30},
            "human_review_rate": {"value": 0.5, "samples": 30},
        }
        cheaper = json.loads(json.dumps(baseline))
        cheaper["agent_calls_per_finding"]["value"] = 3.0
        self.assertTrue(evaluate_candidate(baseline, cheaper, spec)["eligible"])
        unsafe = json.loads(json.dumps(cheaper))
        unsafe["critical_finding_recall"]["value"] = 0.9
        decision = evaluate_candidate(baseline, unsafe, spec)
        self.assertFalse(decision["eligible"])
        self.assertIn("critical_finding_recall", {row["metric"] for row in decision["violations"]})

    def test_metric_summary_includes_sample_count_and_interval(self) -> None:
        spec = validate_metric_spec(
            load_spec(AGENTS / "config/metric-spec.json", "metrics")
        )
        summary = summarize_observations(
            [
                {"example_id": "a", "metrics": {"critical_finding_recall": 1}},
                {"example_id": "b", "metrics": {"critical_finding_recall": 0}},
                {"example_id": "c", "metrics": {"critical_finding_recall": 1}},
            ],
            spec,
        )
        row = summary["critical_finding_recall"]
        self.assertEqual(row["samples"], 3)
        self.assertAlmostEqual(row["value"], 2 / 3)
        self.assertEqual(row["interval_method"], "wilson-95")
        self.assertLess(row["ci95"][0], row["value"])
        self.assertGreater(row["ci95"][1], row["value"])

    def test_online_feedback_updates_bayesian_confidence_and_ema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StudyStore(Path(directory) / "optimization.sqlite")
            candidate = {"overrides": {"semantic.accept_at": 0.75}}
            store.record_trial(
                run_id="run-1", algorithm="mcts", candidate=candidate,
                reward=0.2, decision={"eligible": True},
            )
            first = store.posterior("semantic.accept_at", 0.75)
            self.assertEqual((first["alpha"], first["beta"], first["count"]), (2.0, 1.0, 1))
            store.record_trial(
                run_id="run-2", algorithm="mcts", candidate=candidate,
                reward=-0.2, decision={"eligible": False},
            )
            second = store.posterior("semantic.accept_at", 0.75)
            self.assertEqual((second["alpha"], second["beta"], second["count"]), (2.0, 2.0, 2))
            self.assertAlmostEqual(second["reward_ema"], 0.12)
            root = store.prefix_stats(["semantic.accept_at"], {})
            child = store.prefix_stats(
                ["semantic.accept_at"], {"semantic.accept_at": 0.75}
            )
            self.assertEqual(root["visits"], 2)
            self.assertEqual(child["visits"], 2)
            self.assertAlmostEqual(child["mean_reward"], 0.0)

    def test_random_wide_deep_and_mcts_search_emit_valid_candidates(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        selected = ["semantic.accept_at", "semantic.noise_accept_at"]
        with tempfile.TemporaryDirectory() as directory:
            store = StudyStore(Path(directory) / "optimization.sqlite")
            searches = [
                random_search(registry, selected, 4, 7),
                wide_deep_search(registry, selected, 4, 7, store),
                mcts_search(registry, selected, 4, 7, store),
            ]
        for rows in searches:
            self.assertEqual(len(rows), 4)
            for row in rows:
                values = row["overrides"]
                if set(values) == set(selected):
                    self.assertLessEqual(
                        values["semantic.accept_at"],
                        values["semantic.noise_accept_at"],
                    )

    def test_fixed_and_future_policies_share_typed_compiler_boundary(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        profile = load_profile(AGENTS / "profiles/low-cost.json")
        preprocessing = json.loads(
            (AGENTS / "common/preprocessing-config.json").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            finding = workspace / "traces/derived/findings/sig/finding.json"
            finding.parent.mkdir(parents=True)
            finding.write_text(
                json.dumps(
                    {
                        "signal_id": "sig",
                        "detector": "repeated-instructions",
                        "severity": "high",
                        "confidence": 0.9,
                        "score": -4,
                        "evidence": [{"trace_id": "one"}],
                    }
                )
            )
            features = extract_policy_features(
                workspace,
                run_id="run-1",
                profile=profile,
                execution_config={"config_digest": "sha256:x", "max_cost_tier": 3},
            )
            documents = {"profile": profile, "preprocessing": preprocessing}
            decision = FixedPolicy(registry).decide(features, documents)
            compiled = PolicyCompiler(registry).compile(decision, documents)
            self.assertEqual(compiled["status"], "valid")
            self.assertEqual(
                compiled["documents"]["profile"]["phases"]["semantic_prefilter"]["accept_at"],
                0.7,
            )
            self.assertIn("FINDING", {row["type"] for row in features["tokens"]})

    def test_policy_store_preserves_features_decisions_and_feedback(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        profile = load_profile(AGENTS / "profiles/low-cost.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            features = extract_policy_features(
                root,
                run_id="run-1",
                profile=profile,
                execution_config={"config_digest": "sha256:x"},
            )
            decision = FixedPolicy(registry).decide(features, {"profile": profile})
            store = PolicyStore(root / "optimization.sqlite")
            store.record_features(features)
            store.record_decision(decision)
            store.record_feedback(
                {
                    "feedback_id": "feedback-1",
                    "run_id": "run-1",
                    "decision_id": decision["decision_id"],
                    "source": "human",
                    "signal": "stars",
                    "value": 5,
                    "confidence": 1.0,
                }
            )
            import sqlite3

            with sqlite3.connect(root / "optimization.sqlite") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM feature_records").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM policy_decisions").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0], 1)

    def test_registry_builds_typed_output_heads(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        heads = build_head_specs(registry)
        self.assertEqual(heads["recall.top_k"]["head_type"], "categorical")
        self.assertEqual(heads["score.severity_weight"]["head_type"], "simplex_member")
        self.assertNotIn("publish.atomic", heads)

    def test_search_and_transformer_adapters_emit_same_policy_contract(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        profile = load_profile(AGENTS / "profiles/low-cost.json")
        with tempfile.TemporaryDirectory() as directory:
            features = extract_policy_features(
                Path(directory), run_id="run-1", profile=profile,
                execution_config={"config_digest": "sha256:x"},
            )
        candidate = CandidatePolicy(
            {"overrides": {"semantic.accept_at": 0.75}}
        ).decide(features, {"profile": profile})
        model = ModelPolicy(
            lambda _: {
                "actions": {
                    "semantic.accept_at": {
                        "value": 0.75,
                        "probability": 0.8,
                        "head_type": "bounded_numeric",
                    }
                },
                "uncertainty": 0.2,
            },
            checkpoint_revision="checkpoint-1",
        ).decide(features, {"profile": profile})
        self.assertEqual(set(candidate["actions"]), set(model["actions"]))
        self.assertEqual(model["provider"], "transformer")
        compiled = PolicyCompiler(registry).compile(model, {"profile": profile})
        self.assertEqual(compiled["status"], "valid")

    def test_policy_compiler_rejects_out_of_domain_model_output(self) -> None:
        registry = validate_knob_registry(
            load_spec(AGENTS / "config/knob-registry.json", "knob registry")
        )
        profile = load_profile(AGENTS / "profiles/low-cost.json")
        with tempfile.TemporaryDirectory() as directory:
            features = extract_policy_features(
                Path(directory), run_id="run-1", profile=profile,
                execution_config={"config_digest": "sha256:x"},
            )
        decision = CandidatePolicy(
            {"overrides": {"semantic.accept_at": 9.0}}
        ).decide(features, {"profile": profile})
        compiled = PolicyCompiler(registry).compile(decision, {"profile": profile})
        self.assertEqual(compiled["status"], "rejected")
        self.assertIn("value_outside_domain:semantic.accept_at", compiled["errors"])

    def test_state_machine_validates_and_persists_dynamic_flow(self) -> None:
        definition = load_machine(AGENTS / "config/state-machine.json")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            machine = StateMachineRuntime(
                definition,
                run_id="run-1",
                item_id="finding-1",
                database=root / "optimization.sqlite",
                journal=root / "transitions.jsonl",
            )
            route = [
                TransitionDecision("NORMALIZE", "run_started", "normalize.vendor-json-v1"),
                TransitionDecision("DETECT", "normalized", "detect.rules-v1"),
                TransitionDecision("POLICY", "findings_ready", "policy.fixed-v1"),
                TransitionDecision("LABEL_SKILLS", "semantic_bypassed"),
                TransitionDecision("SELECT_UNITS", "labels_ready", "selection.evidence-gate-v1"),
                TransitionDecision("DIAGNOSE", "units_selected", "diagnosis.agent-full-json-v1"),
                TransitionDecision("RECALL", "diagnosis_complete", "recall.embedding-v1"),
                TransitionDecision("GOAL", "recall_complete", "goal.agent-full-json-v1"),
                TransitionDecision("OPTIMIZE", "change_proposed", "optimize.agent-v1"),
                TransitionDecision("VERIFY", "candidate_ready", "verify.agent-structural-v1"),
                TransitionDecision("PUBLISH", "verified", "publish.atomic-v1"),
                TransitionDecision("COMPLETE", "published"),
            ]
            for decision in route:
                machine.transition(decision)
            self.assertTrue(machine.terminal)
            self.assertEqual(machine.state, "COMPLETE")
            self.assertEqual(len(machine.history), len(route))
            self.assertEqual(len((root / "transitions.jsonl").read_text().splitlines()), len(route))
            restored = StateMachineRuntime.restore(
                definition,
                machine.snapshot(),
                database=root / "optimization.sqlite",
            )
            self.assertEqual(restored.state, "COMPLETE")
            self.assertEqual(restored.step, len(route))

    def test_state_machine_blocks_invalid_edges_and_publish_without_verify(self) -> None:
        definition = load_machine(AGENTS / "config/state-machine.json")
        with tempfile.TemporaryDirectory() as directory:
            machine = StateMachineRuntime(
                definition, run_id="run-1", item_id="finding-1",
                database=Path(directory) / "optimization.sqlite",
            )
            with self.assertRaisesRegex(StateMachineError, "not allowed"):
                machine.transition(TransitionDecision("PUBLISH", "published"))

    def test_generic_state_machine_executor_can_choose_dynamic_branch(self) -> None:
        definition = load_machine(AGENTS / "config/state-machine.json")
        decisions = iter(
            [
                TransitionDecision("NORMALIZE", "run_started", "normalize.vendor-json-v1"),
                TransitionDecision("DETECT", "normalized", "detect.rules-v1"),
                TransitionDecision("POLICY", "findings_ready", "policy.search-v1"),
                TransitionDecision("LABEL_SKILLS", "semantic_bypassed"),
                TransitionDecision("SELECT_UNITS", "labels_ready", "selection.evidence-gate-v1"),
                TransitionDecision("COMPLETE", "no_units"),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            machine = StateMachineRuntime(
                definition, run_id="run-1", item_id="finding-1",
                database=Path(directory) / "optimization.sqlite",
            )
            result = machine.run({}, lambda state, context, allowed: next(decisions))
        self.assertEqual(result["state"], "COMPLETE")
    def test_shipped_profiles_validate(self) -> None:
        super_config = load_super_config(AGENTS / "config/super-config.json")
        service_tiers = load_service_tiers(AGENTS / "config/service-tiers.json")
        for name in ("full-agent", "balanced", "low-cost", "low-cost-local-service"):
            profile = load_profile(AGENTS / "profiles" / f"{name}.json")
            self.assertEqual(profile["name"], name)
            self.assertTrue(profile["config_digest"].startswith("sha256:"))
            resolved = resolve_execution_config(profile, super_config, service_tiers)
            self.assertEqual(resolved["profile"], name)

    def test_local_embedding_phase_timeouts_cover_measured_cpu_latency(self) -> None:
        profile = load_profile(AGENTS / "profiles/low-cost-local-service.json")
        runtime_timeout = profile["embedding_runtime"]["timeout_ms"]
        for phase_name in ("semantic_prefilter", "recall"):
            phase_timeout = profile["phases"][phase_name]["timeout_ms"]
            self.assertGreaterEqual(phase_timeout, 10_000)
            self.assertLessEqual(phase_timeout, runtime_timeout)

    def test_super_config_rejects_phase_algorithm_mismatch(self) -> None:
        profile = load_profile(AGENTS / "profiles/full-agent.json")
        profile["phases"]["goal"]["algorithm"] = "diagnosis.agent-full-json-v1"
        super_config = load_super_config(AGENTS / "config/super-config.json")
        service_tiers = load_service_tiers(AGENTS / "config/service-tiers.json")
        with self.assertRaisesRegex(SuperConfigError, "belongs to phase"):
            resolve_execution_config(profile, super_config, service_tiers)

    def test_cost_tier_budget_rejects_large_agent(self) -> None:
        profile = load_profile(AGENTS / "profiles/full-agent.json")
        profile["max_cost_tier"] = 1
        super_config = load_super_config(AGENTS / "config/super-config.json")
        service_tiers = load_service_tiers(AGENTS / "config/service-tiers.json")
        with self.assertRaisesRegex(SuperConfigError, "exceeds profile"):
            resolve_execution_config(profile, super_config, service_tiers)

    def test_publish_cannot_be_delegated(self) -> None:
        profile = json.loads((AGENTS / "profiles/full-agent.json").read_text())
        profile["phases"]["publish"] = {"mode": "enabled", "kind": "agent"}
        with self.assertRaisesRegex(ProfileError, "publish"):
            validate_profile(profile)

    def test_embedding_thresholds_need_uncertainty_band(self) -> None:
        profile = json.loads((AGENTS / "profiles/balanced.json").read_text())
        profile["phases"]["semantic_prefilter"]["reject_below"] = 0.8
        profile["phases"]["semantic_prefilter"]["accept_at"] = 0.5
        with self.assertRaisesRegex(ProfileError, "thresholds"):
            validate_profile(profile)
        self.assertEqual(band_decision(0.1, 0.3, 0.8), "rejected")
        self.assertEqual(band_decision(0.5, 0.3, 0.8), "escalate")
        self.assertEqual(band_decision(0.9, 0.3, 0.8), "selected")

    def test_semantic_category_filter_only_rejects_confident_noise(self) -> None:
        config = {"accept_at": 0.7, "noise_accept_at": 0.75, "minimum_margin": 0.08}
        low = runner.semantic_category_decision(
            [{"id": "correction", "score": 0.1}], config
        )
        self.assertEqual(low["disposition"], "escalate")
        noise = runner.semantic_category_decision(
            [
                {"id": "noise", "score": 0.82},
                {"id": "methodology", "score": 0.60},
            ],
            config,
        )
        self.assertEqual(noise["disposition"], "rejected")
        ambiguous = runner.semantic_category_decision(
            [
                {"id": "noise", "score": 0.82},
                {"id": "methodology", "score": 0.78},
            ],
            config,
        )
        self.assertEqual(ambiguous["disposition"], "escalate")

    def test_edit_priority_score_is_bounded_and_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            finding = workspace / "traces/derived/findings/sig/finding.json"
            finding.parent.mkdir(parents=True)
            finding.write_text(
                json.dumps(
                    {"severity": "high", "confidence": 0.9, "score": 4.0}
                )
            )
            rank = runner.rank_edit(
                workspace, {"cluster": "sig", "confidence": 0.1, "affected": []}
            )
            self.assertAlmostEqual(rank["super_score"], 0.67)
            self.assertLessEqual(rank["super_score"], 1.0)
            self.assertEqual(rank["score_components"]["severity"], 0.75)

    def test_modes_do_not_accidentally_apply_observed_results(self) -> None:
        calls = []

        def operation():
            calls.append(True)
            return {"disposition": "rejected"}

        base = {
            "run_id": "run-1",
            "phase": "semantic_prefilter",
            "item_id": "sig-1",
            "implementation": {
                "kind": "embedding-service",
                "name": "test",
                "version": "1",
                "config_digest": "sha256:test",
            },
            "operation": operation,
        }
        result, envelope = execute_adapter(config={"mode": "observe"}, **base)
        self.assertIsNone(result)
        self.assertEqual(envelope["decision"]["disposition"], "observed_rejected")
        self.assertEqual(len(calls), 1)
        result, envelope = execute_adapter(config={"mode": "passthrough"}, **base)
        self.assertIsNone(result)
        self.assertEqual(envelope["decision"]["disposition"], "passthrough")
        self.assertEqual(len(calls), 1)

    def test_envelope_is_atomic_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.json"
            output.write_text("{}\n")
            envelope = build_envelope(
                run_id="run-1",
                phase="recall",
                item_id="sig-1",
                implementation={
                    "kind": "deterministic",
                    "name": "metadata-recall",
                    "version": "1",
                    "config_digest": "sha256:test",
                },
                status="completed",
                started_at="2026-10-23T00:00:00+00:00",
                output_ref=artifact_ref(output, relative_to=root),
            )
            path = root / "status/recall/sig-1.json"
            write_envelope(path, envelope)
            saved = validate_envelope(json.loads(path.read_text()))
            self.assertEqual(saved["output_ref"]["path"], "result.json")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_reference_embedding_service_protocol(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = EmbeddingClient(f"http://127.0.0.1:{server.server_port}")
            embedded = client.embeddings(["deploy release"])
            self.assertEqual(len(embedded["embeddings"]), 1)
            self.assertEqual(len(embedded["embeddings"][0]), 256)
            searched = client.search(
                ["deploy release"],
                {"release": "deploy release", "image": "generate image"},
                top_k=1,
            )
            self.assertEqual(searched["results"][0]["matches"][0]["id"], "release")
            self.assertEqual(searched["index_revision"], "request-local")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_embedding_service_selects_pytorch_without_overwriting_operator_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            configure_framework_environment()
            self.assertEqual(os.environ["USE_TF"], "0")
            self.assertEqual(os.environ["USE_TORCH"], "1")
        with patch.dict(
            os.environ, {"USE_TF": "1", "USE_TORCH": "0"}, clear=True
        ):
            configure_framework_environment()
            self.assertEqual(os.environ["USE_TF"], "1")
            self.assertEqual(os.environ["USE_TORCH"], "0")

    def test_in_process_embedding_provider_uses_no_http(self) -> None:
        provider = EmbeddingProvider(
            {"transport": "in_process"},
            AGENTS / "services/embedding_api/server.py",
        )
        result = provider.search(
            ["deploy release"], {"release": "deploy release"}, top_k=1
        )
        self.assertEqual(result["transport"], "in_process")
        self.assertEqual(result["results"][0]["matches"][0]["id"], "release")

    def test_managed_local_embedding_process(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        provider = EmbeddingProvider(
            {
                "transport": "local_process",
                "host": "127.0.0.1",
                "port": port,
                "startup_timeout_seconds": 5,
            },
            AGENTS / "services/embedding_api/server.py",
        )
        with provider:
            result = provider.classify(
                ["retry failure"], {"failure": "retry failure"}, top_k=1
            )
            self.assertEqual(result["results"][0]["matches"][0]["id"], "failure")
        self.assertIsNone(provider.process)

    def test_reference_generation_service_protocol(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), GenerationHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = GenerationClient(
                f"http://127.0.0.1:{server.server_port}"
            ).generate_json(
                input_data={"_reference_output": {"category": "retry"}},
                output_schema={"type": "object"},
                instruction="Classify the finding.",
                method="jev",
            )
            self.assertEqual(result["output"], {"category": "retry"})
            self.assertEqual(result["method"], "jev")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_agent_call_budget_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            previous = runner.ACTIVE_EXECUTION_CONFIG
            runner.ACTIVE_EXECUTION_CONFIG = {
                "budgets": {"hard_agent_call_cap": 1, "on_cap": "defer"}
            }
            try:
                runner.reserve_agent_call(workspace, "diagnosis", "one")
                with self.assertRaises(runner.AgentCallBudgetExceeded):
                    runner.reserve_agent_call(workspace, "goal", "two")
                report = json.loads(
                    (workspace / "logs/agent-call-budget.json").read_text()
                )
                self.assertEqual(report["used"], 1)
                self.assertEqual(report["remaining"], 0)
            finally:
                runner.ACTIVE_EXECUTION_CONFIG = previous


if __name__ == "__main__":
    unittest.main()
