"""The guardrails at each step of a turn, kept apart from the steps themselves.

`TurnGuard` holds the turn's `GuardrailConfig` (or None: no guardrails) and the
`GuardReport` it builds as a plain dict in the state, so it checkpoints like the rest.
"""

from dataclasses import dataclass
from typing import Any

from sec_agent.guardrails.answer import guard_answer
from sec_agent.guardrails.canary import leaks
from sec_agent.guardrails.config import GuardrailConfig
from sec_agent.guardrails.models import GuardReport
from sec_agent.guardrails.quarantine import quarantine
from sec_agent.guardrails.screen import screen_question
from sec_agent.llm.messages import Message

WITHHELD_QUESTION = "[question withheld: refused by the guardrails as an attack]"
"""What the conversation keeps of a refused question, so no later turn shows it the model."""

Report = dict[str, Any]


@dataclass(frozen=True)
class Screened:
    report: Report | None
    refused: bool


class TurnGuard:
    def __init__(self, config: GuardrailConfig | None) -> None:
        self._config = config

    @property
    def canary(self) -> str | None:
        return None if self._config is None else self._config.canary

    def screen(self, question: str) -> Screened:
        """The turn's first report, and whether the question is refused as an attack."""
        if self._config is None:
            return Screened(None, refused=False)
        if not self._config.screen_questions:
            return Screened(GuardReport().model_dump(), refused=False)
        screen = screen_question(question)
        report = GuardReport(question=screen.kind, rule=screen.rule).model_dump()
        return Screened(report, refused=screen.kind == "attack")

    def reply_leaks(self, message: Message) -> bool:
        """The canary anywhere in a model reply: its text, or any tool call's name or
        arguments. A reply may carry text and tool calls together, so both are read."""
        canary = self.canary
        if canary is None:
            return False
        parts = [message.get("content") or ""]
        for c in message.get("tool_calls") or []:
            parts += [c["function"]["name"], c["function"]["arguments"]]
        return any(leaks(canary, part) for part in parts)

    def draft_leaks(self, draft: str) -> bool:
        canary = self.canary
        return canary is not None and leaks(canary, draft)

    def tool_result(
        self, report: Report | None, name: str, content: str
    ) -> tuple[str, Report | None]:
        """The result as the model may read it: filing text quarantined."""
        if self._config is None or report is None or not self._config.quarantine_passages:
            return content, report
        out = quarantine(name, content)
        if not out.flagged:
            return content, report
        return out.content, {**report, "flagged_passages": report["flagged_passages"] + out.flagged}

    def answer(self, report: Report | None, text: str) -> tuple[str, Report | None]:
        """The text the user is shown: advice dropped, the disclaimer added (E9)."""
        if self._config is None or report is None:
            return text, report
        guard = guard_answer(
            text,
            canary=None,  # the draft was checked whole, before the faithfulness check
            advice_requested=report["question"] == "advice",
            filter_advice=self._config.filter_advice,
        )
        return guard.text, {**report, "advice_dropped": guard.advice_dropped}


def leaked(report: Report | None) -> Report:
    return {**(report or GuardReport().model_dump()), "canary_leaked": True}
