#!/usr/bin/env python3
"""Normalize JSONL records according to references/record-schema.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def normalize(record: object, line_number: int) -> dict[str, object]:
    if not isinstance(record, dict):
        raise ValueError(f"line {line_number}: record must be an object")
    identifier = record.get("id")
    text = record.get("text")
    tags = record.get("tags", [])
    if not isinstance(identifier, str) or not identifier:
        raise ValueError(f"line {line_number}: id must be a non-empty string")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"line {line_number}: text must be a non-empty string")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError(f"line {line_number}: tags must be an array of strings")
    return {
        "id": identifier,
        "text": " ".join(text.split()),
        "tags": sorted({tag.strip() for tag in tags if tag.strip()}),
    }


def normalize_file(source: Path, destination: Path) -> None:
    output: list[str] = []
    for line_number, raw_line in enumerate(source.read_text().splitlines(), 1):
        if not raw_line.strip():
            continue
        output.append(
            json.dumps(
                normalize(json.loads(raw_line), line_number),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    destination.write_text("\n".join(output) + ("\n" if output else ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    normalize_file(args.source, args.destination)


if __name__ == "__main__":
    main()
