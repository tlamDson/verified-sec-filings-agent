"""runs.csv rows for A1: task success per system with its Wilson interval, and one McNemar
p value per pair. Eval rows measure systems, not users: cohort `none`."""

import datetime as dt

from sec_agent.eval.agent.report import AgentReport
from sec_agent.golden.split import CompanySplitName
from sec_agent.runs import RunRow

AGENT_CONFIG = (
    "every check passes: tool+resolved args, traced figure, citation, faithful, text;ci=wilson95"
)


def agent_rows(
    report: AgentReport,
    *,
    split: CompanySplitName,
    date: dt.date,
    git_sha: str,
    index_version: str,
) -> list[RunRow]:
    common = {
        "date": date,
        "git_sha": git_sha,
        "split": split,
        "cohort": "none",
        "index_version": index_version,
        "config": AGENT_CONFIG,
    }
    rows = [
        RunRow.model_validate(
            {
                **common,
                "metric": "A1",
                "system": s.system,
                "n": s.n,
                "value": s.rate,
                "unit": "fraction",
                "ci_low": s.interval.low,
                "ci_high": s.interval.high,
                "notes": f"model={','.join(s.models)}; {report.scored} of {report.scenarios}",
            }
        )
        for s in report.systems
    ]
    rows += [
        RunRow.model_validate(
            {
                **common,
                "metric": "A1_mcnemar_p",
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
