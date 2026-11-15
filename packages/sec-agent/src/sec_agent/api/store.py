"""What the API keeps: questions per user per day, the turns asked, and their feedback.

`ApiStore` is what the routes need; `MemoryApiStore` is the one-process implementation
(tests, a single local replica) and `store_postgres.PostgresApiStore` the shared one.
Every record carries its cohort, and `cohort_counts` reports `real` and `simulated`
side by side: a simulated row is never counted as a real user (U1).
"""

import datetime as dt
import threading
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.api.identity import COHORTS, Cohort, Identity

Rating = Literal["up", "down"]
_FROZEN = ConfigDict(frozen=True, extra="forbid")


class TurnRecord(BaseModel):
    """One turn a user asked, written when its answer was sent."""

    model_config = _FROZEN

    user_id: str
    cohort: Cohort
    thread_id: str
    """The conversation id the user's browser chose."""
    turn: int = Field(ge=1)
    asked_at: dt.datetime
    status: str
    """How the agent's turn ended: answered, step_limit, degraded or blocked."""
    degraded: bool
    """No model answered: the user was shown tool results without written explanation."""


class Feedback(BaseModel):
    model_config = _FROZEN

    user_id: str
    cohort: Cohort
    thread_id: str
    turn: int = Field(ge=1)
    rating: Rating
    at: dt.datetime


class CohortCounts(BaseModel):
    """Activity of one cohort over a span of UTC days. Counts, straight from the rows."""

    model_config = _FROZEN

    users: int
    conversations: int
    turns: int
    degraded_turns: int
    thumbs_up: int
    thumbs_down: int


class ApiStore(Protocol):
    def charge_question(self, identity: Identity, day: dt.date, limit: int) -> int | None:
        """Count one question of the user on `day` (UTC) and return the new count, or
        None, counting nothing, when the day already holds `limit` questions."""
        ...

    def questions_used(self, user_id: str, day: dt.date) -> int: ...

    def record_turn(self, record: TurnRecord) -> None:
        """Keep the turn; recording the same turn again replaces it."""
        ...

    def save_feedback(self, feedback: Feedback) -> bool:
        """Keep the user's rating of a turn they asked, replacing an earlier one. False,
        keeping nothing, when that user has no such turn."""
        ...

    def cohort_counts(self, first_day: dt.date, last_day: dt.date) -> dict[Cohort, CohortCounts]:
        """Counts of each cohort for turns asked from `first_day` to `last_day` (UTC,
        inclusive), and the ratings of those turns."""
        ...


class MemoryApiStore:
    """One process only; calls from several threads take turns."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._questions: dict[tuple[str, dt.date], int] = {}
        self._turns: dict[tuple[str, str, int], TurnRecord] = {}
        self._feedback: dict[tuple[str, str, int], Feedback] = {}

    def charge_question(self, identity: Identity, day: dt.date, limit: int) -> int | None:
        key = (identity.user_id, day)
        with self._lock:
            used = self._questions.get(key, 0)
            if used >= limit:
                return None
            self._questions[key] = used + 1
            return used + 1

    def questions_used(self, user_id: str, day: dt.date) -> int:
        with self._lock:
            return self._questions.get((user_id, day), 0)

    def record_turn(self, record: TurnRecord) -> None:
        with self._lock:
            self._turns[(record.user_id, record.thread_id, record.turn)] = record

    def save_feedback(self, feedback: Feedback) -> bool:
        key = (feedback.user_id, feedback.thread_id, feedback.turn)
        with self._lock:
            if key not in self._turns:
                return False
            self._feedback[key] = feedback
            return True

    def cohort_counts(self, first_day: dt.date, last_day: dt.date) -> dict[Cohort, CohortCounts]:
        with self._lock:
            turns = {
                key: turn
                for key, turn in self._turns.items()
                if first_day <= turn.asked_at.astimezone(dt.UTC).date() <= last_day
            }
            ratings: dict[tuple[str, str, int], Rating] = {
                key: self._feedback[key].rating for key in turns if key in self._feedback
            }
        return {cohort: _counts(cohort, turns, ratings) for cohort in COHORTS}


def _counts(
    cohort: Cohort,
    turns: dict[tuple[str, str, int], TurnRecord],
    ratings: dict[tuple[str, str, int], Rating],
) -> CohortCounts:
    mine = {key: turn for key, turn in turns.items() if turn.cohort == cohort}
    rated = [ratings[key] for key in mine if key in ratings]
    return CohortCounts(
        users=len({turn.user_id for turn in mine.values()}),
        conversations=len({(turn.user_id, turn.thread_id) for turn in mine.values()}),
        turns=len(mine),
        degraded_turns=sum(turn.degraded for turn in mine.values()),
        thumbs_up=rated.count("up"),
        thumbs_down=rated.count("down"),
    )
