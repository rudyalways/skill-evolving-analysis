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
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CONFIG_PATH = ROOT / "common/preprocessing-config.json"
AGENT_CONFIG_PATH = ROOT / "common/agent-config.json"
VERIFICATION_INPUT_TEMPLATE = (
    ROOT
    / "05_verifiter_agent"
    / "verifiter"
    / "verification-input.template.json"
)
KNOWN_BACKENDS = ("cursor", "codex", "claude", "docker-claude")
CONTAINER_WORKSPACE = "/opt/skill-evolver/skill_evolving_agents/workspace"
SESSION_ROOT = Path(
    os.environ.get("SKILL_EVOLVER_SESSION_ROOT", "")
    or Path(tempfile.gettempdir()) / "skill-evolver-sessions"
)
SKILL_CHANGELOG_DIR = Path("target/skill_changelogs")
POOL_CHANGELOG_DIR = Path("candidate_skills_changelog")
CHANGELOG_SUMMARY_LIMIT = 120
DEFAULT_CLUSTER_WORKERS = 16
DEFAULT_OP_WORKERS = 16
RETRY_BUDGET = 0
VERIFIER_RESPONSE_RETRY_BUDGET = 2
AGENT_SESSION_TIMEOUT_SECONDS = int(
    os.environ.get("SKILL_EVOLVER_AGENT_TIMEOUT_SECONDS", "180")
)
# One skill's checks and scored JSON were still being written at 180 seconds.
VERIFIER_SESSION_TIMEOUT_SECONDS = int(
    os.environ.get("SKILL_EVOLVER_VERIFIER_TIMEOUT_SECONDS", "360")
)
_EXECUTION_LOG_LOCK = threading.Lock()
ACTIVE_BACKEND = "docker-claude"
AGENT_NUMBERS = {
    "preprocessing": "01",
    "label-skills": "02.1",
    "label-traces-cluster": "02.2",
    "goal": "03",
    "optimize": "04",
    "verifiter": "05",
    "judge": "06",
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
_RECALL_PATH = ROOT / "03_goal_agent/skill-select/recall_skills.py"
_RECALL_SPEC = importlib.util.spec_from_file_location(
    "pipeline_recall_skills", _RECALL_PATH
)
recall_skills_mod = importlib.util.module_from_spec(_RECALL_SPEC)
assert _RECALL_SPEC.loader is not None
_RECALL_SPEC.loader.exec_module(recall_skills_mod)
_VERIFICATION_BUILDER_PATH = (
    ROOT
    / "05_verifiter_agent"
    / "verifiter"
    / "verification_from_goal.py"
)
sys.path.insert(0, str(_VERIFICATION_BUILDER_PATH.parent))
_VERIFICATION_BUILDER_SPEC = importlib.util.spec_from_file_location(
    "verification_from_goal_runtime", _VERIFICATION_BUILDER_PATH
)
verification_builder = importlib.util.module_from_spec(
    _VERIFICATION_BUILDER_SPEC
)
assert _VERIFICATION_BUILDER_SPEC.loader is not None
_VERIFICATION_BUILDER_SPEC.loader.exec_module(verification_builder)
_FORMAT_PATH = ROOT / "common/skill_format_checker.py"
_FORMAT_SPEC = importlib.util.spec_from_file_location(
    "skill_format_checker", _FORMAT_PATH
)
skill_format_checker = importlib.util.module_from_spec(_FORMAT_SPEC)
assert _FORMAT_SPEC.loader is not None
_FORMAT_SPEC.loader.exec_module(skill_format_checker)
_EVALUATION_PATH = ROOT / "common/skill_evaluation.py"
_EVALUATION_SPEC = importlib.util.spec_from_file_location(
    "skill_evaluation", _EVALUATION_PATH
)
skill_evaluation = importlib.util.module_from_spec(_EVALUATION_SPEC)
assert _EVALUATION_SPEC.loader is not None
_EVALUATION_SPEC.loader.exec_module(skill_evaluation)
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
        "04_optimize_agent/skill-edit/skill.md",
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
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(display or command), flush=True)
    if log_path is None:
        return subprocess.run(
            command,
            cwd=cwd or REPO,
            text=True,
            input=input_text,
            check=check,
            timeout=timeout,
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
            start_new_session=True,
        )
        if input_text is not None and process.stdin is not None:
            process.stdin.write(input_text)
            process.stdin.close()

        def pump_output() -> None:
            if process.stdout is not None:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)

        pump = threading.Thread(target=pump_output, daemon=True)
        pump.start()
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
        finally:
            pump.join(timeout=5)
            if process.stdout is not None:
                process.stdout.close()
    if check and code != 0:
        raise subprocess.CalledProcessError(code, command)
    return subprocess.CompletedProcess(command, code)


def failure_text(error: BaseException) -> str:
    """Short lane failure text. Timeout errors omit the agent command."""
    if isinstance(error, subprocess.TimeoutExpired):
        if error.timeout is None:
            return "timed out"
        return f"timed out after {error.timeout} seconds"
    lines = str(error).strip().splitlines()
    text = lines[0] if lines else error.__class__.__name__
    return text[:500]


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


def _contains_file(root: Path) -> bool:
    if not root.exists():
        return False
    return any(
        path.is_file() and path.name != ".DS_Store" for path in root.rglob("*")
    )


def workspace_was_started(workspace: Path) -> bool:
    """True once a pipeline start has written output into this directory."""
    if _contains_file(workspace / "logs") or _contains_file(
        workspace / "traces/derived"
    ):
        return True
    run_root = workspace / "run"
    return run_root.is_dir() and any(
        path.is_file()
        and path.name != ".DS_Store"
        and path.relative_to(run_root).as_posix() != "trace-selection.json"
        for path in run_root.rglob("*")
    )


def allocate_execution_workspace(
    source: Path, moment: datetime | None = None
) -> Path:
    """Move the seed into a minute-stamped execution directory.

    Every start writes ``<run-id>@YYYY-MM-DDTHH:MM`` and removes the unstamped
    seed. A second start in the same minute gets ``-2``.
    """
    started = moment.astimezone() if moment is not None else datetime.now().astimezone()
    base = f"{source.name}@{started.strftime('%Y-%m-%dT%H:%M')}"
    candidate = source.parent / base
    suffix = 2
    while candidate.exists():
        candidate = source.parent / f"{base}-{suffix}"
        suffix += 1
    initialize_workspace(candidate)
    for relative in ("traces/raw", "target"):
        origin = source / relative
        destination = candidate / relative
        if not origin.is_dir():
            continue
        shutil.rmtree(destination)
        shutil.copytree(origin, destination, symlinks=False)
    if candidate != source and "@" not in source.name:
        shutil.rmtree(source)
    print(f"execution directory: {candidate}")
    return candidate


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


def instruction(
    stage: str,
    context: str,
    *,
    cluster: bool = False,
    skill_paths: list[str] | None = None,
) -> str:
    paths = list(skill_paths if skill_paths is not None else SKILLS[stage])
    if stage == "preprocessing" and cluster:
        paths.append("01_preprocessing_agent/cluster/skill.md")
    skills = "\n".join(f"- {path}" for path in paths)
    if stage == "optimize":
        scope = (
            "Fast decision. One pass.\n\n"
            "Read AGENT.md and these skill files:\n"
            f"{skills}\n\n"
            "The working directory is `workspace/`. It contains the target skill "
            "directory and that skill's changelog beside it, `<skill>.md`. "
            "Explore that skill and its changelog. Edit the skill directory. "
            "Do not edit the changelog. Do not read or write metadata; the runner does that.\n"
            "Do not open the parent repository, other stages, logs, pipeline traces, "
            "raw vendor logs, or any skill this session does not name.\n"
        )
    else:
        scope = (
            "Fast decision. One pass. Do not explore.\n\n"
            "Read only AGENT.md and these skill files:\n"
            f"{skills}\n\n"
            "Then read only the input paths named in the session block below. "
            "Write the required output and stop.\n"
            "Do not open the parent repository, other stages, logs, pipeline traces, "
            "raw vendor logs, or any cluster, finding, or skill this session does not name.\n"
            "Do not search. Do not reread a file. Run a command only when one of those "
            "skill files tells you to run that command.\n"
        )
    return f"""{scope}Follow the output schema and stop condition in the stage skill; do not substitute a generic decision object.
Do not ask questions. Do not work on another stage, cluster, or op.

Session:
{context}

The host records execution status. Do not write logs or status records.
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
    json_output: bool = False,
    input_root: Path | None = None,
) -> None:
    del json_output
    data_root = input_root or workspace
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
        f"{data_root}:{CONTAINER_WORKSPACE}",
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
        details["session_add_dir"] = str(data_root)
    run(
        command,
        display=[
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "-v",
            f"{data_root}:{CONTAINER_WORKSPACE}",
            "[credentials and instruction omitted]",
            AGENT_RUNTIME_IMAGE,
        ],
        log_path=log_path,
        timeout=session_timeout_seconds(stage),
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


def load_agent_config(path: Path | None = None) -> dict:
    """Load agent backends. Exactly one entry has status active."""
    source = AGENT_CONFIG_PATH if path is None else path
    try:
        data = json.loads(source.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid agent config {source}: {error}") from error
    if data.get("schema_version") != 1:
        raise SystemExit(f"unsupported agent config: {source}")
    agents = data.get("agents")
    if not isinstance(agents, list) or not agents:
        raise SystemExit("agent config agents must be a non-empty list")
    seen: set[str] = set()
    active = 0
    for index, row in enumerate(agents):
        where = f"agents[{index}]"
        if not isinstance(row, dict):
            raise SystemExit(f"{where} must be an object")
        backend = row.get("backend")
        status = row.get("status")
        model = row.get("model")
        if backend not in KNOWN_BACKENDS:
            raise SystemExit(f"{where}.backend is unknown: {backend}")
        if not isinstance(backend, str) or backend in seen:
            raise SystemExit(f"{where}.backend duplicates {backend}")
        seen.add(backend)
        if status not in {"active", "inactive"}:
            raise SystemExit(f"{where}.status must be active or inactive")
        if not isinstance(model, str):
            raise SystemExit(f"{where}.model must be a string")
        if status == "active":
            active += 1
            if not model.strip():
                raise SystemExit(f"active agent {backend} needs a model")
    if active != 1:
        raise SystemExit(
            f"agent config must mark exactly one agent active, found {active}"
        )
    return data


def active_agent(config: dict | None = None) -> dict:
    data = load_agent_config() if config is None else config
    return next(row for row in data["agents"] if row["status"] == "active")


def configured_model(
    backend: str, override: str | None = None, config: dict | None = None
) -> str:
    if isinstance(override, str) and override.strip():
        return override.strip()
    data = load_agent_config() if config is None else config
    for row in data["agents"]:
        if row["backend"] == backend:
            model = str(row["model"]).strip()
            if not model:
                raise SystemExit(f"{backend} has no model in agent config")
            return model
    raise SystemExit(f"{backend} is not in agent config")


def select_backend(requested: str, allow_local: bool) -> str:
    del allow_local
    config = load_agent_config()
    if requested == "auto":
        backend = str(active_agent(config)["backend"])
    else:
        known = {str(row["backend"]) for row in config["agents"]}
        if requested not in known:
            raise SystemExit(f"{requested} is not in agent config")
        backend = requested
    if backend == "docker-claude":
        print(f"selected agent backend: {backend}")
        return backend
    checks = {
        "cursor": ["agent", "models"],
        "codex": ["codex", "login", "status"],
        "claude": ["claude", "auth", "status"],
    }
    if not authenticated(checks[backend]):
        raise SystemExit(f"{backend} is not installed or authenticated")
    print(f"selected agent backend: {backend}")
    return backend


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
    json_output: bool = False,
    input_root: Path | None = None,
) -> None:
    data_root = input_root or workspace
    view = make_session_view(stage, data_root, suffix)
    allowed = [str(data_root)]
    if details is not None:
        details["session_cwd"] = str(view)
        details["session_add_dir"] = str(data_root)

    try:
        if backend == "cursor":
            command = cursor_command(view, data_root, prompt, model)
            run(
                command,
                cwd=view,
                log_path=log_path,
                timeout=session_timeout_seconds(stage),
            )
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
            if json_output:
                command.append("--json")
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
            run(
                command,
                cwd=view,
                log_path=log_path,
                input_text=prompt,
                timeout=session_timeout_seconds(stage),
            )
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
            run(
                command,
                cwd=view,
                log_path=log_path,
                input_text=prompt,
                timeout=session_timeout_seconds(stage),
            )
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


def session_timeout_seconds(stage: str) -> int:
    """Verifier sessions get the longer limit. Every other stage stays at 180."""
    if stage == "verifiter":
        return VERIFIER_SESSION_TIMEOUT_SECONDS
    return AGENT_SESSION_TIMEOUT_SECONDS


def append_execution_event(workspace: Path, stage: str, event: str) -> None:
    path = workspace / "logs/execution.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "agent": AGENT_NUMBERS[stage],
        "state": stage,
        "event": event,
        "at": datetime.now(UTC).isoformat(),
    }
    line = json.dumps(row, separators=(",", ":")) + "\n"
    with _EXECUTION_LOG_LOCK:
        with path.open("a") as stream:
            stream.write(line)


def run_session(
    stage: str,
    workspace: Path,
    prompt: str,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    suffix: str,
    metadata: dict[str, object] | None = None,
    *,
    json_output: bool = False,
    input_root: Path | None = None,
) -> Path:
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
    append_execution_event(workspace, stage, "started")
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
                        json_output,
                        input_root,
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
                        json_output,
                        input_root,
                    )
            finally:
                details.update(session_counts(log_path))
    except BaseException as error:
        append_execution_event(workspace, stage, "failed")
        write_status(
            workspace, stage, suffix, "failed", error=failure_text(error)
        )
        raise
    append_execution_event(workspace, stage, "done")
    return log_path


def write_status(
    workspace: Path,
    stage: str,
    item: str,
    state: str,
    *,
    outputs: list[Path] | None = None,
    error: str | None = None,
    skills: list[str] | None = None,
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
    if skills:
        record["skills"] = [str(name) for name in skills if str(name).strip()]
    elif isinstance(previous.get("skills"), list):
        record["skills"] = previous["skills"]
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
            or name.endswith(".tmp")
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
        detach_skill_changelogs(workspace)
        pipeline_contracts.validate_metadata(metadata, current)


def write_publication(
    workspace: Path,
    cluster: str,
    op_index: int,
    *,
    accepted: bool,
    reason: str | None,
    outcome: str | None = None,
    selected_cluster: str | None = None,
    selected_op_index: int | None = None,
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
    publication: dict[str, object] = {
        "schema_version": 1,
        "accepted": accepted,
        "reason": reason,
        "outcome": outcome or ("accepted" if accepted else "rejected"),
    }
    if selected_cluster is not None and selected_op_index is not None:
        publication["selected_operation"] = {
            "cluster": selected_cluster,
            "op_index": selected_op_index,
        }
    atomic_write_json(path, publication)
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
        trajectory_relative = data.get("task_trajectory_path")
        if not isinstance(trajectory_relative, str) or not trajectory_relative:
            raise SystemExit(f"canonical turn has no task trajectory: {path}")
        trajectory_path = workspace / trajectory_relative
        pipeline_contracts.validate_task_trajectory(trajectory_path, trace_id)
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
    pipeline_contracts.validate_selection_decisions(
        signals / "selection-decisions.jsonl", signal_ids, selected_ids
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


QUALITY_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _quality_words(value: object) -> set[str]:
    if isinstance(value, str):
        return {token.casefold() for token in QUALITY_TOKEN.findall(value)}
    if isinstance(value, dict):
        return set().union(
            *(_quality_words(item) for item in value.values()),
            set(),
        )
    if isinstance(value, list):
        return set().union(*(_quality_words(item) for item in value), set())
    return set()


def _maximum_existing_skill_similarity(workspace: Path, op: dict) -> float:
    proposed = _quality_words(op)
    if len(proposed) < 8:
        return 0.0
    maximum = 0.0
    roots = (
        workspace / "target/raw_skills",
        workspace / "target/to_be_improved_skills",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*/SKILL.md"):
            existing = _quality_words(path.read_text(errors="replace"))
            union = proposed | existing
            if union:
                maximum = max(maximum, len(proposed & existing) / len(union))
    return maximum


def enforce_creation_policy(
    workspace: Path, cluster: str, goal: dict, op: dict
) -> None:
    finding_path = (
        workspace / "traces" / "derived" / "findings" / cluster / "finding.json"
    )
    if not finding_path.is_file():
        return
    config = json.loads((ROOT / "common/preprocessing-config.json").read_text())
    policy = config.get("evolution_policy") or {}
    finding = json.loads(finding_path.read_text())
    features = finding.get("features") or {}
    source = features.get("candidate_source")
    if source in {"methodology", "methodology_consolidated"}:
        quality = features.get("quality") or {}
        value = float(quality.get("value") or 0)
        minimum_value = float(policy.get("min_methodology_value", 0.08))
        if value < minimum_value:
            raise pipeline_contracts.ContractError(
                f"{cluster} proposes methodology below the utility gate: "
                f"value={value}, minimum={minimum_value}"
            )
        methodology_policy = config.get("methodology") or {}
        obviousness = float(quality.get("obviousness") or 0)
        task_specificity = float(quality.get("task_specificity") or 0)
        if obviousness > float(
            methodology_policy.get("max_obviousness", 0.55)
        ):
            raise pipeline_contracts.ContractError(
                f"{cluster} proposes obvious methodology: "
                f"obviousness={obviousness}"
            )
        if task_specificity > float(
            methodology_policy.get("max_task_specificity", 0.65)
        ):
            raise pipeline_contracts.ContractError(
                f"{cluster} proposes task-specific methodology: "
                f"task_specificity={task_specificity}"
            )
        similarity = _maximum_existing_skill_similarity(workspace, op)
        maximum_similarity = float(
            policy.get("novelty_max_similarity", 0.82)
        )
        if similarity > maximum_similarity:
            raise pipeline_contracts.ContractError(
                f"{cluster} proposes methodology already covered by a skill: "
                f"similarity={similarity:.3f}, maximum={maximum_similarity}"
            )
    if op.get("op") != "create":
        return
    evidence = finding.get("evidence") or []
    distinct_session_count = int(features.get("distinct_sessions") or 0)
    sessions = {
        value for value in [finding.get("session_id")]
        if isinstance(value, str) and value
    }
    distinct_session_count = max(distinct_session_count, len(sessions))
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
    enough_sessions = distinct_session_count >= int(
        policy.get("create_min_distinct_sessions", 2)
    )
    single_session_allowed = bool(policy.get("allow_single_session_create"))
    pattern_confidence = float(
        policy.get(
            "single_session_pattern_min_confidence",
            policy.get("create_min_confidence", 0.75),
        )
    )
    pattern_windows = int(features.get("distinct_windows") or 0)
    repeated_pattern_allowed = (
        bool(policy.get("allow_single_session_repeated_pattern_create"))
        and features.get("candidate_source") == "cut_pattern"
        and confidence >= pattern_confidence
        and pattern_windows
        >= int(policy.get("single_session_pattern_min_distinct_windows", 3))
    )
    ood_override = (
        is_ood and bool(policy.get("allow_single_session_ood_create", True))
    )
    methodology_allowed = (
        source in {"methodology", "methodology_consolidated"}
        and bool(policy.get("allow_single_session_methodology_create", False))
        and confidence
        >= float(policy.get("single_session_methodology_min_confidence", 0.82))
        and float((features.get("quality") or {}).get("value") or 0)
        >= float(policy.get("single_session_methodology_min_value", 0.18))
    )
    if (enough_evidence or methodology_allowed) and enough_confidence and (
        enough_sessions
        or single_session_allowed
        or repeated_pattern_allowed
        or ood_override
        or methodology_allowed
    ):
        return
    raise pipeline_contracts.ContractError(
        f"{cluster} proposes create without sufficient recurrence: "
        f"confidence={confidence}, evidence_records={len(evidence)}, "
        f"distinct_sessions={distinct_session_count}, "
        f"distinct_windows={pattern_windows}, "
        f"repeated_pattern={repeated_pattern_allowed}, "
        f"methodology={methodology_allowed}, ood={is_ood}. Goal "
        "should use no_change or update an existing skill."
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


def materialize_created_skill_metadata(
    workspace: Path,
    op: dict,
    cluster: str | None = None,
    run_id: str | None = None,
) -> None:
    """Merge create labels into the canonical metadata shape deterministically."""
    if op.get("op") != "create":
        return
    path = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    try:
        document = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        document = {"skills_metadata": []}
    rows = document.get("skills_metadata")
    if not isinstance(rows, list):
        rows = []
    by_name = {
        row.get("skill"): row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("skill"), str)
        and row["skill"]
    }
    lifecycle: dict[str, object] | None = None
    if cluster:
        finding_path = (
            workspace
            / "traces"
            / "derived"
            / "findings"
            / cluster
            / "finding.json"
        )
        if finding_path.is_file():
            finding = json.loads(finding_path.read_text())
            features = finding.get("features") or {}
            session_ids = {
                value
                for value in [finding.get("session_id")]
                if isinstance(value, str) and value
            }
            distinct_sessions = max(
                len(session_ids),
                int(features.get("distinct_sessions") or 0),
            )
            policy = preprocessing_config().get("evolution_policy") or {}
            minimum_sessions = int(
                policy.get("create_min_distinct_sessions", 2)
            )
            selection_path = workspace / "run/trace-selection.json"
            selection = (
                json.loads(selection_path.read_text())
                if selection_path.is_file()
                else {}
            )
            lifecycle = {
                "status": (
                    str(
                        policy.get(
                            "single_session_create_lifecycle",
                            "provisional",
                        )
                    )
                    if distinct_sessions < minimum_sessions
                    else "stable"
                ),
                "origin_run_id": selection.get("run_id") or workspace.name,
                "origin_finding_id": cluster,
                "origin_session_ids": sorted(session_ids),
                "distinct_sessions": distinct_sessions,
                "confidence": float(finding.get("confidence") or 0),
                "evidence_records": len(finding.get("evidence") or []),
                "distinct_windows": int(
                    features.get("distinct_windows") or 0
                ),
            }
            if features.get("candidate_source") in {
                "methodology",
                "methodology_consolidated",
            }:
                lifecycle["method_fingerprint"] = features.get(
                    "method_fingerprint"
                )
                lifecycle["methodology_value"] = float(
                    (features.get("quality") or {}).get("value") or 0
                )
            if selection.get("seeded_from"):
                lifecycle["seeded_from"] = selection["seeded_from"]
    for skill in op.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        name = skill.get("skill")
        if not isinstance(name, str) or not name:
            continue
        labels = [
            dict(label)
            for label in skill.get("labels") or []
            if isinstance(label, dict)
        ]
        existing = by_name.get(name)
        row = {
            "skill": name,
            "description": str(skill.get("description") or ""),
            "skill_types": labels,
            "unmatched_skill_types": [],
        }
        carried = (
            existing.get("changelog")
            if isinstance(existing, dict)
            else None
        )
        if isinstance(carried, list):
            append_changelog_lines(
                workspace / SKILL_CHANGELOG_DIR,
                name,
                lines_from_history(carried),
            )
        phase_lines = []
        for entry in skill_phase_entries(workspace, name, run_id):
            if entry.get("phase") == "verification":
                continue
            line = _phase_line(entry)
            if line:
                phase_lines.append(line)
        append_changelog_lines(
            workspace / SKILL_CHANGELOG_DIR, name, phase_lines
        )
        for field in ("dependencies", "sources"):
            value = skill.get(field)
            if value is None and isinstance(existing, dict):
                value = existing.get(field)
            if isinstance(value, list):
                row[field] = copy.deepcopy(value)
        if lifecycle is not None:
            row["lifecycle"] = lifecycle
        by_name[name] = row
    for name, row in by_name.items():
        if not isinstance(row, dict) or "changelog" not in row:
            continue
        history = row.pop("changelog")
        if isinstance(name, str) and isinstance(history, list):
            append_changelog_lines(
                workspace / SKILL_CHANGELOG_DIR,
                name,
                lines_from_history(history),
            )
    atomic_write_json(
        path,
        {
            "skills_metadata": [
                by_name[name] for name in sorted(by_name)
            ]
        },
    )


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
        if name == "create":
            problems = skill_format_checker.validate_authored_skill(
                improved / skill
            )
            if problems:
                raise SystemExit(
                    f"invalid created skill {skill}: " + "; ".join(problems)
                )
            evals = improved / skill / "evals/evals.json"
            if evals.is_file():
                eval_problems = skill_evaluation.validate_evals_file(
                    evals, skill
                )
                if eval_problems:
                    raise SystemExit(
                        f"invalid evals for {skill}: "
                        + "; ".join(eval_problems)
                    )
    for skill in removed:
        if (improved / skill).exists():
            raise SystemExit(f"removed skill still exists after {name}: {skill}")
    for skill in snapshot:
        if not (raw / skill).is_dir():
            raise SystemExit(f"raw skill snapshot was not produced: {skill}")
    current = {path.name for path in improved.iterdir() if path.is_dir()}
    metadata = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    detach_skill_changelogs(workspace)
    pipeline_contracts.validate_metadata(metadata, current)
    return [improved, raw, metadata]


def judge_action(verification: Path) -> str:
    data = pipeline_contracts.validate_verification(verification, judged=True)
    action = ((data.get("feedback") or {}).get("action") or {}).get("op")
    if action not in {"pass", "fail"}:
        raise SystemExit(f"judge did not set pass or fail in {verification}")
    return action


def apply_judge_formula(verification: Path) -> str:
    """Apply the validated, non-discretionary Judge pass/fail formula."""
    data = pipeline_contracts.validate_verification(verification, judged=False)
    feedback = data["feedback"]
    action = "pass" if feedback["overall_status"] == "pass" else "fail"
    feedback["action"] = {"op": action, "to": None}
    atomic_write_json(verification, data)
    pipeline_contracts.validate_verification(verification, judged=True)
    return action


def validate_replay_artifacts(
    workspace: Path, verification: dict
) -> list[Path]:
    replay = ((verification.get("feedback") or {}).get("replay") or {})
    if replay.get("available") is not True:
        return []
    root = workspace / "run/replay"
    manifest = root / "manifest.json"
    benchmark = root / "benchmark.json"
    held_out = root / "held-out-evals.json"
    require_path(manifest, "behavioral replay manifest")
    require_path(benchmark, "behavioral replay benchmark")
    require_path(held_out, "behavioral replay held-out evals")
    manifest_data = json.loads(manifest.read_text())
    manifest_problems = skill_evaluation.validate_replay_manifest_data(
        manifest_data
    )
    if manifest_problems:
        raise SystemExit(
            "invalid behavioral replay manifest: "
            + "; ".join(manifest_problems)
        )
    skill_name = str(manifest_data.get("skill") or "")
    development = (
        workspace
        / "target/to_be_improved_skills"
        / skill_name
        / "evals/evals.json"
    )
    require_path(development, "development evals")
    development_data = json.loads(development.read_text())
    held_out_data = json.loads(held_out.read_text())
    held_out_problems = skill_evaluation.validate_held_out_evals_data(
        held_out_data,
        skill_name,
        development_data,
    )
    held_out_digest = hashlib.sha256(held_out.read_bytes()).hexdigest()
    if manifest_data.get("held_out_sha256") != held_out_digest:
        held_out_problems.append(
            "manifest held_out_sha256 does not match held-out-evals.json"
        )
    held_out_ids = [
        row.get("id")
        for row in held_out_data.get("evals") or []
        if isinstance(row, dict)
    ]
    if manifest_data.get("held_out_eval_ids") != held_out_ids:
        held_out_problems.append(
            "manifest held_out_eval_ids do not match held-out-evals.json"
        )
    if held_out_problems:
        raise SystemExit(
            "invalid held-out behavioral evals: "
            + "; ".join(held_out_problems)
        )
    benchmark_problems = skill_evaluation.validate_benchmark_data(
        json.loads(benchmark.read_text())
    )
    if benchmark_problems:
        raise SystemExit(
            "invalid behavioral replay benchmark: "
            + "; ".join(benchmark_problems)
        )
    if (
        replay.get("kind") == "paired_skill_eval"
        and replay.get("status") == "pass"
        and not replay_meets_promotion_gate(replay)
    ):
        raise SystemExit(
            "paired replay claimed pass without meeting anti-overfit "
            "held-out and activation thresholds"
        )
    return [manifest, benchmark, held_out]


def replay_meets_promotion_gate(replay: dict) -> bool:
    if (
        replay.get("available") is not True
        or replay.get("status") != "pass"
        or replay.get("kind") != "paired_skill_eval"
    ):
        return False
    after = replay.get("after") or {}
    policy = preprocessing_config().get("evolution_policy") or {}
    return (
        int(after.get("held_out_cases") or 0)
        >= int(policy.get("promotion_min_held_out_cases", 2))
        and float(after.get("held_out_pass_rate", 0))
        >= float(policy.get("promotion_min_held_out_pass_rate", 0.8))
        and float(after.get("activation_false_positive_rate", 1))
        <= float(
            policy.get(
                "promotion_max_activation_false_positive_rate",
                0.2,
            )
        )
    )


def archive_verification(workspace: Path, cluster: str, op_index: int) -> None:
    source = workspace / "run/verification.json"
    require_path(source, "verification")
    target = workspace / "run" / cluster / "ops" / str(op_index)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target / "verification.json")
    verification_input = workspace / "run/verification-input.json"
    require_path(verification_input, "verification input")
    shutil.copy2(verification_input, target / "verification-input.json")
    goal = target / "evolve-goal.json"
    require_path(goal, "operation goal")
    changelog_source = workspace / "run/changelog.json"
    require_path(changelog_source, "operation changelog")
    changelog = target / "changelog.json"
    shutil.copy2(changelog_source, changelog)
    write_judge_record(target)
    pipeline_contracts.validate_operation_artifacts(target)


def _empty_diagnosis() -> dict[str, object]:
    return {
        "skill_capabilities_missing": [],
        "newly_detected_skill_capabilites_missing": [],
    }


def _diagnose_scope(
    workspace: Path,
    cluster: str,
    suffix: str,
    *,
    clustered: bool,
    unit_kind: str,
    workers: int,
    pool_items: int,
    ready_us: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
) -> tuple[str, str, Path]:
    stage = "label-traces-cluster"
    queue_wait_ms = record_queue(
        workspace,
        "diagnosis-queue",
        suffix,
        ready_us,
        {"workers": workers, "pool_items": pool_items},
    )
    private = copy_worker(workspace, stage, suffix)
    diagnosis = private / "run/diagnosis.json"
    diagnosis.unlink(missing_ok=True)
    source = scope_source(cluster, clustered, unit_kind)
    embedded_source = ""
    if unit_kind == "finding":
        finding_path = private / source / "finding.json"
        if finding_path.is_file():
            embedded_source = (
                "The complete finding.json input is embedded below. Do not "
                "read it from disk or look for alternate copies.\n"
                "<finding-json>\n"
                f"{finding_path.read_text()}"
                "</finding-json>\n"
            )
    try:
        run_session(
            stage,
            private,
            instruction(
                stage,
                f"This isolated session is cluster <{cluster}> at {source}. "
                f"{embedded_source}"
                "Use the finding slice as the trace. "
                "In legacy cluster mode read slice in cut.jsonl when it "
                "exists. Do not open canonical turns, manifest turn paths, "
                "or tool sidecars. The cwd's workspace entry already points "
                "at the worker root; do not create a nested workspace "
                f"directory. Write only this cluster's records exactly to "
                f"{diagnosis}. Then run exactly `python3 "
                "02.2_label_traces_cluster_agent/dignosis/"
                f"evolve-goal-checker.py {diagnosis}` once. Do not search "
                "for the checker.",
            ),
            auth,
            model,
            install_agent,
            suffix,
            {
                "workers": workers,
                "pool_items": pool_items,
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
        write_status(
            workspace, stage, suffix, "failed", error=failure_text(error)
        )
        remove_worker_workspace(private)
        raise


def _publish_diagnosis(
    workspace: Path, cluster: str, suffix: str, private: Path
) -> dict[str, object]:
    source = private / "run/diagnosis.json"
    data = json.loads(source.read_text())
    scoped = workspace / "run" / cluster / "diagnosis.json"
    replace_path(source, scoped)
    merge_worker_log(private, workspace)
    complete_session(workspace, "label-traces-cluster", suffix, [scoped])
    return data if isinstance(data, dict) else {}


def _diagnosis_document(
    clusters: list[str], published: dict[str, dict[str, object]]
) -> dict[str, object]:
    known: list[object] = []
    ood: list[object] = []
    feedback: dict[str, object] = {}
    for cluster in clusters:
        data = published[cluster]
        known.extend(data.get("skill_capabilities_missing") or [])
        ood.extend(data.get("newly_detected_skill_capabilites_missing") or [])
        if "feedback" in data:
            feedback[cluster] = data["feedback"]
    document: dict[str, object] = {
        "skill_capabilities_missing": known,
        "newly_detected_skill_capabilites_missing": ood,
    }
    if feedback:
        document["feedback_by_cluster"] = feedback
    return document


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
        atomic_write_json(aggregate, _empty_diagnosis())
        return aggregate
    items = [(cluster, f"{run_id}-{cluster}") for cluster in clusters]
    for _cluster, suffix in items:
        write_status(workspace, stage, suffix, "started")

    ready_us = time.time_ns() // 1000

    def work(item: object) -> object:
        cluster, suffix = item
        return _diagnose_scope(
            workspace,
            str(cluster),
            str(suffix),
            clustered=clustered,
            unit_kind=unit_kind,
            workers=workers,
            pool_items=len(items),
            ready_us=ready_us,
            auth=auth,
            model=model,
            install_agent=install_agent,
        )

    try:
        results = run_pool(items, workers, work)
    except BaseException:
        remove_worker_stage(workspace, stage)
        raise
    try:
        published = {
            str(cluster): _publish_diagnosis(
                workspace, str(cluster), str(suffix), private
            )
            for cluster, suffix, private in results
        }
        document = _diagnosis_document(clusters, published)
        atomic_write_json(aggregate, document)
        pipeline_contracts.validate_diagnosis(
            aggregate, set(clusters) if clustered else None
        )
        return aggregate
    finally:
        for _cluster, _suffix, private in results:
            remove_worker_workspace(private)


def _goal_skill_names(
    goal_path: Path | None, recalled: list[dict] | None
) -> list[str]:
    """Names the live goal bar can show before an operation changelog exists."""
    names: list[str] = []

    def add(value: object) -> None:
        if not isinstance(value, str):
            return
        name = skill_names_mod.bare(value).strip()
        if name and name not in names:
            names.append(name)

    if goal_path is not None and goal_path.is_file():
        try:
            data = json.loads(goal_path.read_text())
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            goal = data.get("goal")
            if isinstance(goal, dict):
                improve = goal.get("improve_skills")
                if isinstance(improve, list):
                    for item in improve:
                        if isinstance(item, str):
                            add(item)
                        elif isinstance(item, dict):
                            add(item.get("skill"))
            action = data.get("action")
            if isinstance(action, dict):
                for op in action.get("ops") or []:
                    if isinstance(op, dict):
                        for name in skill_names_mod.skill_names(op):
                            add(name)
    if names:
        return names
    for row in recalled or []:
        if isinstance(row, dict):
            add(row.get("skill"))
    return names


def _publish_goal_skills(
    workspace: Path,
    suffix: str,
    *,
    goal_path: Path | None = None,
    recalled: list[dict] | None = None,
) -> None:
    names = _goal_skill_names(goal_path, recalled)
    if names:
        write_status(workspace, "goal", suffix, "started", skills=names)


def _goal_scope(
    workspace: Path,
    cluster: str,
    suffix: str,
    *,
    clustered: bool,
    unit_kind: str,
    workers: int,
    pool_items: int,
    ready_us: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
) -> tuple[str, str, Path]:
    stage = "goal"
    queue_wait_ms = record_queue(
        workspace,
        "goal-queue",
        suffix,
        ready_us,
        {"workers": workers, "pool_items": pool_items},
    )
    private = copy_worker(workspace, stage, suffix)
    private_cluster = private / "run" / cluster
    scoped_diagnosis = private_cluster / "diagnosis.json"
    scoped_diagnosis_bytes = (
        scoped_diagnosis.read_bytes() if scoped_diagnosis.is_file() else None
    )
    if private_cluster.exists():
        shutil.rmtree(private_cluster)
    if scoped_diagnosis_bytes is not None:
        diagnosis_path = private / "run/diagnosis.json"
        diagnosis_path.parent.mkdir(parents=True, exist_ok=True)
        diagnosis_path.write_bytes(scoped_diagnosis_bytes)
    source = scope_source(cluster, clustered, unit_kind)
    try:
        matching = private_cluster / "label-matching.json"
        goal = private_cluster / "evolve-goal.json"
        cluster_source = (
            private / "traces/derived/findings"
            if unit_kind == "finding"
            else private / "traces/derived/cluster"
        )
        taxonomy_path = ROOT / "skill_capabilites/skill_capabilites.json"
        recall_config_path = ROOT / "common/recall-config.json"
        preflight_available = (
            taxonomy_path.is_file()
            and recall_config_path.is_file()
            and (private / "run/diagnosis.json").is_file()
            and (
                private
                / "target/to_be_improved_skills_metadata/metadata.json"
            ).is_file()
        )
        recalled: list[dict] | None = None
        if preflight_available:
            diagnosis = json.loads(
                (private / "run/diagnosis.json").read_text()
            )
            metadata = json.loads(
                (
                    private
                    / "target/to_be_improved_skills_metadata/metadata.json"
                ).read_text()
            )
            skill_dirs = recall_skills_mod.skill_dirs(
                private / "target/to_be_improved_skills"
            )
            cluster_dirs = recall_skills_mod.skill_dirs(cluster_source)
            leaves = recall_skills_mod.skill_type_checker.leaf_paths(
                taxonomy_path
            )
            recall_config = recall_skills_mod.load_config(recall_config_path)
            matching_data = recall_skills_mod.recall(
                diagnosis,
                metadata,
                skill_dirs,
                cluster_dirs,
                leaves,
                recall_config,
            )
            scoped_matches = [
                row
                for row in matching_data["clusters"]
                if row.get("cluster") == cluster
                or (cluster == "cut" and "cluster" not in row)
            ]
            if not scoped_matches:
                scoped_matches = [
                    {"cluster": cluster, "labels": [], "skills": []}
                ]
            matching_data = {
                "matching": matching_data["matching"],
                "clusters": scoped_matches,
            }
            atomic_write_json(matching, matching_data)
            matching_data = pipeline_contracts.validate_label_matching(
                matching, cluster
            )
            recalled = matching_data["clusters"][0]["skills"]
        creation_error: str | None = None
        if recalled == []:
            try:
                enforce_creation_policy(
                    workspace, cluster, {}, {"op": "create", "skills": []}
                )
            except pipeline_contracts.ContractError as error:
                creation_error = str(error)
        if creation_error is not None:
            atomic_write_json(
                goal,
                {
                    "goal": {
                        "improve_harness": {"scope": "out_of_scope"},
                        "improve_skills": [],
                        "avoid": (
                            "Do not create or edit a skill without "
                            "policy-qualified evidence."
                        ),
                    },
                    "reasoning": creation_error,
                    "plan": "Leave skills unchanged.",
                    "feedback_to": "diagnosis",
                    "action": {
                        "disposition": "no_change",
                        "reason": creation_error,
                        "ops": [],
                    },
                },
            )
            with pipeline_metrics.span(
                workspace,
                stage,
                suffix,
                "deterministic",
                metadata={"policy_no_change": True},
            ):
                pass
        else:
            if matching.is_file():
                diagnosis_text = (private / "run/diagnosis.json").read_text()
                matching_text = matching.read_text()
                finding_path = private / source / "finding.json"
                finding_text = (
                    finding_path.read_text() if finding_path.is_file() else ""
                )
                session_context = (
                    "Select is already complete. The complete inputs are "
                    "embedded below; do not read them from disk, glob for "
                    "copies, or run recall again.\n"
                    f"<diagnosis-json>\n{diagnosis_text}</diagnosis-json>\n"
                    f"<label-matching-json>\n{matching_text}"
                    "</label-matching-json>\n"
                    f"<finding-json>\n{finding_text}</finding-json>\n"
                    f"Write {goal}."
                )
            else:
                clusters_argument = (
                    " --clusters workspace/traces/derived/findings"
                    if unit_kind == "finding"
                    else ""
                )
                session_context = (
                    f"Run select with `--cluster '{cluster}'"
                    f"{clusters_argument} --out {matching}`, then write {goal}."
                )
            _publish_goal_skills(workspace, suffix, recalled=recalled)
            run_session(
                stage,
                private,
                instruction(
                    stage,
                    f"This isolated session is cluster <{cluster}> at {source}. "
                    f"{session_context} The cwd's workspace entry already "
                    "points at the worker root; do not create a nested "
                    "workspace directory. Then run exactly `python3 "
                    "03_goal_agent/goal-generator/one_action.py "
                    f"{goal}` once. Do not search for the validator.",
                    skill_paths=(
                        ["03_goal_agent/goal-generator/skill.md"]
                        if matching.is_file()
                        else None
                    ),
                ),
                auth,
                model,
                install_agent,
                suffix,
                {
                    "workers": workers,
                    "pool_items": pool_items,
                    "queue_wait_ms": queue_wait_ms,
                },
            )
        pipeline_contracts.validate_label_matching(matching, cluster)
        pipeline_contracts.validate_goal(goal)
        _publish_goal_skills(
            workspace, suffix, goal_path=goal, recalled=recalled
        )
        _emit_goal_decision(workspace, str(cluster), goal)
        return cluster, suffix, private
    except BaseException as error:
        write_status(
            workspace, stage, suffix, "failed", error=failure_text(error)
        )
        remove_worker_workspace(private)
        raise


def _publish_goal(
    workspace: Path, cluster: str, suffix: str, private: Path
) -> None:
    source = private / "run" / cluster
    target = workspace / "run" / cluster
    target.mkdir(parents=True, exist_ok=True)
    matching = target / "label-matching.json"
    goal = target / "evolve-goal.json"
    replace_path(source / "label-matching.json", matching)
    replace_path(source / "evolve-goal.json", goal)
    merge_worker_log(private, workspace)
    sync_skill_changelogs(workspace)
    complete_session(workspace, "goal", suffix, [matching, goal])


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
        return _goal_scope(
            workspace,
            str(cluster),
            str(suffix),
            clustered=clustered,
            unit_kind=unit_kind,
            workers=workers,
            pool_items=len(items),
            ready_us=ready_us,
            auth=auth,
            model=model,
            install_agent=install_agent,
        )

    try:
        results = run_pool(items, workers, work)
    except BaseException:
        remove_worker_stage(workspace, stage)
        raise
    try:
        for cluster, suffix, private in results:
            _publish_goal(workspace, str(cluster), str(suffix), private)
    finally:
        for _cluster, _suffix, private in results:
            remove_worker_workspace(private)


def pipeline_diagnosis_and_goals(
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
    """Run each goal as soon as its diagnosis is published.

    Diagnosis and goal share one worker cap. Operation scheduling still waits
    for every goal so same-skill edits can be reduced together.
    """
    clusters = agent_scopes(workspace, clusters)
    aggregate = workspace / "run/diagnosis.json"
    if not clusters:
        atomic_write_json(aggregate, _empty_diagnosis())
        return aggregate
    if workers < 1:
        raise SystemExit("worker count must be at least 1")
    items = [(cluster, f"{run_id}-{cluster}") for cluster in clusters]
    for _cluster, suffix in items:
        write_status(workspace, "label-traces-cluster", suffix, "started")
    diagnosis_ready_us = time.time_ns() // 1000
    published: dict[str, dict[str, object]] = {}
    goal_futures: dict[Future, tuple[str, str]] = {}
    try:
        with ThreadPoolExecutor(
            max_workers=min(workers, len(items))
        ) as pool:
            diagnosis_futures = {
                pool.submit(
                    _diagnose_scope,
                    workspace,
                    cluster,
                    suffix,
                    clustered=clustered,
                    unit_kind=unit_kind,
                    workers=workers,
                    pool_items=len(items),
                    ready_us=diagnosis_ready_us,
                    auth=auth,
                    model=model,
                    install_agent=install_agent,
                ): (cluster, suffix)
                for cluster, suffix in items
            }
            try:
                for future in as_completed(diagnosis_futures):
                    _expected_cluster, expected_suffix = diagnosis_futures[future]
                    try:
                        cluster, suffix, private = future.result()
                    except BaseException as error:
                        write_status(
                            workspace,
                            "goal",
                            expected_suffix,
                            "skipped",
                            error=(
                                "upstream diagnosis failed: "
                                f"{failure_text(error)}"
                            ),
                        )
                        continue
                    try:
                        published[str(cluster)] = _publish_diagnosis(
                            workspace, str(cluster), str(suffix), private
                        )
                    finally:
                        remove_worker_workspace(private)
                    write_status(workspace, "goal", suffix, "started")
                    goal_futures[
                        pool.submit(
                            _goal_scope,
                            workspace,
                            str(cluster),
                            str(suffix),
                            clustered=clustered,
                            unit_kind=unit_kind,
                            workers=workers,
                            pool_items=len(items),
                            ready_us=time.time_ns() // 1000,
                            auth=auth,
                            model=model,
                            install_agent=install_agent,
                        )
                    ] = (str(cluster), str(suffix))
                successful_diagnoses = [
                    cluster for cluster in clusters if cluster in published
                ]
                document = _diagnosis_document(successful_diagnoses, published)
                with tempfile.NamedTemporaryFile(
                    suffix=".json", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                try:
                    atomic_write_json(temporary, document)
                    pipeline_contracts.validate_diagnosis(
                        temporary,
                        set(successful_diagnoses) if clustered else None,
                    )
                finally:
                    temporary.unlink(missing_ok=True)
                for future in as_completed(list(goal_futures)):
                    try:
                        cluster, suffix, private = future.result()
                    except BaseException:
                        continue
                    try:
                        _publish_goal(workspace, cluster, suffix, private)
                    finally:
                        remove_worker_workspace(private)
                atomic_write_json(aggregate, document)
                pipeline_contracts.validate_diagnosis(
                    aggregate,
                    set(successful_diagnoses) if clustered else None,
                )
            except BaseException:
                for future in (*diagnosis_futures, *goal_futures):
                    future.cancel()
                raise
    finally:
        remove_worker_stage(workspace, "label-traces-cluster")
        remove_worker_stage(workspace, "goal")
        for parent in (
            ROOT / ".pipeline-workers" / workspace.name,
            ROOT / ".pipeline-workers",
        ):
            try:
                parent.rmdir()
            except OSError:
                break
    return aggregate


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
                    "remove": [],
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
            for value in row.get("remove") or []:
                if value not in bucket["remove"]:
                    bucket["remove"].append(value)
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
        if bucket["remove"]:
            item["remove"] = bucket["remove"]
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
                "Apply every section, directory, and removal goal in this single update. "
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
            input_path = path.parent / "verification-input.json"
            if input_path.is_file():
                existing_input = json.loads(input_path.read_text())
                materialize_verification_input(
                    workspace,
                    document,
                    merged,
                    str(existing_input.get("run_id") or ""),
                    str(representative["cluster"]),
                    int(representative["op_index"]),
                    out=input_path,
                )
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
            skip_operation_phases(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                ("optimize", "verification", "judge"),
                reason,
            )
            finalize_unexecuted_operation(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                status="skipped",
                reason=reason,
            )
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
                bundled_reason = (
                    "bundled into "
                    f"{representative['cluster']} op "
                    f"{representative['op_index']}"
                )
                skip_operation_phases(
                    workspace,
                    str(task["cluster"]),
                    int(task["op_index"]),
                    ("optimize", "verification", "judge"),
                    bundled_reason,
                )
                finalize_unexecuted_operation(
                    workspace,
                    str(task["cluster"]),
                    int(task["op_index"]),
                    status="skipped",
                    reason=bundled_reason,
                )
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
            duplicate_reason = (
                "duplicate of "
                f"{first['cluster']} op {first['op_index']}"
            )
            skip_operation_phases(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                ("optimize", "verification", "judge"),
                duplicate_reason,
            )
            finalize_unexecuted_operation(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                status="skipped",
                reason=duplicate_reason,
            )
            write_publication(
                workspace,
                str(task["cluster"]),
                int(task["op_index"]),
                accepted=False,
                reason="duplicate",
            )
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
    detach_skill_changelogs(workspace)
    detach_skill_changelogs(worker)
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


def skill_content_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (value for value in directory.rglob("*") if value.is_file()),
        key=lambda value: value.relative_to(directory).as_posix(),
    ):
        relative = path.relative_to(directory).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _operation_change_claims(op: dict, skill: str) -> tuple[list[str], list[str]]:
    sections: set[str] = set()
    directories: set[str] = set()

    def collect(values: object, field: str, target: set[str]) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if isinstance(value, str) and value.strip():
                target.add(value.strip())
            elif isinstance(value, dict):
                name = value.get(field)
                if isinstance(name, str) and name.strip():
                    target.add(name.strip())

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("skill") == skill:
                collect(value.get("sections"), "section", sections)
                collect(value.get("dirs"), "dir", directories)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(op)
    return sorted(sections), sorted(directories)


OPERATION_PHASES = ("goal", "optimize", "verification", "judge")


def _operation_changelog_path(
    workspace: Path, finding_id: str, op_index: int
) -> Path:
    return (
        workspace
        / "run"
        / finding_id
        / "ops"
        / str(op_index)
        / "changelog.json"
    )


def _phase_marker(
    phase: str,
    status: str,
    reason: str | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    marker: dict[str, object] = {
        "phase": phase,
        "status": status,
        "date": now.date().isoformat(),
        "at": now.isoformat(),
    }
    if reason:
        marker["reason"] = reason
    return marker


def initialize_operation_changelog(
    workspace: Path,
    op: dict,
    run_id: str,
    finding_id: str,
    op_index: int,
) -> Path:
    """Create the phase journal as soon as the operation goal exists."""
    raw = workspace / "target/raw_skills"
    improved = workspace / "target/to_be_improved_skills"
    changed_on = datetime.now(UTC).date().isoformat()
    changes = []
    for skill in skill_names_mod.skill_names(op):
        before_dir = raw / skill
        after_dir = improved / skill
        sections, directories = _operation_change_claims(op, skill)
        changes.append(
            {
                "id": f"{run_id}:{finding_id}:{op_index}:{skill}",
                "skill": skill,
                "operation": str(op.get("op") or ""),
                "run_id": run_id,
                "finding_id": finding_id,
                "op_index": op_index,
                "date": changed_on,
                "sections": sections,
                "directories": directories,
                "before_sha256": (
                    skill_content_sha256(before_dir)
                    if before_dir.is_dir()
                    else None
                ),
                "after_sha256": (
                    skill_content_sha256(after_dir)
                    if after_dir.is_dir()
                    else None
                ),
                "status": "pending",
            }
        )
    phase_markers = [
        _phase_marker("goal", "completed"),
        *[
            _phase_marker(phase, "pending")
            for phase in OPERATION_PHASES[1:]
        ],
    ]
    document = {
        "schema_version": 1,
        "changes": changes,
        "phase_markers": phase_markers,
        "phase_events": copy.deepcopy(phase_markers),
    }
    path = _operation_changelog_path(workspace, finding_id, op_index)
    atomic_write_json(path, document)
    return path


def mark_operation_phase(
    workspace: Path,
    finding_id: str,
    op_index: int,
    phase: str,
    status: str,
    reason: str | None = None,
) -> None:
    path = _operation_changelog_path(workspace, finding_id, op_index)
    if not path.is_file():
        raise SystemExit(f"operation changelog was not initialized: {path}")
    document = json.loads(path.read_text())
    markers = document.get("phase_markers")
    if not isinstance(markers, list):
        raise SystemExit(f"operation changelog has no phase markers: {path}")
    replacement = _phase_marker(phase, status, reason)
    for index, marker in enumerate(markers):
        if isinstance(marker, dict) and marker.get("phase") == phase:
            markers[index] = replacement
            break
    else:
        markers.append(replacement)
    events = document.setdefault("phase_events", [])
    if not isinstance(events, list):
        raise SystemExit(f"operation changelog has invalid phase events: {path}")
    events.append(copy.deepcopy(replacement))
    atomic_write_json(path, document)
    active = workspace / "run/changelog.json"
    if active.is_file():
        atomic_write_json(active, document)


def skip_operation_phases(
    workspace: Path,
    finding_id: str,
    op_index: int,
    phases: tuple[str, ...],
    reason: str,
) -> None:
    for phase in phases:
        mark_operation_phase(
            workspace, finding_id, op_index, phase, "skipped", reason
        )


def materialize_operation_changelog(
    workspace: Path,
    op: dict,
    run_id: str,
    finding_id: str,
    op_index: int,
) -> Path:
    """Record claimed changes and content hashes before verification."""
    raw = workspace / "target/raw_skills"
    improved = workspace / "target/to_be_improved_skills"
    operation = str(op.get("op") or "")
    archive = _operation_changelog_path(workspace, finding_id, op_index)
    existing = json.loads(archive.read_text()) if archive.is_file() else {}
    changed_on = datetime.now(UTC).date().isoformat()
    changes: list[dict[str, object]] = []
    for skill in skill_names_mod.skill_names(op):
        before_dir = raw / skill
        after_dir = improved / skill
        sections, directories = _operation_change_claims(op, skill)
        changes.append(
            {
                "id": f"{run_id}:{finding_id}:{op_index}:{skill}",
                "skill": skill,
                "operation": operation,
                "run_id": run_id,
                "finding_id": finding_id,
                "op_index": op_index,
                "date": changed_on,
                "sections": sections,
                "directories": directories,
                "before_sha256": (
                    skill_content_sha256(before_dir)
                    if before_dir.is_dir()
                    else None
                ),
                "after_sha256": (
                    skill_content_sha256(after_dir)
                    if after_dir.is_dir()
                    else None
                ),
                "status": "pending",
            }
        )

    fallback_markers = [
        _phase_marker("goal", "completed"),
        *[
            _phase_marker(phase, "pending")
            for phase in OPERATION_PHASES[1:]
        ],
    ]
    document = {
        "schema_version": 1,
        "changes": changes,
        "phase_markers": existing.get("phase_markers")
        or fallback_markers,
        "phase_events": existing.get("phase_events")
        or copy.deepcopy(fallback_markers),
    }
    path = workspace / "run/changelog.json"
    atomic_write_json(path, document)
    atomic_write_json(archive, document)
    mark_operation_phase(
        workspace, finding_id, op_index, "optimize", "completed"
    )
    for change in changes:
        skill = change.get("skill")
        line = _operation_line(change)
        if isinstance(skill, str) and line:
            append_changelog_lines(
                workspace / SKILL_CHANGELOG_DIR, skill, [line]
            )
    return path


def _verification_requirements(op: dict, skill: str, avoid: object) -> dict:
    sections: list[dict[str, str]] = []
    directories: list[dict[str, str]] = []
    removals: list[str] = []

    def collect(values: object, name_key: str, output_key: str) -> None:
        if not isinstance(values, list):
            return
        for value in values:
            if not isinstance(value, dict):
                continue
            name = value.get(name_key)
            goal = value.get("goal")
            if isinstance(name, str) and name and isinstance(goal, str) and goal:
                target = sections if output_key == "section" else directories
                target.append({output_key: name, "expectation": goal})

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("skill") == skill:
                collect(value.get("sections"), "section", "section")
                collect(value.get("dirs"), "dir", "directory")
                removals.extend(
                    item.strip()
                    for item in value.get("remove") or []
                    if isinstance(item, str) and item.strip()
                )
                reason = value.get("reason")
                if op.get("op") == "delete" and isinstance(reason, str) and reason:
                    removals.append(f"entire skill: {reason}")
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(op)
    avoid_items = (
        [avoid]
        if isinstance(avoid, str) and avoid
        else [item for item in avoid if isinstance(item, str) and item]
        if isinstance(avoid, list)
        else []
    )
    return {
        "sections": sections,
        "directories": directories,
        "avoid": avoid_items,
        "removals": removals,
    }


def _verification_skill_role(op: dict, skill: str) -> tuple[str, bool, bool]:
    operation = op.get("op")
    if operation == "create":
        return "created", False, True
    if operation == "update":
        return "updated", True, True
    if operation == "delete":
        return "deleted", True, False
    if operation == "merge":
        target = (op.get("into") or {}).get("skill")
        if skill == target:
            sources = op.get("skills") or []
            return "merge_target", skill in sources, True
        return "merge_source", True, False
    if operation == "split":
        source = op.get("skill")
        targets = {
            row.get("skill")
            for row in op.get("into") or []
            if isinstance(row, dict)
        }
        if skill in targets:
            return "split_target", skill == source, True
        return "split_source", True, False
    raise pipeline_contracts.ContractError(
        f"cannot build verification role for operation {operation!r}"
    )


def _append_goal_verification_assertions(document: dict) -> None:
    definitions = document.get("checks") or {}
    skill_checks: dict[str, dict[str, dict[str, object]]] = {}
    for row in document.get("skills") or []:
        if not isinstance(row, dict) or not isinstance(row.get("skill"), str):
            continue
        role = row.get("role")
        materialized = [
            {
                "id": step_id,
                "definition_ref": f"#/checks/{step_id}",
                "applicable": role in (definition.get("applies_to") or []),
                "assertions": [],
            }
            for step_id, definition in definitions.items()
            if isinstance(definition, dict)
        ]
        row["checks"] = materialized
        skill_checks[row["skill"]] = {
            str(check["id"]): check for check in materialized
        }

    def append(
        step_id: str,
        skill: str,
        source_ref: str,
        text: str,
    ) -> None:
        digest = hashlib.sha256(
            f"{step_id}:{skill}:{source_ref}:{text}".encode()
        ).hexdigest()[:12]
        skill_checks[skill][step_id]["assertions"].append(
            {
                "id": f"{step_id}-goal-{digest}",
                "text": text,
                "source_ref": source_ref,
            }
        )

    for skill_index, row in enumerate(document.get("skills") or []):
        if not isinstance(row, dict) or not isinstance(row.get("skill"), str):
            continue
        skill = row["skill"]
        requirements = row.get("requirements") or {}
        base = f"#/skills/{skill_index}/requirements"
        for key, name_key, label in (
            ("sections", "section", "Section"),
            ("directories", "directory", "Directory"),
        ):
            for index, requirement in enumerate(requirements.get(key) or []):
                if not isinstance(requirement, dict):
                    continue
                name = requirement.get(name_key)
                expectation = requirement.get("expectation")
                append(
                    "step2",
                    skill,
                    f"{base}/{key}/{index}",
                    f"{label} {name}: {expectation}",
                )
        for index, expectation in enumerate(requirements.get("avoid") or []):
            append(
                "step2",
                skill,
                f"{base}/avoid/{index}",
                f"Forbidden outcome is absent: {expectation}",
            )
        for index, expectation in enumerate(
            requirements.get("removals") or []
        ):
            source_ref = f"{base}/removals/{index}"
            append(
                "step2",
                skill,
                source_ref,
                f"Required removal is applied: {expectation}",
            )
            append(
                "step8",
                skill,
                source_ref,
                f"Obsolete or redundant information is absent: {expectation}",
            )


def materialize_verification_input(
    workspace: Path,
    goal: dict,
    op: dict,
    run_id: str,
    finding_id: str,
    op_index: int,
    out: Path | None = None,
) -> Path:
    """Build explicit, operation-scoped expectations for every verifier step."""
    finding_path = (
        workspace
        / "traces"
        / "derived"
        / "findings"
        / finding_id
        / "finding.json"
    )
    finding = (
        json.loads(finding_path.read_text())
        if finding_path.is_file()
        else {}
    )
    features = finding.get("features") or {}
    quality = features.get("quality") or {}
    policy = preprocessing_config().get("evolution_policy") or {}
    avoid = (goal.get("goal") or {}).get("avoid")
    skills = []
    for skill in skill_names_mod.skill_names(op):
        role, baseline_expected, candidate_expected = _verification_skill_role(
            op, skill
        )
        skills.append(
            {
                "skill": skill,
                "role": role,
                "baseline_expected": baseline_expected,
                "candidate_expected": candidate_expected,
                "requirements": _verification_requirements(op, skill, avoid),
            }
        )
    document = json.loads(VERIFICATION_INPUT_TEMPLATE.read_text())
    document.update(
        {
            "run_id": run_id,
            "finding_id": finding_id,
            "op_index": op_index,
            "operation": str(op.get("op") or ""),
            "skills": skills,
        }
    )
    _append_goal_verification_assertions(document)
    finding_ids = [finding_id]
    bundle = goal.get("bundle") if isinstance(goal.get("bundle"), dict) else {}
    for selected in bundle.get("selected") or []:
        source_id = selected.get("cluster") if isinstance(selected, dict) else None
        if isinstance(source_id, str) and source_id not in finding_ids:
            finding_ids.append(source_id)
    bundled_findings: list[dict[str, object]] = []
    for source_id in finding_ids:
        source_path = (
            workspace
            / "traces"
            / "derived"
            / "findings"
            / source_id
            / "finding.json"
        )
        source = json.loads(source_path.read_text()) if source_path.is_file() else {}
        source_features = source.get("features") or {}
        bundled_findings.append(
            {
                "finding_id": source_id,
                "path": (
                    f"traces/derived/findings/{source_id}/finding.json"
                    if source_path.is_file()
                    else None
                ),
                "candidate_source": source_features.get("candidate_source"),
                "confidence": source.get("confidence"),
                "evidence_records": len(source.get("evidence") or []),
                "distinct_windows": source_features.get("distinct_windows"),
                "lesson": source_features.get("lesson"),
            }
        )
    document["checks"]["step3"]["evidence"] = {
        "findings": bundled_findings,
    }
    document["checks"]["step4"]["thresholds"] = {
        "min_methodology_value": policy.get("min_methodology_value", 0.08),
        "methodology_value": quality.get("value"),
    }
    document["checks"]["step7"]["thresholds"] = {
        "novelty_max_similarity": policy.get(
            "novelty_max_similarity", 0.82
        )
    }
    path = out or workspace / "run/verification-input.json"
    atomic_write_json(path, document)
    pipeline_contracts.validate_verification_input(path)
    return path


def _artifact_reference(path: Path) -> dict[str, str]:
    return {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _reindex_single_skill_refs(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _reindex_single_skill_refs(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_reindex_single_skill_refs(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"(#?/skills/)\d+/", r"\g<1>0/", value)
    return value


def verifier_skill_payloads(
    verification_input: dict[str, object],
    output_skeleton: dict[str, object],
    skill: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Create the concrete input and required output shape for one skill."""
    input_rows = [
        row
        for row in verification_input.get("skills") or []
        if isinstance(row, dict) and row.get("skill") == skill
    ]
    step_rows = [
        row
        for row in output_skeleton.get("verification_steps") or []
        if isinstance(row, dict) and row.get("skill") == skill
    ]
    feedback = output_skeleton.get("feedback")
    feedback_rows = [
        row
        for row in (feedback or {}).get("per_skill") or []
        if isinstance(row, dict) and row.get("skill") == skill
    ]
    if len(input_rows) != 1 or len(step_rows) != 1 or len(feedback_rows) != 1:
        raise pipeline_contracts.ContractError(
            f"cannot materialize exactly one verifier payload for {skill}"
        )
    skill_input = copy.deepcopy(verification_input)
    skill_input["skills"] = input_rows
    skill_input = _reindex_single_skill_refs(skill_input)
    input_text = json.dumps(skill_input, indent=2, ensure_ascii=False) + "\n"

    required_output = copy.deepcopy(output_skeleton)
    required_output["verification_input"] = {
        "path": "verification-input.json",
        "sha256": hashlib.sha256(input_text.encode()).hexdigest(),
    }
    required_output["verification_steps"] = step_rows
    required_output["verification_steps"] = _reindex_single_skill_refs(
        required_output["verification_steps"]
    )
    required_output["changelog"] = [
        row
        for row in required_output.get("changelog") or []
        if isinstance(row, dict) and row.get("skill") == skill
    ]
    required_feedback = required_output["feedback"]
    required_feedback["bottleneck_skills"] = [skill]
    required_feedback["per_skill"] = feedback_rows
    required_feedback["ood"] = []
    required_feedback["action"] = None
    return skill_input, required_output


def _prompt_lesson(lesson: object) -> object:
    """Keep the reusable rule and drop per-event retry rows from the prompt."""
    if not isinstance(lesson, dict) or "retry_classifications" not in lesson:
        return lesson
    compact = {
        key: value
        for key, value in lesson.items()
        if key != "retry_classifications"
    }
    return compact or {"kind": lesson.get("kind")}


def _prompt_verification_input(
    verification_input: dict[str, object],
) -> dict[str, object]:
    document = copy.deepcopy(verification_input)
    findings = (
        ((document.get("checks") or {}).get("step3") or {}).get("evidence") or {}
    ).get("findings")
    if isinstance(findings, list):
        for row in findings:
            if isinstance(row, dict) and "lesson" in row:
                row["lesson"] = _prompt_lesson(row["lesson"])
    return document


def verifier_response_prompt(
    skill: str,
    verification_input: dict[str, object],
    required_output: dict[str, object],
    *,
    previous_error: str | None = None,
) -> str:
    correction = (
        "\nYour previous response was rejected by the JSON/contract parser:\n"
        f"{previous_error}\nReturn a corrected complete JSON object.\n"
        if previous_error
        else ""
    )
    verification_input = _prompt_verification_input(verification_input)
    return f"""Verify exactly one skill: {skill}.

Read AGENT.md and 05_verifiter_agent/verifiter/skill.md, then inspect only the
workspace evidence named by the concrete input below. Run the prescribed
deterministic checks. Do not edit skills and do not write verification.json.

Mechanical standards. These are the defects the decision score prices. Apply
them from this list and from one run of verify_sections.py and verify_goal.py.
A script finding is one listed penalty, not a veto. Do not open the checker
source or the parent repository to re-derive them.

- Section match: for this one skill, match a claimed name with a loose regex.
  Case, extra words, and heading level do not matter. `overview`,
  `## Overview`, and `# Overview` are the same name. Pass that claim when its
  content is new, deleted, or changed in the direction of the goal. That is
  enough. Do not fail it because the wording is tighter than the goal, including
  "all of the following are true", when the goal's cases are present.
- Frontmatter: YAML between `---` lines. `name` is lowercase hyphen-case,
  matches the skill directory, and is at most 64 characters. `description` is
  required, at most 1024 characters, and contains no angle brackets. Allowed
  fields are name, description, license, compatibility, allowed-tools, and
  metadata.
- Shape: SKILL.md is at most 500 lines. No `TODO`, `[TODO`, `EXAMPLE_SCRIPT`,
  `EXAMPLE_REFERENCE`, or `EXAMPLE_ASSET` placeholder. No symbolic links. No
  file over 10MB. Reference files are one directory level deep. A named
  `scripts/*.py` file must compile. A named `evals` directory must contain
  `evals/evals.json`, including the positive and near-miss cases the goal
  requires. Directories are only references, scripts, agents, assets, evals,
  or a goal-named other/ood directory.
- Edit diff: create must contain every claimed section and directory. Update
  must change every claimed section and leave frontmatter, the text before the
  first heading, and every unclaimed section identical to target/raw_skills.
  Both copies must exist. Delete removes the skill directory. Merge and split
  keep the source snapshot and remove only the sources the operation names.
- Hashes: changelog.json already stores the before and after content hashes.
  Do not reimplement that digest.
- Decision: list each defect once in feedback.per_skill[].penalties as
  {{"id", "target"}}. The runner prices that list and writes the skill score
  and status. Do not fold a penalty into an assertion average or a step
  weight. The score starts at 1.0. The sections and directories this goal
  names share a 0.80 claim budget; do not charge a section or directory the
  goal did not name. The 8 core sections are the inventory, not the divisor.
  missing_section, missing_directory, and goal_contradiction each cost one
  share of that budget. missing_near_miss_eval costs half a share.
  heading_level, unclaimed_heading, tighter_wording, and description_shape
  each cost 0.05, and those shape charges stop at 0.20, so shape alone stays
  at or above 0.80 and still passes. replay_fail costs 0.125. The runner adds
  it when replay status is fail, and one replay failure still passes. Pass
  when the priced score is at least pass_threshold.

The concrete verification input for this skill is part of this prompt:
<verification-input-json>
{json.dumps(verification_input, indent=2, ensure_ascii=False)}
</verification-input-json>

The complete required response shape is also part of this prompt. Replace all
placeholders and preserve every field, step, assertion ID, reference, and
runner-owned changelog entry:
<verification-output-json>
{json.dumps(required_output, indent=2, ensure_ascii=False)}
</verification-output-json>

Return only one JSON object matching that output shape. Do not use Markdown
fences or explanatory text. `feedback.action` and every per-skill `action`
must remain null. Optimization retries remain disabled; a runner may repeat
this same request only when your response is malformed JSON or violates the
output contract.{correction}"""


def parse_verifier_response_log(path: Path) -> dict[str, object]:
    """Extract the last verifier-shaped JSON object from a CLI event stream."""
    strings: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    for line in path.read_text(errors="replace").splitlines():
        try:
            collect(json.loads(line))
        except json.JSONDecodeError:
            strings.append(line)
    candidates: list[dict[str, object]] = []
    decoder = json.JSONDecoder()
    for text in strings:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        positions = [index for index, char in enumerate(stripped) if char == "{"]
        for position in positions:
            try:
                value, _ = decoder.raw_decode(stripped[position:])
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and isinstance(value.get("verification_steps"), list)
                and isinstance(value.get("feedback"), dict)
            ):
                candidates.append(value)
                break
    if not candidates:
        raise pipeline_contracts.ContractError(
            "verifier response contains no JSON object with verification_steps and feedback"
        )
    return candidates[-1]


def validate_skill_verifier_response(
    operation_directory: Path,
    skill: str,
    verification_input: dict[str, object],
    required_output: dict[str, object],
    response: dict[str, object],
) -> dict[str, object]:
    """Validate an agent response in an isolated one-skill contract directory."""
    root = operation_directory / "verifier-responses" / safe_name(skill)
    root.mkdir(parents=True, exist_ok=True)
    input_path = root / "verification-input.json"
    output_path = root / "verification.json"
    atomic_write_json(input_path, verification_input)
    candidate = copy.deepcopy(response)
    for key in ("diagnosis", "nod", "result", "verification_input", "changelog"):
        candidate[key] = copy.deepcopy(required_output.get(key))
    candidate_feedback = candidate.get("feedback")
    if not isinstance(candidate_feedback, dict):
        raise pipeline_contracts.ContractError("$.feedback: must be an object")
    candidate_feedback["action"] = None
    for row in candidate_feedback.get("per_skill") or []:
        if isinstance(row, dict):
            row["action"] = None
            row["retries_used"] = 0
    pipeline_contracts.apply_decision_scores(candidate, verification_input)
    atomic_write_json(output_path, candidate)
    return pipeline_contracts.validate_verification(
        output_path,
        judged=False,
        expected_skills={skill},
    )


def aggregate_skill_verifications(
    output_skeleton: dict[str, object],
    responses: list[dict[str, object]],
) -> dict[str, object]:
    """Combine validated per-skill responses into the operation output."""
    result = copy.deepcopy(output_skeleton)
    groups = [
        group
        for response in responses
        for group in response["verification_steps"]
    ]
    for skill_index, group in enumerate(groups):
        group["steps_from"] = (
            f"verification-input.json#/skills/{skill_index}/checks"
        )
        for check_index, step in enumerate(group.get("steps") or []):
            if isinstance(step, dict):
                step["input_ref"] = (
                    f"#/skills/{skill_index}/checks/{check_index}"
                )
    result["verification_steps"] = groups
    rows = [
        row
        for response in responses
        for row in response["feedback"]["per_skill"]
    ]
    scores = {row["skill"]: float(row["score"]) for row in rows}
    overall_score = min(scores.values())
    bottlenecks = sorted(
        skill for skill, score in scores.items()
        if abs(score - overall_score) <= 1e-6
    )
    replays = [response["feedback"]["replay"] for response in responses]
    replay = next(
        (
            item for item in replays
            if item.get("available") and item.get("status") == "fail"
        ),
        next((item for item in replays if item.get("available")), replays[0]),
    )
    feedback = result["feedback"]
    feedback["per_skill"] = rows
    feedback["overall_score"] = overall_score
    feedback["bottleneck_skills"] = bottlenecks
    feedback["replay"] = copy.deepcopy(replay)
    feedback["overall_status"] = (
        "pass" if all(row["status"] == "pass" for row in rows) else "fail"
    )
    feedback["overall_feedback"] = " | ".join(
        f"{row['skill']}: {row['feedback']}" for row in rows
    )
    feedback["retry_budget"] = 0
    feedback["action"] = None
    feedback["ood"] = [
        item
        for response in responses
        for item in response["feedback"]["ood"]
    ]
    return result


def run_per_skill_verification(
    workspace: Path,
    *,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    suffix: str,
    metadata: dict[str, object],
) -> Path:
    """Prompt, parse, validate, and aggregate one verifier response per skill."""
    operation_directory = workspace / "run"
    skeleton_path = operation_directory / "verification-output.required.json"
    input_path = operation_directory / "verification-input.json"
    input_bytes = input_path.read_bytes()
    verification_input = json.loads(input_bytes)
    output_skeleton = verification_builder.build(
        json.loads((operation_directory / "evolve-goal.json").read_text()),
        json.loads(verification_builder.TEMPLATE.read_text()),
        json.loads((operation_directory / "changelog.json").read_text()),
        hashlib.sha256(input_bytes).hexdigest(),
        verification_input,
    )
    atomic_write_json(skeleton_path, output_skeleton)

    def verify_skill(skill_row: dict[str, object]) -> dict[str, object]:
        skill = str(skill_row["skill"])
        skill_input, required_output = verifier_skill_payloads(
            verification_input,
            output_skeleton,
            skill,
        )
        previous_error: str | None = None
        for response_attempt in range(VERIFIER_RESPONSE_RETRY_BUDGET + 1):
            prompt = verifier_response_prompt(
                skill,
                skill_input,
                required_output,
                previous_error=previous_error,
            )
            response_suffix = (
                f"{suffix}-{safe_name(skill)}-response-{response_attempt + 1}"
            )
            log_path = run_session(
                "verifiter",
                workspace,
                prompt,
                auth,
                model,
                install_agent,
                response_suffix,
                {
                    **metadata,
                    "skill": skill,
                    "response_attempt": response_attempt + 1,
                    "response_retry_kind": "json_or_contract_only",
                },
                json_output=True,
            )
            try:
                response = parse_verifier_response_log(log_path)
                return validate_skill_verifier_response(
                    operation_directory,
                    skill,
                    skill_input,
                    required_output,
                    response,
                )
            except (
                json.JSONDecodeError,
                pipeline_contracts.ContractError,
            ) as error:
                previous_error = str(error)
                if response_attempt >= VERIFIER_RESPONSE_RETRY_BUDGET:
                    raise
        raise pipeline_contracts.ContractError(
            f"verifier produced no response for {skill}"
        )

    responses = [
        row
        for row in run_pool(
            list(verification_input["skills"]),
            DEFAULT_OP_WORKERS,
            verify_skill,
        )
        if isinstance(row, dict)
    ]
    final = aggregate_skill_verifications(output_skeleton, responses)
    verification_path = operation_directory / "verification.json"
    atomic_write_json(verification_path, final)
    pipeline_contracts.validate_verification(
        verification_path,
        judged=False,
        expected_skills={
            str(row["skill"]) for row in verification_input["skills"]
        },
    )
    return verification_path


def write_judge_record(
    operation_directory: Path,
    *,
    status: str | None = None,
    reason: str | None = None,
) -> Path:
    verification_path = operation_directory / "verification.json"
    changelog_path = operation_directory / "changelog.json"
    verification = json.loads(verification_path.read_text())
    status = status or str(verification.get("status") or "completed")
    if reason is None and status in {"skipped", "failed"}:
        reason = str(verification.get("reason") or status)
    changes = json.loads(changelog_path.read_text()).get("changes") or []
    if not changes:
        raise SystemExit("operation changelog has no changes")
    first_change = changes[0]
    judge: dict[str, object] = {
        "schema_version": 1,
        "date": first_change.get("date"),
        "run_id": first_change.get("run_id"),
        "finding_id": first_change.get("finding_id"),
        "op_index": first_change.get("op_index"),
        "skills": sorted(
            {
                str(change["skill"])
                for change in changes
                if isinstance(change, dict) and change.get("skill")
            }
        ),
        "status": status,
        "action": copy.deepcopy(
            (verification.get("feedback") or {}).get("action")
        ),
        "artifacts": {
            name: _artifact_reference(operation_directory / filename)
            for name, filename in {
                "goal": "evolve-goal.json",
                "verification_input": "verification-input.json",
                "verification": "verification.json",
                "changelog": "changelog.json",
            }.items()
        },
    }
    if reason:
        judge["reason"] = reason
    path = operation_directory / "judge.json"
    atomic_write_json(path, judge)
    return path


def finalize_no_change_scope(
    workspace: Path,
    run_id: str,
    finding_id: str,
    goal_path: Path,
) -> Path:
    """Publish and validate the terminal bundle for a no-change scope."""
    goal = pipeline_contracts.validate_goal(goal_path)
    action = goal["action"]
    if action.get("disposition") != "no_change" or action.get("ops"):
        raise SystemExit(f"scope is not no_change: {goal_path}")
    reason = str(action["reason"])
    directory = goal_path.parent
    now = datetime.now(UTC)
    date_value = now.date().isoformat()
    markers = [
        _phase_marker("goal", "completed"),
        *[
            _phase_marker(phase, "skipped", reason)
            for phase in OPERATION_PHASES[1:]
        ],
    ]
    changelog = {
        "schema_version": 1,
        "date": date_value,
        "run_id": run_id,
        "finding_id": finding_id,
        "disposition": "no_change",
        "reason": reason,
        "changes": [],
        "phase_markers": markers,
        "phase_events": copy.deepcopy(markers),
    }
    changelog_path = directory / "changelog.json"
    atomic_write_json(changelog_path, changelog)
    verification_input = {
        "schema_version": 1,
        "date": date_value,
        "run_id": run_id,
        "finding_id": finding_id,
        "op_index": 0,
        "operation": "no_change",
        "status": "skipped",
        "reason": reason,
        "skills": [],
    }
    input_path = directory / "verification-input.json"
    atomic_write_json(input_path, verification_input)
    verification = {
        "schema_version": 1,
        "date": date_value,
        "run_id": run_id,
        "finding_id": finding_id,
        "op_index": 0,
        "operation": "no_change",
        "status": "skipped",
        "phase": "verification",
        "reason": reason,
        "skills": [],
        "verification_input": _artifact_reference(input_path),
        "changelog": [],
    }
    verification_path = directory / "verification.json"
    atomic_write_json(verification_path, verification)
    judge = {
        "schema_version": 1,
        "date": date_value,
        "run_id": run_id,
        "finding_id": finding_id,
        "op_index": 0,
        "skills": [],
        "status": "skipped",
        "action": None,
        "reason": reason,
        "artifacts": {
            name: _artifact_reference(directory / filename)
            for name, filename in {
                "goal": "evolve-goal.json",
                "verification_input": "verification-input.json",
                "verification": "verification.json",
                "changelog": "changelog.json",
            }.items()
        },
    }
    atomic_write_json(directory / "judge.json", judge)
    pipeline_contracts.validate_no_change_artifacts(directory)
    return directory


def finalize_unexecuted_operation(
    workspace: Path,
    finding_id: str,
    op_index: int,
    *,
    status: str,
    reason: str,
) -> Path:
    """Write a complete, linked bundle when later phases cannot execute."""
    operation_directory = (
        workspace / "run" / finding_id / "ops" / str(op_index)
    )
    changelog = json.loads(
        (operation_directory / "changelog.json").read_text()
    )
    input_path = operation_directory / "verification-input.json"
    if not input_path.is_file():
        goal = json.loads(
            (operation_directory / "evolve-goal.json").read_text()
        )
        operation = goal["action"]["ops"][0]
        materialize_verification_input(
            workspace,
            goal,
            operation,
            str((changelog.get("changes") or [{}])[0].get("run_id") or ""),
            finding_id,
            op_index,
            out=input_path,
        )
    require_path(input_path, "operation verification input")
    verification = {
        "schema_version": 1,
        "phase": "verification",
        "status": status,
        "date": datetime.now(UTC).date().isoformat(),
        "reason": reason,
        "skills": sorted(
            {
                str(change["skill"])
                for change in changelog.get("changes") or []
                if isinstance(change, dict) and change.get("skill")
            }
        ),
        "verification_input": {
            "path": "verification-input.json",
            "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        },
        "changelog": copy.deepcopy(changelog.get("changes") or []),
    }
    atomic_write_json(operation_directory / "verification.json", verification)
    write_judge_record(
        operation_directory, status=status, reason=reason
    )
    pipeline_contracts.validate_operation_artifacts(operation_directory)
    return operation_directory


def accept_operation_bundle(
    workspace: Path,
    finding_id: str,
    op_index: int,
) -> None:
    operation_directory = (
        workspace / "run" / finding_id / "ops" / str(op_index)
    )
    changelog_path = operation_directory / "changelog.json"
    verification_path = operation_directory / "verification.json"
    changelog = json.loads(changelog_path.read_text())
    verification = json.loads(verification_path.read_text())
    accepted_ids: set[str] = set()
    for change in changelog.get("changes") or []:
        if isinstance(change, dict):
            change["status"] = "accepted"
            accepted_ids.add(str(change.get("id")))
    for change in verification.get("changelog") or []:
        if isinstance(change, dict) and str(change.get("id")) in accepted_ids:
            change["status"] = "accepted"
    atomic_write_json(changelog_path, changelog)
    atomic_write_json(verification_path, verification)
    write_judge_record(operation_directory)
    pipeline_contracts.validate_operation_artifacts(operation_directory)


def transition_worker_lifecycle(
    worker: Path,
    cluster: str,
    op_index: int,
    affected: set[str],
) -> None:
    metadata_path = (
        worker / "target/to_be_improved_skills_metadata/metadata.json"
    )
    if not metadata_path.is_file():
        return
    verification_path = (
        worker
        / "run"
        / cluster
        / "ops"
        / str(op_index)
        / "verification.json"
    )
    verification = (
        json.loads(verification_path.read_text())
        if verification_path.is_file()
        else {}
    )
    replay = ((verification.get("feedback") or {}).get("replay") or {})
    behavioral = replay_meets_promotion_gate(replay)
    document = json.loads(metadata_path.read_text())
    changed = False
    now = datetime.now(UTC).isoformat()
    skill_root = worker / "target/to_be_improved_skills"
    policy = preprocessing_config().get("evolution_policy") or {}
    minimum_sessions = int(policy.get("create_min_distinct_sessions", 2))
    for row in document.get("skills_metadata") or []:
        if not isinstance(row, dict) or row.get("skill") not in affected:
            continue
        entry = verification_changelog_entry(
            worker, cluster, op_index, str(row.get("skill"))
        )
        line = _phase_line(entry) if entry is not None else ""
        if line:
            append_changelog_lines(
                worker / SKILL_CHANGELOG_DIR, str(row.get("skill")), [line]
            )
        lifecycle = row.get("lifecycle")
        if not isinstance(lifecycle, dict):
            continue
        enough_sessions = (
            int(lifecycle.get("distinct_sessions") or 0)
            >= minimum_sessions
        )
        lifecycle["status"] = (
            "promoted"
            if enough_sessions and behavioral
            else "evaluated"
        )
        lifecycle["evaluated_at"] = now
        lifecycle["evaluation_kind"] = (
            "behavioral_replay" if behavioral else "structural"
        )
        if lifecycle["status"] == "promoted":
            lifecycle["promoted_at"] = now
        else:
            lifecycle.pop("promoted_at", None)
        directory = skill_root / str(row["skill"])
        if directory.is_dir():
            lifecycle["content_sha256"] = skill_content_sha256(directory)
        changed = True
    if changed:
        atomic_write_json(metadata_path, document)


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
    final_judge_action = str(result.get("judge_action", "pass"))
    if final_judge_action != "pass":
        _archive_operation_records(workspace, result)
        write_publication(
            workspace,
            cluster,
            op_index,
            accepted=False,
            reason=f"judge-{final_judge_action}",
        )
        for source in result.get("bundled_sources") or []:
            if not isinstance(source, dict):
                continue
            write_publication(
                workspace,
                str(source.get("cluster")),
                int(source.get("op_index")),
                accepted=False,
                reason=f"judge-{final_judge_action}",
            )
        return
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
    update_candidate_pool(
        workspace, {str(name) for name in result.get("affected") or []}
    )
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
        accept_operation_bundle(
            workspace, source_cluster, source_index
        )
        write_publication(
            workspace,
            source_cluster,
            source_index,
            accepted=True,
            reason="bundled",
            outcome="bundled",
            selected_cluster=cluster,
            selected_op_index=op_index,
        )


def _archive_operation_records(
    workspace: Path, result: dict[str, object]
) -> None:
    worker = result["worker"]
    cluster = str(result["cluster"])
    op_index = int(result["op_index"])
    operation_directory = (
        worker / "run" / cluster / "ops" / str(op_index)
    )
    pipeline_contracts.validate_operation_artifacts(operation_directory)
    for relative in (
        Path("run") / cluster / "ops" / str(op_index) / "verification.json",
        Path("run") / cluster / "ops" / str(op_index) / "verification-input.json",
        Path("run") / cluster / "ops" / str(op_index) / "evolve-goal.json",
        Path("run") / cluster / "ops" / str(op_index) / "judge.json",
        Path("run") / cluster / "ops" / str(op_index) / "changelog.json",
    ):
        source = worker / relative
        replace_path(source, workspace / relative)
    replay_source = worker / "run/replay"
    if replay_source.is_dir():
        replay_target = (
            workspace / "run" / cluster / "ops" / str(op_index) / "replay"
        )
        replace_path(replay_source, replay_target)
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
    accept_operation_bundle(worker, cluster, op_index)
    pipeline_contracts.validate_operation_artifacts(
        worker / "run" / cluster / "ops" / str(op_index)
    )
    affected = set(result["affected"])
    transition_worker_lifecycle(worker, cluster, op_index, affected)
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
    for skill in sorted(affected):
        merge_changelog_file(
            worker / SKILL_CHANGELOG_DIR / f"{skill}.md",
            workspace / SKILL_CHANGELOG_DIR / f"{skill}.md",
        )
    current = {
        path.name
        for path in (workspace / improved_rel).iterdir()
        if path.is_dir()
    }
    pipeline_contracts.validate_metadata(metadata, current)
    archived_rel = Path("run") / cluster / "ops" / str(op_index) / "verification.json"
    replace_path(worker / archived_rel, workspace / archived_rel)
    input_rel = (
        Path("run")
        / cluster
        / "ops"
        / str(op_index)
        / "verification-input.json"
    )
    replace_path(worker / input_rel, workspace / input_rel)
    op_goal_rel = Path("run") / cluster / "ops" / str(op_index) / "evolve-goal.json"
    replace_path(worker / op_goal_rel, workspace / op_goal_rel)
    judge_rel = Path("run") / cluster / "ops" / str(op_index) / "judge.json"
    replace_path(worker / judge_rel, workspace / judge_rel)
    changelog_rel = (
        Path("run") / cluster / "ops" / str(op_index) / "changelog.json"
    )
    replace_path(worker / changelog_rel, workspace / changelog_rel)
    pipeline_contracts.validate_operation_artifacts(
        workspace / "run" / cluster / "ops" / str(op_index)
    )
    replay_source = worker / "run/replay"
    if replay_source.is_dir():
        replay_target = (
            workspace / "run" / cluster / "ops" / str(op_index) / "replay"
        )
        replace_path(replay_source, replay_target)
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
            "will_retry": False,
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


def candidate_directory(workspace: Path, cluster: str, op_index: int) -> Path:
    return workspace / "run" / cluster / "ops" / str(op_index) / "candidate"


def preserve_optimized_candidate(
    workspace: Path,
    private: Path,
    cluster: str,
    op_index: int,
    op: dict,
) -> None:
    """Keep the optimized skill in the run so verification can be repeated."""
    root = candidate_directory(workspace, cluster, op_index)
    if root.exists():
        shutil.rmtree(root)
    names = skill_names_mod.skill_names(op)
    improved = private / "target/to_be_improved_skills"
    raw = private / "target/raw_skills"
    for name in names:
        source = improved / name
        if source.is_dir():
            shutil.copytree(source, root / "to_be_improved_skills" / name)
        raw_source = raw / name
        if raw_source.is_dir():
            shutil.copytree(raw_source, root / "raw_skills" / name)
    metadata_path = (
        private / "target/to_be_improved_skills_metadata/metadata.json"
    )
    rows: list[object] = []
    if metadata_path.is_file():
        document = json.loads(metadata_path.read_text())
        wanted = set(names)
        rows = [
            row
            for row in document.get("skills_metadata") or []
            if isinstance(row, dict) and row.get("skill") in wanted
        ]
    atomic_write_json(root / "metadata.json", {"skills_metadata": rows})
    operation_directory = workspace / "run" / cluster / "ops" / str(op_index)
    private_directory = private / "run" / cluster / "ops" / str(op_index)
    for filename in (
        "evolve-goal.json",
        "verification-input.json",
        "changelog.json",
    ):
        source = private_directory / filename
        if source.is_file():
            replace_path(source, operation_directory / filename)


def restore_optimized_candidate(
    worker: Path, workspace: Path, cluster: str, op_index: int
) -> None:
    """Put a saved optimized skill back into an operation worker."""
    root = candidate_directory(workspace, cluster, op_index)
    if not root.is_dir():
        raise SystemExit(
            f"optimized skill was not saved for {cluster} op {op_index}"
        )
    improved = root / "to_be_improved_skills"
    if improved.is_dir():
        for skill_dir in improved.iterdir():
            if skill_dir.is_dir():
                replace_path(
                    skill_dir,
                    worker / "target/to_be_improved_skills" / skill_dir.name,
                )
    raw = root / "raw_skills"
    if raw.is_dir():
        for skill_dir in raw.iterdir():
            if skill_dir.is_dir():
                replace_path(
                    skill_dir, worker / "target/raw_skills" / skill_dir.name
                )
    saved_metadata = root / "metadata.json"
    if not saved_metadata.is_file():
        return
    incoming = json.loads(saved_metadata.read_text()).get("skills_metadata") or []
    destination = worker / "target/to_be_improved_skills_metadata/metadata.json"
    document = (
        json.loads(destination.read_text())
        if destination.is_file()
        else {"skills_metadata": []}
    )
    rows = [
        row
        for row in document.get("skills_metadata") or []
        if isinstance(row, dict)
    ]
    index_by_name = {
        row.get("skill"): index for index, row in enumerate(rows)
    }
    for row in incoming:
        if not isinstance(row, dict):
            continue
        name = row.get("skill")
        if name in index_by_name:
            rows[index_by_name[name]] = row
        else:
            rows.append(row)
    document["skills_metadata"] = rows
    atomic_write_json(destination, document)
    detach_skill_changelogs(worker)
    current = {
        path.name
        for path in (worker / "target/to_be_improved_skills").iterdir()
        if path.is_dir()
    }
    pipeline_contracts.validate_metadata(destination, current)


def stage_saved_operation(
    worker: Path, cluster: str, op_index: int, *, include_verification: bool
) -> None:
    """Point the worker's active run files at one saved operation."""
    operation_directory = worker / "run" / cluster / "ops" / str(op_index)
    for filename in (
        "evolve-goal.json",
        "verification-input.json",
        "changelog.json",
    ):
        replace_path(
            operation_directory / filename, worker / "run" / filename
        )
    if include_verification:
        replace_path(
            operation_directory / "verification.json",
            worker / "run/verification.json",
        )


def changelog_phase_status(path: Path, phase: str) -> str:
    if not path.is_file():
        return ""
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ""
    for marker in document.get("phase_markers") or []:
        if isinstance(marker, dict) and marker.get("phase") == phase:
            return str(marker.get("status") or "")
    return ""


def verification_has_feedback(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return False
    return isinstance(document, dict) and isinstance(
        document.get("feedback"), dict
    )


def resumable_operations(
    workspace: Path, phase: str
) -> tuple[list[dict[str, object]], list[str]]:
    """Operations whose optimized skill is saved and not yet accepted."""
    ready: list[dict[str, object]] = []
    skipped: list[str] = []
    run_root = workspace / "run"
    if not run_root.is_dir():
        return ready, skipped
    for operation_directory in sorted(run_root.glob("*/ops/*")):
        if not operation_directory.is_dir():
            continue
        if not str(operation_directory.name).isdigit():
            continue
        cluster = operation_directory.parent.parent.name
        op_index = int(operation_directory.name)
        label = f"{cluster} op {op_index}"
        publication_path = operation_directory / "publication.json"
        if publication_path.is_file():
            try:
                publication = json.loads(publication_path.read_text())
            except json.JSONDecodeError:
                publication = {}
            if publication.get("accepted") is True:
                continue
        if not candidate_directory(workspace, cluster, op_index).is_dir():
            skipped.append(f"{label}: optimized skill was not saved")
            continue
        if (
            changelog_phase_status(
                operation_directory / "changelog.json", "optimize"
            )
            != "completed"
        ):
            skipped.append(f"{label}: optimize did not finish")
            continue
        goal_path = operation_directory / "evolve-goal.json"
        if not goal_path.is_file():
            skipped.append(f"{label}: operation goal is missing")
            continue
        goal = pipeline_contracts.validate_goal(goal_path)
        ops = goal["action"]["ops"]
        if len(ops) != 1:
            skipped.append(f"{label}: saved goal does not contain one operation")
            continue
        if phase == "judge" and not verification_has_feedback(
            operation_directory / "verification.json"
        ):
            skipped.append(f"{label}: verification has no result to judge")
            continue
        op = ops[0]
        affected = set(skill_names_mod.skill_names(op))
        ready.append(
            {
                "cluster": cluster,
                "op_index": op_index,
                "op": op,
                "affected": affected,
                "conflicts": affected or {"*"},
                "bundle": {},
                "rank": {},
            }
        )
    return ready, skipped


def run_verification_and_judge(
    *,
    workspace: Path,
    private: Path,
    cluster: str,
    op_index: int,
    op: dict,
    suffix: str,
    attempt: int,
    op_metadata: dict[str, object],
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
    stage_box: dict[str, str],
    start_stage: str,
) -> str:
    """Run verification and judge, or judge alone when verification is saved."""
    if start_stage == "verifiter":
        stage_box["stage"] = "verifiter"
        mark_operation_phase(
            private,
            cluster,
            op_index,
            "verification",
            "running",
        )
        write_status(workspace, "verifiter", suffix, "started")
        verification = run_per_skill_verification(
            private,
            auth=auth,
            model=model,
            install_agent=install_agent,
            suffix=suffix,
            metadata={**op_metadata, "attempt": attempt},
        )
        verification_data = pipeline_contracts.validate_verification(
            verification,
            judged=False,
            expected_skills=set(skill_names_mod.skill_names(op)),
        )
        mark_operation_phase(
            private,
            cluster,
            op_index,
            "verification",
            "completed",
        )
        operation_directory = (
            workspace / "run" / cluster / "ops" / str(op_index)
        )
        replace_path(verification, operation_directory / "verification.json")
        saved_changelog = (
            private / "run" / cluster / "ops" / str(op_index) / "changelog.json"
        )
        if saved_changelog.is_file():
            replace_path(saved_changelog, operation_directory / "changelog.json")
        replay_outputs = validate_replay_artifacts(private, verification_data)
        complete_session(
            private,
            "verifiter",
            suffix,
            [verification, *replay_outputs],
        )
    else:
        verification = private / "run/verification.json"
        require_path(verification, "verification")
    stage_box["stage"] = "judge"
    mark_operation_phase(private, cluster, op_index, "judge", "running")
    write_status(workspace, "judge", suffix, "started")
    append_execution_event(private, "judge", "started")
    try:
        with pipeline_metrics.span(
            metrics_workspace(private),
            "judge",
            suffix,
            "deterministic",
            metadata={
                **op_metadata,
                "attempt": attempt,
                "formula": "overall_status",
            },
        ):
            action = apply_judge_formula(verification)
    except BaseException:
        append_execution_event(private, "judge", "failed")
        raise
    else:
        append_execution_event(private, "judge", "done")
    mark_operation_phase(
        private,
        cluster,
        op_index,
        "judge",
        "completed",
        f"decision: {action}",
    )
    _emit_judge_decision(workspace, cluster, op_index, verification, attempt)
    archive_verification(private, cluster, op_index)
    archived = private / "run" / cluster / "ops" / str(op_index)
    complete_session(
        private,
        "judge",
        suffix,
        [
            archived / "verification.json",
            archived / "judge.json",
            archived / "changelog.json",
            archived / "evolve-goal.json",
        ],
    )
    return action


def settle_failed_operation(
    *,
    workspace: Path,
    private: Path,
    cluster: str,
    op_index: int,
    current_stage: str,
    suffix: str,
    suffixes: list[str],
    task: dict[str, object],
    error: BaseException,
) -> dict[str, object]:
    """Record one lane failure and keep any optimized skill already saved."""
    reason = failure_text(error)
    phase = {
        "optimize": "optimize",
        "verifiter": "verification",
        "judge": "judge",
    }.get(current_stage)
    if phase is not None:
        try:
            mark_operation_phase(
                private, cluster, op_index, phase, "failed", reason
            )
            remaining = OPERATION_PHASES[OPERATION_PHASES.index(phase) + 1 :]
            if remaining:
                skip_operation_phases(
                    private,
                    cluster,
                    op_index,
                    remaining,
                    f"blocked by failed {phase} phase",
                )
            failed_directory = finalize_unexecuted_operation(
                private,
                cluster,
                op_index,
                status="failed",
                reason=f"{phase} failed: {reason}",
            )
            target_directory = (
                workspace / "run" / cluster / "ops" / str(op_index)
            )
            for filename in (
                "evolve-goal.json",
                "verification-input.json",
                "verification.json",
                "judge.json",
                "changelog.json",
            ):
                if filename == "verification.json" and verification_has_feedback(
                    target_directory / filename
                ):
                    continue
                replace_path(
                    failed_directory / filename, target_directory / filename
                )
            write_publication(
                workspace,
                cluster,
                op_index,
                accepted=False,
                reason=f"{phase}-failed",
            )
        except BaseException as archival_error:
            note = (
                "failed to archive the operation failure: "
                f"{failure_text(archival_error)}"
            )
            write_status(
                workspace,
                current_stage,
                suffix,
                "failed",
                error=f"{reason}; {note}",
            )
    for done_suffix in suffixes:
        merge_worker_statuses(private, workspace, done_suffix)
    write_status(workspace, current_stage, suffix, "failed", error=reason)
    return {
        **task,
        "worker": private,
        "suffixes": suffixes,
        "judge_action": None,
        "failed": True,
        "published": True,
    }


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
        infrastructure_blocked = infrastructure_evolution_blocked(
            workspace, cluster
        )
        cluster_goal = workspace / "run" / cluster / "evolve-goal.json"
        goal = pipeline_contracts.validate_goal(cluster_goal)
        operations = goal_ops(cluster_goal)
        if not operations:
            finalize_no_change_scope(
                workspace, run_id, cluster, cluster_goal
            )
            continue
        for op_index, op in enumerate(operations, start=1):
            op_goal = materialize_op_goal(
                workspace,
                cluster,
                op_index,
                goal,
                op,
                activate=False,
            )
            initialize_operation_changelog(
                workspace, op, run_id, cluster, op_index
            )
            materialize_verification_input(
                workspace,
                json.loads(op_goal.read_text()),
                op,
                run_id,
                cluster,
                op_index,
                out=op_goal.parent / "verification-input.json",
            )
            if infrastructure_blocked:
                skip_operation_phases(
                    workspace,
                    cluster,
                    op_index,
                    ("optimize", "verification", "judge"),
                    INFRASTRUCTURE_REFUSAL,
                )
                drop_created_skills(
                    workspace, created_skill_names(op)
                )
                write_publication(
                    workspace,
                    cluster,
                    op_index,
                    accepted=False,
                    reason=INFRASTRUCTURE_REFUSAL,
                )
                finalize_unexecuted_operation(
                    workspace,
                    cluster,
                    op_index,
                    status="skipped",
                    reason=INFRASTRUCTURE_REFUSAL,
                )
                continue
            try:
                enforce_creation_policy(workspace, cluster, goal, op)
            except BaseException as error:
                skip_operation_phases(
                    workspace,
                    cluster,
                    op_index,
                    ("optimize", "verification", "judge"),
                    f"policy gate: {error}",
                )
                reason = f"policy gate: {error}"
                finalize_unexecuted_operation(
                    workspace,
                    cluster,
                    op_index,
                    status="skipped",
                    reason=reason,
                )
                write_publication(
                    workspace,
                    cluster,
                    op_index,
                    accepted=False,
                    reason="policy-gate",
                )
                continue
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
    publish_lock = threading.Lock()

    def publish_now(result: dict[str, object]) -> None:
        with publish_lock:
            publish_operation_result(workspace, result)
        result["published"] = True

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
                "source edits of this skill. Apply every section, directory, and removal "
                "goal in this one op. Verification and judge run once, with --op 1."
            )
        snapshot_optimize_sources(private, op)
        optimize_input = prepare_optimize_input(private, op)
        context = optimize_session_context(cluster, op_index, op, bundle_note)
        action = "pending"
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
            "operation": str(op.get("op") or ""),
            "queue_wait_ms": queue_wait_ms,
            "bundle_size": len(bundle.get("selected") or []) or 1,
            "super_score": (task.get("rank") or {}).get("super_score"),
            "retry_budget": RETRY_BUDGET,
            "max_attempts": RETRY_BUDGET + 1,
            **_rank_fields(task),
        }
        stage_box = {"stage": "optimize"}
        try:
            while action == "pending" and attempt < RETRY_BUDGET + 1:
                attempt += 1
                suffix = f"{item}-try-{attempt}"
                suffixes.append(suffix)
                current_stage = "optimize"
                stage_box["stage"] = "optimize"
                mark_operation_phase(
                    private,
                    cluster,
                    op_index,
                    "optimize",
                    "running",
                )
                write_status(
                    workspace,
                    current_stage,
                    suffix,
                    "started",
                    skills=skill_names_mod.skill_names(op),
                )
                run_session(
                    current_stage,
                    private,
                    instruction(current_stage, context),
                    auth,
                    model,
                    install_agent,
                    suffix,
                    {**op_metadata, "attempt": attempt},
                    input_root=optimize_input,
                )
                collect_optimize_input(private, op)
                materialize_created_skill_metadata(
                    private, op, cluster, run_id
                )
                optimized_outputs = validate_optimized_op(private, op)
                changelog = materialize_operation_changelog(
                    private,
                    op,
                    run_id,
                    cluster,
                    op_index,
                )
                verification_input = materialize_verification_input(
                    private,
                    json.loads(private_op_goal.read_text()),
                    op,
                    run_id,
                    cluster,
                    op_index,
                )
                complete_session(
                    private,
                    current_stage,
                    suffix,
                    [
                        private_op_goal,
                        *optimized_outputs,
                        changelog,
                        verification_input,
                    ],
                )
                preserve_optimized_candidate(
                    workspace, private, cluster, op_index, op
                )
                action = run_verification_and_judge(
                    workspace=workspace,
                    private=private,
                    cluster=cluster,
                    op_index=op_index,
                    op=op,
                    suffix=suffix,
                    attempt=attempt,
                    op_metadata=op_metadata,
                    auth=auth,
                    model=model,
                    install_agent=install_agent,
                    stage_box=stage_box,
                    start_stage="verifiter",
                )
            result = {
                **task,
                "worker": private,
                "suffixes": suffixes,
                "judge_action": action,
            }
            publish_now(result)
            return result
        except BaseException as error:
            return settle_failed_operation(
                workspace=workspace,
                private=private,
                cluster=cluster,
                op_index=op_index,
                current_stage=stage_box["stage"],
                suffix=suffix,
                suffixes=suffixes,
                task=task,
                error=error,
            )

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
                if result.get("failed") or result.get("published"):
                    continue
                publish_now(result)
        finally:
            for result in results:
                remove_worker_workspace(result["worker"])


def continue_operations(
    workspace: Path,
    run_id: str,
    phase: str,
    workers: int,
    auth: dict[str, str],
    model: str | None,
    install_agent: bool,
) -> list[str]:
    """Rerun verification or judge for operations with a saved skill."""
    tasks, skipped = resumable_operations(workspace, phase)
    for note in skipped:
        print(f"skip {note}", flush=True)
    if not tasks:
        print(f"no saved operation to continue from {phase}", flush=True)
        return []
    print(
        f"continuing {len(tasks)} operation"
        f"{'' if len(tasks) == 1 else 's'} from {phase}",
        flush=True,
    )
    publish_lock = threading.Lock()

    def publish_now(result: dict[str, object]) -> None:
        with publish_lock:
            publish_operation_result(workspace, result)
        result["published"] = True

    def work(task_object: object) -> object:
        task = task_object
        cluster = str(task["cluster"])
        op_index = int(task["op_index"])
        op = task["op"]
        item = f"{run_id}-{cluster}-op-{op_index}-resume-1"
        conflicts = sorted(str(name) for name in task["conflicts"])
        private = copy_worker(workspace, "operations", item)
        suffix = item
        suffixes = [suffix]
        stage_name = "verifiter" if phase == "verification" else "judge"
        stage_box = {"stage": stage_name}
        op_metadata = {
            "workers": workers,
            "pool_items": len(tasks),
            "conflicts": conflicts,
            "operation": str(op.get("op") or ""),
            "resume_from": phase,
            "attempt": 1,
        }
        try:
            restore_optimized_candidate(private, workspace, cluster, op_index)
            stage_saved_operation(
                private,
                cluster,
                op_index,
                include_verification=phase == "judge",
            )
            action = run_verification_and_judge(
                workspace=workspace,
                private=private,
                cluster=cluster,
                op_index=op_index,
                op=op,
                suffix=suffix,
                attempt=1,
                op_metadata=op_metadata,
                auth=auth,
                model=model,
                install_agent=install_agent,
                stage_box=stage_box,
                start_stage=stage_name,
            )
            result = {
                **task,
                "worker": private,
                "suffixes": suffixes,
                "judge_action": action,
            }
            publish_now(result)
            return result
        except BaseException as error:
            return settle_failed_operation(
                workspace=workspace,
                private=private,
                cluster=cluster,
                op_index=op_index,
                current_stage=stage_box["stage"],
                suffix=suffix,
                suffixes=suffixes,
                task=task,
                error=error,
            )

    try:
        results = run_pool(tasks, workers, work)
    except BaseException:
        remove_worker_stage(workspace, "operations")
        raise
    for result in results:
        remove_worker_workspace(result["worker"])
    return sorted({str(task["cluster"]) for task in tasks})


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
            operation_root = (
                Path("run") / cluster / "ops" / str(op_index)
            )
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
                else {
                    "accepted": False,
                    "reason": "missing-publication",
                }
            )
            accepted = bool(publication.get("accepted", False))
            judge_action_value = None
            verification_rel = None
            artifact_error = None
            verification_document = (
                json.loads(verification_path.read_text())
                if verification_path.is_file()
                else {}
            )
            completed_verification = isinstance(
                verification_document.get("feedback"), dict
            )
            if completed_verification:
                verification = pipeline_contracts.validate_verification(
                    verification_path,
                    judged=True,
                )
                judge_action_value = verification["feedback"]["action"]["op"]
                verification_rel = verification_path.relative_to(
                    workspace
                ).as_posix()
            elif accepted:
                artifact_error = (
                    "accepted operation has no completed verification"
                )
                if verification_path.is_file():
                    verification_rel = verification_path.relative_to(
                        workspace
                    ).as_posix()
            elif verification_path.is_file():
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
                    "publication_outcome": publication.get("outcome"),
                    "artifact_bundle": operation_root.as_posix(),
                    "goal": (operation_root / "evolve-goal.json").as_posix(),
                    "verification_input": (
                        operation_root / "verification-input.json"
                    ).as_posix(),
                    "local_verification": (
                        operation_root / "verification.json"
                    ).as_posix(),
                    "verification": verification_rel,
                    "judge": (operation_root / "judge.json").as_posix(),
                    "changelog": (
                        operation_root / "changelog.json"
                    ).as_posix(),
                    "judge_action": judge_action_value,
                    "artifact_error": artifact_error,
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


OPTIMIZE_AVOIDANCE = """
Important. These reject the skill. Avoid them.

- Description: put it on the same line as `description:`. Do not write
  `description: >` or `description: |`. The checker reads only that line, so
  `>` is the description and the run fails before verification with
  "frontmatter description contains angle brackets". No `<` or `>` on that line.
- Triggers: when the goal says a first case and a later restatement are each
  enough, do not write "all of the following are true" and do not make the
  restatement a required condition. That wording scored 0.99 and still failed:
  When to Use required every bullet at once, so a first authorization that had
  not yet been restated was outside the skill.
- Headings: a required section is a level-2 heading, `## Overview`. `# Overview`
  is reported missing.
""".strip()


def _clip_changelog(text: object) -> str:
    collapsed = " ".join(str(text).split())
    if len(collapsed) <= CHANGELOG_SUMMARY_LIMIT:
        return collapsed
    return collapsed[: CHANGELOG_SUMMARY_LIMIT - 1].rstrip() + "…"


def _compact_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


def _changelog_filename(skill: str) -> str | None:
    if (
        not skill
        or skill in {".", ".."}
        or "/" in skill
        or "\\" in skill
        or skill.startswith(".")
    ):
        return None
    return f"{skill}.md"


def _phase_line(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return ""
    phase = entry.get("phase")
    finding = entry.get("finding_id")
    day = entry.get("date")
    if not isinstance(finding, str) or not finding or not isinstance(day, str):
        return ""
    if phase == "diagnosis":
        kind = f"diagnosis {finding}"
    elif phase == "goal":
        kind = f"goal {entry.get('operation') or 'no_change'} {finding}"
    elif phase == "verification":
        status = entry.get("status")
        op_index = entry.get("op_index")
        if status not in {"pass", "fail"} or not isinstance(op_index, int):
            return ""
        kind = f"verify {status} {finding}/{op_index}"
    else:
        return ""
    return f"- {day} {kind} | {_clip_changelog(entry.get('summary') or '')}"


def _operation_line(change: dict) -> str:
    operation = change.get("operation")
    finding = change.get("finding_id")
    op_index = change.get("op_index")
    day = change.get("date")
    if operation not in {"create", "update", "delete", "merge", "split"}:
        return ""
    if not isinstance(finding, str) or not isinstance(day, str):
        return ""
    if not isinstance(op_index, int) or isinstance(op_index, bool):
        return ""
    sections = ",".join(
        value
        for value in change.get("sections") or []
        if isinstance(value, str) and value
    )
    directories = ",".join(
        value
        for value in change.get("directories") or []
        if isinstance(value, str) and value
    )
    detail = " ".join(part for part in (directories, sections) if part)
    if len(detail) > CHANGELOG_SUMMARY_LIMIT:
        count = sections.count(",") + (1 if sections else 0)
        detail = f"{count} sections"
        if directories:
            detail = f"{directories} {detail}"
    if not detail and operation == "delete":
        detail = "removed"
    return (
        f"- {day} {operation} {finding}/{op_index} | {_clip_changelog(detail)}"
    )


def lines_from_history(history: list) -> list[str]:
    lines: list[str] = []
    for record in history:
        if not isinstance(record, dict):
            continue
        if record.get("phase") in {"diagnosis", "goal", "verification"}:
            line = _phase_line(record)
        else:
            line = _operation_line(record)
        if line:
            lines.append(line)
    return lines


def append_changelog_lines(
    directory: Path, skill: str, lines: list[str]
) -> None:
    """Append changelog lines. Existing lines are never rewritten."""
    filename = _changelog_filename(skill)
    if filename is None or not lines:
        return
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if not path.is_file():
        path.write_text(f"# {skill}\n")
    existing = path.read_text()
    keys = {
        line.split(" | ", 1)[0]
        for line in existing.splitlines()
        if line.startswith("- ")
    }
    fresh: list[str] = []
    for line in lines:
        if not line.startswith("- "):
            continue
        key = line.split(" | ", 1)[0]
        if key in keys:
            continue
        keys.add(key)
        fresh.append(line)
    if not fresh:
        return
    with path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write("\n".join(fresh) + "\n")


def merge_changelog_file(source: Path, destination: Path) -> None:
    """Append lines from source that destination does not already have."""
    if not source.is_file():
        return
    skill = source.stem
    append_changelog_lines(
        destination.parent,
        skill,
        [
            line
            for line in source.read_text().splitlines()
            if line.startswith("- ")
        ],
    )


def _run_day(workspace: Path) -> str:
    match = re.search(r"@(\d{4}-\d{2}-\d{2})", workspace.name)
    if match:
        return match.group(1)
    return datetime.now(UTC).date().isoformat()


def _read_json_object(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _changelog_skills(workspace: Path, cluster: str) -> list[str]:
    """Skills this finding diagnosed, targeted, or recalled."""
    names: list[str] = []
    goal = _read_json_object(workspace / "run" / cluster / "evolve-goal.json")
    improve = (goal.get("goal") or {}).get("improve_skills") or []
    if isinstance(improve, list):
        names.extend(value for value in improve if isinstance(value, str) and value)
    for op in (goal.get("action") or {}).get("ops") or []:
        if isinstance(op, dict):
            names.extend(skill_names_mod.skill_names(op))
    matching = _read_json_object(
        workspace / "run" / cluster / "label-matching.json"
    )
    for group in matching.get("clusters") or []:
        if not isinstance(group, dict):
            continue
        if group.get("cluster") not in {cluster, None} and cluster != "cut":
            continue
        for row in group.get("skills") or []:
            if isinstance(row, dict) and isinstance(row.get("skill"), str):
                names.append(row["skill"])
    ordered: list[str] = []
    for name in names:
        if name not in ordered:
            ordered.append(name)
    return ordered


def _goal_operation(goal: dict, skill: str) -> str:
    for op in (goal.get("action") or {}).get("ops") or []:
        if isinstance(op, dict) and skill in skill_names_mod.skill_names(op):
            return str(op.get("op") or "no_change")
    return "no_change"


def skill_phase_entries(
    workspace: Path, skill: str, run_id: str | None = None
) -> list[dict[str, object]]:
    """Diagnosis, goal, and verification notes for one skill."""
    run_name = run_id or workspace.name
    day = _run_day(workspace if run_id is None else Path(run_name))
    if run_id is not None:
        match = re.search(r"@(\d{4}-\d{2}-\d{2})", run_id)
        day = match.group(1) if match else datetime.now(UTC).date().isoformat()
    entries: list[dict[str, object]] = []
    run_root = workspace / "run"
    if not run_root.is_dir():
        return entries
    for goal_path in sorted(run_root.glob("*/evolve-goal.json")):
        cluster = goal_path.parent.name
        if skill not in _changelog_skills(workspace, cluster):
            continue
        diagnosis = _read_json_object(goal_path.parent / "diagnosis.json")
        gaps = [
            str(item.get("description") or item.get("reasoning") or "")
            for item in diagnosis.get("skill_capabilities_missing") or []
            if isinstance(item, dict)
        ]
        goal = _read_json_object(goal_path)
        action = goal.get("action") if isinstance(goal.get("action"), dict) else {}
        entries.append(
            {
                "id": f"{run_name}:{cluster}:{skill}:diagnosis",
                "skill": skill,
                "phase": "diagnosis",
                "run_id": run_name,
                "finding_id": cluster,
                "date": day,
                "summary": _clip_changelog(" ".join(gaps)),
            }
        )
        entries.append(
            {
                "id": f"{run_name}:{cluster}:{skill}:goal",
                "skill": skill,
                "phase": "goal",
                "operation": _goal_operation(goal, skill),
                "run_id": run_name,
                "finding_id": cluster,
                "date": day,
                "summary": _clip_changelog(
                    action.get("reason") or goal.get("plan") or goal.get("reasoning")
                ),
            }
        )
        ops_root = goal_path.parent / "ops"
        if not ops_root.is_dir():
            continue
        for verification_path in sorted(ops_root.glob("*/verification.json")):
            if not verification_path.parent.name.isdigit():
                continue
            op_index = int(verification_path.parent.name)
            verification = _read_json_object(verification_path)
            feedback = verification.get("feedback") or {}
            row = next(
                (
                    item
                    for item in feedback.get("per_skill") or []
                    if isinstance(item, dict) and item.get("skill") == skill
                ),
                None,
            )
            if row is None:
                continue
            status = row.get("status")
            if status not in {"pass", "fail"}:
                continue
            score = row.get("score")
            feedback = str(row.get("feedback") or "")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                feedback = f"{_compact_number(float(score))} {feedback}"
            entries.append(
                {
                    "id": f"{run_name}:{cluster}:{op_index}:{skill}:verification",
                    "skill": skill,
                    "phase": "verification",
                    "operation": _goal_operation(goal, skill),
                    "run_id": run_name,
                    "finding_id": cluster,
                    "op_index": op_index,
                    "date": day,
                    "status": status,
                    "summary": _clip_changelog(feedback),
                }
            )
    return entries


def verification_changelog_entry(
    workspace: Path, cluster: str, op_index: int, skill: str
) -> dict[str, object] | None:
    changelog = _read_json_object(
        workspace / "run" / cluster / "ops" / str(op_index) / "changelog.json"
    )
    changes = changelog.get("changes") or []
    run_id = (
        str(changes[0].get("run_id"))
        if changes and isinstance(changes[0], dict) and changes[0].get("run_id")
        else None
    )
    for entry in skill_phase_entries(workspace, skill, run_id):
        if (
            entry.get("phase") == "verification"
            and entry.get("finding_id") == cluster
            and entry.get("op_index") == op_index
        ):
            return entry
    return None


def detach_skill_changelogs(workspace: Path) -> None:
    """Move changelog lists off metadata and onto the append-only files."""
    path = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    if not path.is_file():
        return
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return
    rows = document.get("skills_metadata")
    if not isinstance(rows, list):
        return
    moved = False
    directory = workspace / SKILL_CHANGELOG_DIR
    for row in rows:
        if not isinstance(row, dict) or "changelog" not in row:
            continue
        history = row.pop("changelog")
        moved = True
        skill = row.get("skill")
        if isinstance(skill, str) and isinstance(history, list):
            append_changelog_lines(directory, skill, lines_from_history(history))
    if moved:
        atomic_write_json(path, document)


def sync_skill_changelogs(workspace: Path) -> None:
    """Append diagnosis, goal, and verification onto each skill changelog."""
    detach_skill_changelogs(workspace)
    path = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    if not path.is_file():
        return
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError:
        return
    rows = document.get("skills_metadata")
    if not isinstance(rows, list):
        return
    names: list[str] = []
    run_root = workspace / "run"
    if run_root.is_dir():
        for goal_path in run_root.glob("*/evolve-goal.json"):
            for name in _changelog_skills(workspace, goal_path.parent.name):
                if name not in names:
                    names.append(name)
    present = {
        row.get("skill")
        for row in rows
        if isinstance(row, dict)
    }
    directory = workspace / SKILL_CHANGELOG_DIR
    for skill in names:
        if skill not in present:
            continue
        append_changelog_lines(
            directory,
            skill,
            [
                line
                for entry in skill_phase_entries(workspace, skill)
                if (line := _phase_line(entry))
            ],
        )


def _row_without_changelog(row: dict, directory: Path) -> dict:
    row = copy.deepcopy(row)
    history = row.pop("changelog", None)
    skill = row.get("skill")
    if isinstance(skill, str) and isinstance(history, list):
        append_changelog_lines(directory, skill, lines_from_history(history))
    return row


def update_candidate_pool(
    workspace: Path,
    names: set[str],
    inventory: Path | None = None,
) -> None:
    """Write accepted creates and updates into the candidate pool.

    A name with no skill directory left in the run is removed from the pool.
    Its changelog file stays.
    """
    detach_skill_changelogs(workspace)
    root = inventory or (ROOT / "workspace")
    skills_src = workspace / "target/to_be_improved_skills"
    skills_dest = root / "candidate_skills"
    meta_src = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    meta_dest = root / "candidate_skills_metadata/metadata.json"
    run_logs = workspace / SKILL_CHANGELOG_DIR
    pool_logs = root / POOL_CHANGELOG_DIR
    skills_dest.mkdir(parents=True, exist_ok=True)
    incoming: dict[str, dict] = {}
    if meta_src.is_file():
        try:
            document = json.loads(meta_src.read_text())
        except json.JSONDecodeError:
            document = {}
        incoming = {
            str(row["skill"]): row
            for row in document.get("skills_metadata") or []
            if isinstance(row, dict) and isinstance(row.get("skill"), str)
        }
    current: dict[str, dict] = {}
    if meta_dest.is_file():
        try:
            document = json.loads(meta_dest.read_text())
        except json.JSONDecodeError:
            document = {}
        current = {
            str(row["skill"]): _row_without_changelog(row, pool_logs)
            for row in document.get("skills_metadata") or []
            if isinstance(row, dict) and isinstance(row.get("skill"), str)
        }
    for name in sorted(names):
        merge_changelog_file(
            run_logs / f"{name}.md", pool_logs / f"{name}.md"
        )
        source = skills_src / name
        destination = skills_dest / name
        if source.is_dir() and (source / "SKILL.md").is_file():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
            if name in incoming:
                current[name] = _row_without_changelog(incoming[name], pool_logs)
        else:
            if destination.exists():
                shutil.rmtree(destination)
            current.pop(name, None)
    meta_dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        meta_dest,
        {
            "skills_metadata": [
                current[name] for name in sorted(current, key=str.casefold)
            ]
        },
    )


def publish_inventory(
    workspace: Path, inventory: Path | None = None
) -> None:
    """Copy accepted skills, metadata, and changelogs out of the run."""
    detach_skill_changelogs(workspace)
    root = inventory or (ROOT / "workspace")
    skills_src = workspace / "target/to_be_improved_skills"
    meta_src = workspace / "target/to_be_improved_skills_metadata/metadata.json"
    skills_dest = root / "candidate_skills"
    meta_dest = root / "candidate_skills_metadata/metadata.json"
    pool_logs = root / POOL_CHANGELOG_DIR
    run_logs = workspace / SKILL_CHANGELOG_DIR
    if skills_src.is_dir():
        skills_dest.mkdir(parents=True, exist_ok=True)
        for skill_dir in skills_src.iterdir():
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            destination = skills_dest / skill_dir.name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(skill_dir, destination)
    if run_logs.is_dir():
        for path in sorted(run_logs.glob("*.md")):
            merge_changelog_file(path, pool_logs / path.name)
    if not meta_src.is_file():
        return
    try:
        incoming = json.loads(meta_src.read_text())
    except json.JSONDecodeError:
        return
    rows = [
        _row_without_changelog(row, pool_logs)
        for row in incoming.get("skills_metadata") or []
        if isinstance(row, dict) and isinstance(row.get("skill"), str)
    ]
    by_name = {str(row["skill"]): row for row in rows}
    if meta_dest.is_file():
        try:
            current = json.loads(meta_dest.read_text())
        except json.JSONDecodeError:
            current = {}
        for row in current.get("skills_metadata") or []:
            if (
                isinstance(row, dict)
                and isinstance(row.get("skill"), str)
                and row["skill"] not in by_name
            ):
                by_name[row["skill"]] = _row_without_changelog(row, pool_logs)
    meta_dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        meta_dest,
        {
            "skills_metadata": [
                by_name[name]
                for name in sorted(by_name, key=str.casefold)
            ]
        },
    )


OPTIMIZE_INPUT = Path("optimize-input")


def optimize_written_and_removed(op: dict) -> tuple[list[str], list[str]]:
    """Skill directories this op writes, and skill directories it removes."""
    operation = op.get("op")
    names = skill_names_mod.skill_names(op)
    if operation == "delete":
        return [], names
    if operation == "merge":
        target = (op.get("into") or {}).get("skill")
        written = [target] if isinstance(target, str) and target else []
        return written, [name for name in names if name not in written]
    if operation == "split":
        written = [
            row.get("skill")
            for row in op.get("into") or []
            if isinstance(row, dict) and isinstance(row.get("skill"), str)
        ]
        source = op.get("skill")
        removed = (
            [source]
            if isinstance(source, str) and source not in written
            else []
        )
        return written, removed
    if operation == "update":
        return names, []
    return names, []


def snapshot_optimize_sources(workspace: Path, op: dict) -> None:
    """Copy source skills to raw_skills before the optimize session."""
    if op.get("op") == "create":
        return
    improved = workspace / "target/to_be_improved_skills"
    raw = workspace / "target/raw_skills"
    for name in skill_names_mod.skill_names(op):
        source = improved / name
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            continue
        destination = raw / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)


def prepare_optimize_input(workspace: Path, op: dict) -> Path:
    """Temp directory with each target skill and its changelog beside it."""
    root = workspace / OPTIMIZE_INPUT
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    improved = workspace / "target/to_be_improved_skills"
    logs = workspace / SKILL_CHANGELOG_DIR
    for name in skill_names_mod.skill_names(op):
        append_changelog_lines(
            logs,
            name,
            [
                line
                for entry in skill_phase_entries(workspace, name)
                if entry.get("phase") != "verification"
                and (line := _phase_line(entry))
            ],
        )
        source = improved / name
        if source.is_dir() and (source / "SKILL.md").is_file():
            shutil.copytree(source, root / name)
        changelog = logs / f"{name}.md"
        aside = root / f"{name}.md"
        if changelog.is_file():
            shutil.copy2(changelog, aside)
        else:
            aside.write_text(f"# {name}\n")
    return root


def collect_optimize_input(workspace: Path, op: dict) -> None:
    """Copy edited skill directories back. Leave changelog files behind."""
    root = workspace / OPTIMIZE_INPUT
    improved = workspace / "target/to_be_improved_skills"
    improved.mkdir(parents=True, exist_ok=True)
    written, removed = optimize_written_and_removed(op)
    for name in written:
        source = root / name
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            continue
        destination = improved / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    for name in removed:
        destination = improved / name
        if destination.exists():
            shutil.rmtree(destination)


def optimize_session_context(
    cluster: str, op_index: int, op: dict, bundle_note: str
) -> str:
    names = skill_names_mod.skill_names(op)
    listed = ", ".join(f"`{name}/` and `{name}.md`" for name in names)
    return (
        f"This isolated session is cluster <{cluster}>, action.ops item "
        f"{op_index}: {json.dumps(op, ensure_ascii=False)}. "
        f"workspace/ contains {listed}. "
        "Each `.md` file beside a skill directory is that skill's changelog, "
        "not the skill. Read it. Do not edit it. Edit only the skill directory. "
        f"Do not read or write metadata.{bundle_note}\n\n"
        f"{OPTIMIZE_AVOIDANCE}"
    )


def execute(args: argparse.Namespace) -> None:
    global ACTIVE_BACKEND
    workspace = (ROOT / "workspace/runs" / args.run_id).resolve()
    if args.init:
        initialize_workspace(workspace)
        return
    require_path(workspace, "run workspace")
    resuming = bool(getattr(args, "resume_from", None))
    if resuming:
        if not workspace_was_started(workspace):
            raise SystemExit(f"{workspace.name} has not been started")
    else:
        require_path(
            workspace / "target/to_be_improved_skills",
            "existing skills directory",
        )
        require_seed_inputs(workspace)
        workspace = allocate_execution_workspace(workspace)
        args.run_id = workspace.name
    ACTIVE_BACKEND = select_backend(args.agent, args.allow_local_fallback)
    args.model = configured_model(ACTIVE_BACKEND, args.model)
    print(f"selected model: {args.model}")
    auth = require_auth() if ACTIVE_BACKEND == "docker-claude" else {}
    if args.build:
        build_images()

    try:
        if resuming:
            continue_operations(
                workspace,
                args.run_id,
                args.resume_from,
                getattr(args, "op_workers", DEFAULT_OP_WORKERS),
                auth,
                args.model,
                not args.agent_installed,
            )
            clusters = sorted(
                path.parent.name
                for path in (workspace / "run").glob("*/evolve-goal.json")
                if path.is_file()
            )
            if clusters:
                write_pipeline_summary(workspace, clusters)
            sync_skill_changelogs(workspace)
            publish_inventory(workspace)
            print(
                f"completed continuation {args.run_id} from "
                f"{args.resume_from}: {workspace}"
            )
            return
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
                workspace,
                "preprocessing",
                args.run_id,
                "failed",
                error=failure_text(error),
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

        metadata_path = (
            workspace / "target/to_be_improved_skills_metadata/metadata.json"
        )
        seed_names = {
            path.name
            for path in (workspace / "target/to_be_improved_skills").iterdir()
            if path.is_dir()
        }
        detach_skill_changelogs(workspace)
        try:
            pipeline_contracts.validate_metadata(metadata_path, seed_names)
        except (FileNotFoundError, json.JSONDecodeError, pipeline_contracts.ContractError):
            run_session(
                "label-skills",
                workspace,
                instruction(
                    "label-skills", "Label the complete existing skill set once."
                ),
                auth,
                args.model,
                not args.agent_installed,
                args.run_id,
            )
        else:
            with pipeline_metrics.span(
                workspace,
                "label-skills",
                args.run_id,
                "deterministic",
                metadata={"reused": True},
            ):
                pass
            print("reused validated skill metadata", flush=True)
        with pipeline_metrics.span(
            workspace,
            "validate-skill-labels",
            args.run_id,
            "deterministic",
        ):
            detach_skill_changelogs(workspace)
            pipeline_contracts.validate_metadata(metadata_path, seed_names)
        complete_session(workspace, "label-skills", args.run_id, [metadata_path])

        unit_kind = getattr(args, "evolution_unit", "cluster")
        clusters = evolution_units(workspace, active_clustered, unit_kind)
        refuse_blocked_scopes(workspace, active_clustered, unit_kind)
        if not clusters:
            publish_inventory(workspace)
            print(
                f"completed run {args.run_id}: no evolution units remained after "
                "the configured selection and infrastructure filters"
            )
            return
        scope_clustered = active_clustered or unit_kind == "finding"
        cluster_workers = getattr(args, "cluster_workers", DEFAULT_CLUSTER_WORKERS)
        op_workers = getattr(args, "op_workers", DEFAULT_OP_WORKERS)
        pipeline_diagnosis_and_goals(
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
        successful_clusters = [
            cluster
            for cluster in clusters
            if (workspace / "run" / cluster / "evolve-goal.json").is_file()
        ]
        fanout_operations(
            workspace,
            args.run_id,
            successful_clusters,
            op_workers,
            auth,
            args.model,
            not args.agent_installed,
            getattr(args, "max_ops_per_skill", None),
            getattr(args, "min_super_score", None),
        )
        write_pipeline_summary(workspace, successful_clusters)
        sync_skill_changelogs(workspace)
        publish_inventory(workspace)

        print(f"completed run {args.run_id}: {workspace}")

    finally:
        pipeline_metrics.write_run_report(workspace)
        try:
            pipeline_metrics.write_phase_metrics_summary(workspace.parent)
        except Exception as error:
            print(
                f"phase metrics summary failed: {error}",
                file=sys.stderr,
                flush=True,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="directory name under workspace/runs")
    parser.add_argument(
        "--init", action="store_true", help="create the run workspace and stop"
    )
    parser.add_argument(
        "--from",
        dest="resume_from",
        choices=("verification", "judge"),
        help=(
            "continue a stamped run from verification or judge for every "
            "operation whose optimized skill was saved and not accepted"
        ),
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
        help=(
            "maximum combined diagnosis and goal workers; a finding's goal "
            "starts when its diagnosis finishes"
        ),
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
    parser.add_argument(
        "--model",
        help="override the model of the selected agent config entry",
    )
    parser.add_argument(
        "--agent",
        choices=("auto", "cursor", "codex", "claude", "docker-claude"),
        default="auto",
        help="agent backend; auto uses the single active entry in agent-config.json",
    )
    parser.add_argument(
        "--allow-local-fallback",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--agent-installed",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.resume_from and args.init:
        parser.error("--from cannot be combined with --init")
    stamped = re.fullmatch(
        r"[A-Za-z0-9_.-]+@[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?:-[0-9]+)?",
        args.run_id,
    )
    if args.resume_from:
        if not stamped:
            parser.error(
                "--from requires the stamped run directory name, "
                "such as run-id@YYYY-MM-DDTHH:MM"
            )
    elif not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_id):
        parser.error(
            "run_id may contain only letters, numbers, dot, underscore, dash"
        )
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
