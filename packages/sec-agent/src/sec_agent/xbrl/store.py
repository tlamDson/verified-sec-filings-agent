"""Facts in Postgres: write one company's normalised snapshot, read versions and latest."""

import datetime as dt
from types import TracebackType
from typing import Any, Protocol, Self

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

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
        """Upsert every fact and the ingest record in one transaction; return facts written."""
        ...


class PostgresFactStore:
    def __init__(self, conn: psycopg.Connection[DictRow]) -> None:
        self._conn = conn

    @classmethod
    def connect(cls, conninfo: str) -> Self:
        conn = psycopg.Connection[DictRow].connect(conninfo, autocommit=True, row_factory=dict_row)
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

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
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(sql.LOCK_COMPANY, company)
            cur.executemany(sql.UPSERT_FACT, rows)
            cur.execute(sql.UPSERT_INGEST, ingest)
        return len(rows)

    def count(self, *, index_version: str, cik: int) -> int:
        row = self._conn.execute(sql.COUNT, {"index_version": index_version, "cik": cik}).fetchone()
        return 0 if row is None else int(row["n"])

    def versions(self, *, index_version: str, cik: int, concept: str | None = None) -> list[Fact]:
        """Every stored version, ordered by concept, unit, period, then filing."""
        params = {"index_version": index_version, "cik": cik, "concept": concept}
        return [Fact.model_validate(r) for r in self._conn.execute(sql.VERSIONS, params)]

    def latest(
        self, *, index_version: str, cik: int, concept: str | None = None
    ) -> list[LatestFact]:
        """One row per concept, unit and period: the latest filed version (E2)."""
        params = {"index_version": index_version, "cik": cik, "concept": concept}
        return [_latest(r) for r in self._conn.execute(sql.LATEST, params)]

    def ingest_record(self, *, index_version: str, cik: int) -> IngestRecord | None:
        params = {"index_version": index_version, "cik": cik}
        row = self._conn.execute(sql.GET_INGEST, params).fetchone()
        return None if row is None else IngestRecord.model_validate(row)


def _latest(row: dict[str, Any]) -> LatestFact:
    extra = {k: row.pop(k) for k in _LATEST_FIELDS}
    return LatestFact.model_validate({"fact": Fact.model_validate(row), **extra})
