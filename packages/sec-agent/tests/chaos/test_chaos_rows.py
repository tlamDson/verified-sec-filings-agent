"""A worker-kill run -> runs.csv rows: duplicates found and jobs redone, never estimated."""

import datetime as dt

from sec_agent.chaos.integrity import IngestIntegrity
from sec_agent.chaos.rows import kill_rows
from sec_agent.chaos.worker_kill import KillReport
from sec_agent.runs import RunRow

KILL = KillReport(
    workers=3,
    killed_pid=4242,
    killed_job_id=7,
    killed_job_key="v1:0000320193",
    killed_job_status="done",
    killed_job_attempts=2,
    jobs_done=10,
    jobs_failed=0,
    seconds_to_recover=12.5,
)
INTEGRITY = IngestIntegrity(
    index_version="v1",
    jobs_total=10,
    jobs_done=10,
    jobs_failed=0,
    jobs_open=0,
    jobs_redone=1,
    duplicate_fact_keys=0,
    facts=5000,
    companies_ingested=10,
    companies_short=0,
)


def test_kill_rows_report_duplicates_redone_jobs_and_recovery() -> None:
    rows = kill_rows(KILL, INTEGRITY, date=dt.date(2026, 11, 13), git_sha="abc1234")
    by_metric = {row.metric: row for row in rows}
    assert set(by_metric) == {
        "CHAOS.duplicate_facts",
        "CHAOS.jobs_redone",
        "CHAOS.jobs_unfinished",
        "CHAOS.recovery_seconds",
    }
    dup = by_metric["CHAOS.duplicate_facts"]
    assert (dup.value, dup.n, dup.unit, dup.index_version) == (0, 5000, "rows", "v1")
    assert by_metric["CHAOS.jobs_redone"].value == 1
    assert by_metric["CHAOS.jobs_redone"].n == 10
    assert by_metric["CHAOS.jobs_unfinished"].value == 0
    assert by_metric["CHAOS.recovery_seconds"].value == 12.5
    for row in rows:
        RunRow.model_validate(row.model_dump())
        assert (row.cohort, row.split) == ("none", "none")
        assert row.system == "worker-x3"
        assert "kill" in row.config
