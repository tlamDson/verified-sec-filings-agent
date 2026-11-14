"""What the guardrails did in one turn, kept with the `Answer`."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

QuestionKind = Literal["ok", "attack", "advice"]


class GuardReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question: QuestionKind | None = None
    """The screen's verdict; None when screening is off."""
    rule: str | None = None
    """The pattern that decided `question`, for an attack or advice."""
    flagged_passages: int = 0
    """Sentences of filing text replaced by the quarantine mark in this turn."""
    advice_dropped: int = 0
    """Sentences of the answer dropped as investment advice."""
    canary_leaked: bool = False
