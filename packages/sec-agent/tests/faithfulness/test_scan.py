"""Reading the figures, dates, periods and citation keys out of one sentence of an answer.

Every sentence below is simulated: it stands in for what a model writes.
"""

import datetime as dt
from decimal import Decimal

import pytest

from sec_agent.faithfulness.scan import NumberMention, scan


def _number(text: str) -> NumberMention:
    (mention,) = scan(text).numbers
    return mention


@pytest.mark.parametrize(
    ("text", "value", "tolerance", "unit"),
    [
        ("Revenue was $391.0 billion.", "391000000000", "50000000", "usd"),
        ("Revenue was $391,035 million.", "391035000000", "500000", "usd"),
        ("Revenue was $391,035,000,000.", "391035000000", "0.5", "usd"),
        ("Revenue was $391B.", "391000000000", "500000000", "usd"),
        ("Revenue was $60.9bn.", "60900000000", "50000000", "usd"),
        ("Revenue was USD 60.9 billion.", "60900000000", "50000000", "usd"),
        ("Revenue was 60.9 billion dollars.", "60900000000", "50000000", "usd"),
        ("Gross margin was 46.2%.", "46.2", "0.05", "percent"),
        ("Gross margin was 46.21 percent.", "46.21", "0.005", "percent"),
        ("Diluted EPS was $6.08 per diluted share.", "6.08", "0.005", "per_share"),
        ("Diluted EPS was $6.08.", "6.08", "0.005", "usd"),
        ("The current ratio was 1.07x.", "1.07", "0.005", "times"),
        ("The current ratio was 1.07 times.", "1.07", "0.005", "times"),
        ("It had 15.4 billion diluted shares.", "15400000000", "50000000", "shares"),
        ("Net sales were 391,035.", "391035", "0.5", "none"),
        ("Apple ranked 2nd.", "2", "0", "rank"),
    ],
)
def test_a_figure_is_read_with_its_scale_precision_and_unit(
    text: str, value: str, tolerance: str, unit: str
) -> None:
    """The tolerance is half a unit of the last digit shown: what rounding can explain."""
    mention = _number(text)
    assert (mention.value, mention.tolerance, mention.unit) == (
        Decimal(value),
        Decimal(tolerance),
        unit,
    )
    assert text[mention.start : mention.end] == mention.text
    assert not mention.signed


@pytest.mark.parametrize(
    "text",
    ["Revenue fell (2.5)%.", "Revenue changed by -2.5%.", "Revenue changed by \u22122.5%."],
)
def test_an_explicit_sign_is_kept(text: str) -> None:
    mention = _number(text)
    assert (mention.value, mention.signed, mention.unit) == (Decimal("-2.5"), True, "percent")


def test_a_number_without_a_sign_is_unsigned() -> None:
    mention = _number("Revenue fell 2.5% in the 10-K.")
    assert (mention.value, mention.signed) == (Decimal("2.5"), False)


@pytest.mark.parametrize(
    "text",
    [
        "In fiscal 2024 Apple filed its annual report.",
        "FY2024 and FY24 and FY 2023 are fiscal years.",
        "See the Form 10-K, the 10-K/A and the 10-Q.",
        "Item 1A and Item 7A and Item 7 discuss risks.",
        "Results for Q3 were in Part II.",
        "Apple's 53-week fiscal year and the three months ended then.",
        "The 12 months ended in September.",
        "Apple is in the S&P 100.",
        "The passage says so [0000320193-24-000123/mdna/3].",
    ],
)
def test_years_forms_items_quarters_durations_and_citations_are_not_figures(text: str) -> None:
    assert scan(text).numbers == ()


def test_years_named_in_a_sentence_are_its_periods() -> None:
    found = scan("Revenue grew from fiscal 2023 to FY24, and in 2022 it was lower.")
    assert found.years == frozenset({2022, 2023, 2024})
    assert found.numbers == ()


def test_a_number_written_with_a_separator_or_a_unit_is_a_figure_not_a_year() -> None:
    found = scan("It employed 2,024 people and spent $2024 on SIM supplies.")
    assert [m.value for m in found.numbers] == [Decimal(2024), Decimal(2024)]
    assert found.years == frozenset()


@pytest.mark.parametrize(
    ("text", "date"),
    [
        ("The fiscal year ended September 28, 2024.", dt.date(2024, 9, 28)),
        ("The fiscal year ended Sep 28, 2024.", dt.date(2024, 9, 28)),
        ("The fiscal year ended Sept. 28, 2024.", dt.date(2024, 9, 28)),
        ("The fiscal year ended January 28th, 2024.", dt.date(2024, 1, 28)),
        ("The fiscal year ended 2024-09-28.", dt.date(2024, 9, 28)),
        ("The fiscal year ended 9/28/2024.", dt.date(2024, 9, 28)),
    ],
)
def test_a_full_date_is_read_and_its_year_is_a_period(text: str, date: dt.date) -> None:
    found = scan(text)
    (mention,) = found.dates
    assert mention.date == date
    assert text[mention.start : mention.end] == mention.text
    assert found.numbers == ()
    assert date.year in found.years


def test_a_date_that_does_not_exist_is_kept_without_a_value() -> None:
    (mention,) = scan("It ended February 30, 2024.").dates
    assert mention.date is None


def test_a_month_and_year_is_a_period_not_a_date() -> None:
    found = scan("NVIDIA's fiscal 2024 ended in January 2024.")
    assert (found.dates, found.numbers, found.years) == ((), (), frozenset({2024}))


def test_citation_keys_are_read_from_brackets() -> None:
    text = (
        "Two passages [9999999999-25-000008/mdna/3; 9999999999-25-000008/risk_factors/1] "
        "and a filing [0000320193-25-000079]."
    )
    keys = [c.key for c in scan(text).citations]
    assert keys == [
        "9999999999-25-000008/mdna/3",
        "9999999999-25-000008/risk_factors/1",
        "0000320193-25-000079",
    ]
    first = scan(text).citations[0]
    assert text[first.start : first.end] == first.key


def test_a_bracket_without_a_citation_key_is_ordinary_text() -> None:
    found = scan("See note [1].")
    assert found.citations == ()
    assert [m.value for m in found.numbers] == [Decimal(1)]


def test_offsets_are_shifted_by_the_sentence_start() -> None:
    mention = scan("Margin was 46.2%.", offset=100).numbers[0]
    assert (mention.start, mention.end) == (111, 116)


@pytest.mark.parametrize(
    "text", ["Its H100 and A17 chips.", "COVID-19 hurt sales.", "It sells 5G phones."]
)
def test_digits_inside_a_name_are_not_figures(text: str) -> None:
    assert scan(text).numbers == ()


def test_a_malformed_citation_key_is_read_whole() -> None:
    text = "It says so [9999999999-25-000008/mdna; 9999999999-25-000008/mdna/3x]."
    assert [c.key for c in scan(text).citations] == [
        "9999999999-25-000008/mdna",
        "9999999999-25-000008/mdna/3x",
    ]
    assert scan(text).numbers == ()
