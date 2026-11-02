#!/usr/bin/env python3
"""Probe Claude Agent SDK WebSearch and JSONL persistence through DeepSeek.

Setup:
    python -m pip install claude-agent-sdk==0.2.174
    # Put DEEPSEEK_API_KEY=... in the repository .env, then:
    python scripts/probe_claude_sdk_deepseek.py

The API key is passed to Claude Code as ANTHROPIC_AUTH_TOKEN and is never
written to the evidence files or printed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from uuid import uuid4

DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
DEFAULT_MODEL = "deepseek-flash"
URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without replacing exported variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def find_tool_names(records: list[dict[str, Any]], *, calls_only: bool = False) -> list[str]:
    names: set[str] = set()
    for record in records:
        for item in walk(record):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            looks_like_call = "id" in item and "input" in item
            if (
                isinstance(name, str)
                and ("search" in name.lower() or "web" in name.lower())
                and (looks_like_call or not calls_only)
            ):
                names.add(name)
            tools = item.get("tools") if not calls_only else None
            if isinstance(tools, list):
                names.update(tool for tool in tools if isinstance(tool, str))
    return sorted(names)


def find_urls(records: list[dict[str, Any]]) -> list[str]:
    urls: set[str] = set()
    for record in records:
        for item in walk(record):
            if isinstance(item, str):
                urls.update(match.rstrip(".,;]}") for match in URL_RE.findall(item))
    return sorted(urls)


def transcript_candidates(config_dir: Path, cwd: Path, session_id: str) -> list[Path]:
    project_key = re.sub(r"[^A-Za-z0-9]", "-", str(cwd.resolve()))
    direct = config_dir / "projects" / project_key / f"{session_id}.jsonl"
    candidates = [direct]
    projects = config_dir / "projects"
    if projects.is_dir():
        candidates.extend(projects.glob(f"*/{session_id}.jsonl"))
    return list(dict.fromkeys(candidates))


def wait_for_transcript(config_dir: Path, cwd: Path, session_id: str) -> Path | None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        for candidate in transcript_candidates(config_dir, cwd, session_id):
            if candidate.is_file() and candidate.stat().st_size:
                return candidate.resolve()
        time.sleep(0.25)
    return None


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            records.append({"jsonl_parse_error": str(error), "line": line_number})
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


async def run_probe(args: argparse.Namespace) -> int:
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:
        print(
            "Missing dependency. Run: python -m pip install claude-agent-sdk==0.2.174",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "DEEPSEEK_API_KEY is not set. Add it to the repository .env or export it.",
            file=sys.stderr,
        )
        return 2

    cwd = Path(args.cwd).resolve()
    session_id = str(uuid4())
    evidence_dir = Path(args.evidence_dir).expanduser().resolve() / session_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    stream_path = evidence_dir / "sdk-stream.jsonl"
    report_path = evidence_dir / "report.json"
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude")).expanduser()
    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_ANTHROPIC_BASE_URL)

    child_env = {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": args.model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": args.model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": args.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": args.model,
        "CLAUDE_CODE_SUBAGENT_MODEL": args.model,
    }
    options = ClaudeAgentOptions(
        allowed_tools=["WebSearch"],
        tools=["WebSearch"],
        permission_mode="dontAsk",
        cwd=cwd,
        env=child_env,
        model=args.model,
        max_turns=args.max_turns,
        max_budget_usd=args.max_budget_usd,
        session_id=session_id,
    )

    sdk_records: list[dict[str, Any]] = []
    try:
        with stream_path.open("w", encoding="utf-8") as stream:
            async for message in query(prompt=args.prompt, options=options):
                record = {
                    "sdk_type": type(message).__name__,
                    "message": jsonable(message),
                }
                sdk_records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
    except Exception as error:
        sdk_records.append(
            {
                "sdk_type": type(error).__name__,
                "error": str(error),
            }
        )
        with stream_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sdk_records[-1], ensure_ascii=False) + "\n")

    transcript_path = wait_for_transcript(config_dir, cwd, session_id)
    transcript_records = read_jsonl(transcript_path)
    all_records = [*sdk_records, *transcript_records]
    available_tool_names = find_tool_names(all_records)
    invoked_tool_names = find_tool_names(all_records, calls_only=True)
    urls = find_urls(all_records)
    web_search_available = any(
        name.lower() in {"websearch", "web_search"} for name in available_tool_names
    )
    web_search_invoked = any(
        name.lower() in {"websearch", "web_search"} for name in invoked_tool_names
    )
    result_errors = [
        record
        for record in sdk_records
        if record.get("sdk_type") == "ResultMessage"
        and record.get("message", {}).get("is_error")
    ]
    runtime_errors = [record for record in sdk_records if "error" in record]

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "sdk": "claude-agent-sdk",
        "session_id": session_id,
        "cwd": str(cwd),
        "provider": {
            "name": "DeepSeek",
            "base_url": base_url,
            "model": args.model,
            "credential_present": True,
            "credential_recorded": False,
        },
        "checks": {
            "web_search_available": web_search_available,
            "web_search_invoked": web_search_invoked,
            "native_jsonl_found": transcript_path is not None,
            "reference_urls_found": bool(urls),
            "completed_without_reported_error": not result_errors and not runtime_errors,
        },
        "evidence": {
            "sdk_stream_jsonl": str(stream_path),
            "native_session_jsonl": str(transcript_path) if transcript_path else None,
            "report_json": str(report_path),
            "available_web_tool_names": available_tool_names,
            "invoked_web_tool_names": invoked_tool_names,
            "reference_urls": urls,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all(report["checks"].values()) else 1


def parse_args() -> argparse.Namespace:
    default_evidence = Path("/tmp/claude-sdk-deepseek-probe")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=str(Path.cwd()), help="Claude session working directory")
    parser.add_argument("--evidence-dir", default=str(default_evidence))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--max-budget-usd", type=float, default=0.25)
    parser.add_argument(
        "--prompt",
        default=(
            "You must use WebSearch now. Find the official DeepSeek documentation page "
            "about integrating with Claude Code. Answer with the page title and its full "
            "https URL. Do not use any other tool."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe(parse_args())))
