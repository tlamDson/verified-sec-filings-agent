"""guard_answer: the last look at what the user will be shown.

The canary in the text ends the turn: the prompt leaked or an injected order was followed.
Sentences that give investment advice or forecast the stock are dropped, and the
disclaimer is added when advice was asked for or dropped (E9): the historical figures
stay. A label whose call is on the next line drops both lines. An answer that was
nothing but advice becomes the declined notice.
"""

from dataclasses import dataclass
from typing import Literal

from sec_agent.faithfulness.sentences import split_sentences
from sec_agent.guardrails.advice import ADVICE_STATEMENT, advice_rule
from sec_agent.guardrails.canary import leaks
from sec_agent.guardrails.notices import (
    ADVICE_DECLINED_TEXT,
    ADVICE_DISCLAIMER,
    CANARY_BLOCKED_TEXT,
)

_DISCLAIMED = "not investment advice"
_LABELLED_CALL = dict(ADVICE_STATEMENT)["labelled_call"]


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
    pieces = [text[s.start : s.end] for s in split_sentences(text)]
    advice = [advice_rule(piece) is not None for piece in pieces]
    for index in range(len(pieces) - 1):
        if _call_across(pieces[index], pieces[index + 1]):
            advice[index] = advice[index + 1] = True
    kept = [piece for piece, gives in zip(pieces, advice, strict=True) if not gives]
    dropped = len(pieces) - len(kept)
    shown = "".join(kept).rstrip() if dropped else text
    if dropped and not shown.strip():
        return AnswerGuard(ADVICE_DECLINED_TEXT, "trimmed", None, dropped)
    if (dropped or advice_requested) and _DISCLAIMED not in shown.lower():
        shown = f"{shown.rstrip()}\n\n{ADVICE_DISCLAIMER}"
    return AnswerGuard(shown, "trimmed" if dropped else "pass", None, dropped)


def _call_across(first: str, second: str) -> bool:
    """A label ends `first` and its call starts `second` ("**Recommendation:**" then
    "Overweight" on the next line): the split at the line hid the call from both."""
    joined = first + second
    return any(call.start() < len(first) < call.end() for call in _LABELLED_CALL.finditer(joined))
