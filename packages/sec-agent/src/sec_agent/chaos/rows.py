"""Worker-kill results as runs.csv rows: every reported number comes from a run.

The rows measure the ingest, not users, so their cohort is `none`.
"""

import datetime as dt

from sec_agent.chaos.integrity import IngestIntegrity
from sec_agent.chaos.worker_kill import KillReport
from sec_agent.eval.stats.wilson import wilson_interval
from sec_agent.runs import RunRow


def kill_rows(
    kill: KillReport, integrity: IngestIntegrity, *, date: dt.date, git_sha: str
) -> list[RunRow]:
    common: dict[str, object] = {
        "date": date,
        "git_sha": git_sha,
        "system": f"worker-x{kill.workers}",
        "split": "none",
        "cohort": "none",
        "index_version": integrity.index_version,
        "config": f"kill 1 of {kill.workers} workers mid-job (job {kill.killed_job_key})",
    }
    unfinished = integrity.jobs_open + integrity.jobs_failed
    return [
        RunRow.model_validate(
            {
                **common,
                "metric": "CHAOS.duplicate_facts",
                "n": integrity.facts,
                "value": integrity.duplicate_fact_keys,
                "unit": "rows",
            }
        ),
        RunRow.model_validate(
            {
                **common,
                "metric": "CHAOS.jobs_redone",
                "n": integrity.jobs_total,
                "value": integrity.jobs_redone,
                "unit": "jobs",
            }
        ),
        RunRow.model_validate(
            {
                **common,
                "metric": "CHAOS.jobs_unfinished",
                "n": integrity.jobs_total,
                "value": unfinished,
                "unit": "jobs",
            }
        ),
        RunRow.model_validate(
            {
                **common,
                "metric": "CHAOS.recovery_seconds",
                "n": 1,
                "value": round(kill.seconds_to_recover, 3),
                "unit": "s",
                "notes": "from the kill until no job was queued or running",
            }
        ),
    ]


def proportion_row(metric: str, hits: int, n: int, common: dict[str, object]) -> RunRow:
    interval = wilson_interval(hits, n)
    return RunRow.model_validate(
        {
            **common,
            "metric": metric,
            "n": n,
            "value": hits / n,
            "unit": "fraction",
            "ci_low": interval.low,
            "ci_high": interval.high,
        }
    )
