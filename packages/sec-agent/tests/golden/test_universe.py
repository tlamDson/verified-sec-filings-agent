"""The packaged S&P 100 universe: one row per company, CIKs from SEC, exclusions explained."""

from collections import Counter
from pathlib import Path

import pytest

from sec_agent.golden.universe import GICS_SECTORS, Company, load_universe, universe_digest


def test_universe_has_one_row_per_company_with_unique_tickers_and_ciks() -> None:
    universe = load_universe()
    assert len(universe) == 100  # 101 index rows; Alphabet's two share classes are one company
    assert len({c.ticker for c in universe}) == len(universe)
    assert len({c.cik for c in universe}) == len(universe)
    assert {c.sector for c in universe} <= set(GICS_SECTORS)


def test_known_companies_carry_their_sec_cik() -> None:
    by_ticker = {c.ticker: c for c in load_universe()}
    assert by_ticker["AAPL"].cik == 320193
    assert by_ticker["NVDA"].cik == 1045810
    assert by_ticker["GOOGL"].cik == 1652044
    assert "GOOG" not in by_ticker


def test_companies_without_fiscal_2020_to_2024_filings_are_excluded_with_a_reason() -> None:
    excluded = {c.ticker: c.excluded for c in load_universe() if c.excluded}
    assert set(excluded) == {"GEV", "SNDK"}
    assert all(reason for reason in excluded.values())


def test_sector_sizes_match_the_index() -> None:
    sizes = Counter(c.sector for c in load_universe())
    assert sizes["Information Technology"] == 24
    assert sizes["Materials"] == 1
    assert sizes["Real Estate"] == 1


def test_load_universe_rejects_duplicate_ciks(tmp_path: Path) -> None:
    path = tmp_path / "u.csv"
    path.write_text(
        "ticker,name,sector,cik,excluded\nAAA,A Corp,Energy,1,\nBBB,B Corp,Energy,1,\n",
        "utf-8",
    )
    with pytest.raises(ValueError, match="CIK"):
        load_universe(path)


def test_universe_digest_changes_with_any_company_field() -> None:
    a = Company(ticker="AAA", name="A", sector="Energy", cik=1)
    b = Company(ticker="AAA", name="A", sector="Utilities", cik=1)
    assert universe_digest((a,)) == universe_digest((a,))
    assert universe_digest((a,)) != universe_digest((b,))
    assert len(universe_digest((a,))) == 64


def test_fiscal_year_end_comes_from_sec_and_marks_off_calendar_years() -> None:
    by_ticker = {c.ticker: c for c in load_universe()}
    assert by_ticker["AAPL"].fiscal_year_end == "0926"
    assert by_ticker["NVDA"].fiscal_year_end == "0131"
    assert by_ticker["AAPL"].off_calendar
    assert by_ticker["NVDA"].off_calendar
    assert not by_ticker["JPM"].off_calendar
    assert not by_ticker["JNJ"].off_calendar  # 52/53-week year ending near January 1
    assert not by_ticker["INTC"].off_calendar  # 52/53-week year ending late December
