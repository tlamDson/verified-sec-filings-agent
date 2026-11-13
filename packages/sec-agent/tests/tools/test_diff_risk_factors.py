"""diff_risk_factors: two 10-K Item 1A sections of one company, by fiscal year, from Postgres.

Every company, filing and paragraph here is simulated.
"""

import datetime as dt
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from retrieval_fakes import HASH_SPEC
from tools_data import FACTS_VERSION, SIM_CIK

from sec_agent.filings.models import FilingForm, FilingRef, IndexedFiling, Section, SectionKey
from sec_agent.filings.store import PostgresChunkStore
from sec_agent.golden.universe import Company
from sec_agent.retrieval.space import make_space
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import TextContext
from sec_agent.tools.errors import InvalidRequestError, UnknownCompanyError
from sec_agent.tools.risk_factors import DiffRiskFactorsArgs, diff_risk_factors
from sec_agent.tools.risk_sections import PostgresRiskSections
from sec_agent.xbrl.models import Fact, NormalizationReport
from sec_agent.xbrl.normalize import Normalized
from sec_agent.xbrl.store import PostgresFactStore

TEXT_VERSION = "c-sim"
SIMT_CIK = 9999999997  # a simulated retailer that names its fiscal year by the year it starts

INTRO = "Investing in a simulated company involves risks."
SUPPLY = "Supply of simulated parts may be interrupted by a single supplier."
FLOOD = "Our simulated factory is located in one region exposed to floods."
DIST_3 = "We depend on three distributors for most of our simulated sales."
DIST_2 = "We depend on two distributors for most of our simulated sales."
EXPORT = "New export controls may restrict sales of simulated widgets abroad."
CYBER = "A simulated cyber attack could disrupt our order systems."

DIRECTORY = CompanyDirectory(
    [
        Company(ticker="SIMW", name="Simulated Widgets Inc.", sector="Industrials", cik=SIM_CIK),
        Company(ticker="SIMT", name="Simulated Retail Corp", sector="Industrials", cik=SIMT_CIK),
        Company(ticker="SIMN", name="Simulated Nothing Co", sector="Industrials", cik=9999999996),
    ]
)


def _filing(cik: int, n: int, form: FilingForm, filed: str, report: str) -> FilingRef:
    return FilingRef(
        cik=str(cik),
        accession=f"{cik:010d}-{filed[2:4]}-{n:06d}",
        form=form,
        filing_date=dt.date.fromisoformat(filed),
        report_date=dt.date.fromisoformat(report),
        primary_document=f"sim-{n}.htm",
    )


def _store(
    store: PostgresChunkStore,
    ref: FilingRef,
    paragraphs: list[str],
    *,
    version: str = TEXT_VERSION,
    key: SectionKey = "risk_factors",
) -> None:
    text = "\n".join(paragraphs)
    section = Section(
        key=key, item="Item 1A", heading="Risk Factors", text=text, token_count=len(text.split())
    )
    store.replace(IndexedFiling(index_version=version, filing=ref, sections=(section,), chunks=()))


def _fy_label(cik: int, end: dt.date, fiscal_year: int) -> Fact:
    return Fact(
        cik=cik,
        concept="revenue",
        unit="USD",
        period_kind="annual",
        period_start=end - dt.timedelta(days=364),
        period_end=end,
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        value=Decimal(1),
        taxonomy="us-gaap",
        tag="Revenues",
        accession=f"{cik:010d}-99-{fiscal_year:06d}",
        form="10-K",
        filed=end + dt.timedelta(days=40),
    )


@pytest.fixture
def ctx(tools_db: str, tools_conn: psycopg.Connection[Any]) -> TextContext:
    with PostgresChunkStore.connect(tools_db) as store:
        k22 = _filing(SIM_CIK, 1, "10-K", "2023-02-20", "2022-12-31")
        k23 = _filing(SIM_CIK, 2, "10-K", "2024-02-20", "2023-12-31")
        k23a = _filing(SIM_CIK, 3, "10-K/A", "2024-05-01", "2023-12-31")
        k24 = _filing(SIM_CIK, 4, "10-K", "2025-02-20", "2024-12-31")
        q24 = _filing(SIM_CIK, 5, "10-Q", "2024-08-01", "2024-06-30")
        _store(store, k22, [INTRO, SUPPLY])
        _store(store, k23, [INTRO, SUPPLY, FLOOD])
        _store(store, k23a, [INTRO, SUPPLY, FLOOD, DIST_3])  # the amendment supersedes
        _store(store, k24, [INTRO, DIST_2, SUPPLY, EXPORT, CYBER])
        _store(store, q24, [INTRO, "A quarterly risk update."])
        _store(store, k24, [INTRO], version="c-other")  # another text index version
        t23 = _filing(SIMT_CIK, 1, "10-K", "2023-03-20", "2023-01-28")
        t24 = _filing(SIMT_CIK, 2, "10-K", "2024-03-20", "2024-02-03")
        _store(store, t23, [INTRO])
        _store(store, t24, [INTRO, EXPORT])
    with PostgresFactStore.connect(tools_db) as facts:
        labels = [
            _fy_label(SIMT_CIK, t23.report_date, 2022),
            _fy_label(SIMT_CIK, t24.report_date, 2023),
        ]
        facts.write(
            index_version=FACTS_VERSION,
            cik=SIMT_CIK,
            entity_name="Simulated Retail Corp",
            normalized=Normalized(facts=labels, report=NormalizationReport()),
        )
    return TextContext(
        companies=DIRECTORY,
        conn=tools_conn,
        space=make_space(TEXT_VERSION, HASH_SPEC),
        sections=PostgresRiskSections(tools_conn),
        facts_version=FACTS_VERSION,
    )


def test_latest_10k_against_the_year_before(ctx: TextContext) -> None:
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMW"))
    assert result.status == "compared"
    assert result.current is not None
    assert result.previous is not None
    assert (result.current.fiscal_year, result.current.form) == (2024, "10-K")
    assert result.current.fiscal_year_basis == "report_date"
    # FY2023 was amended with a new Item 1A: the later filing is the one compared (E2)
    assert (result.previous.fiscal_year, result.previous.form) == (2023, "10-K/A")
    assert result.previous.accession == "9999999999-24-000003"
    assert result.current.source_url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert (result.added, result.removed, result.changed, result.unchanged) == (2, 1, 1, 2)
    kinds = [(c.kind, c.text or c.previous_text) for c in result.changes]
    assert kinds == [("added", EXPORT), ("added", CYBER), ("changed", DIST_2), ("removed", FLOOD)]
    changed = result.changes[2]
    assert changed.previous_text == DIST_3
    assert changed.similarity is not None


def test_change_offsets_point_into_the_section_text(ctx: TextContext) -> None:
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMW"))
    current = "\n".join([INTRO, DIST_2, SUPPLY, EXPORT, CYBER])
    previous = "\n".join([INTRO, SUPPLY, FLOOD, DIST_3])
    for change in result.changes:
        if change.text is not None:
            assert change.char_start is not None
            assert change.char_end is not None
            assert current[change.char_start : change.char_end] == change.text
        if change.previous_text is not None:
            assert change.previous_char_start is not None
            assert change.previous_char_end is not None
            assert previous[change.previous_char_start : change.previous_char_end] == (
                change.previous_text
            )


def test_explicit_years(ctx: TextContext) -> None:
    result = diff_risk_factors(
        ctx, DiffRiskFactorsArgs(company="SIMW", fiscal_year=2023, compare_to=2022)
    )
    assert result.current is not None
    assert result.previous is not None
    assert (result.current.fiscal_year, result.previous.fiscal_year) == (2023, 2022)
    assert [(c.kind, c.text) for c in result.changes] == [("added", FLOOD), ("added", DIST_3)]


def test_fiscal_year_comes_from_xbrl_when_the_facts_label_it(ctx: TextContext) -> None:
    """E1: the year ended 2024-02-03 is this simulated retailer's fiscal 2023."""
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMT", fiscal_year=2023))
    assert result.status == "compared"
    assert result.current is not None
    assert result.previous is not None
    assert result.current.report_date == dt.date(2024, 2, 3)
    assert result.current.fiscal_year_basis == "xbrl"
    assert result.previous.report_date == dt.date(2023, 1, 28)
    assert [(c.kind, c.text) for c in result.changes] == [("added", EXPORT)]


def test_a_missing_year_is_reported_not_guessed(ctx: TextContext) -> None:
    """E12: there is no fiscal 2020 10-K, so nothing is compared."""
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMW", fiscal_year=2020))
    assert result.status == "not_found"
    assert result.reason is not None
    assert "2020" in result.reason
    assert result.changes == ()
    assert result.current is None


def test_a_company_without_any_10k_text(ctx: TextContext) -> None:
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMN"))
    assert result.status == "not_found"


def test_long_diffs_are_cut_and_say_so(ctx: TextContext) -> None:
    result = diff_risk_factors(ctx, DiffRiskFactorsArgs(company="SIMW", max_changes=1))
    assert len(result.changes) == 1
    assert result.changes_total == 4


def test_a_year_against_itself_is_refused(ctx: TextContext) -> None:
    with pytest.raises(InvalidRequestError):
        diff_risk_factors(
            ctx, DiffRiskFactorsArgs(company="SIMW", fiscal_year=2024, compare_to=2024)
        )


def test_unknown_company(ctx: TextContext) -> None:
    with pytest.raises(UnknownCompanyError):
        diff_risk_factors(ctx, DiffRiskFactorsArgs(company="AAPL"))
