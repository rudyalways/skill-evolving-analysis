"""Generate related task cards from a golden skill's task contract."""

from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any


SCENARIOS: list[dict[str, Any]] = [
    {
        "topic": "Quarterly reliability review",
        "audience": "engineering leadership",
        "points": ["error budget burn", "incident count", "top remediation"],
    },
    {
        "topic": "Customer onboarding audit",
        "audience": "customer success",
        "points": ["drop-off step", "time to first value", "top fix"],
    },
    {
        "topic": "Search performance report",
        "audience": "content team",
        "points": ["indexed pages", "top query gap", "next content action"],
    },
    {
        "topic": "Support deflection analysis",
        "audience": "support operations",
        "points": ["deflection rate", "top contact reason", "knowledge gap"],
    },
    {
        "topic": "API latency review",
        "audience": "platform engineers",
        "points": ["p95 latency", "slowest endpoint", "mitigation"],
    },
    {
        "topic": "Data quality assessment",
        "audience": "analytics team",
        "points": ["null rate", "duplicate rate", "owner action"],
    },
    {
        "topic": "Accessibility audit",
        "audience": "product design",
        "points": ["contrast issue", "keyboard trap", "remediation"],
    },
    {
        "topic": "Release readiness report",
        "audience": "release managers",
        "points": ["open blockers", "test coverage", "go or no-go"],
    },
    {
        "topic": "Incident retrospective",
        "audience": "site reliability",
        "points": ["root cause", "detection gap", "prevention action"],
    },
    {
        "topic": "Cost efficiency review",
        "audience": "finance and platform",
        "points": ["largest cost driver", "idle capacity", "savings action"],
    },
]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "report"


def _base_title(topic: str) -> str:
    title = f"{topic} report"
    return title if len(title) <= 60 else title[:57] + "..."


@dataclass
class Task:
    task_id: str
    topic: str
    audience: str
    required_points: list[str]
    request: str
    expected: str = "published"
    auth: bool = True
    suggested_title: str | None = None
    seed_slug: str | None = None
    seed_title: str | None = None
    seed_body: str = ""
    faults: list[dict[str, str]] = field(default_factory=list)
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        allowed = {
            "task_id",
            "topic",
            "audience",
            "required_points",
            "request",
            "expected",
            "auth",
            "suggested_title",
            "seed_slug",
            "seed_title",
            "seed_body",
            "faults",
            "seed",
        }
        values = {key: data[key] for key in allowed if key in data}
        return cls(**values)


def _variant(index: int, scenario: dict[str, Any]) -> str:
    cycle = [
        "normal",
        "normal",
        "long_title",
        "auth_missing",
        "tool_timeout",
        "slug_conflict",
        "duplicate_title",
        "normal",
        "tool_timeout",
        "normal",
    ]
    return cycle[index % len(cycle)]


def generate_tasks(count: int = 10) -> list[Task]:
    tasks: list[Task] = []
    for index in range(count):
        scenario = SCENARIOS[index % len(SCENARIOS)]
        topic = str(scenario["topic"])
        audience = str(scenario["audience"])
        points = [str(value) for value in scenario["points"]]
        variant = _variant(index, scenario)
        title = _base_title(topic)
        slug = _slug(title)
        expected = "published"
        auth = True
        suggested_title: str | None = title
        seed_slug: str | None = None
        seed_title: str | None = None
        faults: list[dict[str, str]] = []
        extra = ""
        if variant == "long_title":
            suggested_title = (
                f"{topic} report for {audience} with findings, methods, "
                "sources, and next actions"
            )
            extra = "The working title is longer than the CMS limit; keep the page title within the limit."
        elif variant == "auth_missing":
            expected = "refusal"
            auth = False
            extra = "Use the CMS access available in this environment."
        elif variant == "tool_timeout":
            faults = [{"tool": "cms_publish", "code": "timeout"}]
            extra = "The CMS may be intermittent; recover if a call times out."
        elif variant == "slug_conflict":
            seed_slug = slug
            seed_title = f"Existing {title}"
            extra = "Avoid overwriting an existing page."
        elif variant == "duplicate_title":
            seed_slug = f"{slug}-existing"
            seed_title = title
            extra = "Avoid duplicating an existing page title."
        request = (
            f"Publish a report about {topic} for {audience}. "
            f"Cover these points: {', '.join(points)}. "
            "Include a source link and a cover image. "
            "Use the report-publishing skill. Do not invent sources. "
            f"{extra}"
        ).strip()
        tasks.append(
            Task(
                task_id=f"report-publishing-{index + 1:03d}",
                topic=topic,
                audience=audience,
                required_points=points,
                request=request,
                expected=expected,
                auth=auth,
                suggested_title=suggested_title,
                seed_slug=seed_slug,
                seed_title=seed_title,
                seed_body=(
                    f"<h2>Existing page</h2><p>{topic} archive.</p>"
                    if seed_title
                    else ""
                ),
                faults=faults,
                seed=index + 1,
            )
        )
    return tasks


def load_task_cards(root: Path | str, count: int | None = None) -> list[Task]:
    """Load frozen task cards from a skill bundle, or generate defaults."""
    path = Path(root) / "evals" / "tasks.json"
    if not path.exists():
        tasks = generate_tasks(count or 10)
        return tasks[:count] if count is not None else tasks
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list")
    tasks = [Task.from_dict(row) for row in data if isinstance(row, dict)]
    return tasks[:count] if count is not None else tasks
