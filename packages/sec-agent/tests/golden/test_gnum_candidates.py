"""G-num candidates from XBRL facts: values, fiscal-period traps, growth, ratios, peers.

Every expected number is a value SEC reported in the recorded companyfacts fixtures, or
arithmetic on those values; the generator never invents one.
"""

import datetime as dt
from decimal import Decimal

from sec_agent.golden.gnum.candidates import (
    GNumCompany,
    growth_questions,
    is_fiscal_period_trap,
    value_questions,
)
from sec_agent.golden.gnum.models import CompanyAnswer, NumberAnswer, NumQuestion
from sec_agent.golden.gnum.peers import peer_questions
from sec_agent.golden.gnum.ratios import RATIOS, ratio_questions
from sec_agent.golden.split import SplitCompany
from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.versions import LatestFact

YEARS = (2022, 2023, 2024, 2025)
SIX = Decimal("0.000001")


def _find(
    questions: list[NumQuestion], concept: str, fy: int, fp: str, kind: str = "annual"
) -> NumQuestion:
    hits = [
        q
        for q in questions
        if q.concept == concept
        and q.fiscal_year == fy
        and q.fiscal_period == fp
        and q.period_kind == kind
    ]
    assert len(hits) == 1, (concept, fy, fp, kind, len(hits))
    return hits[0]


def _number(q: NumQuestion) -> NumberAnswer:
    assert isinstance(q.answer, NumberAnswer)
    return q.answer


def _fact(
    start: dt.date | None, end: dt.date, fy: int, *, value: str = "1", accession: str = ""
) -> Fact:
    return Fact(
        cik=1,
        concept="revenue",
        unit="USD",
        period_kind="annual" if start else "instant",
        period_start=start,
        period_end=end,
        fiscal_year=fy,
        fiscal_period="FY",
        value=Decimal(value),
        taxonomy="us-gaap",
        tag="Revenues",
        accession=accession or f"0000000001-{fy % 100:02d}-000001",
        form="10-K",
        filed=end + dt.timedelta(days=40),
    )


def test_a_quarter_inside_one_calendar_year_is_a_value_question(apple: GNumCompany) -> None:
    questions = value_questions(apple, years=YEARS, index_version="v1")
    q = _find(questions, "revenue", 2023, "Q3", "quarter")
    assert q.qtype == "value"
    assert q.split == "test"
    assert q.tickers == ("AAPL",)
    assert q.ciks == (320193,)
    assert q.index_version == "v1"
    a = _number(q)
    assert (a.value, a.unit) == (Decimal(81797000000), "USD")
    assert (a.period_start, a.period_end) == (dt.date(2023, 4, 2), dt.date(2023, 7, 1))
    assert "Apple Inc. (AAPL)" in q.question
    assert "revenue" in q.question
    assert "third quarter of fiscal year 2023" in q.question
    assert [s.accession for s in q.sources] == ["0000320193-24-000081"]


def test_a_fiscal_year_that_spans_two_calendar_years_is_a_fiscal_period_question(
    apple: GNumCompany,
) -> None:
    q = _find(value_questions(apple, years=YEARS, index_version="v1"), "revenue", 2023, "FY")
    assert q.qtype == "fiscal_period"
    a = _number(q)
    assert a.value == Decimal(383285000000)
    assert a.period_end == dt.date(2023, 9, 30)
    # The question names the fiscal period only: finding its dates is the trap (E1).
    assert "fiscal year 2023" in q.question
    assert "2022" not in q.question
    assert "September" not in q.question


def test_nvidia_first_quarter_of_fiscal_2025_ends_in_april_2024(nvidia: GNumCompany) -> None:
    questions = value_questions(nvidia, years=YEARS, index_version="v1")
    q = _find(questions, "revenue", 2025, "Q1", "quarter")
    assert q.qtype == "fiscal_period"
    a = _number(q)
    assert (a.value, a.period_end) == (Decimal(26044000000), dt.date(2024, 4, 28))
    assert "first quarter of fiscal year 2025" in q.question


def test_balance_sheet_values_are_asked_at_the_end_of_the_period(apple: GNumCompany) -> None:
    questions = value_questions(apple, years=YEARS, index_version="v1")
    q = _find(questions, "total_assets", 2024, "FY", "instant")
    a = _number(q)
    assert (a.value, a.period_start, a.period_end) == (
        Decimal(364980000000),
        None,
        dt.date(2024, 9, 28),
    )
    assert "at the end of fiscal year 2024" in q.question


def test_restated_figures_use_the_latest_filed_version_and_keep_the_original(
    nvidia: GNumCompany,
) -> None:
    # NVIDIA's FY2023 diluted EPS: 1.74 as first filed, 0.17 after the 2024 split (E2).
    questions = value_questions(nvidia, years=YEARS, index_version="v1")
    q = _find(questions, "eps_diluted", 2023, "FY")
    a = _number(q)
    assert (a.value, a.unit) == (Decimal("0.17"), "USD/shares")
    (source,) = q.sources
    assert source.restated is True
    assert source.original_value == Decimal("1.74")


def test_only_labelled_annual_quarter_and_instant_facts_within_the_years_are_asked(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    for company in (apple, nvidia):
        questions = value_questions(company, years=(2023, 2024), index_version="v1")
        assert questions
        assert {q.fiscal_year for q in questions} == {2023, 2024}
        assert {q.period_kind for q in questions} <= {"annual", "quarter", "instant"}
        assert {q.qtype for q in questions} == {"value", "fiscal_period"}


def test_trap_rule_is_whether_the_period_leaves_the_calendar_year_its_label_names() -> None:
    assert not is_fiscal_period_trap(_fact(dt.date(2023, 1, 1), dt.date(2023, 12, 31), 2023))
    assert is_fiscal_period_trap(_fact(dt.date(2022, 9, 25), dt.date(2023, 9, 30), 2023))
    assert is_fiscal_period_trap(_fact(dt.date(2023, 1, 30), dt.date(2024, 1, 28), 2024))
    assert not is_fiscal_period_trap(_fact(None, dt.date(2024, 1, 28), 2024))
    assert is_fiscal_period_trap(_fact(None, dt.date(2023, 12, 30), 2024))


def test_growth_is_percent_change_from_the_same_period_a_year_before(apple: GNumCompany) -> None:
    questions = growth_questions(apple, years=YEARS, index_version="v1")
    q = _find(questions, "revenue", 2023, "FY")
    assert q.qtype == "yoy_growth"
    a = _number(q)
    assert a.unit == "percent"
    assert a.value == Decimal("-2.800461")  # (383,285 - 394,328) / 394,328, in percent
    assert [s.fiscal_year for s in q.sources] == [2022, 2023]
    assert "fiscal year 2022" in q.question
    assert "fiscal year 2023" in q.question
    for each in questions:
        prior, current = each.sources
        assert (prior.fiscal_period, prior.unit) == (current.fiscal_period, current.unit)
        assert prior.fiscal_year == current.fiscal_year - 1
        expected = (current.value - prior.value) / abs(prior.value) * 100
        assert _number(each).value == expected.quantize(SIX)


def test_quarterly_growth_compares_the_same_fiscal_quarter(apple: GNumCompany) -> None:
    questions = growth_questions(apple, years=YEARS, index_version="v1")
    q = _find(questions, "revenue", 2024, "Q1", "quarter")
    assert "first quarter of fiscal year 2023" in q.question
    assert "first quarter of fiscal year 2024" in q.question


def _latest(fact: Fact) -> LatestFact:
    return LatestFact(
        fact=fact,
        original_value=fact.value,
        original_accession=fact.accession,
        original_filed=fact.filed,
        versions=1,
        restated=False,
    )


def test_growth_from_zero_is_not_asked() -> None:
    company = SplitCompany(
        ticker="SYN", name="Synthetic Test Corp", sector="Energy", cik=1, split="dev"
    )
    facts = (
        _latest(_fact(dt.date(2022, 1, 1), dt.date(2022, 12, 31), 2022, value="0")),
        _latest(_fact(dt.date(2023, 1, 1), dt.date(2023, 12, 31), 2023, value="5")),
    )
    synthetic = GNumCompany(company=company, facts=facts)
    assert growth_questions(synthetic, years=(2023,), index_version="v1") == []


def test_ratios_are_percentages_of_two_facts_of_the_same_period(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    assert set(RATIOS) == {"gross_margin", "operating_margin", "net_margin", "effective_tax_rate"}
    q = _find(ratio_questions(apple, years=YEARS, index_version="v1"), "gross_margin", 2023, "FY")
    assert q.qtype == "ratio"
    assert _number(q) == NumberAnswer(
        value=Decimal("44.131130"),  # 169,148 / 383,285
        unit="percent",
        period_start=dt.date(2022, 9, 25),
        period_end=dt.date(2023, 9, 30),
    )
    assert [s.concept for s in q.sources] == ["gross_profit", "revenue"]
    assert "gross margin" in q.question
    nvidia_ratios = ratio_questions(nvidia, years=YEARS, index_version="v1")
    tax = _find(nvidia_ratios, "effective_tax_rate", 2023, "FY")
    numerator, denominator = tax.sources
    assert (numerator.value, denominator.value) == (Decimal(-187000000), Decimal(4181000000))
    assert _number(tax).value == (Decimal(-187000000) / Decimal(4181000000) * 100).quantize(SIX)
    for company in (apple, nvidia):
        for r in ratio_questions(company, years=YEARS, index_version="v1"):
            num, den = r.sources
            assert den.value > 0
            assert (num.period_start, num.period_end) == (den.period_start, den.period_end)


def test_peer_question_compares_each_companys_own_fiscal_year(
    apple: GNumCompany, nvidia: GNumCompany
) -> None:
    questions = peer_questions(apple, nvidia, years=YEARS, index_version="v1", seed=1)
    q = _find(questions, "revenue", 2024, "FY")
    assert q.qtype == "peer_comparison"
    assert set(q.ciks) == {320193, 1045810}
    assert q.answer == CompanyAnswer(ticker="AAPL", cik=320193)
    ends = {s.cik: s.period_end for s in q.sources}
    assert ends == {320193: dt.date(2024, 9, 28), 1045810: dt.date(2024, 1, 28)}  # E3
    assert "AAPL" in q.question
    assert "NVDA" in q.question
    assert "its own fiscal year 2024" in q.question
    for each in questions:
        a, b = each.sources
        assert a.value != b.value
        assert a.fiscal_year == b.fiscal_year
        winner = max((a, b), key=lambda s: s.value)
        assert isinstance(each.answer, CompanyAnswer)
        assert each.answer.cik == winner.cik


def test_question_ids_are_stable_and_unique(apple: GNumCompany, nvidia: GNumCompany) -> None:
    def ids() -> list[str]:
        questions = (
            value_questions(apple, years=YEARS, index_version="v1")
            + growth_questions(apple, years=YEARS, index_version="v1")
            + ratio_questions(apple, years=YEARS, index_version="v1")
            + peer_questions(apple, nvidia, years=YEARS, index_version="v1", seed=1)
        )
        return [q.id for q in questions]

    first = ids()
    assert first == ids()
    assert len(set(first)) == len(first)
    assert all(i.startswith("gnum-") for i in first)
    one = peer_questions(apple, nvidia, years=YEARS, index_version="v1", seed=1)
    other = peer_questions(nvidia, apple, years=YEARS, index_version="v1", seed=2)
    assert {q.id for q in one} == {q.id for q in other}  # pair order and seed do not matter
