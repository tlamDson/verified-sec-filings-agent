"""`sec-agent api cohorts`: the dashboard of activity, real and simulated side by side.

The users are made up for the tests; the simulated one is test traffic.
"""

import datetime as dt

import pytest
from api_kit import NOW, REAL, SIM

from sec_agent.api.cohort_table import cohort_lines
from sec_agent.api.identity import Identity
from sec_agent.api.store import CohortCounts, Feedback, TurnRecord
from sec_agent.api.store_postgres import PostgresApiStore
from sec_agent.cli import main

DAY = NOW.date().isoformat()


def _counts(users: int) -> CohortCounts:
    return CohortCounts(
        users=users,
        conversations=users,
        turns=users,
        degraded_turns=0,
        thumbs_up=0,
        thumbs_down=0,
    )


def test_the_table_keeps_the_cohorts_apart_and_never_sums_them() -> None:
    lines = cohort_lines({"real": _counts(2), "simulated": _counts(30)})
    text = "\n".join(lines)
    assert "real" in lines[0]
    assert "simulated" in lines[0]
    assert "32" not in text
    assert "total" not in text.lower()
    assert "simulated accounts" in text
    assert "test traffic" in text


def _turn(user: Identity, thread: str) -> TurnRecord:
    return TurnRecord(
        user_id=user.user_id,
        cohort=user.cohort,
        thread_id=thread,
        turn=1,
        asked_at=NOW,
        status="answered",
        degraded=False,
    )


def test_api_cohorts_reads_the_tables(api_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    with PostgresApiStore.connect(api_db) as store:
        store.record_turn(_turn(REAL, "thread-real-1"))
        for n in range(3):
            store.record_turn(_turn(SIM, f"thread-sim-{n}"))
        rating = Feedback(
            user_id=SIM.user_id,
            cohort="simulated",
            thread_id="thread-sim-0",
            turn=1,
            rating="down",
            at=NOW + dt.timedelta(seconds=1),
        )
        assert store.save_feedback(rating)
    assert main(["api", "--database-url", api_db, "cohorts", "--from", DAY, "--to", DAY]) == 0
    lines = capsys.readouterr().out.splitlines()
    rows = {line.split()[0]: line.split()[1:] for line in lines if line.strip()}
    assert rows["turns"] == ["1", "3"]
    assert rows["thumbs_down"] == ["0", "1"]
