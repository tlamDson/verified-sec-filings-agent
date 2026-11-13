"""Where the numeric tools read facts: the latest filed version of each value (E2).

`PostgresFactStore.lookup` (one SQL query over `facts_latest`) is the production source;
`MemoryFactQuery` applies the same rule (`latest_versions`) to facts in memory, for eval
runs over a fixture and for tests. A test holds the two to the same answer.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Protocol, Self

from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.versions import LatestFact, latest_versions


class FactQuery(Protocol):
    def lookup(
        self,
        *,
        index_version: str,
        ciks: Sequence[int],
        concepts: Sequence[str],
        fiscal_years: Sequence[int],
    ) -> list[LatestFact]:
        """Latest versions of these companies' concepts whose fiscal year is one of these."""
        ...


class MemoryFactQuery:
    def __init__(self, index_version: str, latest: Iterable[LatestFact]) -> None:
        self._index_version = index_version
        self._latest = tuple(latest)

    @classmethod
    def from_facts(cls, index_version: str, facts: Iterable[Fact]) -> Self:
        """Every filed version in; the latest of each company's value kept."""
        by_company: defaultdict[int, list[Fact]] = defaultdict(list)
        for fact in facts:
            by_company[fact.cik].append(fact)  # a series key does not include the CIK
        return cls(index_version, [x for f in by_company.values() for x in latest_versions(f)])

    def lookup(
        self,
        *,
        index_version: str,
        ciks: Sequence[int],
        concepts: Sequence[str],
        fiscal_years: Sequence[int],
    ) -> list[LatestFact]:
        if index_version != self._index_version:
            return []
        cik_set, concept_set, year_set = set(ciks), set(concepts), set(fiscal_years)
        return [
            x
            for x in self._latest
            if x.fact.cik in cik_set
            and x.fact.concept in concept_set
            and x.fact.fiscal_year in year_set
        ]
