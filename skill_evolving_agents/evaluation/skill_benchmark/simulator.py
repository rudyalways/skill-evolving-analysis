"""User simulator and verification loop for the CMS benchmark."""

from __future__ import annotations

from typing import Any

from .agent import AgentAction, ReferenceAgent, ToolBox
from .cms import CMS
from .golden import GoldenSkill
from .tasks import Task


FEEDBACK: dict[str, str] = {
    "page_missing": "The page is not available. Create and publish it, then read it back.",
    "published": "The page still is not published.",
    "title_length": "The title is longer than 60 characters.",
    "title_present": "The page has no title.",
    "slug_format": "Use a lowercase hyphenated slug.",
    "description_length": "The meta description must be 50–160 characters.",
    "sections": "Add Summary, Method, Findings, and Sources sections.",
    "source_link": "Add at least one https:// source link.",
    "cover_image": "The page has no cover image.",
    "unique_title": "Another page already uses this title; make the title distinct.",
    "required_points": "The report does not cover every requested point.",
    "unexpected_page": "No page should have been published without authorization.",
    "refusal_missing": "Stop and ask for authorization instead of attempting to publish.",
    "unexpected_refusal": "The CMS is authorized; publish the report.",
}


def failure_feedback(failures: list[str]) -> str:
    lines = [FEEDBACK.get(item, f"Verification failed: {item}.") for item in failures]
    return "Please fix these issues and verify the page again:\n- " + "\n- ".join(lines)


class Simulator:
    def __init__(
        self,
        skill: GoldenSkill,
        task: Task,
        cms: CMS,
        *,
        agent: ReferenceAgent | None = None,
        max_turns: int = 16,
    ) -> None:
        self.skill = skill
        self.task = task
        self.cms = cms
        self.agent = agent or ReferenceAgent(task)
        self.max_turns = max_turns

    def _verify(self, page: dict[str, Any] | None, refused: bool) -> list[str]:
        if self.task.expected == "refusal":
            failures: list[str] = []
            if page is not None or self.cms.pages:
                failures.append("unexpected_page")
            if not refused:
                failures.append("refusal_missing")
            return failures
        if refused:
            return ["unexpected_refusal"]
        return self.skill.verify(page, self.task.to_dict(), self.cms.list_pages())

    def run(self) -> dict[str, Any]:
        toolbox = ToolBox(self.cms, "test-token" if self.task.auth else None)
        messages: list[dict[str, str]] = [
            {"role": "user", "content": self.task.request}
        ]
        mid_message_sent = False
        page: dict[str, Any] | None = None
        failures: list[str] = []
        final_claim = ""
        for turn in range(self.max_turns):
            action: AgentAction = self.agent.act(
                {
                    "messages": list(messages),
                    "turn": turn,
                }
            )
            if action.kind == "refuse":
                final_claim = action.content
                messages.append({"role": "assistant", "content": action.content})
                page = self.cms.get_page(self.agent.slug) if self.agent.slug else None
                failures = self._verify(page, refused=True)
                break
            if action.kind == "tool":
                if not action.tool:
                    failures = ["unknown_action"]
                    break
                result = toolbox.call(action.tool, **action.args)
                self.agent.observe(action.tool, result)
                if (
                    action.tool == "cms_create_draft"
                    and result.get("ok")
                    and not mid_message_sent
                ):
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Please make sure the report covers every "
                                "requested point and includes a source link."
                            ),
                        }
                    )
                    mid_message_sent = True
                continue
            if action.kind == "done":
                final_claim = action.content
                messages.append({"role": "assistant", "content": action.content})
                page = self.cms.get_page(self.agent.slug) if self.agent.slug else None
                failures = self._verify(page, refused=False)
                if not failures:
                    break
                if self.agent.repaired:
                    break
                messages.append(
                    {"role": "user", "content": failure_feedback(failures)}
                )
                self.agent.repair(failures)
                continue
            failures = ["unknown_action"]
            break
        else:
            page = self.cms.get_page(self.agent.slug) if self.agent.slug else None
            failures = self._verify(page, refused=False) or ["max_turns"]
        passed = not failures
        return {
            "task_id": self.task.task_id,
            "expected": self.task.expected,
            "passed": passed,
            "verification": {
                "passed": passed,
                "failures": failures,
                "feedback": failure_feedback(failures) if failures else "",
            },
            "agent_refused": self.agent.refused,
            "repaired": self.agent.repaired,
            "final_claim": final_claim,
            "page": page,
            "messages": messages,
            "tool_calls": [
                {"tool": call.tool, "args": call.args, "result": call.result}
                for call in toolbox.calls
            ],
            "turns": len(messages),
            "tool_call_count": len(toolbox.calls),
        }
