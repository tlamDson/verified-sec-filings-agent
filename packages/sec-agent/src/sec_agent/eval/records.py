"""runs.csv rows for eval reports: one row per measured number.

Accuracies and retrieval means carry their interval. A McNemar or bootstrap p value is its
own row (unit `p_value`), and so is each paired difference (unit `difference`). Eval rows
measure systems, not users: cohort `none`.
"""

import datetime as dt

from sec_agent.eval.numeric.grade import PERCENT_POINT_TOLERANCE, RELATIVE_TOLERANCE
from sec_agent.eval.numeric.report import NumericReport
from sec_agent.eval.retrieval.report import RetrievalReport
from sec_agent.golden.split import CompanySplitName
from sec_agent.runs import RunRow

NUMERIC_CONFIG = (
    f"rel_tol={RELATIVE_TOLERANCE};percent_tol={PERCENT_POINT_TOLERANCE}pt;"
    "unit+period must match;ci=wilson95"
)


def numeric_rows(
    report: NumericReport, *, split: CompanySplitName, date: dt.date, git_sha: str
) -> list[RunRow]:
    common = {
        "date": date,
        "git_sha": git_sha,
        "split": split,
        "cohort": "none",
        "index_version": report.index_version,
        "config": NUMERIC_CONFIG,
    }
    rows = [
        RunRow.model_validate(
            {
                **common,
                "metric": "N1",
                "system": s.system,
                "n": s.n,
                "value": s.accuracy,
                "unit": "fraction",
                "ci_low": s.interval.low,
                "ci_high": s.interval.high,
                "notes": f"model={','.join(s.models)}; {report.scored} of {report.questions}",
            }
        )
        for s in report.systems
    ]
    rows += [
        RunRow.model_validate(
            {
                **common,
                "metric": "N1_mcnemar_p",
                "system": f"{c.system}_vs_{c.other}",
                "n": c.result.n,
                "value": c.result.p_value,
                "unit": "p_value",
                "notes": (
                    f"exact two-sided; {c.system} only {c.result.a_only},"
                    f" {c.other} only {c.result.b_only}"
                ),
            }
        )
        for c in report.comparisons
    ]
    return rows


def retrieval_rows(
    report: RetrievalReport, *, date: dt.date, git_sha: str, index_version: str
) -> list[RunRow]:
    common = {
        "date": date,
        "git_sha": git_sha,
        "split": "test",  # G-ret questions are about test companies only
        "cohort": "none",
        "index_version": index_version,
        "config": f"bootstrap=company;resamples={report.resamples};seed={report.seed};ci=95",
    }
    rows: list[RunRow] = []
    for s in report.systems:
        for metric, r in s.metrics.items():
            rows.append(
                RunRow.model_validate(
                    {
                        **common,
                        "metric": f"R1_{metric}",
                        "system": s.system,
                        "n": r.n,
                        "value": r.estimate,
                        "unit": "fraction",
                        "ci_low": r.low,
                        "ci_high": r.high,
                        "notes": f"{r.clusters} companies; {len(report.unscored)} unscored",
                    }
                )
            )
    for c in report.comparisons:
        name = f"{c.system}_vs_{c.baseline}"
        r = c.result
        base = {**common, "system": name, "n": r.n, "notes": f"{r.clusters} companies, paired"}
        rows.append(
            RunRow.model_validate(
                {
                    **base,
                    "metric": f"R1_{c.metric}_diff",
                    "value": r.estimate,
                    "unit": "difference",
                    "ci_low": r.low,
                    "ci_high": r.high,
                }
            )
        )
        rows.append(
            RunRow.model_validate(
                {**base, "metric": f"R1_{c.metric}_p", "value": r.p_value, "unit": "p_value"}
            )
        )
    return rows
