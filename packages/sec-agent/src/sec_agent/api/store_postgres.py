"""The API's records in Postgres, shared by every replica.

A question is counted by one statement that inserts or increments the user's row for the
day only while it is under the limit, so replicas racing for a user's last question never
pass it. Feedback is inserted from the turn's own row: a rating for a turn the user never
asked matches no row and is not kept.
"""

import datetime as dt
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Self

import psycopg

from sec_agent.api.identity import COHORTS, Cohort, Identity
from sec_agent.api.store import CohortCounts, Feedback, TurnRecord

_CHARGE = """
INSERT INTO api_usage (user_id, cohort, day, questions)
VALUES (%(user_id)s, %(cohort)s, %(day)s, 1)
ON CONFLICT (user_id, day) DO UPDATE SET questions = api_usage.questions + 1
WHERE api_usage.questions < %(limit)s
RETURNING questions
"""
_USED = "SELECT questions FROM api_usage WHERE user_id = %s AND day = %s"
_RECORD_TURN = """
INSERT INTO api_turns (user_id, cohort, thread_id, turn, asked_at, status, degraded)
VALUES (%(user_id)s, %(cohort)s, %(thread_id)s, %(turn)s, %(asked_at)s, %(status)s, %(degraded)s)
ON CONFLICT (user_id, thread_id, turn) DO UPDATE
SET asked_at = EXCLUDED.asked_at, status = EXCLUDED.status, degraded = EXCLUDED.degraded
"""
_SAVE_FEEDBACK = """
INSERT INTO api_feedback (user_id, cohort, thread_id, turn, rating, rated_at)
SELECT user_id, cohort, thread_id, turn, %(rating)s, %(at)s
FROM api_turns
WHERE user_id = %(user_id)s AND thread_id = %(thread_id)s AND turn = %(turn)s
ON CONFLICT (user_id, thread_id, turn) DO UPDATE
SET rating = EXCLUDED.rating, rated_at = EXCLUDED.rated_at
"""
_COUNTS = """
SELECT t.cohort,
       count(DISTINCT t.user_id),
       count(DISTINCT (t.user_id, t.thread_id)),
       count(*),
       count(*) FILTER (WHERE t.degraded),
       count(*) FILTER (WHERE f.rating = 'up'),
       count(*) FILTER (WHERE f.rating = 'down')
FROM api_turns t
LEFT JOIN api_feedback f USING (user_id, thread_id, turn)
WHERE t.asked_at >= %(start)s AND t.asked_at < %(end)s
GROUP BY t.cohort
"""
_NO_COUNTS = CohortCounts(
    users=0, conversations=0, turns=0, degraded_turns=0, thumbs_up=0, thumbs_down=0
)


class PostgresApiStore:
    """One connection; calls from several threads take turns."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    @classmethod
    @contextmanager
    def connect(cls, conninfo: str) -> Generator[Self]:
        conn: psycopg.Connection[Any]
        with psycopg.connect(conninfo, autocommit=True) as conn:
            yield cls(conn)

    def charge_question(self, identity: Identity, day: dt.date, limit: int) -> int | None:
        params = {
            "user_id": identity.user_id,
            "cohort": identity.cohort,
            "day": day,
            "limit": limit,
        }
        with self._lock:
            row = self._conn.execute(_CHARGE, params).fetchone()
        return None if row is None else int(row[0])

    def questions_used(self, user_id: str, day: dt.date) -> int:
        with self._lock:
            row = self._conn.execute(_USED, (user_id, day)).fetchone()
        return 0 if row is None else int(row[0])

    def record_turn(self, record: TurnRecord) -> None:
        with self._lock:
            self._conn.execute(_RECORD_TURN, record.model_dump())

    def save_feedback(self, feedback: Feedback) -> bool:
        with self._lock:
            return self._conn.execute(_SAVE_FEEDBACK, feedback.model_dump()).rowcount == 1

    def cohort_counts(self, first_day: dt.date, last_day: dt.date) -> dict[Cohort, CohortCounts]:
        span = {"start": _midnight(first_day), "end": _midnight(last_day + dt.timedelta(days=1))}
        with self._lock:
            rows = self._conn.execute(_COUNTS, span).fetchall()
        found = {
            row[0]: CohortCounts(
                users=row[1],
                conversations=row[2],
                turns=row[3],
                degraded_turns=row[4],
                thumbs_up=row[5],
                thumbs_down=row[6],
            )
            for row in rows
        }
        return {cohort: found.get(cohort, _NO_COUNTS) for cohort in COHORTS}


def _midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC)
