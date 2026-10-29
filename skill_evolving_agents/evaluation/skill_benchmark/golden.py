"""Load a golden skill bundle and evaluate its verification section."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class GoldenSkillError(ValueError):
    pass


def _field(page: dict[str, Any], field: str) -> Any:
    value: Any = page
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


@dataclass(frozen=True)
class GoldenSkill:
    root: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, root: Path | str) -> "GoldenSkill":
        root = Path(root)
        path = root / "skill.json" if root.is_dir() else root
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError as error:
            raise GoldenSkillError(f"missing skill bundle: {path}") from error
        except json.JSONDecodeError as error:
            raise GoldenSkillError(f"invalid skill JSON: {path}: {error}") from error
        if not isinstance(data, dict):
            raise GoldenSkillError("skill.json must be an object")
        for key in ("skill_id", "visible", "workflow", "verification", "source", "review"):
            if key not in data:
                raise GoldenSkillError(f"skill.json missing {key!r}")
        if not isinstance(data["verification"], list) or not data["verification"]:
            raise GoldenSkillError("verification must be a non-empty list")
        return cls(root=root, data=data)

    @property
    def skill_id(self) -> str:
        return str(self.data["skill_id"])

    @property
    def title(self) -> str:
        return str(self.data.get("title") or self.skill_id)

    @property
    def visible(self) -> dict[str, Any]:
        return dict(self.data["visible"])

    @property
    def workflow(self) -> list[str]:
        return [str(value) for value in self.data["workflow"]]

    @property
    def verification(self) -> list[dict[str, Any]]:
        return [dict(value) for value in self.data["verification"]]

    @property
    def source(self) -> dict[str, Any]:
        return dict(self.data["source"])

    @property
    def review(self) -> dict[str, Any]:
        return dict(self.data["review"])

    def verify(
        self,
        page: dict[str, Any] | None,
        task: dict[str, Any],
        pages: list[dict[str, Any]],
    ) -> list[str]:
        if page is None:
            return ["page_missing"]
        failures: list[str] = []
        for check in self.verification:
            kind = str(check.get("type") or "")
            check_id = str(check.get("id") or kind or "check")
            field = str(check.get("field") or "")
            value = _field(page, field)
            if kind == "field_equals":
                if value != check.get("value"):
                    failures.append(check_id)
            elif kind == "max_length":
                if not isinstance(value, str) or len(value) > int(check["max"]):
                    failures.append(check_id)
            elif kind == "non_empty":
                if not isinstance(value, str) or not value.strip():
                    failures.append(check_id)
            elif kind == "regex":
                if not isinstance(value, str) or re.fullmatch(str(check["pattern"]), value) is None:
                    failures.append(check_id)
            elif kind == "length_between":
                if not isinstance(value, str) or not (
                    int(check["min"]) <= len(value) <= int(check["max"])
                ):
                    failures.append(check_id)
            elif kind == "contains":
                needle = str(check.get("value") or "")
                if not isinstance(value, str) or needle not in value:
                    failures.append(check_id)
            elif kind == "contains_all":
                values = [str(item) for item in check.get("values") or []]
                text = str(value or "")
                if any(item not in text for item in values):
                    failures.append(check_id)
            elif kind == "media_present":
                media = page.get("media") or []
                if not media:
                    failures.append(check_id)
            elif kind == "unique_field":
                if not isinstance(value, str):
                    failures.append(check_id)
                else:
                    matches = [
                        row for row in pages
                        if str(_field(row, field) or "").casefold() == value.casefold()
                    ]
                    if len(matches) > 1:
                        failures.append(check_id)
            elif kind == "contains_all_task_points":
                body = str(page.get("body") or "")
                missing = [
                    str(point) for point in task.get("required_points") or []
                    if str(point).casefold() not in body.casefold()
                ]
                if missing:
                    failures.append(check_id)
            else:
                raise GoldenSkillError(f"unknown verification type: {kind}")
        return failures
