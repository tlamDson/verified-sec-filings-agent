"""Chunk text for the pool, read from the `chunks` table of one index version."""

from collections.abc import Sequence
from types import TracebackType
from typing import Any, Protocol, Self

import psycopg

from sec_agent.golden.gret.models import ChunkRef, ChunkText

_FETCH = b"""
SELECT c.accession, c.section, c.ordinal, c.cik, c.text, c.text_sha256
FROM chunks AS c
JOIN unnest(%(accessions)s::text[], %(sections)s::text[], %(ordinals)s::int[])
    AS k (accession, section, ordinal)
    USING (accession, section, ordinal)
WHERE c.index_version = %(index_version)s
"""


class ChunkTextSource(Protocol):
    def fetch(self, *, index_version: str, refs: Sequence[ChunkRef]) -> dict[ChunkRef, ChunkText]:
        """The chunks that exist in `index_version`; absent ones are left out."""
        ...


class PostgresChunkText:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    @classmethod
    def connect(cls, conninfo: str) -> Self:
        return cls(psycopg.connect(conninfo, autocommit=True))

    def fetch(self, *, index_version: str, refs: Sequence[ChunkRef]) -> dict[ChunkRef, ChunkText]:
        params = {
            "index_version": index_version,
            "accessions": [r.accession for r in refs],
            "sections": [r.section for r in refs],
            "ordinals": [r.ordinal for r in refs],
        }
        out: dict[ChunkRef, ChunkText] = {}
        for accession, section, ordinal, cik, text, sha in self._conn.execute(_FETCH, params):
            ref = ChunkRef(accession=accession, section=section, ordinal=ordinal)
            out[ref] = ChunkText(cik=cik, text=text, text_sha256=sha)
        return out

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
