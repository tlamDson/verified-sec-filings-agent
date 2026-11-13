"""Facts in Postgres: idempotent upserts, every version kept, `facts_latest` view (E2)."""

import datetime as dt
from collections.abc import Iterator
from decimal import Decimal

import psycopg
import pytest
from xbrl_docs import APPLE, NVIDIA

from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import Normalized, normalize
from sec_agent.xbrl.schema import apply_schema
from sec_agent.xbrl.store import PostgresFactStore
from sec_agent.xbrl.versions import LatestFact, latest_versions

APPLE_CIK = 320193


@pytest.fixture
def store(facts_db_url: str) -> Iterator[PostgresFactStore]:
    with PostgresFactStore.connect(facts_db_url) as s:
        yield s


@pytest.fixture(scope="module")
def apple() -> Normalized:
    return normalize(parse_companyfacts(APPLE.read_bytes()))


def _write(store: PostgresFactStore, normalized: Normalized, version: str = "v1") -> int:
    return store.write(
        index_version=version, cik=APPLE_CIK, entity_name="Apple Inc.", normalized=normalized
    )


def _summary(items: list[LatestFact]) -> set[tuple[object, ...]]:
    return {
        (
            x.fact.concept,
            x.fact.unit,
            x.fact.period_start,
            x.fact.period_end,
            x.fact.value,
            x.fact.accession,
            x.fact.fiscal_year,
            x.fact.fiscal_period,
            x.original_value,
            x.original_accession,
            x.original_filed,
            x.versions,
            x.restated,
        )
        for x in items
    }


def test_apply_schema_is_idempotent(facts_db_url: str) -> None:
    with psycopg.connect(facts_db_url, autocommit=True) as conn:
        apply_schema(conn)
        apply_schema(conn)


def test_write_stores_every_version(store: PostgresFactStore, apple: Normalized) -> None:
    assert _write(store, apple) == len(apple.facts)
    assert store.count(index_version="v1", cik=APPLE_CIK) == len(apple.facts)


def test_rewriting_the_same_facts_adds_no_rows(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple)
    _write(store, apple)
    assert store.count(index_version="v1", cik=APPLE_CIK) == len(apple.facts)


def test_rewrite_updates_a_changed_value_in_place(
    store: PostgresFactStore, apple: Normalized
) -> None:
    _write(store, apple)
    first = apple.facts[0]
    changed = Normalized(
        facts=[first.model_copy(update={"value": first.value + 1}), *apple.facts[1:]],
        report=apple.report,
    )
    _write(store, changed)
    assert store.count(index_version="v1", cik=APPLE_CIK) == len(apple.facts)
    stored = store.versions(index_version="v1", cik=APPLE_CIK, concept=first.concept)
    match = [f for f in stored if f.version_key == first.version_key]
    assert [f.value for f in match] == [first.value + 1]


def test_index_versions_are_isolated(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple, "v1")
    _write(store, apple, "v2")
    assert store.count(index_version="v1", cik=APPLE_CIK) == len(apple.facts)
    assert store.count(index_version="v2", cik=APPLE_CIK) == len(apple.facts)
    assert store.count(index_version="v3", cik=APPLE_CIK) == 0


def test_stored_versions_round_trip(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple)
    stored = store.versions(index_version="v1", cik=APPLE_CIK)
    assert sorted(stored, key=lambda f: f.version_key) == sorted(
        apple.facts, key=lambda f: f.version_key
    )


def test_latest_view_matches_latest_versions(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple)
    from_sql = store.latest(index_version="v1", cik=APPLE_CIK)
    assert _summary(from_sql) == _summary(latest_versions(apple.facts))


def test_latest_view_for_a_restated_figure(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple)
    rows = [
        x
        for x in store.latest(index_version="v1", cik=APPLE_CIK, concept="net_income")
        if x.fact.period_end == dt.date(2008, 9, 27) and x.fact.period_kind == "annual"
    ]
    assert len(rows) == 1
    assert rows[0].fact.value == Decimal(6119000000)
    assert rows[0].original_value == Decimal(4834000000)
    assert rows[0].restated is True


def test_ingest_record_keeps_the_report(store: PostgresFactStore, apple: Normalized) -> None:
    _write(store, apple)
    record = store.ingest_record(index_version="v1", cik=APPLE_CIK)
    assert record is not None
    assert record.entity_name == "Apple Inc."
    assert record.facts_written == len(apple.facts)
    assert record.report == apple.report


def test_two_companies_do_not_mix(store: PostgresFactStore, apple: Normalized) -> None:
    nvidia = normalize(parse_companyfacts(NVIDIA.read_bytes()))
    _write(store, apple)
    store.write(index_version="v1", cik=1045810, entity_name="NVIDIA CORP", normalized=nvidia)
    assert store.count(index_version="v1", cik=APPLE_CIK) == len(apple.facts)
    assert store.count(index_version="v1", cik=1045810) == len(nvidia.facts)
