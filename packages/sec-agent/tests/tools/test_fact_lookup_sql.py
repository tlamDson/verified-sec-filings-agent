"""PostgresFactStore.lookup: the SQL the numeric tools read gives what the in-memory rule gives."""

from collections.abc import Iterator

import pytest
from tools_data import APPLE_CIK, FACTS_VERSION, NVIDIA_CIK

from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.tools.get_fact import GetFactArgs, get_fact
from sec_agent.tools.peers import ComparePeersArgs, compare_peers
from sec_agent.tools.ratios import ComputeRatioArgs, compute_ratio
from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.store import PostgresFactStore
from sec_agent.xbrl.versions import LatestFact


@pytest.fixture
def pg_store(tools_db: str, recorded_facts: dict[int, list[Fact]]) -> Iterator[PostgresFactStore]:
    with PostgresFactStore.connect(tools_db) as store:
        for cik, facts in recorded_facts.items():
            report = NormalizationReport()
            store.write(
                index_version=FACTS_VERSION,
                cik=cik,
                entity_name=f"cik {cik}",
                normalized=Normalized(facts=facts, report=report),
            )
            store.write(  # another snapshot beside it must never leak into reads
                index_version="x-other",
                cik=cik,
                entity_name=f"cik {cik}",
                normalized=Normalized(facts=facts[:5], report=report),
            )
        yield store


def _key(x: LatestFact) -> tuple[object, ...]:
    f = x.fact
    return (f.cik, f.concept, f.unit, str(f.period_start), f.period_end)


@pytest.mark.parametrize(
    ("ciks", "concepts", "years"),
    [
        ((APPLE_CIK,), ("revenue",), (2024,)),
        ((APPLE_CIK, NVIDIA_CIK), ("gross_profit", "revenue", "total_assets"), (2023, 2024)),
        ((NVIDIA_CIK,), ("eps_diluted",), (2013, 2024, 2026)),
        ((APPLE_CIK,), ("revenue",), (1999,)),
    ],
)
def test_sql_lookup_equals_the_in_memory_lookup(
    pg_store: PostgresFactStore,
    memory_query: MemoryFactQuery,
    ciks: tuple[int, ...],
    concepts: tuple[str, ...],
    years: tuple[int, ...],
) -> None:
    args = {
        "index_version": FACTS_VERSION,
        "ciks": ciks,
        "concepts": concepts,
        "fiscal_years": years,
    }
    from_sql = sorted(pg_store.lookup(**args), key=_key)
    from_memory = sorted(memory_query.lookup(**args), key=_key)
    assert from_sql == from_memory
    assert all(x.fact.fiscal_year in years for x in from_sql)


def test_tools_answer_the_same_from_postgres(
    pg_store: PostgresFactStore, directory: CompanyDirectory, facts_ctx: FactsContext
) -> None:
    pg_ctx = FactsContext(companies=directory, facts=pg_store, index_version=FACTS_VERSION)
    fact_args = GetFactArgs(company="NVDA", concept="eps_diluted", fiscal_year=2024)
    assert get_fact(pg_ctx, fact_args) == get_fact(facts_ctx, fact_args)
    ratio_args = ComputeRatioArgs(company="AAPL", ratio="gross_margin", fiscal_year=2023)
    assert compute_ratio(pg_ctx, ratio_args) == compute_ratio(facts_ctx, ratio_args)
    peer_args = ComparePeersArgs(companies=("AAPL", "NVDA"), metric="net_margin", fiscal_year=2024)
    assert compare_peers(pg_ctx, peer_args) == compare_peers(facts_ctx, peer_args)
