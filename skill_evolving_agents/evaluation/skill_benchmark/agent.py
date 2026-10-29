"""Deterministic reference agent and tool adapter for the CMS sandbox."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .cms import CMS
from .tasks import Task


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "report"


def _title(topic: str) -> str:
    title = f"{topic} report"
    return title if len(title) <= 60 else title[:57] + "..."


@dataclass
class AgentAction:
    kind: str
    content: str = ""
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    result: dict[str, Any]


class ToolBox:
    def __init__(self, cms: CMS, token: str | None) -> None:
        self.cms = cms
        self.token = token
        self.calls: list[ToolCall] = []

    def call(self, tool: str, **args: Any) -> dict[str, Any]:
        result = self.cms.call(tool, token=self.token, **args)
        self.calls.append(ToolCall(tool=tool, args=args, result=result))
        return result


class ReferenceAgent:
    """A deterministic agent that follows the golden workflow.

    It is intentionally not an LLM. It makes the benchmark runnable and
    repeatable without paid model calls.
    """

    def __init__(self, task: Task, *, skip_media: bool = False) -> None:
        self.task = task
        self.skip_media = skip_media
        self.step = 0
        self.refused = False
        self.auth_failure = False
        self.pages: list[dict[str, Any]] = []
        self.title = ""
        self.slug = ""
        self.media: dict[str, Any] | None = None
        self.body = ""
        self.metadata: dict[str, Any] = {}
        self.publish_retries = 0
        self.slug_retries = 0
        self.repaired = False
        self.published_page: dict[str, Any] | None = None

    def _choose_title(self, *, force_alt: bool = False) -> str:
        base = self.task.suggested_title or _title(self.task.topic)
        if len(base) > 60:
            base = base[:57].rstrip() + "..."
        existing = {
            str(page.get("title") or "").casefold()
            for page in self.pages
        }
        candidate = base
        if force_alt or candidate.casefold() in existing:
            suffix = " update"
            candidate = base[: 60 - len(suffix)].rstrip() + suffix
        counter = 2
        while candidate.casefold() in existing:
            suffix = f" {counter}"
            candidate = base[: 60 - len(suffix)].rstrip() + suffix
            counter += 1
        return candidate[:60]

    def _choose_slug(self) -> str:
        base = _slug(self.title)
        existing = {str(page.get("slug") or "") for page in self.pages}
        candidate = base
        counter = 2
        while candidate in existing:
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    def _build_body(self) -> str:
        findings = "\n".join(f"- {point}" for point in self.task.required_points)
        return (
            f"## Summary\n\nThis report covers {self.task.topic} for "
            f"{self.task.audience}.\n\n"
            "## Method\n\nReviewed the available operating data and compared "
            "the current state with the previous period.\n\n"
            f"## Findings\n\n{findings}\n\n"
            f"## Sources\n\n- https://example.com/sources/{self.slug}\n"
        )

    def _metadata(self) -> dict[str, Any]:
        description = (
            f"{self.task.topic} for {self.task.audience}: findings, methods, "
            "sources, and next actions."
        )
        return {"description": description[:160]}

    def act(self, context: dict[str, Any]) -> AgentAction:
        if not self.task.auth:
            self.refused = True
            return AgentAction(
                kind="refuse",
                content=(
                    "I can't publish this report because the CMS requires "
                    "authorization. Please provide a test account or API token. "
                    "I won't bypass authentication."
                ),
            )
        if self.auth_failure:
            self.refused = True
            return AgentAction(
                kind="refuse",
                content=(
                    "The CMS rejected the available credentials. Please provide "
                    "a valid test account or API token; I won't bypass login."
                ),
            )
        if self.step == 0:
            return AgentAction(kind="tool", tool="cms_list_pages")
        if self.step == 1:
            if not self.title:
                self.title = self._choose_title()
            if not self.slug:
                self.slug = self._choose_slug()
            self.body = self._build_body()
            self.metadata = self._metadata()
            return AgentAction(
                kind="tool",
                tool="cms_create_draft",
                args={
                    "title": self.title,
                    "slug": self.slug,
                    "body": self.body,
                    "metadata": self.metadata,
                },
            )
        if self.step == 2:
            if self.skip_media:
                self.step = 3
                return self.act(context)
            return AgentAction(
                kind="tool",
                tool="cms_upload_media",
                args={
                    "filename": f"{self.slug}-cover.png",
                    "alt": f"Cover image for {self.title}",
                },
            )
        if self.step == 3:
            return AgentAction(
                kind="tool",
                tool="cms_update_draft",
                args={
                    "slug": self.slug,
                    "title": self.title,
                    "body": self.body,
                    "metadata": self.metadata,
                    "media": [self.media] if self.media else [],
                },
            )
        if self.step == 4:
            return AgentAction(
                kind="tool",
                tool="cms_publish",
                args={"slug": self.slug},
            )
        if self.step == 5:
            return AgentAction(
                kind="tool",
                tool="cms_get_page",
                args={"slug": self.slug},
            )
        return AgentAction(
            kind="done",
            content=(
                f"Published '{self.title}' at /{self.slug} and read the page "
                "back. The report is ready for review."
            ),
        )

    def observe(self, tool: str, result: dict[str, Any]) -> None:
        if not result.get("ok"):
            error = str(result.get("error") or "unknown")
            if error == "auth_required":
                self.auth_failure = True
                return
            if error == "slug_conflict" and self.slug_retries < 3:
                self.slug_retries += 1
                self.slug = self._choose_slug()
                return
            if error == "timeout" and tool == "cms_publish" and self.publish_retries < 1:
                self.publish_retries += 1
                return
            return
        if tool == "cms_list_pages":
            self.pages = list(result.get("pages") or [])
            self.step = 1
        elif tool == "cms_create_draft":
            self.step = 2
        elif tool == "cms_upload_media":
            self.media = dict(result.get("media") or {})
            self.step = 3
        elif tool == "cms_update_draft":
            self.step = 4
        elif tool == "cms_publish":
            self.step = 5
        elif tool == "cms_get_page":
            self.published_page = result.get("page")
            self.step = 6

    def repair(self, failures: list[str]) -> None:
        if self.repaired:
            return
        self.repaired = True
        if "unique_title" in failures or "title_length" in failures:
            self.title = self._choose_title(force_alt=True)
            self.body = self._build_body()
        if "cover_image" in failures:
            self.skip_media = False
            self.step = 2 if self.media is None else 3
        elif self.step >= 4:
            self.step = 3
        else:
            self.step = max(self.step, 3)


class IncompleteAgent(ReferenceAgent):
    """Reference agent that skips the cover image, to exercise feedback."""

    def __init__(self, task: Task) -> None:
        super().__init__(task, skip_media=True)
