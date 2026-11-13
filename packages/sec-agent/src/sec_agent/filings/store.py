"""Write one filing's sections and chunks to Postgres, keyed by (index_version, accession).

`replace` deletes the filing's rows for that version and inserts the new ones in one
transaction, under an advisory lock on the key. Running a job twice, or two workers running
it at once after a lease takeover, leaves exactly one copy.
"""

from importlib.resources import files
from types import TracebackType
from typing import Any, Protocol, Self

import psycopg

from sec_agent.filings.models import IndexedFiling

_SCHEMA_LOCK = 0x5EC0_0004  # advisory lock id; serialises concurrent apply_schema calls

_LOCK_FILING = b"SELECT pg_advisory_xact_lock(hashtextextended(%s, 4))"
_DELETE_FILING = b"DELETE FROM indexed_filings WHERE index_version = %s AND accession = %s"
_INSERT_FILING = b"""
INSERT INTO indexed_filings (index_version, accession, cik, form, filing_date, report_date,
                             source_url, section_count, chunk_count)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_INSERT_SECTION = b"""
INSERT INTO filing_sections (index_version, accession, section, item, heading, text,
                             token_count)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
_INSERT_CHUNK = b"""
INSERT INTO chunks (index_version, accession, section, ordinal, cik, form, filing_date,
                    report_date, char_start, char_end, token_count, text, text_sha256)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class ChunkStore(Protocol):
    def replace(self, indexed: IndexedFiling) -> None:
        """Make the stored rows of this filing and version equal to `indexed`."""
        ...


def schema_sql() -> str:
    return files("sec_agent.filings").joinpath("schema.sql").read_text("utf-8")


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Apply `schema.sql` in one transaction, under an advisory lock."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK,))
        conn.execute(schema_sql().encode())


class PostgresChunkStore:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    @classmethod
    def connect(cls, conninfo: str) -> Self:
        return cls(psycopg.connect(conninfo, autocommit=True))

    def apply_schema(self) -> None:
        apply_schema(self._conn)

    def replace(self, indexed: IndexedFiling) -> None:
        filing, version = indexed.filing, indexed.index_version
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute(_LOCK_FILING, (f"{version}/{filing.accession}",))
            cur.execute(_DELETE_FILING, (version, filing.accession))
            cur.execute(
                _INSERT_FILING,
                (
                    version,
                    filing.accession,
                    filing.cik,
                    filing.form,
                    filing.filing_date,
                    filing.report_date,
                    filing.document_url,
                    len(indexed.sections),
                    len(indexed.chunks),
                ),
            )
            cur.executemany(
                _INSERT_SECTION,
                [
                    (version, filing.accession, s.key, s.item, s.heading, s.text, s.token_count)
                    for s in indexed.sections
                ],
            )
            cur.executemany(
                _INSERT_CHUNK,
                [
                    (
                        c.index_version,
                        c.accession,
                        c.section,
                        c.ordinal,
                        c.cik,
                        c.form,
                        c.filing_date,
                        c.report_date,
                        c.char_start,
                        c.char_end,
                        c.token_count,
                        c.text,
                        c.text_sha256,
                    )
                    for c in indexed.chunks
                ],
            )

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
