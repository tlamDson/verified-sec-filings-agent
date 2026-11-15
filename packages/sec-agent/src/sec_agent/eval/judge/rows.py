"""runs.csv rows for J1: kappa, TPR and TNR of each judge, naming who made the labels.

The answers are from the test split, so the rows are `split=test`. They measure judges,
not users: cohort `none`. An undefined number (no positives, no negatives) has no row.
"""

import datetime as dt
from collections.abc import Sequence

from sec_agent.eval.judge.score import JudgeScore
from sec_agent.eval.stats.wilson import Interval
from sec_agent.runs import RunRow

CONFIG = "positive=correct;unsure excluded;ci=wilson95"


def judge_rows(
    scores: Sequence[JudgeScore], *, labelled_by: str, date: dt.date, git_sha: str
) -> list[RunRow]:
    rows: list[RunRow] = []
    for s in scores:
        notes = (
            f"labels: {labelled_by}; {s.positives} labelled correct, {s.negatives} incorrect;"
            f" {s.unsure} unsure, {s.missing} without verdict"
        )
        metrics: list[tuple[str, float | None, str, Interval | None]] = [
            ("J1_kappa", s.kappa, "kappa", None),
            ("J1_tpr", s.tpr, "fraction", s.tpr_interval),
            ("J1_tnr", s.tnr, "fraction", s.tnr_interval),
        ]
        for metric, value, unit, interval in metrics:
            if value is None:
                continue
            rows.append(
                RunRow.model_validate(
                    {
                        "date": date,
                        "git_sha": git_sha,
                        "metric": metric,
                        "system": s.judge,
                        "split": "test",
                        "cohort": "none",
                        "n": s.n,
                        "value": value,
                        "unit": unit,
                        "ci_low": interval.low if interval else None,
                        "ci_high": interval.high if interval else None,
                        "config": CONFIG,
                        "notes": notes,
                    }
                )
            )
    return rows
