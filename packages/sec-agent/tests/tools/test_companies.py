"""CompanyDirectory: tickers, CIKs, names and aliases resolve by CIK (E8); others are out (E7)."""

import pytest

from sec_agent.golden.universe import Company
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.errors import AmbiguousCompanyError, UnknownCompanyError


@pytest.mark.parametrize(
    "text", ["AAPL", "aapl", " AAPL ", "320193", "0000320193", "Apple", "apple inc.", "APPLE INC"]
)
def test_ticker_cik_and_name_resolve_to_one_company(directory: CompanyDirectory, text: str) -> None:
    ref = directory.resolve(text)
    assert (ref.ticker, ref.cik, ref.name) == ("AAPL", 320193, "Apple Inc.")


@pytest.mark.parametrize(("alias", "ticker"), [("FB", "META"), ("facebook", "META")])
def test_renamed_tickers_resolve_to_the_same_cik(
    directory: CompanyDirectory, alias: str, ticker: str
) -> None:
    ref = directory.resolve(alias)
    assert ref.ticker == ticker
    assert ref.cik == directory.resolve(ticker).cik


@pytest.mark.parametrize("text", ["ZZZZ", "Simulated Widgets", "1234567", "", "   "])
def test_a_company_outside_the_universe_is_out_of_scope(
    directory: CompanyDirectory, text: str
) -> None:
    with pytest.raises(UnknownCompanyError, match="not in the"):
        directory.resolve(text)


def test_excluded_companies_are_out_of_scope() -> None:
    directory = CompanyDirectory(
        [
            Company(ticker="SIMA", name="Sim A Corp", sector="Energy", cik=9999999990),
            Company(
                ticker="SIMB", name="Sim B", sector="Energy", cik=9999999991, excluded="no 10-K"
            ),
        ]
    )
    assert directory.resolve("SIMA").cik == 9999999990
    with pytest.raises(UnknownCompanyError):
        directory.resolve("SIMB")


def test_two_companies_with_one_name_are_ambiguous() -> None:
    directory = CompanyDirectory(
        [
            Company(ticker="SIMA", name="Sim Holdings Inc.", sector="Energy", cik=9999999990),
            Company(ticker="SIMB", name="Sim Holdings Corp", sector="Energy", cik=9999999991),
        ]
    )
    with pytest.raises(AmbiguousCompanyError, match="SIMA, SIMB"):
        directory.resolve("sim holdings")


def test_sector_peers_are_the_same_sector_in_cik_order(directory: CompanyDirectory) -> None:
    nvidia = directory.resolve("NVDA")
    peers = directory.sector_peers(nvidia)
    assert nvidia in peers
    assert {p.sector for p in peers} == {"Information Technology"}
    assert [p.cik for p in peers] == sorted(p.cik for p in peers)
    assert "MSFT" in {p.ticker for p in peers}


def test_by_cik_finds_a_company_or_none(directory: CompanyDirectory) -> None:
    ref = directory.by_cik(1045810)
    assert ref is not None
    assert ref.ticker == "NVDA"
    assert directory.by_cik(9999999999) is None
