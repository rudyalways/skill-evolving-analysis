from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


AGENTS = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


contracts = load("pipeline_contracts_test", AGENTS / "common/pipeline_contracts.py")
metrics_dashboard = load(
    "metrics_dashboard_test", AGENTS / "common/metrics_dashboard.py"
)
runner = load("run_pipeline_test", AGENTS / "run_pipeline.py")
candidates = load("candidate_traces_test", AGENTS / "candidate_traces.py")
signals = load(
    "trace_signals_test",
    AGENTS / "01_preprocessing_agent/trace_mining/signals.py",
)
type_checker = load("skill_type_checker_test", AGENTS / "common/skill_type_checker.py")
format_checker = load(
    "skill_format_checker_test", AGENTS / "common/skill_format_checker.py"
)
VERIFIER = AGENTS / "05_verifiter_agent/verifiter"
sys.path.insert(0, str(VERIFIER))
transforms = load("verify_transforms_test", VERIFIER / "verify_transforms.py")
verification_builder = load(
    "verification_from_goal_test", VERIFIER / "verification_from_goal.py"
)
RECALL = AGENTS / "03_goal_agent/skill-select"
recall_module = load("recall_skills_test", RECALL / "recall_skills.py")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def codex_trace_rows(
    session: str = "session-a",
    turn: str = "turn-a",
    user: str = "Fix the failing deployment script",
    assistant: str = "Updated and verified the script.",
) -> list[dict]:
    return [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "ordinal": 1,
            "type": "session_meta",
            "payload": {"session_id": session},
        },
        {
            "timestamp": "2026-01-01T00:00:01Z",
            "ordinal": 2,
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": turn,
                "root_turn_id": turn,
            },
        },
        {
            "timestamp": "2026-01-01T00:00:02Z",
            "ordinal": 3,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user}],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:03Z",
            "ordinal": 4,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant}],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:04Z",
            "ordinal": 5,
            "type": "event_msg",
            "payload": {"type": "task_complete", "turn_id": turn},
        },
    ]


def claude_trace_rows() -> list[dict]:
    return [
        {
            "type": "user",
            "uuid": "claude-turn",
            "sessionId": "claude-session",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": "Diagnose the release failure"},
        },
        {
            "type": "assistant",
            "uuid": "claude-response",
            "sessionId": "claude-session",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "content": [
                    {"type": "text", "text": "I found the release issue."},
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "shell",
                        "input": {"command": "test"},
                    },
                ]
            },
        },
        {
            "type": "user",
            "uuid": "claude-tool-result",
            "sessionId": "claude-session",
            "timestamp": "2026-01-01T00:00:02Z",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "ok",
                    }
                ]
            },
        },
    ]


def cursor_trace_rows() -> list[dict]:
    return [
        {
            "role": "user",
            "id": "cursor-turn",
            "timestamp": "2026-01-01T00:00:00Z",
            "content": "Improve the release workflow",
        },
        {
            "role": "assistant",
            "timestamp": "2026-01-01T00:00:01Z",
            "content": "The workflow is improved.",
        },
    ]


def valid_goal(op: dict | None = None) -> dict:
    return {
        "goal": {
            "improve_harness": {"scope": "out_of_scope"},
            "improve_skills": ["seed"],
            "avoid": "generic advice",
        },
        "reasoning": "The skill is incomplete.",
        "plan": "Apply the named operation.",
        "action": {
            "ops": [
                op
                or {
                    "op": "update",
                    "skills": [
                        {
                            "skill": "seed",
                            "goal": "Improve it.",
                            "facet": "workflow",
                            "sections": [
                                {"section": "workflow", "goal": "Add checks."}
                            ],
                        }
                    ],
                }
            ]
        },
        "feedback_to": "diagnosis",
    }


def valid_verification(skill: str, action=None) -> dict:
    return {
        "diagnosis": None,
        "verification_steps": [{"skill": skill, "steps": []}],
        "nod": None,
        "result": None,
        "feedback": {
            "overall_status": "pass",
            "overall_feedback": "all checks pass",
            "retry_budget": 1,
            "replay": {
                "available": False,
                "status": "not_run",
                "reason": "No post-edit replay was provided.",
                "before": None,
                "after": None,
            },
            "action": action,
            "per_skill": [
                {
                    "skill": skill,
                    "status": "pass",
                    "feedback": "pass",
                    "retries_used": 0,
                    "action": None,
                }
            ],
            "ood": [],
        },
        "changelog": None,
    }


class ContractTests(unittest.TestCase):
    def test_initialize_workspace_is_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "workspace"
            (template / "run/cut").mkdir(parents=True)
            (template / "run/cut/stale.json").write_text("{}\n")
            (template / "outside").mkdir()
            (template / "bad-link").symlink_to(template / "outside")
            target = root / "new-run"
            with patch.object(runner, "ROOT", root):
                runner.initialize_workspace(target)
            self.assertTrue((target / "traces/raw/codex").is_dir())
            self.assertTrue((target / "traces/derived/cut").is_dir())
            self.assertFalse((target / "run/cut/stale.json").exists())
            self.assertFalse((target / "bad-link").exists())
            self.assertFalse(
                (target / "target/to_be_improved_skills_metadata/metadata.json").exists()
            )

    def test_pipeline_timings_write_local_global_and_chrome_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/timed-run"
            workspace.mkdir(parents=True)
            with runner.pipeline_metrics.span(
                workspace,
                "goal",
                "finding-a",
                "llm_agent",
                backend="cursor",
                model="test-model",
            ):
                pass
            local = workspace / "logs/metrics.sqlite"
            shared = workspace.parents[1] / "metrics.sqlite"
            for database in (local, shared):
                with sqlite3.connect(database) as connection:
                    row = connection.execute(
                        "SELECT run_id, phase, category, backend, model "
                        "FROM pipeline_spans"
                    ).fetchone()
                self.assertEqual(
                    row,
                    (
                        "timed-run",
                        "goal",
                        "llm_agent",
                        "cursor",
                        "test-model",
                    ),
                )
            trace = json.loads(
                (workspace / "logs/pipeline-trace.json").read_text()
            )
            self.assertEqual(trace["traceEvents"][0]["ph"], "M")
            complete = next(
                event for event in trace["traceEvents"] if event["ph"] == "X"
            )
            self.assertLess(complete["pid"], 2**31)
            self.assertLess(complete["tid"], 2**31)
            with runner.pipeline_metrics.span(
                workspace, "goal", "finding-b", "llm_agent"
            ):
                pass
            rebuilt = json.loads(
                (workspace / "logs/pipeline-trace.json").read_text()
            )
            tracks = {
                event["tid"]
                for event in rebuilt["traceEvents"]
                if event["ph"] == "X"
            }
            self.assertEqual(len(tracks), 2)
            self.assertTrue(
                (workspace / "logs/pipeline-timings.jsonl").is_file()
            )
            dashboard = Path(directory) / "dashboard.html"
            metrics_dashboard.render(shared, dashboard)
            rendered = dashboard.read_text()
            self.assertIn("timed-run", rendered)
            self.assertIn("Cross-run phase statistics", rendered)
            self.assertIn("Phase wall", rendered)
            status = workspace / "run/status/goal/live.json"
            status.parent.mkdir(parents=True)
            status.write_text(
                json.dumps(
                    {
                        "stage": "goal",
                        "item": "live",
                        "state": "started",
                        "started_at": datetime.now(UTC).isoformat(),
                    }
                )
            )
            server = metrics_dashboard.make_server(
                shared, "127.0.0.1", 0, 0.25
            )
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                port = server.server_address[1]
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/metrics"
                ) as response:
                    payload = json.load(response)
                self.assertEqual(payload["run_count"], 1)
                self.assertEqual(payload["runs"][0]["run_id"], "timed-run")
                self.assertEqual(payload["runs"][0]["phases"][0]["phase"], "goal")
                self.assertIn("spans", payload["runs"][0])
                self.assertEqual(payload["runs"][0]["active"][0]["stage"], "goal")
                progress = payload["runs"][0]["progress"]
                goal_progress = next(
                    row for row in progress["stages"] if row["stage"] == "goal"
                )
                self.assertEqual(goal_progress["state"], "running")
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/"
                ) as response:
                    live = response.read().decode()
                self.assertIn('data-tab="total"', live)
                self.assertIn("Running now:", live)
                self.assertIn("Current progress", live)
                self.assertIn("Selected findings:", live)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            report = runner.pipeline_metrics.write_run_report(workspace)
            self.assertIsNotNone(report)
            document = json.loads(report.read_text())
            self.assertEqual(document["run_id"], "timed-run")
            self.assertEqual(document["phases"][0]["peak_concurrency"], 1)
            overlapped = runner.pipeline_metrics.summarize_spans(
                [
                    {
                        "phase": "label-traces-cluster",
                        "category": "llm_agent",
                        "item": "a",
                        "started_at": "t0",
                        "started_at_us": 0,
                        "duration_us": 5_000_000,
                        "status": "ok",
                        "backend": "cursor",
                        "model": "m",
                        "metadata": {
                            "queue_wait_ms": 1.0,
                            "slice_tokens": 40,
                            "slice_user_turns": 2,
                            "workers": 16,
                        },
                    },
                    {
                        "phase": "label-traces-cluster",
                        "category": "llm_agent",
                        "item": "b",
                        "started_at": "t1",
                        "started_at_us": 1_000_000,
                        "duration_us": 5_000_000,
                        "status": "ok",
                        "backend": "cursor",
                        "model": "m",
                        "metadata": {
                            "queue_wait_ms": 2.0,
                            "slice_tokens": 50,
                            "slice_user_turns": 3,
                        },
                    },
                ]
            )
            phase = overlapped["phases"][0]
            self.assertEqual(phase["peak_concurrency"], 2)
            self.assertLess(phase["wall_seconds"], phase["sum_seconds"])
            self.assertEqual(overlapped["spans"][0]["slice_user_turns"], 2)

    def test_recreated_run_clears_stale_shared_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/reused"
            workspace.mkdir(parents=True)
            with runner.pipeline_metrics.span(
                workspace, "goal", "old-attempt", "llm_agent"
            ):
                pass
            shared = workspace.parents[1] / "metrics.sqlite"
            runner.pipeline_metrics.clear_shared_run(workspace)
            with sqlite3.connect(shared) as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM pipeline_spans WHERE run_id = ?",
                    ("reused",),
                ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_session_log_slice_and_queue_are_in_the_timing_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "tee.jsonl"
            runner.run(
                ["python3", "-c", "print('tool_use one')"],
                log_path=log_path,
                cwd=root,
            )
            self.assertEqual(runner.session_counts(log_path)["tool_events"], 1)
            workspace = root / "workspace/runs/slice-run"
            finding = workspace / "traces/derived/findings/sig-1"
            finding.mkdir(parents=True)
            (finding / "finding.json").write_text(
                json.dumps(
                    {
                        "slice": {
                            "user_turns": 2,
                            "token_estimate": 80,
                            "turns": [
                                {"truncated": False},
                                {"truncated": True},
                            ],
                        }
                    }
                )
            )
            measured = runner.diagnosis_slice_metadata(
                workspace, "sig-1", "finding"
            )
            self.assertEqual(measured["slice_tokens"], 80)
            self.assertEqual(measured["slice_user_turns"], 2)
            self.assertTrue(measured["slice_truncated"])
            ready = time.time_ns() // 1000 - 1_500_000
            runner.record_queue(
                workspace,
                "operation-queue",
                "op-1",
                ready,
                {
                    "conflicts": ["audit-project-ui"],
                    "batch_index": 2,
                    "workers": 16,
                },
            )
            report_path = runner.pipeline_metrics.write_run_report(workspace)
            report = json.loads(report_path.read_text())
            queued = [
                row
                for row in report["spans"]
                if row["phase"] == "operation-queue"
            ]
            self.assertEqual(queued[0]["conflicts"], ["audit-project-ui"])
            self.assertEqual(queued[0]["batch_index"], 2)
            self.assertGreater(queued[0]["queue_wait_ms"], 1000)
            self.assertIn("conflicts", queued[0]["detail"])

    def test_edit_and_judge_decisions_are_on_the_trace_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/audit-run"
            (workspace / "run/sig-a/ops/1").mkdir(parents=True)
            (workspace / "run/goal-reduction.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "input_operation_count": 2,
                        "selected_operation_count": 1,
                        "decisions": [
                            {
                                "cluster": "sig-a",
                                "op_index": 1,
                                "decision": "selected",
                                "severity": "critical",
                                "confidence": 0.5,
                                "score": -3,
                                "match_score": 1,
                                "super_score": 9,
                            },
                            {
                                "cluster": "sig-b",
                                "op_index": 1,
                                "decision": "below_gate",
                                "selected_cluster": "sig-a",
                                "selected_op_index": 1,
                                "super_score": 0.2,
                            },
                        ],
                    }
                )
            )
            verification = workspace / "run/sig-a/ops/1/verification.json"
            verification.write_text(
                json.dumps(
                    {
                        "feedback": {
                            "overall_status": "fail",
                            "retry_budget": 1,
                            "action": {"op": "back", "to": "Update"},
                            "per_skill": [
                                {
                                    "skill": "audit-project-ui",
                                    "status": "fail",
                                    "retries_used": 1,
                                }
                            ],
                        }
                    }
                )
            )
            runner._emit_edit_decisions(workspace, 5, 0.0)
            runner._emit_judge_decision(workspace, "sig-a", 1, verification, 1)
            runner._emit_judge_decision(workspace, "sig-a", 1, verification, 2)
            trace = json.loads(
                (workspace / "logs/pipeline-trace.json").read_text()
            )
            instants = [
                event for event in trace["traceEvents"] if event["ph"] == "i"
            ]
            names = {event["name"] for event in instants}
            self.assertEqual(names, {"edit-decision", "judge-decision"})
            self.assertTrue(all(event.get("s") == "t" for event in instants))
            self.assertTrue(all("dur" not in event for event in instants))
            audit = (workspace / "logs/audit.jsonl").read_text().splitlines()
            self.assertEqual(len(audit), 4)
            report = json.loads(
                runner.pipeline_metrics.write_run_report(workspace).read_text()
            )
            self.assertEqual(report["policy"]["max_ops_per_skill"], 5)
            self.assertEqual(report["policy"]["min_super_score"], 0.0)
            self.assertEqual(report["policy"]["retry_budget"], 1)
            self.assertEqual(report["policy"]["max_attempts"], 2)
            dropped = next(
                row for row in report["edits"] if row["decision"] == "below_gate"
            )
            self.assertEqual(dropped["super_score"], 0.2)
            self.assertNotIn("publication_accepted", dropped)
            kept = next(
                row for row in report["edits"] if row["decision"] == "selected"
            )
            self.assertEqual(kept["judge_action"], "back")
            self.assertEqual(kept["judge_to"], "Update")
            self.assertEqual(kept["retries_used"], 1)
            self.assertEqual(kept["failed_skills"], ["audit-project-ui"])
            judge_spans = sorted(
                (
                    row
                    for row in report["spans"]
                    if row["phase"] == "judge-decision"
                ),
                key=lambda row: row["attempt"],
            )
            self.assertEqual(
                [row["will_retry"] for row in judge_spans],
                [True, False],
            )
            self.assertEqual(judge_spans[0]["detail"]["judge_action"], "back")

    def test_status_records_duration_from_started_to_done(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runner.write_status(workspace, "goal", "item", "started")
            runner.write_status(workspace, "goal", "item", "done")
            status = json.loads(
                (workspace / "run/status/goal/item.json").read_text()
            )
            self.assertEqual(status["state"], "done")
            self.assertIn("started_at", status)
            self.assertGreaterEqual(status["duration_ms"], 0)

    def test_goal_rejects_empty_ops_and_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "goal.json"
            empty = valid_goal()
            empty["action"]["ops"] = []
            write_json(path, empty)
            with self.assertRaises(contracts.ContractError):
                contracts.validate_goal(path)
            empty["goal"]["improve_skills"] = []
            empty["action"].update(
                {
                    "disposition": "no_change",
                    "reason": "The finding is an infrastructure failure.",
                }
            )
            write_json(path, empty)
            contracts.validate_goal(path)
            with self.assertRaises(contracts.ContractError):
                contracts.validate_goal(path, exactly_one_op=True)
            placeholder = valid_goal()
            placeholder["reasoning"] = "<reason>"
            write_json(path, placeholder)
            with self.assertRaises(contracts.ContractError):
                contracts.validate_goal(path)
            inline_code = valid_goal()
            inline_code["reasoning"] = "Remove the duplicate `<main>` landmark."
            write_json(path, inline_code)
            contracts.validate_goal(path)

    def test_capability_tree_must_exist_and_not_be_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(SystemExit):
                type_checker.leaf_paths(root / "missing")
            empty = root / "empty"
            empty.mkdir()
            with self.assertRaises(SystemExit):
                type_checker.leaf_paths(empty)
            (empty / "job").mkdir()
            self.assertEqual(type_checker.leaf_paths(empty), {"job"})
            taxonomy = root / "skill_capabilites.json"
            write_json(
                taxonomy,
                {
                    "schema_version": 1,
                    "dimensions": {
                        "domain": {"ai": ["agent"]},
                        "audience": {"unspecified": []},
                    },
                },
            )
            self.assertEqual(
                type_checker.leaf_paths(taxonomy),
                {"domain/ai", "domain/ai/agent", "audience/unspecified"},
            )
            self.assertNotIn(
                "audience/unspecified/ai/openai_official--skills",
                type_checker.leaf_paths(type_checker.DEFAULT_TREE),
            )

    def test_codex_normalization_is_bounded_deterministic_and_provenanced(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            raw = workspace / "traces/raw/codex/root.jsonl"
            rows = codex_trace_rows()
            rows.insert(
                2,
                {
                    "timestamp": "2026-01-01T00:00:01Z",
                    "ordinal": 3,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "developer",
                        "content": [{"text": "private system instructions"}],
                    },
                },
            )
            rows.insert(
                4,
                {
                    "timestamp": "2026-01-01T00:00:02Z",
                    "ordinal": 4,
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "call_id": "call-1",
                        "name": "shell",
                        "arguments": {"command": "deploy"},
                    },
                },
            )
            rows.insert(
                5,
                {
                    "timestamp": "2026-01-01T00:00:02Z",
                    "ordinal": 5,
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call_output",
                        "call_id": "call-1",
                        "output": "ERROR data:image/png;base64," + "A" * 20000,
                    },
                },
            )
            rows.append(
                {
                    "timestamp": "2026-01-01T00:00:05Z",
                    "ordinal": 9,
                    "type": "compacted",
                    "payload": {"data": "hidden reasoning " + "x" * 50000},
                }
            )
            write_jsonl(raw, rows)
            child_rows = codex_trace_rows("child", "child-turn", "child request")
            child_rows[0]["payload"]["parent_thread_id"] = "session-a"
            write_jsonl(
                workspace / "traces/raw/codex/child.jsonl", child_rows
            )
            original = raw.read_bytes()
            config = AGENTS / "common/preprocessing-config.json"
            first = runner.normalizer.normalize(workspace, config)
            turn_path = next(
                (workspace / "traces/derived/normalized/turns").glob("*.json")
            )
            first_turn = turn_path.read_text()
            second = runner.normalizer.normalize(workspace, config)
            self.assertEqual(raw.read_bytes(), original)
            self.assertEqual(first["normalized_turns"], 1)
            self.assertEqual(second["normalized_turns"], 1)
            self.assertEqual(turn_path.read_text(), first_turn)
            turn = contracts.validate_canonical_turn(turn_path)
            rendered = json.dumps(turn)
            self.assertNotIn("private system instructions", rendered)
            self.assertNotIn("hidden reasoning", rendered)
            evidence = workspace / turn["tool_summary"]["evidence_path"]
            evidence_text = evidence.read_text()
            self.assertIn("[base64 content removed]", evidence_text)
            self.assertNotIn("A" * 100, evidence_text)
            self.assertGreater(first["reduction_ratio"], 0.9)
            self.assertTrue((workspace / "logs/metrics.sqlite").is_file())

    def test_codex_normalization_uses_real_message_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            rows = codex_trace_rows()
            rows[2]["payload"].update(
                {
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "<in-app-browser-context>ambient UI</"
                                "in-app-browser-context>\n## My request:\n"
                                "Keep only this request"
                            ),
                        }
                    ],
                    "internal_chat_message_metadata_passthrough": {
                        "turn_id": "turn-a",
                        "content_item_kinds": ["user.text"],
                    },
                }
            )
            rows[2]["metadata"] = {"user_input_order": 7}
            rows.insert(
                2,
                {
                    "timestamp": "2026-01-01T00:00:01Z",
                    "ordinal": 2,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "open page"}],
                        "internal_chat_message_metadata_passthrough": {
                            "turn_id": "turn-a",
                            "content_item_kinds": [
                                "additional_content.codex_apps_open_page"
                            ],
                        },
                    },
                },
            )
            rows[4]["payload"]["phase"] = "final_answer"
            rows.insert(
                5,
                {
                    "timestamp": "2026-01-01T00:00:03Z",
                    "ordinal": 5,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": [
                            {"type": "output_text", "text": "later commentary"}
                        ],
                        "internal_chat_message_metadata_passthrough": {
                            "turn_id": "turn-a"
                        },
                    },
                },
            )
            write_jsonl(
                workspace / "traces/raw/codex/root.jsonl", rows
            )
            runner.normalizer.normalize(
                workspace, AGENTS / "common/preprocessing-config.json"
            )
            turn_path = next(
                (workspace / "traces/derived/normalized/turns").glob("*.json")
            )
            turn = contracts.validate_canonical_turn(turn_path)
            self.assertEqual(turn["user"]["text"], "Keep only this request")
            self.assertEqual(
                turn["assistant"]["text"], "Updated and verified the script."
            )

    def test_mixed_source_adapters_emit_stable_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/codex/codex.jsonl",
                codex_trace_rows(),
            )
            write_jsonl(
                workspace / "traces/raw/claude/claude.jsonl",
                claude_trace_rows(),
            )
            write_jsonl(
                workspace / "traces/raw/cursor/cursor.jsonl",
                cursor_trace_rows(),
            )
            config = AGENTS / "common/preprocessing-config.json"
            first = runner.normalizer.normalize(workspace, config)
            first_turns = {
                path.name: path.read_text()
                for path in (
                    workspace / "traces/derived/normalized/turns"
                ).glob("*.json")
            }
            second = runner.normalizer.normalize(workspace, config)
            second_turns = {
                path.name: path.read_text()
                for path in (
                    workspace / "traces/derived/normalized/turns"
                ).glob("*.json")
            }
            manifest = json.loads(
                (
                    workspace / "traces/derived/normalized/manifest.json"
                ).read_text()
            )
            self.assertEqual(first_turns, second_turns)
            self.assertEqual(manifest["source"], "mixed")
            self.assertEqual(
                manifest["source_adapters"], ["claude", "codex", "cursor"]
            )
            self.assertEqual(first["normalized_turns"], 3)
            self.assertEqual(second["normalized_turns"], 3)
            turns = [json.loads(value) for value in first_turns.values()]
            self.assertEqual(
                {turn["source"] for turn in turns},
                {"claude", "codex", "cursor"},
            )
            self.assertTrue(
                all(
                    turn["trace_id"].startswith(f"{turn['source']}:")
                    for turn in turns
                )
            )
            self.assertTrue(
                all(turn["provenance"]["raw_file"] for turn in turns)
            )

    def test_unknown_trace_source_fails_visibly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/cursor/unknown.jsonl",
                [{"kind": "mystery", "payload": "not a chat trace"}],
            )
            with self.assertRaisesRegex(SystemExit, "no source adapter recognized"):
                runner.normalizer.normalize(
                    workspace, AGENTS / "common/preprocessing-config.json"
                )

    def test_detector_text_removes_wrappers_but_keeps_user_request(self) -> None:
        text = (
            '<image name="shot.png">binary-looking wrapper</image>\n'
            "<in-app-browser-context>ambient page text</in-app-browser-context>\n"
            "Please finish the calendar setup."
        )
        self.assertEqual(
            signals.detector_text(text), "Please finish the calendar setup."
        )

    def test_infrastructure_failure_is_routed_out_of_skill_evolution(self) -> None:
        full_config = json.loads(
            (AGENTS / "common/preprocessing-config.json").read_text()
        )
        config = full_config["signals"]
        turn = {
            "trace_id": "codex:session:turn",
            "session_id": "session",
            "_path": "traces/derived/normalized/turns/turn.json",
            "timestamp": "2026-01-01T00:00:00Z",
            "user": {"text": "Please continue."},
            "assistant": {"text": ""},
            "outcome": {
                "status": "failed",
                "error": "HTTP 429 Too Many Requests",
            },
            "tool_summary": {"error_count": 0},
            "timing": {},
        }
        second_turn = json.loads(json.dumps(turn))
        second_turn["trace_id"] = "codex:session:turn-2"
        second_turn["_path"] = "traces/derived/normalized/turns/turn-2.json"
        second_turn["timestamp"] = "2026-01-01T00:00:01Z"
        findings = signals._session_findings(
            "session", [turn, second_turn], config
        )
        finding = next(
            row for row in findings if row["detector"] == "missing-final-response"
        )
        self.assertEqual(finding["routing"], "infrastructure")
        self.assertEqual(finding["evidence"][0]["field"], "outcome.error")
        tool_loop = next(
            row for row in findings if row["detector"] == "tool-error-loop"
        )
        self.assertEqual(tool_loop["routing"], "infrastructure")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            output_root = workspace / "traces/derived"
            for source in (turn, second_turn):
                stored = dict(source)
                stored.pop("_path")
                write_json(
                    output_root
                    / "normalized/turns"
                    / f"{stored['trace_id'].rsplit(':', 1)[-1]}.json",
                    stored,
                )
            signals.run(
                workspace,
                output_root,
                full_config,
                workspace / "logs/metrics.sqlite",
                "test",
            )
            self.assertTrue(
                (output_root / "signals/findings.jsonl").read_text().strip()
            )
            self.assertEqual(
                (output_root / "signals/selected-manifest.jsonl").read_text(),
                "",
            )

    def test_cursor_session_is_limited_to_the_stage_view_and_run_directory(
        self,
    ) -> None:
        view = Path("/tmp/skill-evolver-sessions/example-goal/skill_evolving_agents")
        workspace = Path("/tmp/skill-evolver-workers/example")
        prompt = runner.instruction(
            "goal",
            "This isolated session is cluster <gate-only-run>.",
        )
        self.assertIn("Fast decision. One pass.", prompt)
        self.assertIn("03_goal_agent/skill-select/skill.md", prompt)
        self.assertIn("gate-only-run", prompt)
        self.assertNotIn(str(runner.REPO), prompt)
        command = runner.cursor_command(view, workspace, prompt, "grok-4.7-low")
        self.assertEqual(command[command.index("--workspace") + 1], str(view))
        self.assertEqual(
            [command[index + 1] for index, item in enumerate(command) if item == "--add-dir"],
            [str(workspace)],
        )
        self.assertNotIn(str(runner.REPO), command)
        self.assertFalse(
            Path(runner.SESSION_ROOT).resolve().is_relative_to(runner.REPO.resolve())
        )

    def test_cut_algorithms_keep_a_five_turn_repetition_window_and_long_turns(
        self,
    ) -> None:
        cuts = load(
            "trace_cut_algorithms_test",
            AGENTS / "01_preprocessing_agent/trace_mining/cut_algorithms.py",
        )
        config = json.loads(
            (AGENTS / "common/preprocessing-config.json").read_text()
        )
        names = [item["name"] for item in cuts.algorithm_catalog()]
        self.assertEqual(config["cut"]["algorithms"], names)

        def turn(index: int, user: str, duration_ms: int | None = None) -> dict:
            return {
                "trace_id": f"t{index}",
                "session_id": "session",
                "_path": f"traces/derived/normalized/turns/t{index}.json",
                "timestamp": f"2026-01-01T00:00:{index:02d}Z",
                "user": {"text": user},
                "assistant": {"text": "done"},
                "outcome": {"status": "completed", "error": ""},
                "tool_summary": {"error_count": 0},
                "timing": {}
                if duration_ms is None
                else {"duration_ms": duration_ms},
            }

        repeated = "deploy the same railway service again"
        session = [
            turn(0, "show the weekly page"),
            turn(1, repeated),
            turn(2, repeated),
            turn(3, repeated),
            turn(4, "stop and explain the failure"),
            turn(5, "unrelated calendar question"),
        ]
        windows = cuts.select_windows(session, config)
        repetition = next(
            item
            for item in windows
            if item.algorithm == "consecutive_repetition"
        )
        self.assertEqual(list(repetition.indexes), [0, 1, 2, 3, 4])
        self.assertEqual(list(repetition.anchor_indexes), [1, 2, 3])
        self.assertLessEqual(len(repetition.indexes), config["cut"]["max_window"])

        long_session = [
            turn(0, "prepare the release"),
            turn(1, "publish to railway", 300_000),
            turn(2, "what failed"),
        ]
        long_windows = cuts.select_windows(long_session, config)
        long_turn = next(
            item for item in long_windows if item.algorithm == "long_turn"
        )
        self.assertEqual(list(long_turn.anchor_indexes), [1])
        self.assertEqual(list(long_turn.indexes), [0, 1, 2])
        huge = dict(turn(0, "short request", 600_000))
        huge["assistant"] = {"text": "x" * 20000}
        clipped = cuts.bounded_slice(
            [huge], {"cut": {"max_tokens": 100, "max_user_turns": 1}}
        )
        self.assertLessEqual(clipped["token_estimate"], 100)
        self.assertTrue(clipped["turns"][0]["truncated"])
        self.assertLessEqual(len(clipped["turns"][0]["assistant"]), 400)
        budget = cuts.budget_summary(
            [
                {
                    "algorithm": "long_turn",
                    "session_id": "session",
                    "trace_ids": ["a"],
                    "slice": clipped,
                }
            ],
            {"cut": {}},
        )
        self.assertEqual(budget["max_user_turns"], 5)
        self.assertEqual(budget["max_tokens"], 2000)
        self.assertEqual(budget["truncated_windows"], 1)
        self.assertLessEqual(budget["max_tokens_seen"], budget["max_tokens"])
        self.assertEqual(
            cuts.enabled_algorithms({"cut": {"algorithms": []}}), []
        )
        with self.assertRaises(ValueError):
            cuts.enabled_algorithms({"cut": {"algorithms": ["not-an-algorithm"]}})

    def test_feedback_detectors_select_pointer_scopes_and_store_metrics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            rows: list[dict] = []

            def add_turn(index: int, user: str, tool_error: bool = False) -> None:
                second = index * 4
                rows.append(
                    {
                        "role": "user",
                        "id": f"turn-{index}",
                        "timestamp": f"2026-01-01T00:00:{second:02d}Z",
                        "content": user,
                    }
                )
                if tool_error:
                    rows.append(
                        {
                            "role": "tool",
                            "timestamp": f"2026-01-01T00:00:{second + 1:02d}Z",
                            "name": "shell",
                            "error": True,
                            "content": "failed",
                        }
                    )
                if index != 6:
                    rows.append(
                        {
                            "role": "assistant",
                            "timestamp": f"2026-01-01T00:00:{second + 2:02d}Z",
                            "content": "working",
                        }
                    )

            add_turn(1, "good correct result")
            add_turn(2, "great working result")
            add_turn(3, "No fix the broken deploy script", True)
            add_turn(4, "No fix the broken deploy script", True)
            add_turn(5, "Keep going and finish the broken work")
            add_turn(6, "Keep going and finish the broken work")
            write_jsonl(workspace / "traces/raw/cursor/session.jsonl", rows)
            result = runner.mining_engine.run(
                workspace,
                AGENTS / "common/preprocessing-config.json",
                clustered=True,
            )
            findings_path = (
                workspace / "traces/derived/signals/findings.jsonl"
            )
            first_findings = findings_path.read_text()
            runner.mining_engine.run(
                workspace,
                AGENTS / "common/preprocessing-config.json",
                clustered=True,
            )
            self.assertEqual(findings_path.read_text(), first_findings)
            detectors = set(result["active"]["signals"]["detectors"])
            self.assertTrue(
                {
                    "correction-heavy",
                    "keep-going-loop",
                    "repeated-instructions",
                    "negative-drift",
                    "missing-final-response",
                    "tool-error-loop",
                    "rapid-corrections",
                }.issubset(detectors)
            )
            selected = (
                workspace / "traces/derived/signals/selected-manifest.jsonl"
            ).read_text().splitlines()
            self.assertTrue(selected)
            for directory_path in (
                workspace / "traces/derived/findings"
            ).iterdir():
                finding = json.loads(
                    (directory_path / "finding.json").read_text()
                )
                manifest = [
                    json.loads(line)
                    for line in (
                        directory_path / "manifest.jsonl"
                    ).read_text().splitlines()
                ]
                self.assertEqual(
                    {row["trace_id"] for row in manifest},
                    set(finding["trace_ids"]),
                )
            with sqlite3.connect(workspace / "logs/metrics.sqlite") as database:
                count = database.execute(
                    "SELECT selected_count FROM trace_signal_runs"
                ).fetchone()[0]
            self.assertEqual(count, len(selected))

    def test_trace_features_and_pointer_clusters_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/codex/a.jsonl",
                codex_trace_rows(
                    "a", "turn-a", "Fix deployment build error", "Build fixed"
                ),
            )
            write_jsonl(
                workspace / "traces/raw/codex/b.jsonl",
                codex_trace_rows(
                    "b", "turn-b", "Improve page spacing", "Spacing fixed"
                ),
            )
            config = AGENTS / "common/preprocessing-config.json"
            result = runner.mining_engine.run(
                workspace, config, clustered=True
            )
            self.assertEqual(
                result["active"]["clustering"]["trace_count"], 2
            )
            outputs = runner.validate_preprocessing(workspace, True)
            self.assertIn(workspace / "traces/derived/cluster", outputs)
            manifests = list(
                (workspace / "traces/derived/cluster").glob(
                    "*/manifest.jsonl"
                )
            )
            self.assertTrue(manifests)
            self.assertFalse(
                list(
                    (workspace / "traces/derived/cluster").glob("*/*.json")
                )
            )
            trace_ids = json.loads(
                (
                    workspace / "traces/derived/normalized/manifest.json"
                ).read_text()
            )["eligible_trace_ids"]
            write_jsonl(
                workspace / "traces/inputs/embeddings.jsonl",
                [
                    {
                        "trace_id": trace_id,
                        "vector": [1.0, float(index)],
                    }
                    for index, trace_id in enumerate(trace_ids)
                ],
            )
            embedded = runner.cluster_builder.build(
                workspace,
                config,
                clustered=True,
                strategy_override="embedding",
            )
            self.assertEqual(embedded["strategy"], "embedding")

    def test_deduplication_clusters_representatives_and_expands_aliases(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            rows = [
                {
                    "role": "user",
                    "id": "one",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "content": "Fix deploy script failure now",
                },
                {
                    "role": "assistant",
                    "timestamp": "2026-01-01T00:00:01Z",
                    "content": "Fixed deploy script failure",
                },
                {
                    "role": "user",
                    "id": "two",
                    "timestamp": "2026-01-01T00:00:02Z",
                    "content": "Fix deploy script failure now",
                },
                {
                    "role": "assistant",
                    "timestamp": "2026-01-01T00:00:03Z",
                    "content": "Fixed deploy script failure",
                },
                {
                    "role": "user",
                    "id": "three",
                    "timestamp": "2026-01-01T00:00:04Z",
                    "content": "Fix deploy script failure quickly now",
                },
                {
                    "role": "assistant",
                    "timestamp": "2026-01-01T00:00:05Z",
                    "content": "Fixed deploy script failure",
                },
            ]
            write_jsonl(workspace / "traces/raw/cursor/session.jsonl", rows)
            config = json.loads(
                (AGENTS / "common/preprocessing-config.json").read_text()
            )
            config["deduplication"]["near_duplicate_threshold"] = 0.1
            runner.normalizer.normalize(workspace, config)
            result = runner.cluster_builder.build(
                workspace, config, clustered=True
            )
            self.assertEqual(result["trace_count"], 3)
            self.assertEqual(result["unique_trace_count"], 1)
            dedup_rows = [
                json.loads(line)
                for line in (
                    workspace
                    / "traces/derived/features/dedup-manifest.jsonl"
                ).read_text().splitlines()
            ]
            self.assertEqual(
                {row["relation"] for row in dedup_rows},
                {"representative", "exact_duplicate", "near_duplicate"},
            )
            cluster_dirs = list(
                (workspace / "traces/derived/cluster").iterdir()
            )
            self.assertEqual(len(cluster_dirs), 1)
            members = (
                cluster_dirs[0] / "manifest.jsonl"
            ).read_text().splitlines()
            self.assertEqual(len(members), 3)
            roles = {
                json.loads(line)["role"]
                for line in (
                    cluster_dirs[0] / "representatives.jsonl"
                ).read_text().splitlines()
            }
            self.assertEqual(roles, {"representative"})

    def test_mining_profiles_are_validated_and_experiments_are_isolated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/codex/a.jsonl",
                codex_trace_rows(),
            )
            config = AGENTS / "common/preprocessing-config.json"
            first = runner.mining_engine.run(
                workspace,
                config,
                clustered=True,
                experiment_profiles=["text-only"],
            )
            active_manifest = json.loads(
                (workspace / "traces/derived/normalized/manifest.json").read_text()
            )
            experiment_manifest = json.loads(
                (
                    workspace
                    / "traces/derived/experiments/text-only/normalized/manifest.json"
                ).read_text()
            )
            self.assertEqual(
                active_manifest["mining_profile"]["profile"], "default"
            )
            self.assertEqual(
                experiment_manifest["mining_profile"]["profile"], "text-only"
            )
            self.assertTrue((workspace / "traces/derived/cluster").is_dir())
            self.assertFalse(
                (
                    workspace
                    / "traces/derived/experiments/text-only/cluster"
                ).exists()
            )
            second = runner.mining_engine.run(
                workspace,
                config,
                clustered=True,
                experiment_profiles=["text-only"],
            )
            self.assertEqual(
                first["active"]["fingerprint"],
                second["active"]["fingerprint"],
            )
            with sqlite3.connect(workspace / "logs/metrics.sqlite") as connection:
                profiles = connection.execute(
                    "SELECT profile, run_kind FROM trace_mining_profile_runs "
                    "ORDER BY run_kind"
                ).fetchall()
            self.assertEqual(
                profiles, [("default", "active"), ("text-only", "experiment")]
            )
            with self.assertRaises(
                runner.mining_engine.MiningConfigError
            ):
                runner.mining_engine.run(
                    workspace,
                    config,
                    clustered=True,
                    profile_name="missing",
                )
            with self.assertRaises(
                runner.mining_engine.MiningConfigError
            ):
                runner.mining_engine.run(
                    workspace,
                    config,
                    clustered=True,
                    experiment_profiles=["text-only", "text-only"],
                )

    def test_embedding_mining_profile_uses_external_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/codex/a.jsonl",
                codex_trace_rows(),
            )
            write_jsonl(
                workspace / "traces/inputs/embeddings.jsonl",
                [
                    {
                        "trace_id": "codex:session-a:turn-a",
                        "vector": [0.25, 0.75],
                    }
                ],
            )
            result = runner.mining_engine.run(
                workspace,
                AGENTS / "common/preprocessing-config.json",
                clustered=True,
                profile_name="embedding",
            )
            self.assertEqual(
                result["active"]["clustering"]["strategy"], "embedding"
            )

    def test_mining_registry_rejects_duplicate_and_unsafe_profiles(self) -> None:
        registry = runner.mining_engine.Registry()
        codex = registry.get("adapter", "codex")
        with self.assertRaises(runner.mining_engine.MiningConfigError):
            runner.mining_engine.Registry([codex, codex])
        config = json.loads(
            (AGENTS / "common/preprocessing-config.json").read_text()
        )
        config["profiles"]["../escape"] = config["profiles"]["default"]
        with self.assertRaises(runner.mining_engine.MiningConfigError):
            runner.mining_engine.load_profile(config, "../escape")

    def test_worker_workspace_omits_raw_vendor_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill_evolving_agents"
            workspace = root / "workspace/runs/run"
            write_jsonl(
                workspace / "traces/raw/codex/source.jsonl",
                codex_trace_rows(),
            )
            write_json(
                workspace / "traces/derived/normalized/turns/turn.json",
                {
                    "trace_id": "kept",
                },
            )
            with patch.object(runner, "ROOT", root):
                worker = runner.create_worker_workspace(
                    workspace, "goal", "item"
                )
            self.assertFalse((worker / "traces/raw").exists())
            self.assertTrue(
                (
                    worker
                    / "traces/derived/normalized/turns/turn.json"
                ).is_file()
            )

    def test_configurable_weighted_recall(self) -> None:
        config = recall_module.load_config(AGENTS / "common/recall-config.json")
        result = recall_module.recall(
            {
                "skill_capabilities_missing": [
                    {
                        "type": "domain/ai/agent",
                        "cluster": "cluster-a",
                        "confidence": 0.8,
                    }
                ]
            },
            {
                "skills_metadata": [
                    {
                        "skill": "seed",
                        "skill_types": [
                            {"type": "domain/ai", "weight": 0.9}
                        ],
                    }
                ]
            },
            ["seed"],
            ["cluster-a"],
            {"domain/ai", "domain/ai/agent"},
            config,
        )
        skill = result["clusters"][0]["skills"][0]
        self.assertEqual(result["matching"]["strategy"], "weighted_path_similarity")
        self.assertAlmostEqual(skill["score"], 0.504)
        self.assertEqual(skill["matches"][0]["similarity"], 0.7)

    def test_label_skills_prompt_names_the_validated_metadata_shape(self) -> None:
        prompt = (
            AGENTS
            / "02.1_label_skills_agent/existing_skills_labeler/skill.md"
        ).read_text()
        self.assertIn('"skills_metadata": [', prompt)
        self.assertIn('"skill": "<skill-directory-name>"', prompt)
        self.assertIn("The key is `skills_metadata`, not `skills`", prompt)

    def test_diagnosis_prompt_forbids_placeholder_quotes_in_evidence(self) -> None:
        prompt = (
            AGENTS
            / "02.2_label_traces_cluster_agent/dignosis/skill.md"
        ).read_text()
        self.assertIn("Never copy or quote placeholder text", prompt)
        self.assertIn("including `reasoning`, descriptions, and", prompt)
        self.assertIn("`evidence_list`", prompt)

    def test_goal_prompt_names_the_validated_no_change_shape(self) -> None:
        prompt = (
            AGENTS / "03_goal_agent/goal-generator/skill.md"
        ).read_text()
        self.assertIn("`goal` is always an object", prompt)
        self.assertIn('"improve_skills": []', prompt)
        self.assertIn('"feedback_to": "diagnosis"', prompt)
        self.assertIn('"disposition": "no_change"', prompt)
        self.assertIn("Write concrete values without angle brackets", prompt)

    def test_skill_format_names_and_aliases(self) -> None:
        format_path = AGENTS / "common/skill_format.json"
        document = json.loads(format_path.read_text())
        core = {
            row["name"]
            for row in document["sections"]
            if row.get("core") is True
        }
        self.assertEqual(
            core,
            {
                "overview",
                "when_to_use",
                "do_not_use",
                "workflow",
                "constraints",
                "verification",
                "output_format",
                "limitations",
            },
        )
        sections, aliases, dirs, others = format_checker.load_list(format_path)
        self.assertEqual(aliases["output"], "output_format")
        self.assertEqual(aliases["methodology"], "workflow")
        with tempfile.TemporaryDirectory() as directory:
            goal_path = Path(directory) / "goal.json"
            write_json(
                goal_path,
                {
                    "action": {
                        "ops": [
                            {
                                "op": "update",
                                "skills": [
                                    {
                                        "skill": "seed",
                                        "sections": [
                                            {"section": "output", "goal": "clarify"},
                                            {
                                                "section": "methodology",
                                                "goal": "order steps",
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                },
            )
            self.assertEqual(
                format_checker.check_goal(
                    goal_path, sections, dirs, others, aliases
                ),
                [],
            )

    def test_verification_action_belongs_to_judge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "verification.json"
            write_json(path, valid_verification("seed"))
            contracts.validate_verification(
                path, judged=False, expected_skills={"seed"}
            )
            value = valid_verification("seed", {"op": "pass", "to": ""})
            write_json(path, value)
            contracts.validate_verification(
                path, judged=True, expected_skills={"seed"}
            )
            value["feedback"]["overall_status"] = "fail"
            write_json(path, value)
            with self.assertRaises(contracts.ContractError):
                contracts.validate_verification(path, judged=True)

    def test_verification_replay_contract_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "verification.json"
            value = valid_verification("seed")
            value["feedback"]["replay"]["status"] = "pass"
            write_json(path, value)
            with self.assertRaises(contracts.ContractError):
                contracts.validate_verification(path, judged=False)
            value["feedback"]["replay"] = {
                "available": True,
                "status": "pass",
                "reason": "Targeted detector rerun.",
                "before": {"occurrences": 3},
                "after": {"occurrences": 0},
            }
            write_json(path, value)
            contracts.validate_verification(path, judged=False)

    def test_verification_builder_clears_actions(self) -> None:
        example = json.loads(
            (VERIFIER / "verification-output.example.json").read_text()
        )
        out = verification_builder.build(valid_goal(), example, {}, None)
        self.assertIsNone(out["feedback"]["action"])
        self.assertTrue(
            all(row["action"] is None for row in out["feedback"]["per_skill"])
        )

    def test_materialized_goal_contains_one_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            goal = valid_goal()
            goal["action"]["ops"].append(
                {"op": "delete", "skills": [{"skill": "old", "reason": "stale"}]}
            )
            path = runner.materialize_op_goal(
                workspace, "cluster-a", 2, goal, goal["action"]["ops"][1]
            )
            data = contracts.validate_goal(path, exactly_one_op=True)
            self.assertEqual(data["action"]["ops"][0]["op"], "delete")
            self.assertEqual(
                json.loads((workspace / "run/evolve-goal.json").read_text()), data
            )

    def test_no_change_goal_skips_operation_agents_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            goal = valid_goal()
            goal["goal"]["improve_skills"] = []
            goal["action"] = {
                "disposition": "no_change",
                "reason": "The finding is infrastructure-only.",
                "ops": [],
            }
            write_json(workspace / "run/scope-a/evolve-goal.json", goal)
            write_json(workspace / "run/evolve-goal.json", {"stale": True})
            write_json(workspace / "run/verification.json", {"stale": True})
            with patch.object(runner, "run_session") as run_session:
                runner.fanout_operations(
                    workspace, "run", ["scope-a"], 2, {}, None, True
                )
            run_session.assert_not_called()
            self.assertFalse((workspace / "run/evolve-goal.json").exists())
            self.assertFalse((workspace / "run/verification.json").exists())
            first = runner.write_pipeline_summary(workspace, ["scope-a"]).read_text()
            second = runner.write_pipeline_summary(workspace, ["scope-a"]).read_text()
            self.assertEqual(first, second)
            summary = json.loads(first)
            self.assertEqual(summary["no_change_scopes"], ["scope-a"])
            self.assertEqual(summary["operations"], [])

    def test_creation_policy_requires_recurrence_or_ood(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            finding = {
                "confidence": 0.9,
                "session_id": "one-session",
                "evidence": [{"trace_id": "a"}, {"trace_id": "b"}],
            }
            write_json(
                workspace / "traces/derived/findings/scope-a/finding.json",
                finding,
            )
            diagnosis_path = workspace / "run/scope-a/diagnosis.json"
            write_json(
                diagnosis_path,
                {
                    "skill_capabilities_missing": [{"type": "job/workflow"}],
                    "newly_detected_skill_capabilites_missing": [],
                },
            )
            create = {
                "op": "create",
                "skills": [
                    {
                        "skill": "new-skill",
                        "description": "New skill",
                        "sections": [
                            {"section": "workflow", "goal": "Add workflow."}
                        ],
                    }
                ],
            }
            with self.assertRaises(runner.pipeline_contracts.ContractError):
                runner.enforce_creation_policy(workspace, "scope-a", {}, create)
            write_json(
                diagnosis_path,
                {
                    "skill_capabilities_missing": [],
                    "newly_detected_skill_capabilites_missing": [
                        {"type": "job/new-capability"}
                    ],
                },
            )
            runner.enforce_creation_policy(workspace, "scope-a", {}, create)

    def test_parallel_finding_diagnosis_uses_isolated_workers_and_reducer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill_evolving_agents"
            workspace = root / "workspace/runs/run"
            (workspace / "logs").mkdir(parents=True)
            (workspace / "run").mkdir()
            seen: list[Path] = []

            def fake_session(
                stage, worker, prompt, auth, model, install, suffix, metadata=None
            ):
                self.assertEqual(stage, "label-traces-cluster")
                self.assertIn("traces/derived/findings", prompt)
                seen.append(worker)
                cluster = suffix.rsplit("-", 1)[-1]
                write_json(
                    worker / "run/diagnosis.json",
                    {
                        "skill_capabilities_missing": [
                            {
                                "type": "job/methodology",
                                "cluster": cluster,
                                "description": "missing process",
                                "confidence": 0.8,
                                "reasoning": "trace evidence",
                                "evidence_list": ["missing steps"],
                            }
                        ],
                        "newly_detected_skill_capabilites_missing": [],
                    },
                )

            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "run_session", side_effect=fake_session),
            ):
                aggregate = runner.fanout_diagnosis(
                    workspace,
                    "run",
                    ["a", "b"],
                    True,
                    2,
                    {},
                    None,
                    True,
                    "finding",
                )
            self.assertEqual(len(set(seen)), 2)
            self.assertTrue((workspace / "run/a/diagnosis.json").is_file())
            self.assertTrue((workspace / "run/b/diagnosis.json").is_file())
            self.assertEqual(
                len(json.loads(aggregate.read_text())["skill_capabilities_missing"]),
                2,
            )
            self.assertFalse((root / ".pipeline-workers").exists())

    def test_operation_batches_serialize_overlapping_skills(self) -> None:
        tasks = [
            {"affected": {"a"}, "conflicts": {"a"}},
            {"affected": {"b"}, "conflicts": {"b"}},
            {"affected": {"a", "c"}, "conflicts": {"a", "c"}},
        ]
        batches = runner.operation_batches(tasks)
        self.assertEqual(batches, [tasks[:2], tasks[2:]])

    def test_goal_reducer_removes_identical_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            operation = valid_goal()["action"]["ops"][0]
            tasks = [
                {
                    "cluster": finding,
                    "op_index": 1,
                    "op": operation,
                }
                for finding in ("finding-a", "finding-b")
            ]
            selected = runner.reduce_operation_tasks(workspace, tasks)
            self.assertEqual(len(selected), 1)
            reduction = json.loads(
                (workspace / "run/goal-reduction.json").read_text()
            )
            self.assertEqual(reduction["input_operation_count"], 2)
            self.assertEqual(reduction["selected_operation_count"], 1)
            self.assertEqual(
                [row["decision"] for row in reduction["decisions"]],
                ["selected", "duplicate"],
            )

    def test_same_skill_updates_bundle_into_one_verified_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def task(cluster, skill, section, confidence, kind="update"):
                if kind == "delete":
                    op = {
                        "op": "delete",
                        "skills": [{"skill": skill, "reason": "remove"}],
                    }
                else:
                    op = {
                        "op": "update",
                        "skills": [
                            {
                                "skill": skill,
                                "goal": section,
                                "facet": "workflow",
                                "sections": [
                                    {"section": section, "goal": section}
                                ],
                            }
                        ],
                    }
                goal = valid_goal(op)
                goal["goal"]["improve_skills"] = [skill]
                path = workspace / "run" / cluster / "ops" / "1" / "evolve-goal.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(goal))
                return {
                    "cluster": cluster,
                    "op_index": 1,
                    "op": op,
                    "op_goal": path,
                    "affected": {skill},
                    "conflicts": {skill},
                    "confidence": confidence,
                    "skill_goal": section,
                }

            bundled = runner.bundle_same_skill_updates(
                workspace,
                [
                    task("high", "audit", "workflow", 0.9),
                    task("mid", "audit", "constraints", 0.5),
                    task("low", "audit", "overview", 0.1),
                    task("other", "other-skill", "workflow", 0.4),
                    task("remove", "audit", "unused", 0.8, "delete"),
                ],
                2,
            )
            self.assertEqual(
                [item["cluster"] for item in bundled],
                ["high", "other", "remove"],
            )
            merged = bundled[0]
            sections = [
                row["section"]
                for row in merged["op"]["skills"][0]["sections"]
            ]
            self.assertEqual(sections, ["workflow", "constraints"])
            stored = json.loads(Path(merged["op_goal"]).read_text())
            self.assertEqual(len(stored["action"]["ops"]), 1)
            self.assertEqual(
                [row["cluster"] for row in stored["bundle"]["selected"]],
                ["high", "mid"],
            )
            self.assertEqual(stored["bundle"]["dropped"][0]["reason"], "over_cap")
            batches = runner.operation_batches(bundled)
            self.assertEqual(
                [[item["cluster"] for item in batch] for batch in batches],
                [["high", "other"], ["remove"]],
            )
            reduction = json.loads(
                (workspace / "run/goal-reduction.json").read_text()
            )
            decisions = {
                (row["cluster"], row["decision"])
                for row in reduction["decisions"]
            }
            self.assertIn(("mid", "bundled"), decisions)
            self.assertIn(("low", "over_cap"), decisions)
            self.assertEqual(reduction["selected_operation_count"], 3)
            publication = json.loads(
                (workspace / "run/low/ops/1/publication.json").read_text()
            )
            self.assertFalse(publication["accepted"])
            self.assertEqual(publication["reason"], "over_cap")

    def test_super_score_gate_ranks_ahead_of_raw_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def task(cluster, section, confidence):
                op = {
                    "op": "update",
                    "skills": [
                        {
                            "skill": "audit",
                            "goal": section,
                            "facet": "workflow",
                            "sections": [{"section": section, "goal": section}],
                        }
                    ],
                }
                goal = valid_goal(op)
                path = workspace / "run" / cluster / "ops" / "1" / "evolve-goal.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(goal))
                return {
                    "cluster": cluster,
                    "op_index": 1,
                    "op": op,
                    "op_goal": path,
                    "affected": {"audit"},
                    "conflicts": {"audit"},
                    "confidence": confidence,
                    "skill_goal": section,
                }

            write_json(
                workspace / "traces/derived/findings/critical/finding.json",
                {"confidence": 0.5, "severity": "critical", "score": -3},
            )
            write_json(
                workspace / "run/critical/label-matching.json",
                {
                    "clusters": [
                        {"skills": [{"skill": "audit", "score": 1.0}]}
                    ]
                },
            )
            write_json(
                workspace / "traces/derived/findings/confident/finding.json",
                {"confidence": 0.95, "severity": "low", "score": 0},
            )
            bundled = runner.bundle_same_skill_updates(
                workspace,
                [
                    task("confident", "workflow", 0.95),
                    task("critical", "constraints", 0.5),
                    task("weak", "overview", 0.2),
                ],
                5,
                0.5,
            )
            self.assertEqual([item["cluster"] for item in bundled], ["critical"])
            stored = json.loads(Path(bundled[0]["op_goal"]).read_text())
            selected = [row["cluster"] for row in stored["bundle"]["selected"]]
            self.assertEqual(selected, ["critical", "confident"])
            self.assertGreater(
                stored["bundle"]["selected"][0]["super_score"],
                stored["bundle"]["selected"][1]["super_score"],
            )
            dropped = {
                row["cluster"]: row["reason"] for row in stored["bundle"]["dropped"]
            }
            self.assertEqual(dropped, {"weak": "below_gate"})
            publication = json.loads(
                (workspace / "run/weak/ops/1/publication.json").read_text()
            )
            self.assertFalse(publication["accepted"])
            self.assertEqual(publication["reason"], "below_gate")

    def test_empty_selected_findings_produce_no_evolution_units(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "traces/derived/findings").mkdir(parents=True)
            self.assertEqual(
                runner.evolution_units(workspace, True, "finding"), []
            )

    def test_cluster_units_exclude_infrastructure_only_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            turns = workspace / "traces/derived/normalized/turns"
            infrastructure = {
                "assistant": {"text": ""},
                "outcome": {"error": "HTTP 429 Too Many Requests"},
            }
            substantive = {
                "assistant": {"text": "The requested work is incomplete."},
                "outcome": {"error": None},
            }
            write_json(turns / "infra.json", infrastructure)
            write_json(turns / "work.json", substantive)
            write_jsonl(
                workspace / "traces/derived/cluster/infra/manifest.jsonl",
                [{"turn_path": "traces/derived/normalized/turns/infra.json"}],
            )
            write_jsonl(
                workspace / "traces/derived/cluster/work/manifest.jsonl",
                [{"turn_path": "traces/derived/normalized/turns/work.json"}],
            )
            self.assertEqual(
                runner.evolution_units(workspace, True, "cluster"), ["work"]
            )

    def test_infrastructure_units_stay_when_config_includes_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            turns = workspace / "traces/derived/normalized/turns"
            write_json(
                turns / "infra.json",
                {
                    "assistant": {"text": ""},
                    "outcome": {"error": "HTTP 429 Too Many Requests"},
                },
            )
            write_jsonl(
                workspace / "traces/derived/cluster/infra/manifest.jsonl",
                [{"turn_path": "traces/derived/normalized/turns/infra.json"}],
            )
            write_json(
                workspace / "traces/derived/findings/infra/finding.json",
                {"routing": "infrastructure"},
            )
            write_json(
                workspace / "traces/derived/findings/work/finding.json",
                {"routing": "skill_evolution"},
            )
            self.assertEqual(
                runner.evolution_units(workspace, True, "finding"), ["work"]
            )
            config = json.loads(
                (AGENTS / "common/preprocessing-config.json").read_text()
            )
            config["signals"]["selection"][
                "include_infrastructure_failures"
            ] = True
            with patch.object(
                runner, "preprocessing_config", return_value=config
            ):
                self.assertEqual(
                    runner.evolution_units(workspace, True, "cluster"),
                    ["infra"],
                )
                self.assertEqual(
                    runner.evolution_units(workspace, True, "finding"),
                    ["infra", "work"],
                )
                self.assertFalse(
                    runner.infrastructure_evolution_blocked(workspace, "infra")
                )

    def test_infrastructure_create_is_refused_before_agents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            created = "preserve-request-after-provider-rate-limit"
            turns = workspace / "traces/derived/normalized/turns"
            write_json(
                turns / "infra.json",
                {
                    "assistant": {"text": ""},
                    "outcome": {"error": "HTTP 429 Too Many Requests"},
                },
            )
            write_jsonl(
                workspace / "traces/derived/cluster/push/manifest.jsonl",
                [{"turn_path": "traces/derived/normalized/turns/infra.json"}],
            )
            for skill, text in (
                ("audit-project-ui", "seed"),
                (created, "bad create"),
            ):
                path = workspace / "target/to_be_improved_skills" / skill
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text(text)
            write_json(
                workspace
                / "target/to_be_improved_skills_metadata/metadata.json",
                {
                    "skills_metadata": [
                        {
                            "skill": skill,
                            "skill_types": [
                                {"type": "job/workflow", "weight": 1.0}
                            ],
                            "unmatched_skill_types": [],
                        }
                        for skill in ("audit-project-ui", created)
                    ]
                },
            )
            goal = valid_goal(
                {
                    "op": "create",
                    "skills": [
                        {
                            "skill": created,
                            "description": "Keep the request after a provider limit.",
                            "sections": [
                                {
                                    "section": "workflow",
                                    "goal": "Retry the same request.",
                                }
                            ],
                            "labels": [
                                {"type": "domain/api", "weight": 0.9},
                                {"type": "job/workflow", "weight": 0.8},
                                {"type": "form/procedure", "weight": 0.7},
                            ],
                        }
                    ],
                }
            )
            write_json(workspace / "run/push/evolve-goal.json", goal)
            write_json(
                workspace / "run/push/ops/1/verification.json",
                valid_verification(created, {"op": "pass"}),
            )
            with patch.object(runner, "run_session") as run_session:
                runner.fanout_operations(
                    workspace, "run", ["push"], 2, {}, None, True
                )
            run_session.assert_not_called()
            self.assertFalse(
                (
                    workspace / "target/to_be_improved_skills" / created
                ).exists()
            )
            self.assertEqual(
                (
                    workspace
                    / "target/to_be_improved_skills/audit-project-ui/SKILL.md"
                ).read_text(),
                "seed",
            )
            publication = json.loads(
                (workspace / "run/push/ops/1/publication.json").read_text()
            )
            self.assertFalse(publication["accepted"])
            summary = json.loads(
                runner.write_pipeline_summary(workspace, ["push"]).read_text()
            )
            self.assertFalse(summary["operations"][0]["accepted"])
            self.assertEqual(summary["operations"][0]["judge_action"], "pass")
            metadata = json.loads(
                (
                    workspace
                    / "target/to_be_improved_skills_metadata/metadata.json"
                ).read_text()
            )
            self.assertEqual(
                [row["skill"] for row in metadata["skills_metadata"]],
                ["audit-project-ui"],
            )

    def test_publish_gate_keeps_skill_when_config_includes_infrastructure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            created = "preserve-request-after-provider-rate-limit"
            write_json(
                workspace / "traces/derived/normalized/turns/infra.json",
                {
                    "assistant": {"text": ""},
                    "outcome": {"error": "HTTP 429 Too Many Requests"},
                },
            )
            write_jsonl(
                workspace / "traces/derived/cluster/push/manifest.jsonl",
                [{"turn_path": "traces/derived/normalized/turns/infra.json"}],
            )
            seed = workspace / "target/to_be_improved_skills/audit-project-ui"
            seed.mkdir(parents=True)
            (seed / "SKILL.md").write_text("seed")
            (workspace / "target/raw_skills").mkdir()
            labels = [{"type": "job/workflow", "weight": 1.0}]
            write_json(
                workspace
                / "target/to_be_improved_skills_metadata/metadata.json",
                {
                    "skills_metadata": [
                        {
                            "skill": "audit-project-ui",
                            "skill_types": labels,
                            "unmatched_skill_types": [],
                        }
                    ]
                },
            )
            worker = workspace / "worker"
            produced = (
                worker / "target/to_be_improved_skills" / created
            )
            produced.mkdir(parents=True)
            (produced / "SKILL.md").write_text("from-worker")
            write_json(
                worker / "target/to_be_improved_skills_metadata/metadata.json",
                {
                    "skills_metadata": [
                        {
                            "skill": created,
                            "skill_types": labels,
                            "unmatched_skill_types": [],
                        }
                    ]
                },
            )
            write_json(
                worker / "run/push/ops/1/evolve-goal.json",
                {"action": {"ops": [{"op": "create", "skills": [{"skill": created}]}]}},
            )
            write_json(
                worker / "run/push/ops/1/verification.json",
                valid_verification(created, {"op": "pass"}),
            )
            op = {
                "op": "create",
                "skills": [{"skill": created}],
            }
            config = json.loads(
                (AGENTS / "common/preprocessing-config.json").read_text()
            )
            config["signals"]["selection"][
                "include_infrastructure_failures"
            ] = True
            with patch.object(
                runner, "preprocessing_config", return_value=config
            ):
                runner.publish_operation_result(
                    workspace,
                    {
                        "cluster": "push",
                        "op_index": 1,
                        "op": op,
                        "worker": worker,
                        "affected": {created},
                        "suffixes": [],
                    },
                )
            self.assertEqual(
                (
                    workspace / "target/to_be_improved_skills" / created / "SKILL.md"
                ).read_text(),
                "from-worker",
            )
            self.assertEqual(
                (
                    workspace
                    / "target/to_be_improved_skills/audit-project-ui/SKILL.md"
                ).read_text(),
                "seed",
            )
            publication = json.loads(
                (workspace / "run/push/ops/1/publication.json").read_text()
            )
            self.assertTrue(publication["accepted"])

    def test_shared_docker_runtime_uses_allowlisted_stage_mounts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            with patch.object(runner, "run") as invoke:
                runner.run_docker_session(
                    "goal",
                    workspace,
                    "do the goal",
                    {"ANTHROPIC_API_KEY": "secret"},
                    None,
                    False,
                    "run-a",
                )
            command = invoke.call_args.args[0]
            mounts = [
                command[index + 1]
                for index, value in enumerate(command)
                if value == "-v"
            ]
            self.assertIn(runner.AGENT_RUNTIME_IMAGE, command)
            self.assertIn(
                f"{workspace}:{runner.CONTAINER_WORKSPACE}", mounts
            )
            self.assertTrue(
                any(
                    mount.endswith(
                        "/03_goal_agent/goal_agent.md:"
                        "/opt/skill-evolver/skill_evolving_agents/AGENT.md:ro"
                    )
                    for mount in mounts
                )
            )
            self.assertTrue(
                any("/03_goal_agent:" in mount for mount in mounts)
            )
            self.assertFalse(
                any("/04_optimize_agent:" in mount for mount in mounts)
            )
            shell_command = command[-1]
            self.assertNotIn("apt-get", shell_command)
            self.assertNotIn("npm install", shell_command)

    def test_build_creates_one_shared_docker_image(self) -> None:
        with patch.object(runner, "run") as invoke:
            runner.build_images()
        invoke.assert_called_once()
        command = invoke.call_args.args[0]
        self.assertIn("skill_evolving_agents/Dockerfile.agent-runtime", command)
        self.assertIn(runner.AGENT_RUNTIME_IMAGE, command)

    def test_goal_fanout_runs_findings_concurrently_and_publishes_outputs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill_evolving_agents"
            workspace = root / "workspace/runs/run"
            (workspace / "logs").mkdir(parents=True)
            (workspace / "run").mkdir()
            barrier = threading.Barrier(2)

            def fake_session(
                stage, worker, prompt, auth, model, install, suffix, metadata=None
            ):
                self.assertEqual(stage, "goal")
                self.assertIn("--clusters workspace/traces/derived/findings", prompt)
                cluster = suffix.rsplit("-", 1)[-1]
                barrier.wait(timeout=2)
                write_json(
                    worker / f"run/{cluster}/label-matching.json",
                    {
                        "matching": {
                            "strategy": "weighted_path_similarity",
                            "config_version": 1,
                            "config_sha256": "0" * 64,
                        },
                        "clusters": [
                            {"cluster": cluster, "labels": [], "skills": []}
                        ],
                    },
                )
                write_json(
                    worker / f"run/{cluster}/evolve-goal.json",
                    valid_goal(),
                )

            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "run_session", side_effect=fake_session),
            ):
                runner.fanout_goals(
                    workspace,
                    "run",
                    ["a", "b"],
                    True,
                    2,
                    {},
                    None,
                    True,
                    "finding",
                )
            for cluster in ("a", "b"):
                self.assertTrue(
                    (workspace / f"run/{cluster}/label-matching.json").is_file()
                )
                self.assertTrue(
                    (workspace / f"run/{cluster}/evolve-goal.json").is_file()
                )
            self.assertFalse((root / ".pipeline-workers").exists())

    def test_nonconflicting_operation_chains_run_each_stage_concurrently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill_evolving_agents"
            workspace = root / "workspace/runs/run"
            for skill in ("a", "b"):
                path = workspace / "target/to_be_improved_skills" / skill
                path.mkdir(parents=True)
                (path / "SKILL.md").write_text(f"# {skill}\n")
            (workspace / "target/raw_skills").mkdir(parents=True)
            (workspace / "logs").mkdir(parents=True)
            labels = [
                {"type": "job/a", "weight": 1.0},
                {"type": "job/b", "weight": 0.8},
                {"type": "job/c", "weight": 0.6},
            ]
            write_json(
                workspace
                / "target/to_be_improved_skills_metadata/metadata.json",
                {
                    "skills_metadata": [
                        {
                            "skill": skill,
                            "skill_types": labels,
                            "description": skill,
                        }
                        for skill in ("a", "b")
                    ]
                },
            )
            goal = valid_goal()
            goal["action"]["ops"] = [
                {
                    "op": "update",
                    "skills": [
                        {
                            "skill": skill,
                            "goal": "improve",
                            "facet": "workflow",
                            "sections": [
                                {"section": "workflow", "goal": "improve"}
                            ],
                        }
                    ],
                }
                for skill in ("a", "b")
            ]
            write_json(workspace / "run/cut/evolve-goal.json", goal)
            barriers = {
                stage: threading.Barrier(2)
                for stage in ("optimize", "verifiter", "judge")
            }
            calls = {stage: 0 for stage in barriers}

            def fake_session(
                stage, worker, prompt, auth, model, install, suffix, metadata=None
            ):
                active = json.loads((worker / "run/evolve-goal.json").read_text())
                skill = active["action"]["ops"][0]["skills"][0]["skill"]
                calls[stage] += 1
                barriers[stage].wait(timeout=2)
                if stage == "optimize":
                    raw = worker / "target/raw_skills" / skill
                    raw.mkdir(parents=True, exist_ok=True)
                    (raw / "SKILL.md").write_text(f"# {skill}\n")
                elif stage == "verifiter":
                    write_json(
                        worker / "run/verification.json",
                        valid_verification(skill),
                    )
                elif stage == "judge":
                    write_json(
                        worker / "run/verification.json",
                        valid_verification(
                            skill, {"op": "pass", "to": ""}
                        ),
                    )

            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "run_session", side_effect=fake_session),
            ):
                runner.fanout_operations(
                    workspace,
                    "run",
                    ["cut"],
                    2,
                    {},
                    None,
                    True,
                )
            self.assertEqual(
                calls, {"optimize": 2, "verifiter": 2, "judge": 2}
            )
            for index in (1, 2):
                self.assertTrue(
                    (
                        workspace
                        / f"run/cut/ops/{index}/verification.json"
                    ).is_file()
                )
            self.assertFalse((root / ".pipeline-workers").exists())


class MockedPipelineTest(unittest.TestCase):
    def test_complete_no_model_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skill_evolving_agents"
            write_json(
                root / "common/preprocessing-config.json",
                json.loads(
                    (AGENTS / "common/preprocessing-config.json").read_text()
                ),
            )
            workspace = root / "workspace/runs/test-run"
            trace = workspace / "traces/raw/codex/trace.jsonl"
            write_jsonl(
                trace,
                codex_trace_rows(
                    user="Improve deployment handling",
                    assistant="The deployment response was incomplete.",
                ),
            )
            skill = workspace / "target/to_be_improved_skills/seed"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Seed\n")
            (workspace / "traces/raw/reference_agent").mkdir(parents=True)
            (workspace / "target/raw_skills").mkdir(parents=True)
            (workspace / "target/to_be_improved_skills_metadata").mkdir(parents=True)
            (workspace / "run").mkdir(parents=True)
            (workspace / "logs").mkdir(parents=True)

            labels = [
                {"type": "job/a", "weight": 1.0},
                {"type": "job/b", "weight": 0.8},
                {"type": "job/c", "weight": 0.6},
            ]

            def fake_session(
                stage, ws, prompt, auth, model, install, suffix, metadata=None
            ):
                if stage == "preprocessing":
                    cut = ws / "traces/derived/cut"
                    cut.mkdir(parents=True, exist_ok=True)
                    (cut / "trace.jsonl").write_text(trace.read_text())
                elif stage == "label-skills":
                    write_json(
                        ws / "target/to_be_improved_skills_metadata/metadata.json",
                        {
                            "skills_metadata": [
                                {
                                    "skill": "seed",
                                    "skill_types": labels,
                                    "description": "seed",
                                }
                            ]
                        },
                    )
                elif stage == "label-traces-cluster":
                    write_json(
                        ws / "run/diagnosis.json",
                        {
                            "skill_capabilities_missing": [
                                {
                                    "type": "job/a",
                                    "description": "missing",
                                    "confidence": 0.9,
                                    "reasoning": "trace",
                                    "evidence_list": ["bad"],
                                }
                            ],
                            "newly_detected_skill_capabilites_missing": [],
                        },
                    )
                elif stage == "goal":
                    write_json(
                        ws / "run/cut/label-matching.json",
                        {
                            "matching": {
                                "strategy": "weighted_path_similarity",
                                "config_version": 1,
                                "config_sha256": "0" * 64,
                            },
                            "clusters": [
                                {
                                    "labels": ["job/a"],
                                    "skills": [
                                        {
                                            "skill": "seed",
                                            "score": 0.81,
                                            "labels": [labels[0]],
                                            "matches": [
                                                {
                                                    "cluster_type": "job/a",
                                                    "skill_type": "job/a",
                                                    "similarity": 1.0,
                                                    "contribution": 0.81,
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ]
                        },
                    )
                    write_json(
                        ws / "run/cut/evolve-goal.json",
                        valid_goal(
                            {
                                "op": "create",
                                "skills": [
                                    {
                                        "skill": "created",
                                        "description": "new",
                                        "sections": ["overview"],
                                        "labels": labels,
                                    }
                                ],
                            }
                        ),
                    )
                elif stage == "optimize":
                    created = ws / "target/to_be_improved_skills/created"
                    created.mkdir(parents=True, exist_ok=True)
                    (created / "SKILL.md").write_text("# Created\n")
                    write_json(
                        ws / "target/to_be_improved_skills_metadata/metadata.json",
                        {
                            "skills_metadata": [
                                {
                                    "skill": "seed",
                                    "skill_types": labels,
                                    "description": "seed",
                                },
                                {
                                    "skill": "created",
                                    "skill_types": labels,
                                    "description": "created",
                                },
                            ]
                        },
                    )
                elif stage == "verifiter":
                    write_json(
                        ws / "run/verification.json",
                        valid_verification("created"),
                    )
                elif stage == "judge":
                    write_json(
                        ws / "run/verification.json",
                        valid_verification(
                            "created", {"op": "pass", "to": ""}
                        ),
                    )

            args = SimpleNamespace(
                run_id="test-run",
                init=False,
                agent="cursor",
                allow_local_fallback=False,
                build=False,
                cluster=False,
                model=None,
                agent_installed=False,
            )
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "run_session", side_effect=fake_session),
                patch.object(runner, "select_backend", return_value="cursor"),
            ):
                runner.execute(args)
            self.assertTrue(
                (workspace / "run/cut/ops/1/evolve-goal.json").is_file()
            )
            self.assertTrue(
                (workspace / "run/cut/ops/1/verification.json").is_file()
            )
            judge_status = list((workspace / "run/status/judge").glob("*.json"))
            self.assertEqual(len(judge_status), 1)
            self.assertEqual(json.loads(judge_status[0].read_text())["state"], "done")

    def test_candidate_run_copies_one_trace_and_names_it_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pool = Path(directory) / "candidate_traces"
            runs = Path(directory) / "runs"
            pool.mkdir()
            session = "01a13505-8693-7372-8ff2-2acdcfd7f457"

            def write_trace(name: str, turn_ids: list[str]) -> None:
                lines = [
                    json.dumps(
                        {
                            "type": "session_meta",
                            "payload": {"session_id": session},
                        }
                    )
                ]
                lines.extend(
                    json.dumps(
                        {
                            "type": "event_msg",
                            "payload": {"type": "task_started", "turn_id": turn_id},
                        }
                    )
                    for turn_id in turn_ids
                )
                (pool / name).write_text("\n".join(lines) + "\n")

            write_trace("short.jsonl", ["t1", "t2"])
            write_trace("same-count.jsonl", ["u1", "u2"])
            rows = candidates.index_traces(pool)
            self.assertEqual(
                [(row["file"], row["run_id"]) for row in rows],
                [
                    ("same-count.jsonl", "run-codex-01a135-2turns"),
                    ("short.jsonl", "run-codex-01a13505-2turns"),
                ],
            )
            workspace = candidates.create_run("short.jsonl", pool, runs)
            copied = list((workspace / "traces/raw").rglob("*.jsonl"))
            self.assertEqual([path.name for path in copied], ["short.jsonl"])
            self.assertEqual(workspace.name, "run-codex-01a13505-2turns")
            self.assertTrue((pool / "same-count.jsonl").is_file())
            selection = json.loads(
                (workspace / "run/trace-selection.json").read_text()
            )
            self.assertEqual(selection["turns"], 2)
            self.assertEqual(selection["copied_to"], "traces/raw/codex/short.jsonl")


class TransformVerificationTest(unittest.TestCase):
    def test_merge_and_split_filesystem_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            improved = root / "improved"
            for name in ("a", "b", "source"):
                (raw / name).mkdir(parents=True)
            (improved / "merged/references").mkdir(parents=True)
            (improved / "part-a/scripts").mkdir(parents=True)
            (improved / "part-b").mkdir(parents=True)
            goal = {
                "action": {
                    "ops": [
                        {
                            "op": "merge",
                            "skills": ["a", "b"],
                            "into": {
                                "skill": "merged",
                                "dirs": [{"dir": "references", "goal": "keep"}],
                            },
                        },
                        {
                            "op": "split",
                            "skill": "source",
                            "into": [
                                {
                                    "skill": "part-a",
                                    "dirs": [{"dir": "scripts", "goal": "keep"}],
                                },
                                {"skill": "part-b"},
                            ],
                        },
                    ]
                }
            }
            self.assertEqual(transforms.check(goal, raw, improved), [])
            (improved / "a").mkdir()
            self.assertTrue(transforms.check(goal, raw, improved))


if __name__ == "__main__":
    unittest.main()
