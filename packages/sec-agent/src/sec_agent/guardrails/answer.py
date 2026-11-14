"""guard_answer: the last look at what the user will be shown.

The canary in the text ends the turn: the prompt leaked or an injected order was followed.
Sentences that give investment advice or forecast the stock are dropped, and the
disclaimer is added when advice was asked for or dropped (E9): the historical figures
stay. An answer that was nothing but advice becomes the declined notice.
"""

from dataclasses import dataclass
from typing import Literal

from sec_agent.faithfulness.sentences import split_sentences
from sec_agent.guardrails.advice import advice_rule
from sec_agent.guardrails.canary import leaks
from sec_agent.guardrails.notices import (
    ADVICE_DECLINED_TEXT,
    ADVICE_DISCLAIMER,
    CANARY_BLOCKED_TEXT,
)

_DISCLAIMED = "not investment advice"


@dataclass(frozen=True)
class AnswerGuard:
    text: str
    verdict: Literal["pass", "trimmed", "blocked"]
    reason: Literal["canary_leak"] | None
    advice_dropped: int


def guard_answer(
    text: str, *, canary: str | None, advice_requested: bool, filter_advice: bool = True
) -> AnswerGuard:
    if canary is not None and leaks(canary, text):
        return AnswerGuard(CANARY_BLOCKED_TEXT, "blocked", "canary_leak", 0)
    if not filter_advice:
        return AnswerGuard(text, "pass", None, 0)
    kept: list[str] = []
    dropped = 0
    for sentence in split_sentences(text):
        piece = text[sentence.start : sentence.end]
        if advice_rule(piece) is None:
            kept.append(piece)
        else:
            dropped += 1
    shown = "".join(kept).rstrip() if dropped else text
    if dropped and not shown.strip():
        return AnswerGuard(ADVICE_DECLINED_TEXT, "trimmed", None, dropped)
    if (dropped or advice_requested) and _DISCLAIMED not in shown.lower():
        shown = f"{shown.rstrip()}\n\n{ADVICE_DISCLAIMER}"
    return AnswerGuard(shown, "trimmed" if dropped else "pass", None, dropped)
