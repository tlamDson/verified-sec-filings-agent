"""How many questions simulated users may ask in a day: a share of the LLM quota.

Simulated traffic spends the same free quota as real users, so it takes at most half of a
day's model calls (`MAX_SHARE`). Questions per day = calls per day x share / calls per
question, rounded down; the share is read as a decimal so 0.29 never becomes 0.2899...
"""

from fractions import Fraction

from pydantic import BaseModel, ConfigDict, Field

MAX_SHARE = 0.5
CALLS_PER_QUESTION = 4
"""The plan's planning estimate of model calls per question, not a measurement."""


class QuotaBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    llm_calls_per_day: int = Field(ge=1)
    """The production quota of model calls per day, across providers."""
    calls_per_question: int = Field(default=CALLS_PER_QUESTION, ge=1)
    share: float = Field(default=MAX_SHARE, gt=0, le=MAX_SHARE)

    @property
    def questions_per_day(self) -> int:
        calls = self.llm_calls_per_day * Fraction(str(self.share))
        return int(calls // self.calls_per_question)
