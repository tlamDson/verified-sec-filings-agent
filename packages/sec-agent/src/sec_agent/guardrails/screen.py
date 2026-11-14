"""screen_question: is the question a direct attack, a request for advice, or neither?

An attack is refused before any model call. Advice is answered with historical figures
and the disclaimer (E9), so a question marked advice by mistake costs one extra line.
"""

from dataclasses import dataclass

from sec_agent.guardrails.models import QuestionKind
from sec_agent.guardrails.patterns import ADVICE_REQUEST, ATTACK, first_match


@dataclass(frozen=True)
class QuestionScreen:
    kind: QuestionKind
    rule: str | None


def screen_question(question: str) -> QuestionScreen:
    if rule := first_match(question, ATTACK):
        return QuestionScreen("attack", rule)
    if rule := first_match(question, ADVICE_REQUEST):
        return QuestionScreen("advice", rule)
    return QuestionScreen("ok", None)
