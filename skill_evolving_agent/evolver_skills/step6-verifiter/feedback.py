"""Failure lines a later step can act on."""

from __future__ import annotations


def block(skill: str, check: str, problem: str, fix: str, next_state: str) -> str:
    return "\n".join(
        [
            f"skill: {skill}",
            f"check: {check}",
            f"problem: {problem}",
            f"fix: {fix}",
            f"next: {next_state}",
        ]
    )
