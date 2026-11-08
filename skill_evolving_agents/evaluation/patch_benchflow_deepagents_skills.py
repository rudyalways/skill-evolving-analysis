#!/usr/bin/env python3
"""Make BenchFlow's DeepAgents adapter discover mounted custom skills."""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = '"the user\'s task end to end. Verify your work before finishing."\n'
NEW = (
    '"the user\'s task end to end. Verify your work before finishing. "\n'
    '            "Before planning, use the execute shell tool to run `find /skills "\n'
    '            "-mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null`; filesystem "\n'
    '            "tools cannot see this external mount. Each result is an available skill: "\n'
    '            "use execute with cat to read its SKILL.md and follow "\n'
    '            "any relevant instructions and bundled scripts, references, or assets. "\n'
    '            "Do not claim skill use without reading the corresponding SKILL.md. "\n'
    '            "Never search the web for the task name, benchmark, oracle, answer, "\n'
    '            "or solution repository; network access is only for dependencies and "\n'
    '            "generic technical documentation needed to implement the task."\n'
)

HELPER = '''\n\ndef _load_mounted_skill_context(root="/skills"):\n    """Return mounted SKILL.md files for deterministic prompt injection."""\n    parts = []\n    if not os.path.isdir(root):\n        return ""\n    for name in sorted(os.listdir(root)):\n        path = os.path.join(root, name, "SKILL.md")\n        if not os.path.isfile(path):\n            continue\n        try:\n            with open(path, encoding="utf-8") as stream:\n                content = stream.read()\n        except OSError:\n            continue\n        parts.append(f"<mounted-skill path={path}>\\n{content}\\n</mounted-skill>")\n    return "\\n\\n".join(parts)\n'''

RUN_MARKER = "def run_deep_agent(\n"
STREAM_OLD = '{"messages": [{"role": "user", "content": instruction}]},'
STREAM_NEW = '{"messages": [{"role": "user", "content": effective_instruction}]},'
AGENT_OLD = "    agent = build_deep_agent(model_id, cwd, env)\n"
AGENT_NEW = (
    "    agent = build_deep_agent(model_id, cwd, env)\n"
    "    skill_context = _load_mounted_skill_context()\n"
    "    effective_instruction = (\n"
    '        skill_context + "\\n\\n<task>\\n" + instruction + "\\n</task>"\n'
    "        if skill_context else instruction\n"
    "    )\n"
    "    if skill_context:\n"
    "        _emit_text(session_id, skill_context)\n"
)
BROKEN_EXPRESSION = r'skill_context + \"\n\n<task>\n\" + instruction + \"\n</task>\"'
FIXED_EXPRESSION = r'skill_context + "\n\n<task>\n" + instruction + "\n</task>"'


def patch(path: Path) -> str:
    text = path.read_text()
    repaired = False
    if BROKEN_EXPRESSION in text:
        text = text.replace(BROKEN_EXPRESSION, FIXED_EXPRESSION, 1)
        repaired = True
    if NEW in text and HELPER in text and STREAM_NEW in text:
        if repaired:
            path.write_text(text)
            return "repaired"
        return "already-patched"
    if NEW not in text and OLD not in text:
        raise RuntimeError(f"unsupported BenchFlow shim layout: {path}")
    if NEW not in text:
        text = text.replace(OLD, NEW, 1)
    if HELPER not in text:
        if RUN_MARKER not in text:
            raise RuntimeError(f"missing run marker in BenchFlow shim: {path}")
        text = text.replace(RUN_MARKER, HELPER + "\n\n" + RUN_MARKER, 1)
    if AGENT_NEW not in text:
        if AGENT_OLD not in text:
            raise RuntimeError(f"missing agent construction in BenchFlow shim: {path}")
        text = text.replace(AGENT_OLD, AGENT_NEW, 1)
    if STREAM_NEW not in text:
        if STREAM_OLD not in text:
            raise RuntimeError(f"missing stream input in BenchFlow shim: {path}")
        text = text.replace(STREAM_OLD, STREAM_NEW, 1)
    path.write_text(text)
    return "patched"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shim", type=Path)
    args = parser.parse_args()
    print(patch(args.shim))


if __name__ == "__main__":
    main()
