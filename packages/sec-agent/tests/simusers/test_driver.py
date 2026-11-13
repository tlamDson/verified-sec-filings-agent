"""The driver plays one day's plan through sessions it opens per simulated account.

Sessions here are fakes that answer from a script; nothing reaches the web app or a model.
"""

import datetime as dt

from sec_agent.simusers.budget import QuotaBudget
from sec_agent.simusers.driver import DriverReport, run_plan
from sec_agent.simusers.feedback import Rating
from sec_agent.simusers.outcome import OutcomeKind, TurnOutcome
from sec_agent.simusers.plan import DayPlan, plan_day
from sec_agent.simusers.records import report_rows
from sec_agent.simusers.roster import SimAccount, roster
from sec_agent.simusers.web_client import SimSignInError

DAY = dt.date(2026, 11, 13)
Log = list[tuple[str, ...]]


class FakeSession:
    def __init__(self, log: Log, kinds: list[OutcomeKind]) -> None:
        self.log = log
        self.kinds = kinds
        self.turns: dict[str, int] = {}

    def ask(self, thread_id: str, question: str, asked_on: dt.date) -> TurnOutcome:
        assert asked_on == DAY
        self.log.append(("ask", thread_id, question))
        kind: OutcomeKind = self.kinds.pop(0) if self.kinds else "answered"
        turn = None
        if kind not in ("error", "limited"):
            turn = self.turns.get(thread_id, 0) + 1
            self.turns[thread_id] = turn
        verdict = "pass" if kind == "answered" else None
        return TurnOutcome(
            kind=kind, turn=turn, verdict=verdict, removed=0, evidence=1, seconds=2.0
        )

    def rate(self, thread_id: str, turn: int, rating: Rating) -> bool:
        self.log.append(("rate", thread_id, str(turn), rating))
        return True


def _plan(calls: int = 400) -> DayPlan:
    return plan_day(
        roster(seed=5),
        ("AAPL", "MSFT", "NVDA"),
        day=DAY,
        seed=5,
        budget=QuotaBudget(llm_calls_per_day=calls),
        per_user_limit=20,
        window_seconds=3600,
    )


def _run(
    plan: DayPlan, kinds: list[OutcomeKind] | None = None, fail: frozenset[int] = frozenset()
) -> tuple[DriverReport, Log, list[int]]:
    log: Log = []
    waits: list[int] = []
    queue = list(kinds or [])

    def open_session(account: SimAccount) -> FakeSession:
        if account.number in fail:
            raise SimSignInError("SIMULATED sign-in failure")
        return FakeSession(log, queue)

    report = run_plan(plan, open_session, wait_until=waits.append)
    return report, log, waits


def test_every_planned_question_is_sent_in_order_at_its_start() -> None:
    plan = _plan()
    report, log, waits = _run(plan)
    asked = [entry[2] for entry in log if entry[0] == "ask"]
    assert asked == [q for s in plan.sessions for q in s.questions]
    assert waits == [s.start_second for s in plan.sessions]
    assert report.questions_sent == plan.questions <= plan.budget_questions
    assert report.outcomes["answered"] == plan.questions


def test_a_daily_limit_or_an_error_ends_that_session() -> None:
    plan = _plan()
    first = plan.sessions[0]
    report, log, _ = _run(plan, kinds=["limited"])
    mine = [e for e in log if e[0] == "ask" and e[1] == first.thread_id]
    assert mine == [("ask", first.thread_id, first.questions[0])]
    assert report.outcomes["limited"] == 1
    assert report.questions_sent == plan.questions - len(first.questions) + 1


def test_an_account_that_cannot_sign_in_is_counted_and_skipped() -> None:
    plan = _plan()
    number = plan.sessions[0].account.number
    report, log, _ = _run(plan, fail=frozenset({number}))
    skipped = [s for s in plan.sessions if s.account.number == number]
    assert report.sign_in_failures == len(skipped)
    assert report.sessions_run == len(plan.sessions) - len(skipped)
    assert all(e[1] not in {s.thread_id for s in skipped} for e in log)


def test_ratings_follow_the_written_criteria_and_the_seed() -> None:
    plan = _plan()
    report, log, _ = _run(plan)
    again, log_again, _ = _run(plan)
    assert (report, log) == (again, log_again)
    rated = [e for e in log if e[0] == "rate"]
    assert 0 < len(rated) < plan.questions
    assert all(e[3] == "up" for e in rated)
    assert report.ratings == {"up": len(rated), "down": 0}


def test_unrateable_turns_get_no_rating() -> None:
    plan = _plan()
    _, log, _ = _run(plan, kinds=["degraded"] * plan.questions)
    assert [e for e in log if e[0] == "rate"] == []


def test_the_report_is_recorded_as_simulated_users_only() -> None:
    report, _, _ = _run(_plan())
    rows = report_rows(report, date=DAY, git_sha="abc1234", system="web")
    assert rows
    assert {r.cohort for r in rows} == {"simulated"}
    assert all(r.metric.startswith("U1.") for r in rows)
    assert all("simulated" in r.notes for r in rows)
    sent = next(r for r in rows if r.metric == "U1.questions_sent")
    assert (sent.n, sent.value) == (report.questions_sent, report.questions_sent)


def test_an_empty_plan_sends_nothing() -> None:
    report, log, _ = _run(_plan(calls=1))
    assert (report.questions_sent, log) == (0, [])
