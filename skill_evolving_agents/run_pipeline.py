#!/usr/bin/env python3
"""Run isolated skill-evolving sessions with deterministic stage reducers."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CONFIG_PATH = ROOT / "common/preprocessing-config.json"
CONTAINER_WORKSPACE = "/opt/skill-evolver/skill_evolving_agents/workspace"
SESSION_ROOT = Path(
    os.environ.get("SKILL_EVOLVER_SESSION_ROOT", "")
    or Path(tempfile.gettempdir()) / "skill-evolver-sessions"
)
DEFAULT_CLUSTER_WORKERS = 16
DEFAULT_OP_WORKERS = 16
RETRY_BUDGET = 1
ACTIVE_BACKEND = "docker-claude"


def env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


BACKEND_FEATURE_FLAGS = {
    "cursor": True,
    "codex": env_enabled("SKILL_EVOLVER_ENABLE_CODEX"),
    "claude": env_enabled("SKILL_EVOLVER_ENABLE_CLAUDE"),
    "ollama": env_enabled("SKILL_EVOLVER_ENABLE_OLLAMA"),
    "docker-claude": True,
}

_CONTRACTS_PATH = ROOT / "common/pipeline_contracts.py"
_CONTRACTS_SPEC = importlib.util.spec_from_file_location(
    "pipeline_contracts", _CONTRACTS_PATH
)
pipeline_contracts = importlib.util.module_from_spec(_CONTRACTS_SPEC)
assert _CONTRACTS_SPEC.loader is not None
_CONTRACTS_SPEC.loader.exec_module(pipeline_contracts)
_METRICS_PATH = ROOT / "common/pipeline_metrics.py"
_METRICS_SPEC = importlib.util.spec_from_file_location(
    "pipeline_metrics", _METRICS_PATH
)
pipeline_metrics = importlib.util.module_from_spec(_METRICS_SPEC)
assert _METRICS_SPEC.loader is not None
_METRICS_SPEC.loader.exec_module(pipeline_metrics)
_NAMES_PATH = ROOT / "common/skill_names.py"
_NAMES_SPEC = importlib.util.spec_from_file_location("skill_names", _NAMES_PATH)
skill_names_mod = importlib.util.module_from_spec(_NAMES_SPEC)
assert _NAMES_SPEC.loader is not None
_NAMES_SPEC.loader.exec_module(skill_names_mod)
_NORMALIZER_PATH = ROOT / "01_preprocessing_agent/scripts/normalize_codex.py"
_NORMALIZER_SPEC = importlib.util.spec_from_file_location(
    "normalize_codex", _NORMALIZER_PATH
)
normalizer = importlib.util.module_from_spec(_NORMALIZER_SPEC)
assert _NORMALIZER_SPEC.loader is not None
_NORMALIZER_SPEC.loader.exec_module(normalizer)
_CLUSTER_PATH = ROOT / "01_preprocessing_agent/scripts/cluster_traces.py"
_CLUSTER_SPEC = importlib.util.spec_from_file_location(
    "cluster_traces", _CLUSTER_PATH
)
cluster_builder = importlib.util.module_from_spec(_CLUSTER_SPEC)
assert _CLUSTER_SPEC.loader is not None
_CLUSTER_SPEC.loader.exec_module(cluster_builder)
_PREPROCESSING_ROOT = ROOT / "01_preprocessing_agent"
if str(_PREPROCESSING_ROOT) not in sys.path:
    sys.path.insert(0, str(_PREPROCESSING_ROOT))
from trace_mining import engine as mining_engine
mining_engine.normalizer = normalizer
mining_engine.cluster_builder = cluster_builder

AGENT_RUNTIME_IMAGE = "skill-evolver-agent-runtime"

SKILLS = {
    "preprocessing": ["01_preprocessing_agent/cut-traces/skill.md"],
    "label-skills": ["02.1_label_skills_agent/existing_skills_labeler/skill.md"],
    "label-traces-cluster": [
        "02.2_label_traces_cluster_agent/dignosis/skill.md"
    ],
    "goal": [
        "03_goal_agent/skill-select/skill.md",
        "03_goal_agent/goal-generator/skill.md",
    ],
    "optimize": [
        "04_optimize_agent/skill-create/skill.md",
        "04_optimize_agent/ood-data-updater/skill.md",
    ],
    "verifiter": ["05_verifiter_agent/verifiter/skill.md"],
    "judge": ["06_judge_agent/judge/skill.md"],
}

AGENT_FILES = {
    "preprocessing": "01_preprocessing_agent/preprocessing_agent.md",
    "label-skills": "02.1_label_skills_agent/label_skills_agent.md",
    "label-traces-cluster": (
        "02.2_label_traces_cluster_agent/label_traces_cluster_agent.md"
    ),
    "goal": "03_goal_agent/goal_agent.md",
    "optimize": "04_optimize_agent/optimize_agent.md",
    "verifiter": "05_verifiter_agent/verifiter_agent.md",
    "judge": "06_judge_agent/judge_agent.md",
}

STAGE_DIRS = {
    "preprocessing": "01_preprocessing_agent",
    "label-skills": "02.1_label_skills_agent",
    "label-traces-cluster": "02.2_label_traces_cluster_agent",
    "goal": "03_goal_agent",
    "optimize": "04_optimize_agent",
    "verifiter": "05_verifiter_agent",
    "judge": "06_judge_agent",
}


def run(
    command: list[str],
    *,
    check: bool = True,
    display: list[str] | None = None,
    cwd: Path | None = None,
    log_path: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(display or command), flush=True)
    if log_path is None:
        return subprocess.run(
            command,
            cwd=cwd or REPO,
            text=True,
            input=input_text,
            check=check,
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd or REPO,
            text=True,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if input_text is not None and process.stdin is not None:
            process.stdin.write(input_text)
            process.stdin.close()
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)
            code = process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
    if check and code != 0:
        raise subprocess.CalledProcessError(code, command)
    return subprocess.CompletedProcess(command, code)


def require_auth() -> dict[str, str]:
    names = (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
    )
    values = {name: os.environ[name] for name in names if os.environ.get(name)}
    if not any(name in values for name in names[:3]):
        raise SystemExit(
            "Set ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or "
            "CLAUDE_CODE_OAUTH_TOKEN before running."
        )
    return values


def initialize_workspace(workspace: Path) -> None:
    if workspace.exists():
        raise SystemExit(f"refusing to replace existing run: {workspace}")
    pipeline_metrics.clear_shared_run(workspace)
    workspace.mkdir(parents=True)
    for relative in (
        "logs",
        "run",
        "target/raw_skills",
        "target/to_be_improved_skills",
        "target/to_be_improved_skills_metadata",
        "traces/raw/codex",
        "traces/raw/claude",
        "traces/raw/cursor",
        "traces/raw/reference_agent",
        "traces/derived/cut",
    ):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    print(f"initialized {workspace}")
    print("add raw traces and existing skills, then run again without --init")


def require_seed_inputs(workspace: Path) -> None:
    trace_roots = (
        workspace / "traces/raw/codex",
        workspace / "traces/raw/claude",
        workspace / "traces/raw/cursor",
        workspace / "traces/raw/target_agent",
    )
    skills = workspace / "target/to_be_improved_skills"
    if not any(any(root.glob("*.jsonl")) for root in trace_roots):
        raise SystemExit(
            "no supported trace jsonl files found under "
            f"{workspace / 'traces/raw'}"
        )
    usable_skills = [
        path
        for path in skills.iterdir()
        if path.is_dir()
        and ((path / "SKILL.md").is_file() or (path / "skill.md").is_file())
    ]
    if not usable_skills:
        raise SystemExit(f"no skill directories with SKILL.md or skill.md under {skills}")


def build_images() -> None:
    run(
        [
            "docker",
            "build",
            "-f",
            "skill_evolving_agents/Dockerfile.agent-runtime",
            "-t",
            AGENT_RUNTIME_IMAGE,
            "skill_evolving_agents",
        ]
    )


def instruction(stage: str, context: str, *, cluster: bool = False) -> str:
    paths = list(SKILLS[stage])
    if stage == "preprocessing" and cluster:
        paths.append("01_preprocessing_agent/cluster/skill.md")
    skills = "\n".join(f"- {path}" for path in paths)
    return f"""Fast decision. One pass. Do not explore.

Read only AGENT.md and these skill files:
{skills}

Then read only the input paths named in the session block below. Write the required output and stop.
Do not open the parent repository, other stages, logs, pipeline traces, raw vendor logs, or any cluster, finding, or skill this session does not name.
Do not search. Do not reread a file. Run a command only when one of those skill files tells you to run that command.
If the evidence supports no_change, pass, or fail, write that decision and stop.
Do not ask questions. Do not work on another stage, cluster, or op.

Session:
{context}

After the output exists, append one started record and one done (or failed) record to workspace/logs/execution.jsonl.
Every record must be exactly shaped as
{{"agent":"<agent number>","state":"<state>","event":"<started|done|failed>","at":"<iso8601>"}}.
Exit nonzero if the required output cannot be produced.
"""


def session_command(model: str | None, _install_agent: bool) -> str:
    parts = ["set -eu"]
    parts.append("command -v claude >/dev/null")
    model_arg = f" --model {shlex.quote(model)}" if model else ""
    parts.append(
        'printf "%s" "$SESSION_INSTRUCTION" | '
        "claude --dangerously-skip-permissions --verbose "
        f"--output-format=stream-json{model_arg} --print"
    )
    return "; ".join(parts)


def run_docker_session(
    stage: str,
    workspace: Path,
    prompt: str,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    suffix: str,
    log_path: Path | None = None,
    details: dict[str, object] | None = None,
) -> None:
    safe_suffix = re.sub(r"[^a-zA-Z0-9_.-]+", "-", suffix).strip("-")
    name = f"skill-evolver-{stage}-{safe_suffix}"[:120]
    container_root = "/opt/skill-evolver/skill_evolving_agents"
    mounts = [
        (
            ROOT / AGENT_FILES[stage],
            f"{container_root}/AGENT.md",
        ),
        (
            ROOT / STAGE_DIRS[stage],
            f"{container_root}/{STAGE_DIRS[stage]}",
        ),
        (ROOT / "common", f"{container_root}/common"),
        (
            ROOT / "skill_capabilites",
            f"{container_root}/skill_capabilites",
        ),
    ]
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "-v",
        f"{workspace}:{CONTAINER_WORKSPACE}",
        "-e",
        f"SESSION_INSTRUCTION={prompt}",
        "-e",
        f"STAGE_DIR={STAGE_DIRS[stage]}",
    ]
    for source, target in mounts:
        command.extend(["-v", f"{source.resolve()}:{target}:ro"])
    for key in auth:
        command.extend(["-e", key])
    command.extend(
        [
            AGENT_RUNTIME_IMAGE,
            "sh",
            "-lc",
            session_command(model, install_agent),
        ]
    )
    if details is not None:
        details["session_cwd"] = "docker"
        details["session_add_dir"] = str(workspace)
    run(
        command,
        display=[
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "-v",
            f"{workspace}:{CONTAINER_WORKSPACE}",
            "[credentials and instruction omitted]",
            AGENT_RUNTIME_IMAGE,
        ],
        log_path=log_path,
    )


def authenticated(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command,
            cwd=REPO,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def select_backend(requested: str, allow_local: bool) -> str:
    checks = {
        "cursor": ["agent", "models"],
        "codex": ["codex", "login", "status"],
        "claude": ["claude", "auth", "status"],
        "ollama": ["ollama", "list"],
    }
    if requested != "auto":
        if not BACKEND_FEATURE_FLAGS[requested]:
            flag = f"SKILL_EVOLVER_ENABLE_{requested.upper().replace('-', '_')}"
            raise SystemExit(
                f"{requested} is disabled. Set {flag}=1 to enable it."
            )
        if requested == "docker-claude":
            return requested
        if requested == "ollama" and not allow_local:
            raise SystemExit("Ollama requires --allow-local-fallback")
        if not authenticated(checks[requested]):
            raise SystemExit(f"{requested} is not installed or authenticated")
        return requested
    for backend in ("cursor", "codex", "claude"):
        if BACKEND_FEATURE_FLAGS[backend] and authenticated(checks[backend]):
            print(f"selected agent backend: {backend}")
            return backend
    if (
        allow_local
        and BACKEND_FEATURE_FLAGS["ollama"]
        and authenticated(checks["ollama"])
    ):
        print("selected local fallback: ollama")
        return "ollama"
    raise SystemExit(
        "Cursor is not authenticated. Run `agent login`. Codex, Claude, and "
        "Ollama are disabled by feature flags."
    )


def make_session_view(stage: str, workspace: Path, suffix: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", suffix).strip("-")
    base = SESSION_ROOT / f"{safe}-{stage}"
    if base.exists():
        shutil.rmtree(base)
    agent_root = base / "skill_evolving_agents"
    agent_root.mkdir(parents=True)
    shutil.copy2(ROOT / AGENT_FILES[stage], agent_root / "AGENT.md")
    shutil.copytree(
        ROOT / STAGE_DIRS[stage],
        agent_root / STAGE_DIRS[stage],
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / "common",
        agent_root / "common",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        ROOT / "skill_capabilites",
        agent_root / "skill_capabilites",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (agent_root / "workspace").symlink_to(workspace, target_is_directory=True)
    return agent_root


def cursor_command(
    view: Path, workspace: Path, prompt: str, model: str | None
) -> list[str]:
    """Launch Cursor with the session view as its only project root.

    The run data is a second root so the sandbox can write `workspace/`.
    The process cwd is the session view, outside the source git repository.
    """
    command = [
        "agent",
        "--workspace",
        str(view),
        "--trust",
        "--print",
        "--force",
        "--sandbox",
        "enabled",
        "--output-format",
        "stream-json",
        "--add-dir",
        str(workspace),
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


def run_host_session(
    backend: str,
    stage: str,
    workspace: Path,
    prompt: str,
    model: str | None,
    suffix: str,
    log_path: Path | None = None,
    details: dict[str, object] | None = None,
) -> None:
    if not BACKEND_FEATURE_FLAGS[backend]:
        raise SystemExit(f"{backend} is disabled by its feature flag")
    view = make_session_view(stage, workspace, suffix)
    allowed = [str(workspace)]
    if details is not None:
        details["session_cwd"] = str(view)
        details["session_add_dir"] = str(workspace)

    try:
        if backend == "cursor":
            command = cursor_command(view, workspace, prompt, model)
            run(command, cwd=view, log_path=log_path)
        elif backend in {"codex", "ollama"}:
            command = [
                "codex",
                "exec",
                "--cd",
                str(view),
                "--approve-for-me",
                "--skip-git-repo-check",
                "--ephemeral",
            ]
            for path in allowed:
                command.extend(["--add-dir", path])
            if backend == "ollama":
                command.extend(
                    [
                        "--oss",
                        "--local-provider",
                        "ollama",
                        "--model",
                        model or "qwen2.5-coder:1.5b",
                    ]
                )
            elif model:
                command.extend(["--model", model])
            command.append("-")
            print(f"+ {backend} session {stage} ({suffix})", flush=True)
            run(command, cwd=view, log_path=log_path, input_text=prompt)
        elif backend == "claude":
            command = [
                "claude",
                "--safe-mode",
                "--print",
                "--dangerously-skip-permissions",
                "--no-session-persistence",
                "--verbose",
                "--output-format",
                "stream-json",
            ]
            for path in allowed:
                command.extend(["--add-dir", path])
            command.extend(["--model", model or "claude-sonnet-5-5"])
            print(f"+ claude session {stage} ({suffix})", flush=True)
            run(command, cwd=view, log_path=log_path, input_text=prompt)
        else:
            raise SystemExit(f"unknown agent backend: {backend}")
    finally:
        shutil.rmtree(view.parent, ignore_errors=True)


def metrics_workspace(workspace: Path) -> Path:
    worker_root = ROOT / ".pipeline-workers"
    try:
        relative = workspace.resolve().relative_to(worker_root.resolve())
    except ValueError:
        return workspace
    run_id = relative.parts[0]
    authoritative = ROOT / "workspace/runs" / run_id
    return authoritative if authoritative.is_dir() else workspace


def session_log_path(workspace: Path, stage: str, suffix: str) -> Path:
    return (
        metrics_workspace(workspace)
        / "logs/sessions"
        / stage
        / f"{safe_name(suffix)}.jsonl"
    )


def session_counts(path: Path) -> dict[str, object]:
    """Count stream events without interpreting the agent protocol."""
    if not path.is_file():
        return {"session_lines": 0, "tool_events": 0}
    lines = [
        line
        for line in path.read_text(errors="replace").splitlines()
        if line.strip()
    ]
    tool_events = sum(
        1 for line in lines if "tool_call" in line or "tool_use" in line
    )
    return {"session_lines": len(lines), "tool_events": tool_events}


def copy_worker(workspace: Path, stage: str, item: str) -> Path:
    """Copy a run into an isolated worker and time that copy."""
    started_at = datetime.now(UTC)
    started_us = time.time_ns() // 1000
    private = create_worker_workspace(workspace, stage, item)
    pipeline_metrics.record_span(
        metrics_workspace(workspace),
        phase="worker-copy",
        item=item,
        category="orchestration",
        started_at=started_at,
        started_at_us=started_us,
        duration_us=time.time_ns() // 1000 - started_us,
        status="ok",
    )
    return private


def record_queue(
    workspace: Path,
    phase: str,
    item: str,
    ready_us: int,
    metadata: dict[str, object],
) -> float:
    """Record the wait from when a pool item was eligible until it started."""
    now_us = time.time_ns() // 1000
    wait_ms = round(max(0, now_us - ready_us) / 1000, 3)
    pipeline_metrics.record_span(
        metrics_workspace(workspace),
        phase=phase,
        item=item,
        category="orchestration",
        started_at=datetime.fromtimestamp(ready_us / 1_000_000, UTC),
        started_at_us=ready_us,
        duration_us=max(0, now_us - ready_us),
        status="ok",
        metadata={**metadata, "queue_wait_ms": wait_ms},
    )
    return wait_ms


def diagnosis_slice_metadata(
    workspace: Path, cluster: str, unit_kind: str
) -> dict[str, object]:
    """Token and user-turn size of the slice a diagnosis session is given."""
    if unit_kind == "finding":
        path = workspace / "traces/derived/findings" / cluster / "finding.json"
        slices: list[dict[str, object]] = []
        if path.is_file():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                data = {}
            raw_slice = data.get("slice") if isinstance(data, dict) else None
            if isinstance(raw_slice, dict):
                slices.append(raw_slice)
    else:
        path = workspace / "traces/derived/cluster" / cluster / "cut.jsonl"
        slices = []
        if path.is_file():
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw_slice = row.get("slice") if isinstance(row, dict) else None
                if isinstance(raw_slice, dict):
                    slices.append(raw_slice)
    if not slices:
        return {"slice_present": False, "slice_count": 0}
    tokens = [int(item.get("token_estimate") or 0) for item in slices]
    turns = [int(item.get("user_turns") or 0) for item in slices]
    truncated = any(
        any(
            bool(turn.get("truncated"))
            for turn in (item.get("turns") or [])
            if isinstance(turn, dict)
        )
        for item in slices
    )
    return {
        "slice_present": True,
        "slice_count": len(slices),
        "slice_user_turns": sum(turns),
        "slice_tokens": sum(tokens),
        "slice_max_tokens": max(tokens),
        "slice_truncated": truncated,
    }


def run_session(
    stage: str,
    workspace: Path,
    prompt: str,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    suffix: str,
    metadata: dict[str, object] | None = None,
) -> None:
    details: dict[str, object] = dict(metadata or {})
    log_path = session_log_path(workspace, stage, suffix)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.with_suffix(".prompt.txt").write_text(prompt)
    authoritative = metrics_workspace(workspace)
    try:
        details["session_log"] = log_path.relative_to(authoritative).as_posix()
    except ValueError:
        details["session_log"] = str(log_path)
    details["prompt_chars"] = len(prompt)
    write_status(workspace, stage, suffix, "started")
    try:
        with pipeline_metrics.span(
            authoritative,
            stage,
            suffix,
            "llm_agent",
            backend=ACTIVE_BACKEND,
            model=model,
            metadata=details,
        ):
            try:
                if ACTIVE_BACKEND == "docker-claude":
                    run_docker_session(
                        stage,
                        workspace,
                        prompt,
                        auth,
                        model,
                        install_agent,
                        suffix,
                        log_path,
                        details,
                    )
                else:
                    run_host_session(
                        ACTIVE_BACKEND,
                        stage,
                        workspace,
                        prompt,
                        model,
                        suffix,
                        log_path,
                        details,
                    )
            finally:
                details.update(session_counts(log_path))
    except BaseException as error:
        write_status(workspace, stage, suffix, "failed", error=str(error))
        raise


def write_status(
    workspace: Path,
    stage: str,
    item: str,
    state: str,
    *,
    outputs: list[Path] | None = None,
    error: str | None = None,
) -> None:
    safe_item = re.sub(r"[^a-zA-Z0-9_.-]+", "-", item).strip("-")
    path = workspace / "run/status" / stage / f"{safe_item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    previous: dict[str, object] = {}
    if path.is_file():
        try:
            value = json.loads(path.read_text())
            previous = value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            previous = {}
    started_at = previous.get("started_at")
    if (
        not isinstance(started_at, str)
        or state == "started" and previous.get("state") != "started"
    ):
        started_at = now.isoformat()
    record: dict[str, object] = {
        "stage": stage,
        "item": item,
        "state": state,
        "at": now.isoformat(),
        "started_at": started_at,
    }
    if state != "started":
        try:
            started = datetime.fromisoformat(started_at)
            record["duration_ms"] = round(
                (now - started).total_seconds() * 1000
            )
        except ValueError:
            pass
    if outputs is not None:
        record["outputs"] = [
            str(output.relative_to(workspace)) for output in outputs
        ]
    if error:
        record["error"] = error
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def complete_session(
    workspace: Path, stage: str, item: str, outputs: list[Path]
) -> None:
    write_status(workspace, stage, item, "done", outputs=outputs)


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def create_worker_workspace(
    workspace: Path, stage: str, item: str
) -> Path:
    root = ROOT / ".pipeline-workers" / workspace.name / stage
    worker = root / safe_name(item)
    if worker.exists():
        shutil.rmtree(worker)
    worker.parent.mkdir(parents=True, exist_ok=True)

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if name == "__pycache__"
            or name == ".DS_Store"
            or name.endswith(".pyc")
        }
        if Path(directory).resolve() == (workspace / "traces").resolve():
            ignored.add("raw")
        return ignored

    shutil.copytree(
        workspace,
        worker,
        symlinks=False,
        ignore=ignore,
    )
    worker_log = worker / "logs/execution.jsonl"
    if worker_log.exists():
        worker_log.unlink()
    return worker


def remove_worker_workspace(worker: Path) -> None:
    if worker.exists():
        shutil.rmtree(worker)
    root = ROOT / ".pipeline-workers"
    for parent in (worker.parent, worker.parent.parent, worker.parent.parent.parent):
        if parent == root.parent:
            break
        try:
            parent.rmdir()
        except OSError:
            break


def remove_worker_stage(workspace: Path, stage: str) -> None:
    path = ROOT / ".pipeline-workers" / workspace.name / stage
    if path.exists():
        shutil.rmtree(path)


def replace_path(source: Path, target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def merge_worker_log(worker: Path, workspace: Path) -> None:
    source = worker / "logs/execution.jsonl"
    if not source.is_file():
        return
    target = workspace / "logs/execution.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as output:
        output.write(source.read_text())


def run_pool(
    items: list[object],
    max_workers: int,
    worker,
) -> list[object]:
    if max_workers < 1:
        raise SystemExit("worker count must be at least 1")
    if not items:
        return []
    results: list[object | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        futures: dict[Future, int] = {
            pool.submit(worker, item): index for index, item in enumerate(items)
        }
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return [result for result in results if result is not None]


def require_path(path: Path, description: str) -> None:
    if not path.exists():
        raise SystemExit(f"{description} was not produced: {path}")


def cluster_names(workspace: Path, clustered: bool) -> list[str]:
    if not clustered:
        require_path(workspace / "traces/derived/cut", "cut traces")
        return ["cut"]
    root = workspace / "traces/derived/cluster"
    require_path(root, "cluster directory")
    names = sorted(path.name for path in root.iterdir() if path.is_dir())
    if not names:
        raise SystemExit(f"no cluster directories found under {root}")
    return names


def preprocessing_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def include_infrastructure_failures(config: dict | None = None) -> bool:
    config = preprocessing_config() if config is None else config
    selection = ((config.get("signals") or {}).get("selection") or {})
    return bool(selection.get("include_infrastructure_failures", False))


def evolution_units(
    workspace: Path, clustered: bool, unit_kind: str
) -> list[str]:
    if unit_kind == "finding":
        root = workspace / "traces/derived/findings"
        require_path(root, "selected findings")
        names = sorted(path.name for path in root.iterdir() if path.is_dir())
        return agent_scopes(workspace, names)
    units = cluster_names(workspace, clustered)
    if not clustered:
        return units
    return agent_scopes(workspace, units)


def agent_scopes(workspace: Path, scopes: list[str]) -> list[str]:
    return [
        scope
        for scope in scopes
        if not infrastructure_evolution_blocked(workspace, scope)
    ]


def infrastructure_evolution_blocked(workspace: Path, scope: str) -> bool:
    if include_infrastructure_failures():
        return False
    return scope_is_infrastructure_only(workspace, scope)


def scope_is_infrastructure_only(workspace: Path, scope: str) -> bool:
    if finding_is_infrastructure(workspace, scope):
        return True
    manifest = workspace / "traces/derived/cluster" / scope / "manifest.jsonl"
    return manifest.is_file() and cluster_is_infrastructure_only(workspace, scope)


def finding_is_infrastructure(workspace: Path, scope: str) -> bool:
    path = workspace / "traces/derived/findings" / scope / "finding.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("routing") == "infrastructure"


def cluster_is_infrastructure_only(workspace: Path, cluster: str) -> bool:
    manifest = workspace / "traces/derived/cluster" / cluster / "manifest.jsonl"
    if not manifest.is_file():
        return False
    patterns = (preprocessing_config().get("signals") or {}).get(
        "infrastructure_error_patterns", []
    )
    turns: list[dict[str, object]] = []
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        turn_path = row.get("turn_path")
        if not isinstance(turn_path, str):
            return False
        path = workspace / turn_path
        if not path.is_file():
            return False
        turns.append(json.loads(path.read_text()))
    if not turns:
        return False
    return all(
        pipeline_contracts.infrastructure_only_turn(turn, patterns)
        for turn in turns
    )


INFRASTRUCTURE_REFUSAL = (
    "infrastructure-only source excluded by "
    "signals.selection.include_infrastructure_failures"
)


def created_skill_names(op: dict) -> list[str]:
    if op.get("op") != "create":
        return []
    return skill_names_mod.skill_names(op)


def drop_created_skills(workspace: Path, names: list[str]) -> None:
    if not names:
        return
    removing = set(names)
    for name in names:
        for relative in (
            Path("target/to_be_improved_skills") / name,
            Path("target/raw_skills") / name,
        ):
            target = workspace / relative
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    metadata = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    improved = workspace / "target/to_be_improved_skills"
    if not metadata.is_file():
        return
    data = json.loads(metadata.read_text())
    rows = data.get("skills_metadata") or []
    data["skills_metadata"] = [
        row
        for row in rows
        if not (isinstance(row, dict) and row.get("skill") in removing)
    ]
    atomic_write_json(metadata, data)
    if improved.is_dir():
        current = {path.name for path in improved.iterdir() if path.is_dir()}
        pipeline_contracts.validate_metadata(metadata, current)


def write_publication(
    workspace: Path,
    cluster: str,
    op_index: int,
    *,
    accepted: bool,
    reason: str | None,
) -> Path:
    path = (
        workspace
        / "run"
        / cluster
        / "ops"
        / str(op_index)
        / "publication.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "accepted": accepted,
            "reason": reason,
        },
    )
    return path


def goal_operation_rows(workspace: Path, cluster: str) -> list[dict]:
    path = workspace / "run" / cluster / "evolve-goal.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    ops = (data.get("action") or {}).get("ops")
    if not isinstance(ops, list):
        return []
    return [op for op in ops if isinstance(op, dict)]


def refuse_infrastructure_scope(workspace: Path, cluster: str) -> None:
    """Drop created skills from an infrastructure-only scope before acceptance."""
    for op_index, op in enumerate(goal_operation_rows(workspace, cluster), start=1):
        drop_created_skills(workspace, created_skill_names(op))
        write_publication(
            workspace,
            cluster,
            op_index,
            accepted=False,
            reason=INFRASTRUCTURE_REFUSAL,
        )


def refuse_blocked_scopes(
    workspace: Path, clustered: bool, unit_kind: str
) -> None:
    if include_infrastructure_failures():
        return
    if unit_kind == "finding":
        root = workspace / "traces/derived/findings"
        names = (
            sorted(path.name for path in root.iterdir() if path.is_dir())
            if root.is_dir()
            else []
        )
    elif clustered:
        root = workspace / "traces/derived/cluster"
        names = (
            sorted(path.name for path in root.iterdir() if path.is_dir())
            if root.is_dir()
            else []
        )
    else:
        return
    for name in names:
        if scope_is_infrastructure_only(workspace, name):
            refuse_infrastructure_scope(workspace, name)


def scope_source(cluster: str, clustered: bool, unit_kind: str) -> str:
    if unit_kind == "finding":
        return f"workspace/traces/derived/findings/{cluster}"
    return (
        f"workspace/traces/derived/cluster/{cluster}"
        if clustered
        else "workspace/traces/derived/cut"
    )


def validate_preprocessing(workspace: Path, clustered: bool) -> list[Path]:
    normalized = workspace / "traces/derived/normalized"
    manifest_path = normalized / "manifest.json"
    require_path(manifest_path, "normalization manifest")
    manifest = json.loads(manifest_path.read_text())
    expected = set(manifest.get("eligible_trace_ids") or [])
    if not expected:
        raise SystemExit("normalization produced no eligible traces")
    turns = normalized / "turns"
    turn_ids: set[str] = set()
    for path in turns.glob("*.json"):
        data = pipeline_contracts.validate_canonical_turn(path)
        trace_id = data["trace_id"]
        if trace_id in turn_ids:
            raise SystemExit(f"duplicate canonical trace ID: {trace_id}")
        turn_ids.add(trace_id)
    if turn_ids != expected:
        raise SystemExit("canonical turns do not match normalization manifest")
    cut = workspace / "traces/derived/cut"
    cut_ids = pipeline_contracts.validate_cluster_manifest(
        cut / "manifest.jsonl", "cut", turns
    )
    if cut_ids != expected:
        raise SystemExit("cut manifest does not cover every canonical trace")
    features = workspace / "traces/derived/features"
    require_path(features / "trace-features.jsonl", "trace features")
    pipeline_contracts.validate_dedup_manifest(
        features / "dedup-manifest.jsonl", expected
    )
    signals = workspace / "traces/derived/signals"
    signal_ids = pipeline_contracts.validate_signal_findings(
        signals / "findings.jsonl", expected
    )
    pipeline_contracts.validate_signal_patterns(
        signals / "patterns.jsonl", signal_ids
    )
    selected_ids = pipeline_contracts.validate_selected_findings(
        signals / "selected-manifest.jsonl", signal_ids, expected
    )
    findings = workspace / "traces/derived/findings"
    require_path(findings, "selected finding directory")
    finding_dirs = sorted(path for path in findings.iterdir() if path.is_dir())
    if {path.name for path in finding_dirs} != selected_ids:
        raise SystemExit("selected finding manifest does not match finding directories")
    for directory in finding_dirs:
        finding_ids = pipeline_contracts.validate_cluster_manifest(
            directory / "manifest.jsonl", directory.name, turns
        )
        finding_path = directory / "finding.json"
        require_path(finding_path, "finding details")
        finding = json.loads(finding_path.read_text())
        if finding.get("signal_id") != directory.name:
            raise SystemExit(f"finding ID does not match directory: {finding_path}")
        if finding_ids != set(finding.get("trace_ids") or []):
            raise SystemExit(
                f"finding manifest does not cover its evidence: {directory}"
            )
    outputs = [normalized, cut, features, signals, findings]
    if clustered:
        cluster_root = workspace / "traces/derived/cluster"
        require_path(cluster_root, "cluster directory")
        covered: set[str] = set()
        for directory in sorted(path for path in cluster_root.iterdir() if path.is_dir()):
            covered.update(
                pipeline_contracts.validate_cluster_manifest(
                    directory / "manifest.jsonl", directory.name, turns
                )
            )
            pipeline_contracts.validate_cluster_manifest(
                directory / "representatives.jsonl", directory.name, turns
            )
        if covered != expected:
            raise SystemExit(
                "cluster manifests must cover every canonical trace"
            )
        outputs.append(cluster_root)
    return outputs


def goal_ops(goal: Path) -> list[dict]:
    data = pipeline_contracts.validate_goal(goal)
    ops = (data.get("action") or {}).get("ops")
    return ops


def enforce_creation_policy(
    workspace: Path, cluster: str, goal: dict, op: dict
) -> None:
    if op.get("op") != "create":
        return
    finding_path = (
        workspace / "traces" / "derived" / "findings" / cluster / "finding.json"
    )
    if not finding_path.is_file():
        return
    config = json.loads((ROOT / "common/preprocessing-config.json").read_text())
    policy = config.get("evolution_policy") or {}
    finding = json.loads(finding_path.read_text())
    evidence = finding.get("evidence") or []
    sessions = {
        value
        for value in [finding.get("session_id")]
        if isinstance(value, str) and value
    }
    diagnosis_path = workspace / "run" / cluster / "diagnosis.json"
    diagnosis = json.loads(diagnosis_path.read_text())
    is_ood = bool(diagnosis.get("newly_detected_skill_capabilites_missing"))
    confidence = float(finding.get("confidence") or 0)
    enough_evidence = len(evidence) >= int(
        policy.get("create_min_evidence_records", 2)
    )
    enough_confidence = confidence >= float(
        policy.get("create_min_confidence", 0.75)
    )
    enough_sessions = len(sessions) >= int(
        policy.get("create_min_distinct_sessions", 2)
    )
    single_session_allowed = bool(policy.get("allow_single_session_create"))
    ood_override = (
        is_ood and bool(policy.get("allow_single_session_ood_create", True))
    )
    if enough_evidence and enough_confidence and (
        enough_sessions or single_session_allowed or ood_override
    ):
        return
    raise pipeline_contracts.ContractError(
        f"{cluster} proposes create without sufficient recurrence: "
        f"confidence={confidence}, evidence_records={len(evidence)}, "
        f"distinct_sessions={len(sessions)}, ood={is_ood}. Goal should use "
        "no_change or update an existing skill."
    )


def materialize_op_goal(
    workspace: Path,
    cluster: str,
    op_index: int,
    goal: dict,
    op: dict,
    *,
    activate: bool = True,
) -> Path:
    narrowed = copy.deepcopy(goal)
    narrowed["action"]["ops"] = [copy.deepcopy(op)]
    path = workspace / "run" / cluster / "ops" / str(op_index) / "evolve-goal.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(narrowed, indent=2, ensure_ascii=False) + "\n")
    pipeline_contracts.validate_goal(path, exactly_one_op=True)
    if activate:
        shutil.copy2(path, workspace / "run/evolve-goal.json")
    return path


def validate_optimized_op(workspace: Path, op: dict) -> list[Path]:
    improved = workspace / "target/to_be_improved_skills"
    raw = workspace / "target/raw_skills"
    name = op.get("op")
    expected: list[str] = []
    removed: list[str] = []
    snapshot: list[str] = []
    if name in {"create", "update", "delete"}:
        source_rows = op.get("skills") or []
        skill_names = [
            row.get("skill")
            for row in source_rows
            if isinstance(row, dict) and isinstance(row.get("skill"), str)
        ]
        if name == "create":
            expected = skill_names
        elif name == "update":
            expected = skill_names
            snapshot = skill_names
        else:
            removed = skill_names
            snapshot = skill_names
    elif name == "merge":
        source_names = [value for value in op.get("skills") or [] if isinstance(value, str)]
        target = (op.get("into") or {}).get("skill")
        expected = [target] if isinstance(target, str) else []
        removed = [value for value in source_names if value not in expected]
        snapshot = source_names
    elif name == "split":
        source = op.get("skill")
        expected = [
            row.get("skill")
            for row in op.get("into") or []
            if isinstance(row, dict) and isinstance(row.get("skill"), str)
        ]
        if isinstance(source, str):
            snapshot = [source]
            if source not in expected:
                removed = [source]
    for skill in expected:
        if not (improved / skill).is_dir():
            raise SystemExit(f"optimized skill was not produced: {skill}")
    for skill in removed:
        if (improved / skill).exists():
            raise SystemExit(f"removed skill still exists after {name}: {skill}")
    for skill in snapshot:
        if not (raw / skill).is_dir():
            raise SystemExit(f"raw skill snapshot was not produced: {skill}")
    current = {path.name for path in improved.iterdir() if path.is_dir()}
    metadata = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    pipeline_contracts.validate_metadata(metadata, current)
    return [improved, raw, metadata]


def judge_action(verification: Path) -> str:
    data = pipeline_contracts.validate_verification(verification, judged=True)
    action = ((data.get("feedback") or {}).get("action") or {}).get("op")
    if action not in {"pass", "back", "fail"}:
        raise SystemExit(f"judge did not set pass, back, or fail in {verification}")
    return action


def archive_verification(workspace: Path, cluster: str, op_index: int) -> None:
    source = workspace / "run/verification.json"
    require_path(source, "verification")
    target = workspace / "run" / cluster / "ops" / str(op_index)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target / "verification.json")


def fanout_diagnosis(
    workspace: Path,
    run_id: str,
    clusters: list[str],
    clustered: bool,
    workers: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    unit_kind: str = "cluster",
) -> Path:
    stage = "label-traces-cluster"
    clusters = agent_scopes(workspace, clusters)
    aggregate = workspace / "run/diagnosis.json"
    if not clusters:
        atomic_write_json(
            aggregate,
            {
                "skill_capabilities_missing": [],
                "newly_detected_skill_capabilites_missing": [],
            },
        )
        return aggregate
    items = [(cluster, f"{run_id}-{cluster}") for cluster in clusters]
    for _cluster, suffix in items:
        write_status(workspace, stage, suffix, "started")

    ready_us = time.time_ns() // 1000

    def work(item: object) -> object:
        cluster, suffix = item
        queue_wait_ms = record_queue(
            workspace,
            "diagnosis-queue",
            suffix,
            ready_us,
            {"workers": workers, "pool_items": len(items)},
        )
        private = copy_worker(workspace, stage, suffix)
        diagnosis = private / "run/diagnosis.json"
        diagnosis.unlink(missing_ok=True)
        source = scope_source(cluster, clustered, unit_kind)
        try:
            run_session(
                stage,
                private,
                instruction(
                    stage,
                    f"This isolated session is cluster <{cluster}> at {source}. "
                    "Read finding.json and use its slice as the trace. "
                    "In legacy cluster mode read slice in cut.jsonl when it "
                    "exists. Do not open canonical turns, manifest turn paths, "
                    "or tool sidecars. Write only this cluster's records into "
                    "workspace/run/diagnosis.json.",
                ),
                auth,
                model,
                install_agent,
                suffix,
                {
                    "workers": workers,
                    "pool_items": len(items),
                    "queue_wait_ms": queue_wait_ms,
                    **diagnosis_slice_metadata(workspace, str(cluster), unit_kind),
                    **_finding_audit(workspace, str(cluster)),
                },
            )
            pipeline_contracts.validate_diagnosis(
                diagnosis, {cluster} if clustered else None
            )
            return cluster, suffix, private
        except BaseException as error:
            write_status(workspace, stage, suffix, "failed", error=str(error))
            remove_worker_workspace(private)
            raise

    try:
        results = run_pool(items, workers, work)
    except BaseException:
        remove_worker_stage(workspace, stage)
        raise
    known: list[object] = []
    ood: list[object] = []
    feedback: dict[str, object] = {}
    try:
        for cluster, suffix, private in results:
            source = private / "run/diagnosis.json"
            data = json.loads(source.read_text())
            known.extend(data.get("skill_capabilities_missing") or [])
            ood.extend(data.get("newly_detected_skill_capabilites_missing") or [])
            if "feedback" in data:
                feedback[cluster] = data["feedback"]
            scoped = workspace / "run" / cluster / "diagnosis.json"
            replace_path(source, scoped)
            merge_worker_log(private, workspace)
            complete_session(workspace, stage, suffix, [scoped])
        document: dict[str, object] = {
            "skill_capabilities_missing": known,
            "newly_detected_skill_capabilites_missing": ood,
        }
        if feedback:
            document["feedback_by_cluster"] = feedback
        atomic_write_json(aggregate, document)
        pipeline_contracts.validate_diagnosis(
            aggregate, set(clusters) if clustered else None
        )
        return aggregate
    finally:
        for _cluster, _suffix, private in results:
            remove_worker_workspace(private)


def fanout_goals(
    workspace: Path,
    run_id: str,
    clusters: list[str],
    clustered: bool,
    workers: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    unit_kind: str = "cluster",
) -> None:
    stage = "goal"
    clusters = agent_scopes(workspace, clusters)
    if not clusters:
        return
    items = [(cluster, f"{run_id}-{cluster}") for cluster in clusters]
    for _cluster, suffix in items:
        write_status(workspace, stage, suffix, "started")

    ready_us = time.time_ns() // 1000

    def work(item: object) -> object:
        cluster, suffix = item
        queue_wait_ms = record_queue(
            workspace,
            "goal-queue",
            suffix,
            ready_us,
            {"workers": workers, "pool_items": len(items)},
        )
        private = copy_worker(workspace, stage, suffix)
        private_cluster = private / "run" / cluster
        if private_cluster.exists():
            shutil.rmtree(private_cluster)
        source = scope_source(cluster, clustered, unit_kind)
        clusters_argument = (
            " --clusters workspace/traces/derived/findings"
            if unit_kind == "finding"
            else ""
        )
        try:
            run_session(
                stage,
                private,
                instruction(
                    stage,
                    f"This isolated session is cluster <{cluster}> at {source}. "
                    f"Run select with `--cluster '{cluster}'{clusters_argument} --out "
                    f"workspace/run/{cluster}/label-matching.json`, then write "
                    f"workspace/run/{cluster}/evolve-goal.json. Pass that exact "
                    "path to one_action.py.",
                ),
                auth,
                model,
                install_agent,
                suffix,
                {
                    "workers": workers,
                    "pool_items": len(items),
                    "queue_wait_ms": queue_wait_ms,
                },
            )
            matching = private_cluster / "label-matching.json"
            goal = private_cluster / "evolve-goal.json"
            pipeline_contracts.validate_label_matching(matching, cluster)
            pipeline_contracts.validate_goal(goal)
            _emit_goal_decision(workspace, str(cluster), goal)
            return cluster, suffix, private
        except BaseException as error:
            write_status(workspace, stage, suffix, "failed", error=str(error))
            remove_worker_workspace(private)
            raise

    try:
        results = run_pool(items, workers, work)
    except BaseException:
        remove_worker_stage(workspace, stage)
        raise
    try:
        for cluster, suffix, private in results:
            source = private / "run" / cluster
            target = workspace / "run" / cluster
            target.mkdir(parents=True, exist_ok=True)
            matching = target / "label-matching.json"
            goal = target / "evolve-goal.json"
            replace_path(source / "label-matching.json", matching)
            replace_path(source / "evolve-goal.json", goal)
            merge_worker_log(private, workspace)
            complete_session(workspace, stage, suffix, [matching, goal])
    finally:
        for _cluster, _suffix, private in results:
            remove_worker_workspace(private)


def configured_max_ops_per_skill(explicit: int | None = None) -> int:
    """How many same-skill updates may share one optimize, verify, and judge."""
    if explicit is not None:
        return explicit
    path = ROOT / "common/preprocessing-config.json"
    if path.is_file():
        try:
            config = json.loads(path.read_text())
        except json.JSONDecodeError:
            config = {}
        value = (config.get("evolution_policy") or {}).get("max_ops_per_skill")
        if isinstance(value, int) and value >= 1:
            return value
    return 5


def configured_min_super_score(explicit: float | None = None) -> float:
    """Edits below this super score stay out of a same-skill bundle."""
    if explicit is not None:
        return explicit
    path = ROOT / "common/preprocessing-config.json"
    if path.is_file():
        try:
            config = json.loads(path.read_text())
        except json.JSONDecodeError:
            config = {}
        value = (config.get("evolution_policy") or {}).get("min_super_score")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return 0.0


def _merge_change_rows(rows: list[object], key: str) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get(key) or "")
        extra = str(row.get("heading") or row.get("name") or "")
        identity = (name, extra)
        goal = str(row.get("goal") or "").strip()
        if identity not in merged:
            merged[identity] = dict(row)
            order.append(identity)
            continue
        previous = str(merged[identity].get("goal") or "").strip()
        if goal and goal not in previous:
            merged[identity]["goal"] = f"{previous}\n{goal}".strip()
    return [merged[identity] for identity in order]


def merge_update_ops(ops: list[dict[str, object]]) -> dict[str, object]:
    """Collapse same-skill updates into one op the existing checkers accept."""
    by_skill: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for op in ops:
        for row in op.get("skills") or []:
            if not isinstance(row, dict) or not isinstance(row.get("skill"), str):
                continue
            name = row["skill"]
            if name not in by_skill:
                by_skill[name] = {
                    "skill": name,
                    "goals": [],
                    "facet": row.get("facet"),
                    "sections": [],
                    "dirs": [],
                }
                order.append(name)
            bucket = by_skill[name]
            text = str(row.get("goal") or "").strip()
            goals = bucket["goals"]
            if text and text not in goals:
                goals.append(text)
            if not bucket.get("facet") and row.get("facet"):
                bucket["facet"] = row["facet"]
            bucket["sections"].extend(row.get("sections") or [])
            bucket["dirs"].extend(row.get("dirs") or [])
    skills: list[dict[str, object]] = []
    for name in order:
        bucket = by_skill[name]
        item: dict[str, object] = {
            "skill": name,
            "goal": "\n".join(bucket["goals"]),
            "sections": _merge_change_rows(bucket["sections"], "section"),
            "dirs": _merge_change_rows(bucket["dirs"], "dir"),
        }
        if bucket.get("facet"):
            item["facet"] = bucket["facet"]
        skills.append(item)
    return {"op": "update", "skills": skills}


SEVERITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}


def rank_edit(workspace: Path, task: dict[str, object]) -> dict[str, object]:
    """Score one same-skill edit for the merge gate.

    ``score`` is the detector score. ``match_score`` is the label-matching
    score for a skill this edit touches. ``super_score`` is
    severity weight × confidence × (1 + |score|) + match_score.
    Missing severity does not inflate the score: the weight stays 1.
    """
    cluster = str(task["cluster"])
    confidence = float(task.get("confidence") or 0)
    severity = ""
    raw_score = 0.0
    finding_path = workspace / "traces/derived/findings" / cluster / "finding.json"
    if finding_path.is_file():
        try:
            finding = json.loads(finding_path.read_text())
        except json.JSONDecodeError:
            finding = {}
        if isinstance(finding, dict):
            try:
                confidence = float(finding.get("confidence") or confidence)
            except (TypeError, ValueError):
                pass
            found_severity = finding.get("severity")
            if isinstance(found_severity, str):
                severity = found_severity
            try:
                raw_score = float(finding.get("score") or 0)
            except (TypeError, ValueError):
                raw_score = 0.0
    skills = {str(name) for name in task.get("affected") or []}
    match_score = 0.0
    matching_path = workspace / "run" / cluster / "label-matching.json"
    if matching_path.is_file():
        try:
            matching = json.loads(matching_path.read_text())
        except json.JSONDecodeError:
            matching = {}
        for row in matching.get("clusters") or []:
            if not isinstance(row, dict):
                continue
            for skill in row.get("skills") or []:
                if not isinstance(skill, dict) or skill.get("skill") not in skills:
                    continue
                try:
                    match_score = max(match_score, float(skill.get("score") or 0))
                except (TypeError, ValueError):
                    continue
    weight = SEVERITY_WEIGHT.get(severity, 1.0)
    super_score = weight * confidence * (1 + abs(raw_score)) + match_score
    return {
        "severity": severity or None,
        "confidence": round(confidence, 6),
        "score": round(raw_score, 6),
        "match_score": round(match_score, 6),
        "super_score": round(super_score, 6),
    }


def _source_record(task: dict[str, object]) -> dict[str, object]:
    rank = task.get("rank") if isinstance(task.get("rank"), dict) else {}
    return {
        "cluster": task["cluster"],
        "op_index": task["op_index"],
        "confidence": rank.get("confidence", task.get("confidence", 0)),
        "severity": rank.get("severity"),
        "score": rank.get("score", 0),
        "match_score": rank.get("match_score", 0),
        "super_score": rank.get("super_score", 0),
        "goal": task.get("skill_goal", ""),
        "sections": [
            row.get("section")
            for skill in (task["op"].get("skills") or [])
            if isinstance(skill, dict)
            for row in (skill.get("sections") or [])
            if isinstance(row, dict) and row.get("section")
        ],
    }


def bundle_same_skill_updates(
    workspace: Path,
    tasks: list[dict[str, object]],
    max_ops: int,
    min_super_score: float = 0.0,
) -> list[dict[str, object]]:
    """Keep the top updates of one skill in one op. Verify and judge stay one pass."""
    if max_ops < 1:
        raise SystemExit("max_ops_per_skill must be at least 1")
    if min_super_score < 0:
        raise SystemExit("min_super_score must be non-negative")
    groups: dict[tuple[str, ...], list[dict[str, object]]] = {}
    for task in tasks:
        op = task.get("op")
        affected = tuple(sorted(str(name) for name in task.get("affected") or []))
        if (
            isinstance(op, dict)
            and op.get("op") == "update"
            and affected
        ):
            groups.setdefault(affected, []).append(task)
    consumed: set[int] = set()
    replacements: dict[int, dict[str, object]] = {}
    annotations: list[dict[str, object]] = []
    for affected, group in groups.items():
        if len(group) < 2:
            continue
        for task in group:
            task["rank"] = rank_edit(workspace, task)
        ranked = sorted(
            group,
            key=lambda task: (
                -float((task.get("rank") or {}).get("super_score") or 0),
                -float((task.get("rank") or {}).get("confidence") or 0),
                str(task["cluster"]),
                int(task["op_index"]),
            ),
        )
        passed = [ranked[0]]
        below_gate: list[dict[str, object]] = []
        for task in ranked[1:]:
            super_score = float((task.get("rank") or {}).get("super_score") or 0)
            if super_score >= min_super_score:
                passed.append(task)
            else:
                below_gate.append(task)
        selected = passed[:max_ops]
        dropped = (
            [(task, "over_cap") for task in passed[max_ops:]]
            + [(task, "below_gate") for task in below_gate]
        )
        representative = selected[0]
        if len(selected) > 1:
            merged = merge_update_ops(
                [task["op"] for task in selected if isinstance(task.get("op"), dict)]
            )
            bundle = {
                "schema_version": 1,
                "max_ops_per_skill": max_ops,
                "min_super_score": min_super_score,
                "op": "update",
                "skills": list(affected),
                "selected": [_source_record(task) for task in selected],
                "dropped": [
                    {**_source_record(task), "reason": reason}
                    for task, reason in dropped
                ],
            }
            document = json.loads(Path(representative["op_goal"]).read_text())
            improve: list[str] = []
            for task in selected:
                source = json.loads(Path(task["op_goal"]).read_text())
                for name in (source.get("goal") or {}).get("improve_skills") or []:
                    if isinstance(name, str) and name not in improve:
                        improve.append(name)
            document["goal"]["improve_skills"] = improve
            document["action"]["ops"] = [merged]
            document["bundle"] = bundle
            document["plan"] = (
                "Apply every section and directory goal in this single update. "
                "The source edits are listed in bundle.selected."
            )
            reasoning = str(document.get("reasoning") or "").strip()
            document["reasoning"] = (
                f"{reasoning}\n\nThis update merges {len(selected)} edits of "
                f"{', '.join(affected)} into one optimize, verify, and judge pass."
            ).strip()
            path = Path(representative["op_goal"])
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            )
            pipeline_contracts.validate_goal(path, exactly_one_op=True)
            representative = {
                **representative,
                "op": merged,
                "bundle": bundle,
                "bundled_sources": [
                    {"cluster": task["cluster"], "op_index": task["op_index"]}
                    for task in selected
                ],
            }
        for task, reason in dropped:
            consumed.add(id(task))
            write_publication(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                accepted=False,
                reason=reason,
            )
            annotations.append(
                {
                    "cluster": task["cluster"],
                    "op_index": task["op_index"],
                    "decision": reason,
                    "confidence": (task.get("rank") or {}).get(
                        "confidence", task.get("confidence", 0)
                    ),
                    "score": (task.get("rank") or {}).get("score", 0),
                    "super_score": (task.get("rank") or {}).get("super_score", 0),
                }
            )
        if len(selected) > 1:
            for task in selected:
                consumed.add(id(task))
            replacements[id(selected[0])] = representative
            for task in selected[1:]:
                annotations.append(
                    {
                        "cluster": task["cluster"],
                        "op_index": task["op_index"],
                        "decision": "bundled",
                        "selected_cluster": representative["cluster"],
                        "selected_op_index": representative["op_index"],
                        "confidence": task.get("confidence", 0),
                    }
                )
            annotations.append(
                {
                    "cluster": representative["cluster"],
                    "op_index": representative["op_index"],
                    "decision": "selected",
                    "bundle_size": len(selected),
                    "bundled_skills": list(affected),
                    "super_score": (representative.get("rank") or {}).get(
                        "super_score", 0
                    ),
                }
            )
    result: list[dict[str, object]] = []
    emitted: set[int] = set()
    for task in tasks:
        identity = id(task)
        if identity in replacements and identity not in emitted:
            result.append(replacements[identity])
            emitted.add(identity)
        elif identity not in consumed:
            result.append(task)
    if annotations:
        path = workspace / "run/goal-reduction.json"
        document = (
            json.loads(path.read_text())
            if path.is_file()
            else {"schema_version": 1, "decisions": []}
        )
        rows = {
            (row.get("cluster"), row.get("op_index")): row
            for row in document.get("decisions") or []
            if isinstance(row, dict)
        }
        for annotation in annotations:
            key = (annotation["cluster"], annotation["op_index"])
            row = rows.get(key)
            if row is None:
                document.setdefault("decisions", []).append(annotation)
                rows[key] = annotation
            else:
                row.update(annotation)
        document["max_ops_per_skill"] = max_ops
        document["selected_operation_count"] = len(result)
        atomic_write_json(path, document)
    return result


def operation_batches(tasks: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    pending = list(tasks)
    batches: list[list[dict[str, object]]] = []
    while pending:
        batch: list[dict[str, object]] = []
        deferred: list[dict[str, object]] = []
        used: set[str] = set()
        for task in pending:
            affected = set(task["conflicts"])
            conflicts = (
                "*" in affected
                or "*" in used
                or bool(affected.intersection(used))
            )
            if conflicts:
                deferred.append(task)
                continue
            batch.append(task)
            used.update(affected)
        if not batch:
            batch = [deferred.pop(0)]
        batches.append(batch)
        pending = deferred
    return batches


def _rank_fields(task: dict[str, object]) -> dict[str, object]:
    rank = task.get("rank")
    if not isinstance(rank, dict):
        return {}
    return {
        key: rank.get(key)
        for key in ("severity", "confidence", "score", "match_score", "super_score")
    }


def reduce_operation_tasks(
    workspace: Path, tasks: list[dict[str, object]]
) -> list[dict[str, object]]:
    with pipeline_metrics.span(
        metrics_workspace(workspace),
        "reduce-goals",
        workspace.name,
        "orchestration",
        metadata={"input_operations": len(tasks)},
    ):
        return _reduce_operation_tasks(workspace, tasks)


def _reduce_operation_tasks(
    workspace: Path, tasks: list[dict[str, object]]
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    seen: dict[str, dict[str, object]] = {}
    decisions: list[dict[str, object]] = []
    for task in tasks:
        signature = hashlib.sha256(
            json.dumps(
                task["op"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        first = seen.get(signature)
        if first is None:
            seen[signature] = task
            selected.append(task)
            decisions.append(
                {
                    "cluster": task["cluster"],
                    "op_index": task["op_index"],
                    "signature": signature,
                    "decision": "selected",
                    **_rank_fields(task),
                }
            )
        else:
            decisions.append(
                {
                    "cluster": task["cluster"],
                    "op_index": task["op_index"],
                    "signature": signature,
                    "decision": "duplicate",
                    "selected_cluster": first["cluster"],
                    "selected_op_index": first["op_index"],
                    **_rank_fields(task),
                }
            )
    atomic_write_json(
        workspace / "run/goal-reduction.json",
        {
            "schema_version": 1,
            "input_operation_count": len(tasks),
            "selected_operation_count": len(selected),
            "retry_budget": RETRY_BUDGET,
            "max_attempts": RETRY_BUDGET + 1,
            "decisions": decisions,
        },
    )
    return selected


def merge_metadata(
    workspace: Path, worker: Path, affected: set[str]
) -> Path:
    relative = Path("target/to_be_improved_skills_metadata/metadata.json")
    main_path = workspace / relative
    worker_path = worker / relative
    main = json.loads(main_path.read_text())
    candidate = json.loads(worker_path.read_text())
    kept = [
        row
        for row in main.get("skills_metadata") or []
        if isinstance(row, dict) and row.get("skill") not in affected
    ]
    changed = [
        row
        for row in candidate.get("skills_metadata") or []
        if isinstance(row, dict) and row.get("skill") in affected
    ]
    kept.extend(changed)
    kept.sort(key=lambda row: str(row.get("skill", "")).casefold())
    main["skills_metadata"] = kept
    atomic_write_json(main_path, main)
    return main_path


def merge_worker_statuses(worker: Path, workspace: Path, suffix: str) -> None:
    safe = safe_name(suffix)
    for stage in ("optimize", "verifiter", "judge"):
        source = worker / "run/status" / stage / f"{safe}.json"
        if source.is_file():
            replace_path(source, workspace / "run/status" / stage / source.name)


def publish_operation_result(
    workspace: Path, result: dict[str, object]
) -> None:
    cluster = str(result["cluster"])
    op_index = int(result["op_index"])
    if infrastructure_evolution_blocked(workspace, cluster):
        drop_created_skills(
            workspace, created_skill_names(result["op"])
        )
        _archive_operation_records(workspace, result)
        write_publication(
            workspace,
            cluster,
            op_index,
            accepted=False,
            reason=INFRASTRUCTURE_REFUSAL,
        )
        return
    merge_operation_result(workspace, result)
    write_publication(
        workspace, cluster, op_index, accepted=True, reason=None
    )
    for source in result.get("bundled_sources") or []:
        if not isinstance(source, dict):
            continue
        source_cluster = str(source.get("cluster"))
        source_index = int(source.get("op_index"))
        if source_cluster == cluster and source_index == op_index:
            continue
        write_publication(
            workspace,
            source_cluster,
            source_index,
            accepted=True,
            reason="bundled",
        )


def _archive_operation_records(
    workspace: Path, result: dict[str, object]
) -> None:
    worker = result["worker"]
    cluster = str(result["cluster"])
    op_index = int(result["op_index"])
    for relative in (
        Path("run") / cluster / "ops" / str(op_index) / "verification.json",
        Path("run") / cluster / "ops" / str(op_index) / "evolve-goal.json",
    ):
        source = worker / relative
        if source.is_file():
            replace_path(source, workspace / relative)
    for suffix in result["suffixes"]:
        merge_worker_statuses(worker, workspace, str(suffix))
    merge_worker_log(worker, workspace)


def merge_operation_result(
    workspace: Path, result: dict[str, object]
) -> None:
    with pipeline_metrics.span(
        metrics_workspace(workspace),
        "merge-operation",
        f"{result['cluster']}-op-{result['op_index']}",
        "orchestration",
    ):
        _merge_operation_result(workspace, result)


def _merge_operation_result(
    workspace: Path, result: dict[str, object]
) -> None:
    worker = result["worker"]
    cluster = str(result["cluster"])
    op_index = int(result["op_index"])
    affected = set(result["affected"])
    improved_rel = Path("target/to_be_improved_skills")
    raw_rel = Path("target/raw_skills")
    for skill in sorted(affected):
        source = worker / improved_rel / skill
        target = workspace / improved_rel / skill
        if source.is_dir():
            replace_path(source, target)
        elif target.exists():
            shutil.rmtree(target)
        raw_source = worker / raw_rel / skill
        if raw_source.is_dir():
            replace_path(raw_source, workspace / raw_rel / skill)
    metadata = merge_metadata(workspace, worker, affected)
    current = {
        path.name
        for path in (workspace / improved_rel).iterdir()
        if path.is_dir()
    }
    pipeline_contracts.validate_metadata(metadata, current)
    archived_rel = Path("run") / cluster / "ops" / str(op_index) / "verification.json"
    replace_path(worker / archived_rel, workspace / archived_rel)
    op_goal_rel = Path("run") / cluster / "ops" / str(op_index) / "evolve-goal.json"
    replace_path(worker / op_goal_rel, workspace / op_goal_rel)
    for suffix in result["suffixes"]:
        merge_worker_statuses(worker, workspace, str(suffix))
    merge_worker_log(worker, workspace)


def _finding_audit(workspace: Path, cluster: str) -> dict[str, object]:
    path = workspace / "traces/derived/findings" / cluster / "finding.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "detector": data.get("detector"),
        "routing": data.get("routing"),
        "severity": data.get("severity"),
        "confidence": data.get("confidence"),
        "score": data.get("score"),
    }


def _emit_edit_decisions(
    workspace: Path,
    max_ops_per_skill: int,
    min_super_score: float,
) -> None:
    path = workspace / "run/goal-reduction.json"
    if not path.is_file():
        return
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return
    if not isinstance(document, dict):
        return
    document["max_ops_per_skill"] = document.get("max_ops_per_skill", max_ops_per_skill)
    document["min_super_score"] = document.get("min_super_score", min_super_score)
    document["retry_budget"] = document.get("retry_budget", RETRY_BUDGET)
    document["max_attempts"] = document.get("max_attempts", RETRY_BUDGET + 1)
    atomic_write_json(path, document)
    policy = {
        "max_ops_per_skill": document["max_ops_per_skill"],
        "min_super_score": document["min_super_score"],
        "retry_budget": document["retry_budget"],
        "max_attempts": document["max_attempts"],
    }
    for row in document.get("decisions") or []:
        if not isinstance(row, dict):
            continue
        pipeline_metrics.record_instant(
            metrics_workspace(workspace),
            "edit-decision",
            f"{row.get('cluster')}-op-{row.get('op_index')}",
            {**row, **policy},
        )


def _emit_goal_decision(workspace: Path, cluster: str, goal: Path) -> None:
    try:
        data = json.loads(goal.read_text())
    except json.JSONDecodeError:
        return
    action = data.get("action") if isinstance(data, dict) else None
    if not isinstance(action, dict):
        return
    ops = action.get("ops") if isinstance(action.get("ops"), list) else []
    skills: list[str] = []
    names: set[str] = set()
    for op in ops:
        if not isinstance(op, dict):
            continue
        for name in skill_names_mod.skill_names(op):
            if name not in names:
                names.add(name)
                skills.append(name)
    pipeline_metrics.record_instant(
        metrics_workspace(workspace),
        "goal-decision",
        cluster,
        {
            "cluster": cluster,
            "disposition": action.get("disposition", "change" if ops else "no_change"),
            "reason": action.get("reason"),
            "op_count": len(ops),
            "ops": [op.get("op") for op in ops if isinstance(op, dict)],
            "skills": skills,
        },
    )


def _emit_judge_decision(
    workspace: Path,
    cluster: str,
    op_index: int,
    verification: Path,
    attempt: int,
) -> None:
    try:
        data = json.loads(verification.read_text())
    except json.JSONDecodeError:
        return
    feedback = data.get("feedback") if isinstance(data, dict) else None
    if not isinstance(feedback, dict):
        return
    action = feedback.get("action") if isinstance(feedback.get("action"), dict) else {}
    per_skill = feedback.get("per_skill") if isinstance(feedback.get("per_skill"), list) else []
    used = [
        row.get("retries_used")
        for row in per_skill
        if isinstance(row, dict) and isinstance(row.get("retries_used"), int)
    ]
    failed = [
        row.get("skill")
        for row in per_skill
        if isinstance(row, dict) and row.get("status") == "fail"
    ]
    judge_op = action.get("op")
    pipeline_metrics.record_instant(
        metrics_workspace(workspace),
        "judge-decision",
        f"{cluster}-op-{op_index}-try-{attempt}",
        {
            "cluster": cluster,
            "op_index": op_index,
            "attempt": attempt,
            "judge_action": judge_op,
            "judge_to": action.get("to"),
            "retry_budget": feedback.get("retry_budget", RETRY_BUDGET),
            "max_attempts": RETRY_BUDGET + 1,
            "retries_used": max(used) if used else 0,
            "will_retry": judge_op == "back" and attempt <= RETRY_BUDGET,
            "overall_status": feedback.get("overall_status"),
            "failed_skills": failed,
        },
    )


def _finding_confidence(workspace: Path, cluster: str) -> float:
    path = workspace / "traces/derived/findings" / cluster / "finding.json"
    if not path.is_file():
        return 0.0
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return 0.0
    try:
        return float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def fanout_operations(
    workspace: Path,
    run_id: str,
    clusters: list[str],
    workers: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    max_ops_per_skill: int | None = None,
    min_super_score: float | None = None,
) -> None:
    (workspace / "run/evolve-goal.json").unlink(missing_ok=True)
    (workspace / "run/verification.json").unlink(missing_ok=True)
    tasks: list[dict[str, object]] = []
    for cluster in clusters:
        if infrastructure_evolution_blocked(workspace, cluster):
            refuse_infrastructure_scope(workspace, cluster)
            continue
        cluster_goal = workspace / "run" / cluster / "evolve-goal.json"
        goal = pipeline_contracts.validate_goal(cluster_goal)
        for op_index, op in enumerate(goal_ops(cluster_goal), start=1):
            enforce_creation_policy(workspace, cluster, goal, op)
            op_goal = materialize_op_goal(
                workspace,
                cluster,
                op_index,
                goal,
                op,
                activate=False,
            )
            affected = set(skill_names_mod.skill_names(op))
            skill_rows = op.get("skills") or []
            skill_goal = ""
            if skill_rows and isinstance(skill_rows[0], dict):
                skill_goal = str(skill_rows[0].get("goal") or "")
            tasks.append(
                {
                    "cluster": cluster,
                    "op_index": op_index,
                    "op": op,
                    "op_goal": op_goal,
                    "affected": affected,
                    "conflicts": affected or {"*"},
                    "confidence": _finding_confidence(workspace, cluster),
                    "skill_goal": skill_goal,
                }
            )
            tasks[-1]["rank"] = rank_edit(workspace, tasks[-1])
            tasks[-1]["confidence"] = tasks[-1]["rank"]["confidence"]
    tasks = reduce_operation_tasks(workspace, tasks)
    cap = configured_max_ops_per_skill(max_ops_per_skill)
    gate = configured_min_super_score(min_super_score)
    tasks = bundle_same_skill_updates(workspace, tasks, cap, gate)
    _emit_edit_decisions(workspace, cap, gate)

    batches = operation_batches(tasks)
    batch_state = {
        "ready_us": time.time_ns() // 1000,
        "batch_index": 1,
        "batch_count": len(batches),
        "batch_size": 0,
    }

    def work(task_object: object) -> object:
        task = task_object
        cluster = str(task["cluster"])
        op_index = int(task["op_index"])
        op = task["op"]
        item = f"{run_id}-{cluster}-op-{op_index}"
        conflicts = sorted(str(name) for name in task["conflicts"])
        queue_wait_ms = record_queue(
            workspace,
            "operation-queue",
            item,
            int(batch_state["ready_us"]),
            {
                "workers": workers,
                "pool_items": batch_state["batch_size"],
                "batch_index": batch_state["batch_index"],
                "batch_count": batch_state["batch_count"],
                "conflicts": conflicts,
            },
        )
        private = copy_worker(workspace, "operations", item)
        private_op_goal = (
            private / "run" / cluster / "ops" / str(op_index) / "evolve-goal.json"
        )
        shutil.copy2(private_op_goal, private / "run/evolve-goal.json")
        bundle = task.get("bundle") if isinstance(task.get("bundle"), dict) else {}
        bundle_note = ""
        if bundle:
            bundle_note = (
                f" bundle.selected lists {len(bundle.get('selected') or [])} "
                "source edits of this skill. Apply every section and directory "
                "goal in this one op. Verification and judge run once, with --op 1."
            )
        context = (
            f"This isolated session is cluster <{cluster}>, action.ops item "
            f"{op_index}: {json.dumps(op, ensure_ascii=False)}. The active goal "
            "contains only this op. Use --op 1 where a checker accepts it. "
            "workspace/run/evolve-goal.json is the worker-local compatibility "
            f"copy; the authoritative op goal is workspace/run/{cluster}/ops/"
            f"{op_index}/evolve-goal.json.{bundle_note}"
        )
        action = "back"
        attempt = 0
        suffixes: list[str] = []
        current_stage = "optimize"
        suffix = f"{item}-try-1"
        op_metadata = {
            "workers": workers,
            "pool_items": batch_state["batch_size"],
            "batch_index": batch_state["batch_index"],
            "batch_count": batch_state["batch_count"],
            "conflicts": conflicts,
            "queue_wait_ms": queue_wait_ms,
            "bundle_size": len(bundle.get("selected") or []) or 1,
            "super_score": (task.get("rank") or {}).get("super_score"),
            "retry_budget": RETRY_BUDGET,
            "max_attempts": RETRY_BUDGET + 1,
            **_rank_fields(task),
        }
        try:
            while action == "back" and attempt < RETRY_BUDGET + 1:
                attempt += 1
                suffix = f"{item}-try-{attempt}"
                suffixes.append(suffix)
                current_stage = "optimize"
                write_status(workspace, current_stage, suffix, "started")
                run_session(
                    current_stage,
                    private,
                    instruction(current_stage, context),
                    auth,
                    model,
                    install_agent,
                    suffix,
                    {**op_metadata, "attempt": attempt},
                )
                optimized_outputs = validate_optimized_op(private, op)
                complete_session(
                    private,
                    current_stage,
                    suffix,
                    [private_op_goal, *optimized_outputs],
                )
                current_stage = "verifiter"
                write_status(workspace, current_stage, suffix, "started")
                run_session(
                    current_stage,
                    private,
                    instruction(
                        current_stage,
                        context
                        + " Write a new workspace/run/verification.json. "
                        "Keep feedback.action and every per-skill action null for Judge.",
                    ),
                    auth,
                    model,
                    install_agent,
                    suffix,
                    {**op_metadata, "attempt": attempt},
                )
                verification = private / "run/verification.json"
                pipeline_contracts.validate_verification(
                    verification,
                    judged=False,
                    expected_skills=set(skill_names_mod.skill_names(op)),
                )
                complete_session(private, current_stage, suffix, [verification])
                current_stage = "judge"
                write_status(workspace, current_stage, suffix, "started")
                run_session(
                    current_stage,
                    private,
                    instruction(current_stage, context),
                    auth,
                    model,
                    install_agent,
                    suffix,
                    {**op_metadata, "attempt": attempt},
                )
                action = judge_action(verification)
                _emit_judge_decision(
                    workspace, cluster, op_index, verification, attempt
                )
                archive_verification(private, cluster, op_index)
                archived = (
                    private
                    / "run"
                    / cluster
                    / "ops"
                    / str(op_index)
                    / "verification.json"
                )
                complete_session(private, current_stage, suffix, [archived])
            if action == "back":
                raise SystemExit(
                    f"judge requested another retry after budget {RETRY_BUDGET} "
                    f"for {cluster} op {op_index}"
                )
            return {
                **task,
                "worker": private,
                "suffixes": suffixes,
            }
        except BaseException as error:
            write_status(
                workspace, current_stage, suffix, "failed", error=str(error)
            )
            remove_worker_workspace(private)
            raise

    for batch_index, batch in enumerate(batches, start=1):
        batch_state["batch_index"] = batch_index
        batch_state["batch_size"] = len(batch)
        try:
            results = run_pool(batch, workers, work)
        except BaseException:
            remove_worker_stage(workspace, "operations")
            raise
        try:
            for result in results:
                publish_operation_result(workspace, result)
        finally:
            for result in results:
                remove_worker_workspace(result["worker"])


def write_pipeline_summary(workspace: Path, clusters: list[str]) -> Path:
    scopes: list[dict[str, object]] = []
    operations: list[dict[str, object]] = []
    reduction_path = workspace / "run/goal-reduction.json"
    reduction = json.loads(reduction_path.read_text()) if reduction_path.is_file() else {}
    decisions = {
        (row["cluster"], row["op_index"]): row
        for row in reduction.get("decisions") or []
    }
    for cluster in sorted(clusters):
        goal_path = workspace / "run" / cluster / "evolve-goal.json"
        goal = pipeline_contracts.validate_goal(goal_path)
        action = goal["action"]
        scope_ops = action["ops"]
        scopes.append(
            {
                "scope": cluster,
                "goal": goal_path.relative_to(workspace).as_posix(),
                "disposition": action.get("disposition", "change"),
                "reason": action.get("reason"),
                "operation_count": len(scope_ops),
            }
        )
        for op_index, op in enumerate(scope_ops, start=1):
            decision = decisions.get((cluster, op_index), {"decision": "selected"})
            verification_cluster = str(
                decision.get("selected_cluster", cluster)
            )
            verification_index = int(
                decision.get("selected_op_index", op_index)
            )
            verification_path = (
                workspace
                / "run"
                / verification_cluster
                / "ops"
                / str(verification_index)
                / "verification.json"
            )
            publication_path = (
                workspace
                / "run"
                / cluster
                / "ops"
                / str(op_index)
                / "publication.json"
            )
            publication = (
                json.loads(publication_path.read_text())
                if publication_path.is_file()
                else {"accepted": True, "reason": None}
            )
            accepted = bool(publication.get("accepted", True))
            judge_action_value = None
            verification_rel = None
            if verification_path.is_file() or accepted:
                verification = pipeline_contracts.validate_verification(
                    verification_path, judged=True
                )
                judge_action_value = verification["feedback"]["action"]["op"]
                verification_rel = verification_path.relative_to(
                    workspace
                ).as_posix()
            operations.append(
                {
                    "scope": cluster,
                    "op_index": op_index,
                    "op": op["op"],
                    "skills": sorted(skill_names_mod.skill_names(op)),
                    "reduction_decision": decision["decision"],
                    "accepted": accepted,
                    "publication_reason": publication.get("reason"),
                    "goal": (
                        Path("run")
                        / cluster
                        / "ops"
                        / str(op_index)
                        / "evolve-goal.json"
                    ).as_posix(),
                    "verification": verification_rel,
                    "judge_action": judge_action_value,
                }
            )
    document = {
        "schema_version": 1,
        "scopes": scopes,
        "operations": operations,
        "no_change_scopes": [
            row["scope"] for row in scopes if row["disposition"] == "no_change"
        ],
    }
    destination = workspace / "run/pipeline-summary.json"
    destination.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )
    return destination


def execute(args: argparse.Namespace) -> None:
    global ACTIVE_BACKEND
    workspace = (ROOT / "workspace/runs" / args.run_id).resolve()
    if args.init:
        initialize_workspace(workspace)
        return
    require_path(workspace, "run workspace")
    require_path(
        workspace / "target/to_be_improved_skills", "existing skills directory"
    )
    require_seed_inputs(workspace)
    ACTIVE_BACKEND = select_backend(args.agent, args.allow_local_fallback)
    auth = require_auth() if ACTIVE_BACKEND == "docker-claude" else {}
    if args.build:
        build_images()

    try:
        write_status(workspace, "preprocessing", args.run_id, "started")
        config_path = ROOT / "common/preprocessing-config.json"
        try:
            mining_result = mining_engine.run(
                workspace,
                config_path,
                clustered=args.cluster,
                profile_name=getattr(args, "mining_profile", None),
                experiment_profiles=getattr(args, "experiment_profile", None),
                span_factory=pipeline_metrics.span,
            )
            active_clustered = bool(
                mining_result["active"]["clustering"]["cluster_count"]
            )
            if getattr(args, "review_clusters", False):
                run_session(
                    "preprocessing",
                    workspace,
                    instruction(
                        "preprocessing",
                        (
                            "Review only the canonical turns and pointer manifests. "
                            "Improve unclear cluster directory names when useful and "
                            "update each manifest record's cluster field to match. "
                            "Do not read raw vendor JSONL or copy trace payloads."
                        ),
                        cluster=active_clustered,
                    ),
                    auth,
                    args.model,
                    not args.agent_installed,
                    args.run_id,
                )
        except BaseException as error:
            write_status(
                workspace, "preprocessing", args.run_id, "failed", error=str(error)
            )
            raise
        with pipeline_metrics.span(
            workspace,
            "validate-preprocessing",
            args.run_id,
            "deterministic",
        ):
            preprocessing_outputs = validate_preprocessing(
                workspace, active_clustered
            )
        complete_session(
            workspace, "preprocessing", args.run_id, preprocessing_outputs
        )

        run_session(
            "label-skills",
            workspace,
            instruction("label-skills", "Label the complete existing skill set once."),
            auth,
            args.model,
            not args.agent_installed,
            args.run_id,
        )
        metadata_path = (
            workspace / "target/to_be_improved_skills_metadata/metadata.json"
        )
        seed_names = {
            path.name
            for path in (workspace / "target/to_be_improved_skills").iterdir()
            if path.is_dir()
        }
        with pipeline_metrics.span(
            workspace,
            "validate-skill-labels",
            args.run_id,
            "deterministic",
        ):
            pipeline_contracts.validate_metadata(metadata_path, seed_names)
        complete_session(workspace, "label-skills", args.run_id, [metadata_path])

        unit_kind = getattr(args, "evolution_unit", "cluster")
        clusters = evolution_units(workspace, active_clustered, unit_kind)
        refuse_blocked_scopes(workspace, active_clustered, unit_kind)
        if not clusters:
            print(
                f"completed run {args.run_id}: no evolution units remained after "
                "the configured selection and infrastructure filters"
            )
            return
        scope_clustered = active_clustered or unit_kind == "finding"
        cluster_workers = getattr(args, "cluster_workers", DEFAULT_CLUSTER_WORKERS)
        op_workers = getattr(args, "op_workers", DEFAULT_OP_WORKERS)
        fanout_diagnosis(
            workspace,
            args.run_id,
            clusters,
            scope_clustered,
            cluster_workers,
            auth,
            args.model,
            not args.agent_installed,
            unit_kind,
        )
        fanout_goals(
            workspace,
            args.run_id,
            clusters,
            scope_clustered,
            cluster_workers,
            auth,
            args.model,
            not args.agent_installed,
            unit_kind,
        )
        fanout_operations(
            workspace,
            args.run_id,
            clusters,
            op_workers,
            auth,
            args.model,
            not args.agent_installed,
            getattr(args, "max_ops_per_skill", None),
            getattr(args, "min_super_score", None),
        )
        write_pipeline_summary(workspace, clusters)

        print(f"completed run {args.run_id}: {workspace}")

    finally:
        pipeline_metrics.write_run_report(workspace)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="directory name under workspace/runs")
    parser.add_argument(
        "--init", action="store_true", help="create the run workspace and stop"
    )
    parser.add_argument(
        "--build", action="store_true", help="build the shared agent runtime image"
    )
    parser.add_argument(
        "--cluster", action="store_true", help="run clustering and fan out by cluster"
    )
    parser.add_argument(
        "--review-clusters",
        action="store_true",
        help="ask the preprocessing agent to review deterministic cluster names",
    )
    parser.add_argument(
        "--mining-profile",
        help="override active_profile from preprocessing-config.json",
    )
    parser.add_argument(
        "--experiment-profile",
        action="append",
        default=[],
        help="run a named profile in an isolated experiment namespace; repeatable",
    )
    parser.add_argument(
        "--evolution-unit",
        choices=("finding", "cluster"),
        default="finding",
        help="fan out by selected high-confidence finding or topic cluster",
    )
    parser.add_argument(
        "--cluster-workers",
        type=int,
        default=DEFAULT_CLUSTER_WORKERS,
        help="maximum isolated diagnosis and goal workers",
    )
    parser.add_argument(
        "--op-workers",
        type=int,
        default=DEFAULT_OP_WORKERS,
        help="maximum isolated non-conflicting operation workers",
    )
    parser.add_argument(
        "--max-ops-per-skill",
        type=int,
        help=(
            "merge up to this many update edits of the same skill into one "
            "optimize, verify, and judge pass "
            "(default: evolution_policy.max_ops_per_skill, or 5)"
        ),
    )
    parser.add_argument(
        "--min-super-score",
        type=float,
        help=(
            "same-skill edits below this super score do not join the bundle "
            "(default: evolution_policy.min_super_score, or 0)"
        ),
    )
    parser.add_argument("--model", help="model identifier for the selected backend")
    parser.add_argument(
        "--agent",
        choices=("auto", "cursor", "codex", "claude", "ollama", "docker-claude"),
        default="auto",
        help="agent backend; auto prefers Cursor, Codex, then Claude",
    )
    parser.add_argument(
        "--allow-local-fallback",
        action="store_true",
        help="allow Ollama only when no hosted CLI is authenticated",
    )
    parser.add_argument(
        "--agent-installed",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_id):
        parser.error("run_id may contain only letters, numbers, dot, underscore, dash")
    if args.cluster_workers < 1 or args.op_workers < 1:
        parser.error("worker counts must be at least 1")
    if args.max_ops_per_skill is not None and args.max_ops_per_skill < 1:
        parser.error("max_ops_per_skill must be at least 1")
    if args.min_super_score is not None and args.min_super_score < 0:
        parser.error("min_super_score must be non-negative")
    return args


if __name__ == "__main__":
    try:
        execute(parse_args())
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
