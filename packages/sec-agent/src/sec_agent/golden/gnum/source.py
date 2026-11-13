"""Facts for G-num from Postgres: the latest filed version of every fact (E2)."""

from types import TracebackType
from typing import Protocol, Self

from sec_agent.xbrl.store import PostgresFactStore
from sec_agent.xbrl.versions import LatestFact


class FactSource(Protocol):
    def latest(self, *, index_version: str, cik: int) -> list[LatestFact]: ...


class PostgresFactSource:
    def __init__(self, store: PostgresFactStore) -> None:
        self._store = store

    @classmethod
    def connect(cls, conninfo: str) -> Self:
        return cls(PostgresFactStore.connect(conninfo))

    def latest(self, *, index_version: str, cik: int) -> list[LatestFact]:
        return self._store.latest(index_version=index_version, cik=cik)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
