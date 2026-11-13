"""The concept normalisation table: canonical concepts and the US-GAAP tags behind each."""

import re

import pytest

from sec_agent.xbrl.concepts import CONCEPTS, concept, concepts_by_tag

_TAG = re.compile(r"[A-Z][A-Za-z0-9]+")


def test_table_covers_about_thirty_core_concepts() -> None:
    assert 28 <= len(CONCEPTS) <= 40
    names = [c.name for c in CONCEPTS]
    assert len(names) == len(set(names))
    for name in (
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps_diluted",
        "cash_and_equivalents",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "operating_cash_flow",
        "capital_expenditures",
    ):
        assert concept(name).name == name


def test_every_tag_maps_to_exactly_one_concept() -> None:
    refs = [(t.taxonomy, t.tag) for c in CONCEPTS for t in c.tags]
    assert len(refs) == len(set(refs))
    lookup = concepts_by_tag()
    assert len(lookup) == len(refs)
    for c in CONCEPTS:
        assert c.tags, c.name
        for t in c.tags:
            assert _TAG.fullmatch(t.tag), t.tag
            assert lookup[(t.taxonomy, t.tag)].name == c.name


def test_units_and_period_types_are_declared() -> None:
    for c in CONCEPTS:
        assert c.unit in {"USD", "USD/shares", "shares"}, c.name
        assert c.period_type in {"duration", "instant"}, c.name
    assert concept("eps_diluted").unit == "USD/shares"
    assert concept("weighted_shares_diluted").unit == "shares"
    assert concept("total_assets").period_type == "instant"
    assert concept("revenue").period_type == "duration"


def test_revenue_tags_in_priority_order() -> None:
    tags = [t.tag for t in concept("revenue").tags]
    assert tags[0] == "Revenues"
    assert tags.index("RevenueFromContractWithCustomerExcludingAssessedTax") < tags.index(
        "SalesRevenueNet"
    )


def test_tags_with_a_different_meaning_are_not_synonyms() -> None:
    lookup = concepts_by_tag()
    # Net income including noncontrolling interest is not net income to the parent.
    assert ("us-gaap", "ProfitLoss") not in lookup
    # Equity including noncontrolling interest is not stockholders' equity.
    assert (
        "us-gaap",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ) not in lookup
    # Long-term debt including its current portion is not the noncurrent line.
    assert ("us-gaap", "LongTermDebt") not in lookup


@pytest.mark.parametrize(
    "tag",
    [
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "RevenueFromContractWithCustomerProductMember",
        "CostOfGoodsSold",
        "CostOfServices",
    ],
)
def test_partial_lines_are_not_synonyms_for_totals(tag: str) -> None:
    # Goods-only or services-only revenue and cost are parts of the total: a filing that
    # reports goods and services separately must not have one part stored as the total.
    assert ("us-gaap", tag) not in concepts_by_tag()


@pytest.mark.parametrize(
    ("name", "only_tag"),
    [
        # Total dividends cover common, preferred and noncontrolling holders.
        ("dividends_paid", "PaymentsOfDividends"),
        # Common-only dividends are their own concept, never the total.
        ("dividends_paid_common", "PaymentsOfDividendsCommonStock"),
        # Nonoperating interest leaves out interest charged to operations.
        ("interest_expense", "InterestExpense"),
        # The "...EquityMethodInvestments" pretax line is before equity-method income.
        (
            "pretax_income",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ),
        # Marketable securities are one kind of short-term investment, not all of them.
        ("short_term_investments", "ShortTermInvestments"),
        ("marketable_securities_current", "MarketableSecuritiesCurrent"),
        # Depreciation and amortization without depletion is narrower.
        ("depreciation_amortization", "DepreciationDepletionAndAmortization"),
    ],
)
def test_concepts_with_narrower_or_wider_lookalikes_keep_one_tag(name: str, only_tag: str) -> None:
    assert [t.tag for t in concept(name).tags] == [only_tag]


@pytest.mark.parametrize(
    "tag",
    [
        "PaymentsOfDividendsPreferredStockAndPreferenceStock",
        "PaymentsOfDividendsMinorityInterest",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
)
def test_parts_of_a_line_are_not_in_the_table(tag: str) -> None:
    assert ("us-gaap", tag) not in concepts_by_tag()


def test_unknown_concept_raises() -> None:
    with pytest.raises(KeyError):
        concept("adjusted_ebitda")
