#!/usr/bin/env python3
"""Fail CI when tracked text contains likely live credentials."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)(api[_-]?key|auth[_-]?token|password)\s*=\s*['\"]?[A-Za-z0-9_./+-]{16,}"),
)
ALLOW = {".env.example", "scripts/security_scan.py"}
ALLOW_PREFIXES = ("skill_evolving_agents/tests/",)


def main() -> None:
    files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    findings = []
    for name in files:
        if not name or name in ALLOW or name.startswith(ALLOW_PREFIXES):
            continue
        path = Path(name)
        try:
            text = path.read_text(errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                findings.append(f"{name}: {pattern.pattern}")
    if findings:
        raise SystemExit("possible credentials in tracked files:\n" + "\n".join(findings))


if __name__ == "__main__":
    main()
