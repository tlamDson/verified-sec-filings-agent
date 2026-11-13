"""The thumbs a simulated user gives, by criteria fixed before any answer is seen.

- Up: the answer finished (`answered`), the checker passed it untouched, and it carried at
  least one card or citation.
- Down: the turn hit the step limit or was blocked, or the checker trimmed the draft.
- None: degraded turns (expected when the quota is out, not a fault of the answer),
  errors, the daily limit, and answers with no evidence to judge.

Whether a rateable turn is rated at all is a seeded draw against the persona's
`rate_share`. These ratings only prove the feedback path works; they never measure quality.
"""

import random
from typing import Literal

from sec_agent.golden.ranking import seeded_key
from sec_agent.simusers.outcome import TurnOutcome

Rating = Literal["up", "down"]


def rating_for(outcome: TurnOutcome) -> Rating | None:
    if outcome.kind in ("step_limit", "blocked"):
        return "down"
    if outcome.kind != "answered":
        return None
    if outcome.verdict not in (None, "pass") or outcome.removed > 0:
        return "down"
    return "up" if outcome.verdict == "pass" and outcome.evidence > 0 else None


def wants_to_rate(seed: int, thread_id: str, question_index: int, rate_share: float) -> bool:
    """A draw of its own per turn, so one turn's outcome never shifts another's draw."""
    draw = random.Random(seeded_key(seed, "sim-rate", thread_id, question_index)).random()
    return draw < rate_share
