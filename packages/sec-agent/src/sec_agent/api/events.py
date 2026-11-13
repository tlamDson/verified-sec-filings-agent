"""The payloads of the events a turn is streamed as, in the order they are sent:

turn      the conversation, the user's cohort and today's usage
evidence  the cards and citations of tool results, as each step ends (zero or more)
answer    the checked text, how the turn ended, every card, citation and chart
error     instead of `answer`, when the turn could not finish
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.agent.answer import Reason, Status
from sec_agent.api.cards import Card, Chart, Citation
from sec_agent.api.identity import Cohort
from sec_agent.faithfulness.models import FaithfulnessReport, Verdict

_FROZEN = ConfigDict(frozen=True, extra="forbid")

ErrorCode = Literal["conversation_conflict", "invalid_request", "internal_error"]


class Usage(BaseModel):
    """Questions the user asked today (UTC) against the daily limit."""

    model_config = _FROZEN

    used: int
    limit: int
    resets_at: dt.datetime


class TurnStarted(BaseModel):
    model_config = _FROZEN

    thread_id: str
    cohort: Cohort
    usage: Usage


class CheckSummary(BaseModel):
    """What the faithfulness checker found in the model's draft."""

    model_config = _FROZEN

    verdict: Verdict
    figures: int
    """Figures and dates the draft stated."""
    traced: int
    """How many of them traced to a tool result or a cited passage."""
    removed: int
    """Sentences of the draft the user is not shown."""

    @classmethod
    def of(cls, report: FaithfulnessReport) -> "CheckSummary":
        return cls(
            verdict=report.verdict,
            figures=report.mentions,
            traced=report.traced,
            removed=sum(not sentence.kept for sentence in report.sentences),
        )


class AnswerPayload(BaseModel):
    model_config = _FROZEN

    thread_id: str
    turn: int
    status: Status
    reason: Reason | None
    degraded: bool
    """No model answered: `text` is a fixed notice and the cards stand on their own."""
    text: str
    cards: tuple[Card, ...]
    citations: tuple[Citation, ...]
    charts: tuple[Chart, ...]
    check: CheckSummary | None


class ErrorPayload(BaseModel):
    model_config = _FROZEN

    code: ErrorCode
    message: str
