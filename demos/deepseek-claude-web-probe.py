#!/usr/bin/env python3
"""Probe Claude Agent SDK web tooling through DeepSeek's Anthropic endpoint.

The probe intentionally records evidence instead of assuming that a tool exposed
by Claude Code is implemented by an Anthropic-compatible model provider.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


URL_RE = re.compile(r"https?://[^\s\"'<>\\)\\]]+")


def jsonable(value: Any) -> Any:
    """Convert SDK dataclasses and other common values to JSON-safe objects."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def find_values(value: Any, key_names: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in key_names:
                found.append(item)
            found.extend(find_values(item, key_names))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_values(item, key_names))
    return found


def find_urls(value: Any) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str) and item.startswith(("http://", "https://")):
                urls.add(item)
            urls.update(find_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.update(find_urls(item))
    elif isinstance(value, str):
        urls.update(URL_RE.findall(value))
    return urls


def locate_transcript(session_id: str) -> Path | None:
    root = Path.home() / ".claude" / "projects"
    if not root.exists():
        return None
    matches = list(root.glob(f"*/{session_id}.jsonl"))
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default=(
            "You must use WebSearch to find the current official DeepSeek API model names. "
            "Return a short answer with the source page titles and exact URLs. Then use "
            "WebFetch on one official source URL and state one fact from that page."
        ),
    )
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"))
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/deepseek-claude-web-probe"))
    parser.add_argument("--max-turns", type=int, default=8)
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set DEEPSEEK_API_KEY (preferred) or ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2

    run_dir = args.output_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    event_path = run_dir / "sdk-events.jsonl"
    stderr_path = run_dir / "claude-stderr.log"
    records: list[dict[str, Any]] = []
    session_id: str | None = None

    def capture_stderr(line: str) -> None:
        with stderr_path.open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip("\n") + "\n")

    # Claude Code/Agent SDK reads Anthropic variable names. We map DeepSeek's
    # conventional variables only in the child process and never persist the key.
    child_env = {
        "ANTHROPIC_API_KEY": api_key,
        "ANTHROPIC_BASE_URL": args.base_url.rstrip("/"),
        "ANTHROPIC_MODEL": args.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": args.model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": args.model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": args.model,
    }
    options = ClaudeAgentOptions(
        model=args.model,
        cwd=Path.cwd(),
        tools=["WebSearch", "WebFetch"],
        allowed_tools=["WebSearch", "WebFetch"],
        max_turns=args.max_turns,
        setting_sources=[],
        strict_mcp_config=True,
        include_partial_messages=True,
        env=child_env,
        stderr=capture_stderr,
    )

    error: str | None = None
    try:
        with event_path.open("w", encoding="utf-8") as stream:
            async for message in query(prompt=args.prompt, options=options):
                record = {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "sdk_type": type(message).__name__,
                    "message": jsonable(message),
                }
                records.append(record)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    if message.result:
                        print(message.result)
    except Exception as exc:  # The failure itself is part of the compatibility probe.
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)

    transcript_source = locate_transcript(session_id) if session_id else None
    transcript_copy = run_dir / "session-history.jsonl"
    if transcript_source:
        shutil.copy2(transcript_source, transcript_copy)

    evidence = records.copy()
    if transcript_copy.exists():
        for line in transcript_copy.read_text(encoding="utf-8").splitlines():
            try:
                evidence.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    tool_names = sorted({str(item) for item in find_values(evidence, {"name"}) if "web" in str(item).lower()})
    urls = sorted(find_urls(evidence))
    summary = {
        "status": "error" if error else "completed",
        "error": error,
        "model": args.model,
        "base_url": args.base_url,
        "prompt": args.prompt,
        "session_id": session_id,
        "sdk_event_count": len(records),
        "web_tool_names_observed": tool_names,
        "web_tool_call_observed": any(name.lower() in {"websearch", "webfetch", "web_search", "web_fetch"} for name in tool_names),
        "reference_urls": urls,
        "persisted_transcript_found": transcript_source is not None,
        "persisted_transcript_source": str(transcript_source) if transcript_source else None,
        "files": {
            "sdk_events": str(event_path),
            "session_history": str(transcript_copy) if transcript_copy.exists() else None,
            "stderr": str(stderr_path),
        },
        "note": "Tool exposure is not proof of backend support; inspect events/history and errors.",
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nEvidence: {run_dir.resolve()}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
