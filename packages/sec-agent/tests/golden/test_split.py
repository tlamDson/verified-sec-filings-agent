"""Company-level split: seeded sample of 50 balanced by sector, then 30 train, 10 dev, 10 test.

Test and dev are made of same-sector pairs, so each split can ask peer questions, and
every question in a split is about that split's companies only.
"""

from collections import Counter
from pathlib import Path

import pytest

from sec_agent.golden.split import (
    SPLIT_SEED,
    CompanySplit,
    build_split,
    read_split,
    sample_companies,
    write_split,
)
from sec_agent.golden.universe import Company, load_universe, universe_digest


@pytest.fixture(scope="module")
def universe() -> tuple[Company, ...]:
    return load_universe()


@pytest.fixture(scope="module")
def split(universe: tuple[Company, ...]) -> CompanySplit:
    return build_split(universe, seed=SPLIT_SEED)


def test_split_sizes_are_30_10_10_over_50_distinct_companies(split: CompanySplit) -> None:
    assert Counter(c.split for c in split.companies) == {"train": 30, "dev": 10, "test": 10}
    assert len({c.cik for c in split.companies}) == 50
    assert len(split.of("test")) == 10


def test_split_never_uses_an_excluded_company(split: CompanySplit) -> None:
    assert not any(c.excluded for c in split.companies)
    assert not {"GEV", "SNDK"} & {c.ticker for c in split.companies}


def test_sample_takes_sectors_in_turn_so_sizes_differ_by_at_most_one(
    universe: tuple[Company, ...],
) -> None:
    eligible = Counter(c.sector for c in universe if not c.excluded)
    taken = Counter(c.sector for c in sample_companies(universe, seed=SPLIT_SEED, n=50))
    assert sum(taken.values()) == 50
    assert set(taken) == set(eligible)  # every sector is represented
    top = max(taken.values())
    for sector, n in taken.items():
        # A sector is either exhausted or within one of the largest share.
        assert n == eligible[sector] or n >= top - 1, sector


def test_test_and_dev_are_same_sector_pairs_and_each_pair_sector_stays_in_train(
    split: CompanySplit,
) -> None:
    train_sectors = Counter(c.sector for c in split.of("train"))
    for name in ("test", "dev"):
        sectors = Counter(c.sector for c in split.of(name))
        assert all(n % 2 == 0 for n in sectors.values()), name
        assert all(train_sectors[s] >= 1 for s in sectors), name


def test_split_is_fixed_by_the_seed(universe: tuple[Company, ...], split: CompanySplit) -> None:
    again = build_split(universe, seed=SPLIT_SEED)
    assert again == split
    other = build_split(universe, seed=SPLIT_SEED + 1)
    assert {c.cik for c in other.of("test")} != {c.cik for c in split.of("test")}


def test_split_records_seed_and_universe_digest(
    universe: tuple[Company, ...], split: CompanySplit
) -> None:
    assert split.seed == SPLIT_SEED
    assert split.universe_sha256 == universe_digest(universe)


def test_split_does_not_depend_on_universe_row_order(universe: tuple[Company, ...]) -> None:
    assert build_split(tuple(reversed(universe)), seed=3).companies == (
        build_split(universe, seed=3).companies
    )


def test_lookup_by_ticker_and_cik(split: CompanySplit) -> None:
    first = split.companies[0]
    assert split.by_ticker(first.ticker) == first
    assert split.by_cik(first.cik) == first
    assert split.by_ticker("NOPE") is None


def test_build_split_fails_when_the_universe_is_too_small() -> None:
    small = tuple(
        Company(ticker=f"T{i}", name=f"T{i}", sector="Energy", cik=i + 1) for i in range(10)
    )
    with pytest.raises(ValueError, match="universe"):
        build_split(small, seed=1)


def test_build_split_fails_when_pairs_cannot_fill_test_and_dev() -> None:
    # Five sectors of two: no sector can give a pair and keep one company for train.
    sectors = ("Energy", "Utilities", "Materials", "Real Estate", "Financials")
    tiny = tuple(
        Company(ticker=f"T{i}", name=f"T{i}", sector=sectors[i % 5], cik=i + 1) for i in range(10)
    )
    with pytest.raises(ValueError, match="pair"):
        build_split(tiny, seed=1, n=10, test=2, dev=2)


def test_build_split_rejects_odd_test_or_dev_sizes(universe: tuple[Company, ...]) -> None:
    with pytest.raises(ValueError, match="even"):
        build_split(universe, seed=1, test=9)


def test_write_then_read_round_trips(tmp_path: Path, split: CompanySplit) -> None:
    path = tmp_path / "split.json"
    write_split(path, split)
    assert read_split(path) == split
    assert path.read_text("utf-8").endswith("\n")
