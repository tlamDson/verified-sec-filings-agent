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


def test_unknown_concept_raises() -> None:
    with pytest.raises(KeyError):
        concept("adjusted_ebitda")
