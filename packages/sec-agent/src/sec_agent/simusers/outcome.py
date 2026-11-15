"""What one simulated turn came to, as the driver saw it through the web app."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.faithfulness.models import Verdict

OutcomeKind = Literal["answered", "step_limit", "degraded", "blocked", "error", "limited"]
"""The answer's status, or `error` (no answer event, or a refusal other than the daily
limit), or `limited` (the daily limit refused the question)."""
OUTCOME_KINDS: tuple[OutcomeKind, ...] = (
    "answered",
    "step_limit",
    "degraded",
    "blocked",
    "error",
    "limited",
)


class TurnOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: OutcomeKind
    turn: int | None = Field(default=None, ge=1)
    """The turn number the API gave; None when no answer came back."""
    verdict: Verdict | None = None
    """The faithfulness checker's verdict; None when the checker did not run."""
    removed: int = Field(default=0, ge=0)
    """Sentences of the draft the checker took out."""
    evidence: int = Field(default=0, ge=0)
    """Cards and citations the answer carried."""
    seconds: float = Field(ge=0)
    """From sending the question to the end of the answer, on the driver's clock."""
