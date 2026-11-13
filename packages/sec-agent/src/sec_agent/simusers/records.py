"""runs.csv rows for a driver run: counts of simulated traffic, cohort `simulated` only.

They describe what the system did under simulated load (answers, degraded turns, errors,
the daily limit, latency seen through the web app). Ratings only show the feedback path
works; they are not a quality measure.
"""

import datetime as dt

from sec_agent.observability.latency import percentile
from sec_agent.runs import RunRow
from sec_agent.simusers.driver import DriverReport

NOTES = "simulated users (test traffic); ratings check the feedback path, not quality"


def report_rows(report: DriverReport, *, date: dt.date, git_sha: str, system: str) -> list[RunRow]:
    config = f"seed={report.seed};day={report.day.isoformat()}"

    def row(metric: str, n: int, value: float, unit: str) -> RunRow:
        return RunRow(
            date=date,
            git_sha=git_sha,
            metric=f"U1.{metric}",
            system=system,
            split="none",
            cohort="simulated",
            n=n,
            value=value,
            unit=unit,
            config=config,
            notes=NOTES,
        )

    sent = report.questions_sent
    rows = [
        row("sessions_run", report.sessions_run, report.sessions_run, "count"),
        row("sign_in_failures", report.sessions_planned, report.sign_in_failures, "count"),
        row("questions_sent", sent, sent, "count"),
        *(row(f"turns_{kind}", sent, count, "count") for kind, count in report.outcomes.items()),
        *(row(f"ratings_{r}", sent, count, "count") for r, count in report.ratings.items()),
        row("ratings_refused", sent, report.ratings_refused, "count"),
    ]
    if report.turn_seconds:
        n = len(report.turn_seconds)
        for q in (50, 95):
            value = percentile(report.turn_seconds, q / 100)
            rows.append(row(f"turn_seconds_p{q}", n, round(value, 3), "seconds"))
    return rows
