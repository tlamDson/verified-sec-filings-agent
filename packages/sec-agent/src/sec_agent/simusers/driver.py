"""Play one day's plan: each session signs in its account, asks its questions in order and
rates the turns the criteria allow.

The plan already fits the budget, so the driver never sends more questions than planned.
A session ends early at the daily limit or on an error (the conversation may be broken),
and an account that cannot sign in is counted and skipped. Waiting for a session's start
is the caller's (`wait_until`), so a run can be spread over the night or played at once.
"""

import datetime as dt
from collections import Counter
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from sec_agent.simusers.feedback import Rating, rating_for, wants_to_rate
from sec_agent.simusers.outcome import OUTCOME_KINDS, OutcomeKind, TurnOutcome
from sec_agent.simusers.personas import PERSONAS
from sec_agent.simusers.plan import DayPlan, SessionPlan
from sec_agent.simusers.roster import SimAccount
from sec_agent.simusers.web_client import SimSignInError


class SimSession(Protocol):
    def ask(self, thread_id: str, question: str, asked_on: dt.date) -> TurnOutcome: ...

    def rate(self, thread_id: str, turn: int, rating: Rating) -> bool: ...


@runtime_checkable
class _Closeable(Protocol):
    def close(self) -> None: ...


class DriverReport(BaseModel):
    """What one run did. Counts of simulated traffic only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: dt.date
    seed: int
    sessions_planned: int
    sessions_run: int
    sign_in_failures: int
    questions_planned: int
    questions_sent: int
    outcomes: dict[OutcomeKind, int]
    ratings: dict[Rating, int]
    """Ratings the API kept."""
    ratings_refused: int
    turn_seconds: tuple[float, ...]
    """Seconds of every turn that came back with an answer."""


def run_plan(
    plan: DayPlan,
    open_session: Callable[[SimAccount], SimSession],
    *,
    wait_until: Callable[[int], None],
) -> DriverReport:
    outcomes = Counter[OutcomeKind]()
    ratings = Counter[Rating]()
    refused = runs = failures = 0
    seconds: list[float] = []
    for planned in plan.sessions:
        wait_until(planned.start_second)
        try:
            session = open_session(planned.account)
        except SimSignInError:
            failures += 1
            continue
        runs += 1
        try:
            for outcome, rated in _play(plan, planned, session):
                outcomes[outcome.kind] += 1
                if outcome.turn is not None:
                    seconds.append(outcome.seconds)
                if rated is not None:
                    kept, rating = rated
                    ratings[rating] += kept
                    refused += not kept
        finally:
            if isinstance(session, _Closeable):
                session.close()
    return DriverReport(
        day=plan.day,
        seed=plan.seed,
        sessions_planned=len(plan.sessions),
        sessions_run=runs,
        sign_in_failures=failures,
        questions_planned=plan.questions,
        questions_sent=sum(outcomes.values()),
        outcomes={kind: outcomes[kind] for kind in OUTCOME_KINDS},
        ratings={"up": ratings["up"], "down": ratings["down"]},
        ratings_refused=refused,
        turn_seconds=tuple(seconds),
    )


def _play(
    plan: DayPlan, planned: SessionPlan, session: SimSession
) -> list[tuple[TurnOutcome, tuple[bool, Rating] | None]]:
    """Each turn's outcome and, when it was rated, whether the API kept the rating."""
    share = PERSONAS[planned.account.persona].rate_share
    played: list[tuple[TurnOutcome, tuple[bool, Rating] | None]] = []
    for index, question in enumerate(planned.questions):
        outcome = session.ask(planned.thread_id, question, plan.day)
        rating = rating_for(outcome)
        rated: tuple[bool, Rating] | None = None
        if (
            rating is not None
            and outcome.turn is not None
            and wants_to_rate(plan.seed, planned.thread_id, index, share)
        ):
            rated = (session.rate(planned.thread_id, outcome.turn, rating), rating)
        played.append((outcome, rated))
        if outcome.kind in ("limited", "error"):
            break
    return played
