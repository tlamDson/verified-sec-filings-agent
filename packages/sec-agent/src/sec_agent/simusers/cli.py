"""`sec-agent sim roster|plan|run`: the simulated users (test traffic, cohort `simulated`).

    sec-agent sim roster --seed 1
    sec-agent sim plan --llm-calls-per-day 2000
    SIM_LOGIN_SECRET=... sec-agent sim run --base-url https://app.example --llm-calls-per-day 2000

`run` signs each planned account in through the web app's simulated sign-in and spreads
the sessions over `--window-minutes` from now (`--no-wait` plays them back to back). Run it
on a schedule, mostly at night, or point `--base-url` at a staging app on a local model.
"""

import argparse
import datetime as dt
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from sec_agent.eval.output import add_record_options, record_rows, table
from sec_agent.golden.split import DEFAULT_SPLIT_FILE, read_split
from sec_agent.runs import RunRow
from sec_agent.simusers.budget import CALLS_PER_QUESTION, MAX_SHARE, QuotaBudget
from sec_agent.simusers.driver import DriverReport, run_plan
from sec_agent.simusers.plan import DayPlan, plan_day
from sec_agent.simusers.records import report_rows
from sec_agent.simusers.roster import SimAccount, roster
from sec_agent.simusers.web_client import WebSession

if TYPE_CHECKING:
    Subparsers = argparse._SubParsersAction[argparse.ArgumentParser]  # pyright: ignore[reportPrivateUsage]

PASSWORD_ENV_VAR = "SIM_LOGIN_SECRET"
LABEL = "simulated users (test traffic)"
DEFAULT_SEED = 1
DEFAULT_PER_USER_LIMIT = 20
"""The API's default daily limit per user (`API_DAILY_QUESTIONS`)."""
DEFAULT_WINDOW_MINUTES = 450
USER_AGENT = "sec-agent-simulated-user"


def add_commands(subparsers: "Subparsers") -> None:
    sim = subparsers.add_parser("sim", help=f"{LABEL}: accounts, daily plan, driver")
    commands = sim.add_subparsers(dest="sim_command", metavar="action", required=True)

    listing = commands.add_parser("roster", help="the 50 simulated accounts and their personas")
    listing.add_argument("--seed", type=int, default=DEFAULT_SEED)
    listing.set_defaults(run=_roster)

    planning = commands.add_parser("plan", help="print one day's sessions without sending any")
    _add_plan_options(planning)
    planning.set_defaults(run=_plan)

    driving = commands.add_parser("run", help="play one day's sessions through the web app")
    _add_plan_options(driving)
    driving.add_argument("--base-url", required=True, help="the web app, e.g. https://app.test")
    driving.add_argument("--no-wait", action="store_true", help="play sessions back to back")
    driving.add_argument("--system", default="web", help="system measured, for --record")
    add_record_options(driving)
    driving.set_defaults(run=_run)


def _add_plan_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--day", type=dt.date.fromisoformat, default=None, help="UTC day")
    parser.add_argument(
        "--llm-calls-per-day", type=int, required=True, help="production LLM quota per day"
    )
    parser.add_argument("--calls-per-question", type=int, default=CALLS_PER_QUESTION)
    parser.add_argument(
        "--share", type=float, default=MAX_SHARE, help=f"share of the quota (at most {MAX_SHARE})"
    )
    parser.add_argument("--per-user-limit", type=int, default=DEFAULT_PER_USER_LIMIT)
    parser.add_argument("--window-minutes", type=int, default=DEFAULT_WINDOW_MINUTES)
    parser.add_argument(
        "--split-file",
        type=Path,
        default=DEFAULT_SPLIT_FILE,
        help="companies asked about: the train and dev companies of this split",
    )


def http_client(base_url: str) -> httpx.Client:
    """One browser's cookie jar: each session gets its own."""
    return httpx.Client(base_url=base_url, headers={"user-agent": USER_AGENT}, timeout=30.0)


def _roster(args: argparse.Namespace) -> int:
    print(f"{LABEL}: 50 accounts, seed {args.seed}; never counted as users")
    rows = [["account", "user id", "persona"]]
    rows += [[a.email, a.user_id, a.persona] for a in roster(args.seed)]
    for line in table(rows):
        print(line)
    return 0


def _day_plan(args: argparse.Namespace) -> DayPlan | None:
    if not 0 < args.share <= MAX_SHARE:
        print(f"error: --share must be above 0 and at most {MAX_SHARE}", file=sys.stderr)
        return None
    if min(args.llm_calls_per_day, args.calls_per_question, args.window_minutes) < 1:
        print("error: quota, calls per question and window must be positive", file=sys.stderr)
        return None
    try:
        split = read_split(args.split_file)
    except (OSError, ValueError) as error:
        print(f"error: cannot read {args.split_file}: {error}", file=sys.stderr)
        return None
    companies = [c.ticker for c in (*split.of("train"), *split.of("dev")) if not c.excluded]
    budget = QuotaBudget(
        llm_calls_per_day=args.llm_calls_per_day,
        calls_per_question=args.calls_per_question,
        share=args.share,
    )
    return plan_day(
        roster(args.seed),
        companies,
        day=args.day or dt.datetime.now(dt.UTC).date(),
        seed=args.seed,
        budget=budget,
        per_user_limit=args.per_user_limit,
        window_seconds=args.window_minutes * 60,
    )


def _plan(args: argparse.Namespace) -> int:
    if (plan := _day_plan(args)) is None:
        return 2
    print(_headline(plan))
    rows = [["start", "account", "persona", "thread", "questions"]]
    rows += [
        [
            _clock(s.start_second),
            s.account.email,
            s.account.persona,
            s.thread_id,
            str(len(s.questions)),
        ]
        for s in plan.sessions
    ]
    for line in table(rows):
        print(line)
    return 0


def _run(args: argparse.Namespace) -> int:
    password = os.environ.get(PASSWORD_ENV_VAR, "").strip()
    if password == "":
        print(f"error: set {PASSWORD_ENV_VAR} to the simulated accounts' password", file=sys.stderr)
        return 2
    if (plan := _day_plan(args)) is None:
        return 2
    print(_headline(plan))

    def open_session(account: SimAccount) -> WebSession:
        return WebSession.sign_in(http_client(args.base_url), account, password)

    report = run_plan(plan, open_session, wait_until=_waiter(args.no_wait))
    print(_summary(report))

    def build(date: dt.date, sha: str) -> list[RunRow]:
        return report_rows(report, date=date, git_sha=sha, system=args.system)

    return record_rows(args, build)


def _waiter(no_wait: bool) -> Callable[[int], None]:
    started = time.monotonic()

    def wait_until(second: int) -> None:
        if not no_wait:
            time.sleep(max(0.0, started + second - time.monotonic()))

    return wait_until


def _headline(plan: DayPlan) -> str:
    return (
        f"{LABEL}: {plan.day.isoformat()}, seed {plan.seed}, "
        f"{plan.questions} of {plan.budget_questions} questions in {len(plan.sessions)} sessions"
    )


def _summary(report: DriverReport) -> str:
    outcomes = ", ".join(f"{kind} {count}" for kind, count in report.outcomes.items())
    return (
        f"{LABEL}: {report.sessions_run} sessions run, {report.sign_in_failures} sign-in "
        f"failures, {report.questions_sent} of {report.questions_planned} questions sent "
        f"({outcomes}); ratings kept up {report.ratings['up']}, down {report.ratings['down']}, "
        f"refused {report.ratings_refused}"
    )


def _clock(second: int) -> str:
    return f"+{second // 3600:02d}:{second % 3600 // 60:02d}:{second % 60:02d}"
