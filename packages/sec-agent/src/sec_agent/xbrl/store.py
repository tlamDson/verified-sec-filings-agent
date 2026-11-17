"""Facts in Postgres: write one company's normalised snapshot, read versions and latest."""

import datetime as dt
from collections.abc import Sequence
from types import TracebackType
from typing import Any, Protocol, Self

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from sec_agent.pg_pool import Pool, open_pool
from sec_agent.xbrl import sql
from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.versions import LatestFact

_LATEST_FIELDS = ("original_value", "original_accession", "original_filed", "versions", "restated")


class IngestRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_name: str
    facts_written: int
    report: NormalizationReport
    ingested_at: dt.datetime


class FactWriter(Protocol):
    def write(
        self, *, index_version: str, cik: int, entity_name: str, normalized: Normalized
    ) -> int:
        """Replace the company's facts with this snapshot and record the ingest in one
        transaction: upsert every fact, delete stored ones absent from it; return facts written.
        """
        ...


class PostgresFactStore:
    """A pool lends each call a live connection, so one the server closed is replaced."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    @classmethod
    def connect(cls, conninfo: str) -> Self:
        return cls(open_pool(conninfo, row_factory=dict_row))

    def close(self) -> None:
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def write(
        self, *, index_version: str, cik: int, entity_name: str, normalized: Normalized
    ) -> int:
        company = {"index_version": index_version, "cik": cik}
        rows = [{**fact.model_dump(), "index_version": index_version} for fact in normalized.facts]
        ingest = {
            **company,
            "entity_name": entity_name,
            "facts_written": len(rows),
            "report": Jsonb(normalized.report.model_dump()),
        }
        keys = {
            **company,
            "concepts": [f.concept for f in normalized.facts],
            "units": [f.unit for f in normalized.facts],
            "period_starts": [f.period_start for f in normalized.facts],
            "period_ends": [f.period_end for f in normalized.facts],
            "accessions": [f.accession for f in normalized.facts],
        }
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(sql.LOCK_COMPANY, company)
            cur.execute(sql.DELETE_ABSENT_FACTS, keys)
            cur.executemany(sql.UPSERT_FACT, rows)
            cur.execute(sql.UPSERT_INGEST, ingest)
        return len(rows)

    def count(self, *, index_version: str, cik: int) -> int:
        params = {"index_version": index_version, "cik": cik}
        with self._pool.connection() as conn:
            row = conn.execute(sql.COUNT, params).fetchone()
        return 0 if row is None else int(row["n"])

    def versions(self, *, index_version: str, cik: int, concept: str | None = None) -> list[Fact]:
        """Every stored version, ordered by concept, unit, period, then filing."""
        params = {"index_version": index_version, "cik": cik, "concept": concept}
        with self._pool.connection() as conn:
            return [Fact.model_validate(r) for r in conn.execute(sql.VERSIONS, params)]

    def latest(
        self, *, index_version: str, cik: int, concept: str | None = None
    ) -> list[LatestFact]:
        """One row per concept, unit and period: the latest filed version (E2)."""
        params = {"index_version": index_version, "cik": cik, "concept": concept}
        with self._pool.connection() as conn:
            return [_latest(r) for r in conn.execute(sql.LATEST, params)]

    def lookup(
        self,
        *,
        index_version: str,
        ciks: Sequence[int],
        concepts: Sequence[str],
        fiscal_years: Sequence[int],
    ) -> list[LatestFact]:
        """Latest versions of these companies' concepts in these fiscal years (`FactQuery`)."""
        params = {
            "index_version": index_version,
            "ciks": list(ciks),
            "concepts": list(concepts),
            "fiscal_years": list(fiscal_years),
        }
        with self._pool.connection() as conn:
            return [_latest(r) for r in conn.execute(sql.LOOKUP, params)]

    def ingest_record(self, *, index_version: str, cik: int) -> IngestRecord | None:
        params = {"index_version": index_version, "cik": cik}
        with self._pool.connection() as conn:
            row = conn.execute(sql.GET_INGEST, params).fetchone()
        return None if row is None else IngestRecord.model_validate(row)


def _latest(row: dict[str, Any]) -> LatestFact:
    extra = {k: row.pop(k) for k in _LATEST_FIELDS}
    return LatestFact.model_validate({"fact": Fact.model_validate(row), **extra})
