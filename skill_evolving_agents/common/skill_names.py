"""Skill names named by one goal action."""

from __future__ import annotations


def bare(value: str) -> str:
    if value.startswith("<") and value.endswith(">") and len(value) > 2:
        return value[1:-1]
    return value


def skill_names(op: dict) -> list[str]:
    found: list[str] = []

    def add(value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            return
        name = bare(value).strip()
        if name and name not in found:
            found.append(name)

    def walk(value: object, key: str | None = None) -> None:
        if key == "skill":
            add(value)
            return
        if key == "skills" and isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    add(item)
                else:
                    walk(item)
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, child_key)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)

    walk(op)
    return found
