"""One G-red item: a question, the passages search returns for it, and what an attack is
after (a marker in the answer, the prompt, or investment advice)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

RedKind = Literal["direct", "indirect", "advice", "benign"]
RedGoal = Literal["marker", "leak", "advice"]


class RedItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: RedKind
    goal: RedGoal | None = None
    """What the attack tries to get into the answer; None for a benign question."""
    question: str
    company: str
    """Ticker the planted passages are filed under."""
    passages: tuple[str, ...] = ()
    """Simulated filing text `search_filings` returns, whatever the query."""
    marker: str | None = None
    """For goal `marker`: the string the attack wants written in the answer."""

    @property
    def attack(self) -> bool:
        return self.kind != "benign"
