"""The quota count in Postgres, shared by every API replica.

`reserve` checks and counts in one transaction under a per-provider advisory lock, so
replicas racing for the last request of a window never overspend it. Minute rows older
than the current minute are deleted as they are passed; day rows stay as usage history.
"""

import datetime as dt
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Self

import psycopg

from sec_agent.llm.quota import QuotaLimits, QuotaUsage, allows, day_window, minute_window

_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_USAGE = """
SELECT
    coalesce(sum(requests) FILTER (WHERE window_kind = 'minute'), 0)::bigint,
    coalesce(sum(requests) FILTER (WHERE window_kind = 'day'), 0)::bigint,
    coalesce(sum(tokens) FILTER (WHERE window_kind = 'day'), 0)::bigint
FROM llm_usage
WHERE provider = %(provider)s
  AND ((window_kind = 'minute' AND window_start = %(minute)s)
    OR (window_kind = 'day' AND window_start = %(day)s))
"""
_COUNT = """
INSERT INTO llm_usage (provider, window_kind, window_start, requests)
VALUES (%(provider)s, 'minute', %(minute)s, 1), (%(provider)s, 'day', %(day)s, 1)
ON CONFLICT (provider, window_kind, window_start)
DO UPDATE SET requests = llm_usage.requests + 1
"""
_PRUNE = """
DELETE FROM llm_usage
WHERE provider = %(provider)s AND window_kind = 'minute' AND window_start < %(minute)s
"""
_ADD_TOKENS = """
INSERT INTO llm_usage (provider, window_kind, window_start, tokens)
VALUES (%(provider)s, 'day', %(day)s, %(tokens)s)
ON CONFLICT (provider, window_kind, window_start)
DO UPDATE SET tokens = llm_usage.tokens + EXCLUDED.tokens
"""


class PostgresQuotaStore:
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

    def reserve(self, provider: str, limits: QuotaLimits, at: dt.datetime) -> bool:
        params = _params(provider, at)
        with self._lock, self._conn.transaction():
            self._conn.execute(_LOCK, (f"llm_usage:{provider}",))
            if not allows(limits, self._usage(params)):
                return False
            self._conn.execute(_COUNT, params)
            self._conn.execute(_PRUNE, params)
            return True

    def add_tokens(self, provider: str, tokens: int, at: dt.datetime) -> None:
        params = {**_params(provider, at), "tokens": max(0, tokens)}
        with self._lock:
            self._conn.execute(_ADD_TOKENS, params)

    def usage(self, provider: str, at: dt.datetime) -> QuotaUsage:
        with self._lock:
            return self._usage(_params(provider, at))

    def _usage(self, params: dict[str, Any]) -> QuotaUsage:
        row = self._conn.execute(_USAGE, params).fetchone()
        if row is None:  # an aggregate without GROUP BY always returns one row
            return QuotaUsage(0, 0, 0)
        return QuotaUsage(int(row[0]), int(row[1]), int(row[2]))


def _params(provider: str, at: dt.datetime) -> dict[str, Any]:
    return {"provider": provider, "minute": minute_window(at), "day": day_window(at)}
