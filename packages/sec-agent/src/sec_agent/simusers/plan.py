"""One day of simulated sessions, fixed by the seed and the day.

Each account starts 0 to `max_sessions` sessions of its persona; a session is one opening
question and 1 to 3 different follow-ups, about a company drawn from the ones given and a
fiscal year one to three years before the day. Sessions are then taken in a seeded order
while the day's budget and each account's per-user limit allow; the one that would pass a
limit is cut short. Kept sessions start at seeded seconds inside the window, in order.
"""

import datetime as dt
import random
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.golden.ranking import seeded_key
from sec_agent.simusers.budget import QuotaBudget
from sec_agent.simusers.personas import PERSONAS
from sec_agent.simusers.roster import SimAccount

_FROZEN = ConfigDict(frozen=True, extra="forbid")
MAX_FOLLOW_UPS = 3


class SessionPlan(BaseModel):
    model_config = _FROZEN

    account: SimAccount
    thread_id: str
    start_second: int = Field(ge=0)
    """Seconds after the run starts."""
    questions: tuple[str, ...] = Field(min_length=1)


class DayPlan(BaseModel):
    model_config = _FROZEN

    day: dt.date
    seed: int
    budget_questions: int
    sessions: tuple[SessionPlan, ...]

    @property
    def questions(self) -> int:
        return sum(len(s.questions) for s in self.sessions)


def plan_day(
    accounts: Sequence[SimAccount],
    companies: Sequence[str],
    *,
    day: dt.date,
    seed: int,
    budget: QuotaBudget,
    per_user_limit: int,
    window_seconds: int,
) -> DayPlan:
    if not companies:
        raise ValueError("simulated users need at least one company to ask about")
    if window_seconds < 1:
        raise ValueError("the window must last at least one second")
    rng = random.Random(seeded_key(seed, "sim-day", day.isoformat()))
    candidates = [
        _session(rng, account, index, companies, day, window_seconds)
        for account in accounts
        for index in range(1, rng.randint(0, PERSONAS[account.persona].max_sessions) + 1)
    ]
    rng.shuffle(candidates)
    left = budget.questions_per_day
    asked = Counter[int]()
    kept: list[SessionPlan] = []
    for session in candidates:
        room = min(left, per_user_limit - asked[session.account.number])
        if room <= 0:
            continue
        questions = session.questions[:room]
        kept.append(session.model_copy(update={"questions": questions}))
        left -= len(questions)
        asked[session.account.number] += len(questions)
    kept.sort(key=lambda s: (s.start_second, s.thread_id))
    return DayPlan(
        day=day, seed=seed, budget_questions=budget.questions_per_day, sessions=tuple(kept)
    )


def _session(
    rng: random.Random,
    account: SimAccount,
    index: int,
    companies: Sequence[str],
    day: dt.date,
    window_seconds: int,
) -> SessionPlan:
    persona = PERSONAS[account.persona]
    company = rng.choice(companies)
    others = [c for c in companies if c != company]
    fill = {
        "company": company,
        "peer": rng.choice(others) if others else company,
        "year": str(day.year - rng.randint(1, 3)),
    }
    opener = rng.choice(persona.openers)
    follow_ups = rng.sample(persona.follow_ups, rng.randint(1, MAX_FOLLOW_UPS))
    return SessionPlan(
        account=account,
        thread_id=f"sim-{day:%Y%m%d}-{account.number:02d}-{index}",
        start_second=rng.randrange(window_seconds),
        questions=tuple(t.format(**fill) for t in (opener, *follow_ups)),
    )
