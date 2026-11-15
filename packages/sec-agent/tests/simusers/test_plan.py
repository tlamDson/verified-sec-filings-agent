"""One day of simulated sessions: seeded, inside the budget and the per-user limit."""

import datetime as dt
import re
from collections import Counter

from sec_agent.api.app import THREAD_ID_PATTERN
from sec_agent.simusers.budget import QuotaBudget
from sec_agent.simusers.plan import DayPlan, plan_day
from sec_agent.simusers.roster import roster

DAY = dt.date(2026, 11, 13)
COMPANIES = ("AAPL", "MSFT", "NVDA", "AMZN", "ABT")
WINDOW = 7 * 3600


def _plan(*, seed: int = 3, calls: int = 10_000, limit: int = 20, day: dt.date = DAY) -> DayPlan:
    return plan_day(
        roster(seed=seed),
        COMPANIES,
        day=day,
        seed=seed,
        budget=QuotaBudget(llm_calls_per_day=calls),
        per_user_limit=limit,
        window_seconds=WINDOW,
    )


def test_the_same_seed_and_day_give_the_same_plan() -> None:
    assert _plan() == _plan()
    assert _plan() != _plan(seed=4)
    assert _plan() != _plan(day=DAY + dt.timedelta(days=1))


def test_a_session_is_an_opening_question_and_one_to_three_follow_ups() -> None:
    plan = _plan()
    assert plan.sessions
    for session in plan.sessions:
        assert 2 <= len(session.questions) <= 4
        assert len(set(session.questions)) == len(session.questions)
        assert all("{" not in q for q in session.questions)


def test_the_plan_never_asks_more_than_the_budget() -> None:
    plan = _plan(calls=40)
    assert plan.budget_questions == 5
    assert plan.questions == 5
    assert sum(len(s.questions) for s in plan.sessions) == 5


def test_no_account_asks_more_than_the_per_user_limit() -> None:
    plan = _plan(limit=2)
    asked = Counter[str]()
    for session in plan.sessions:
        asked[session.account.email] += len(session.questions)
    assert max(asked.values()) <= 2


def test_sessions_start_in_order_inside_the_window_with_valid_unique_threads() -> None:
    plan = _plan()
    starts = [s.start_second for s in plan.sessions]
    assert starts == sorted(starts)
    assert all(0 <= s < WINDOW for s in starts)
    threads = [s.thread_id for s in plan.sessions]
    assert len(set(threads)) == len(threads)
    assert all(re.fullmatch(THREAD_ID_PATTERN, t) for t in threads)
    assert all(t.startswith("sim-20261113-") for t in threads)


def test_questions_name_the_companies_given() -> None:
    plan = _plan()
    openers = [s.questions[0] for s in plan.sessions]
    named = [any(c in q for c in COMPANIES) for q in openers]
    assert sum(named) >= len(openers) // 2


def test_a_zero_budget_plans_nothing() -> None:
    assert _plan(calls=3).sessions == ()
