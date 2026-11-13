"""companyfacts -> facts: canonical concept, unit (E5), period, fiscal label, every version."""

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from xbrl_docs import APPLE, NVIDIA, document, entry

from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.normalize import Normalized, normalize

D = dt.date.fromisoformat
A1 = "0000001234-24-000001"
A2 = "0000001234-25-000001"


def _run(raw: dict[str, Any]) -> Normalized:
    return normalize(parse_companyfacts(json.dumps(raw).encode()))


def _pick(facts: list[Fact], concept: str, end: str, start: str | None = None) -> list[Fact]:
    return sorted(
        (
            f
            for f in facts
            if f.concept == concept
            and f.period_end == D(end)
            and f.period_start == (None if start is None else D(start))
        ),
        key=lambda f: (f.filed, f.accession),
    )


def test_apple_fy2023_revenue_from_the_asc606_tag() -> None:
    out = normalize(parse_companyfacts(APPLE.read_bytes()))
    versions = _pick(out.facts, "revenue", "2023-09-30", "2022-09-25")
    assert [v.value for v in versions] == [Decimal(383285000000)] * 3
    first = versions[0]
    assert (first.cik, first.unit, first.period_kind) == (320193, "USD", "annual")
    assert (first.fiscal_year, first.fiscal_period) == (2023, "FY")
    assert (first.taxonomy, first.tag) == (
        "us-gaap",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    )
    assert (first.accession, first.form, first.filed) == (
        "0000320193-23-000106",
        "10-K",
        D("2023-11-03"),
    )


def test_apple_fy2009_revenue_from_the_older_tag_keeps_every_version() -> None:
    out = normalize(parse_companyfacts(APPLE.read_bytes()))
    versions = _pick(out.facts, "revenue", "2009-09-26", "2008-09-28")
    assert {v.tag for v in versions} == {"SalesRevenueNet"}
    assert [(v.form, v.value) for v in versions] == [
        ("10-K", Decimal(36537000000)),
        ("10-K/A", Decimal(42905000000)),
        ("10-K", Decimal(42905000000)),
        ("10-K", Decimal(42905000000)),
    ]
    assert {(v.fiscal_year, v.fiscal_period) for v in versions} == {(2009, "FY")}


def test_quarter_and_year_to_date_are_kept_apart() -> None:
    out = normalize(parse_companyfacts(APPLE.read_bytes()))
    quarter = _pick(out.facts, "revenue", "2024-03-30", "2023-12-31")
    ytd = _pick(out.facts, "revenue", "2024-03-30", "2023-10-01")
    assert quarter
    assert ytd
    assert {(f.period_kind, f.fiscal_year, f.fiscal_period) for f in quarter} == {
        ("quarter", 2024, "Q2")
    }
    assert {(f.period_kind, f.fiscal_year, f.fiscal_period) for f in ytd} == {("ytd", 2024, "Q2")}


def test_instants_have_no_start_and_take_the_balance_sheet_date_label() -> None:
    out = normalize(parse_companyfacts(APPLE.read_bytes()))
    assets = _pick(out.facts, "total_assets", "2023-09-30")
    assert assets
    assert {(f.period_kind, f.fiscal_year, f.fiscal_period) for f in assets} == {
        ("instant", 2023, "FY")
    }


def test_eps_keeps_its_unit() -> None:
    out = normalize(parse_companyfacts(NVIDIA.read_bytes()))
    eps = _pick(out.facts, "eps_diluted", "2024-01-28", "2023-01-30")
    assert {f.unit for f in eps} == {"USD/shares"}
    assert [f.value for f in eps] == [Decimal("11.93"), Decimal("1.19"), Decimal("1.19")]


def test_facts_are_unique_per_version_key() -> None:
    for path in (APPLE, NVIDIA):
        out = normalize(parse_companyfacts(path.read_bytes()))
        keys = [f.version_key for f in out.facts]
        assert len(keys) == len(set(keys))
        assert out.report.facts_kept == len(out.facts)


def test_higher_priority_tag_wins_within_one_filing() -> None:
    raw = document(
        {
            "Revenues": {"USD": [entry("2023-12-31", 120, A1, start="2023-01-01")]},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "USD": [
                    entry("2023-12-31", 100, A1, start="2023-01-01"),
                    entry("2022-12-31", 90, A1, start="2022-01-01"),
                ]
            },
        }
    )
    out = _run(raw)
    assert [(f.tag, f.value) for f in _pick(out.facts, "revenue", "2023-12-31", "2023-01-01")] == [
        ("Revenues", Decimal(120))
    ]
    # Where only the lower-priority tag reports a period, it is used.
    assert [f.tag for f in _pick(out.facts, "revenue", "2022-12-31", "2022-01-01")] == [
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    ]
    assert out.report.lower_priority_tag == 1


def test_wrong_unit_is_skipped_and_counted() -> None:
    raw = document(
        {
            "Revenues": {
                "USD": [entry("2023-12-31", 1, A1, start="2023-01-01")],
                "EUR": [entry("2023-12-31", 2, A1, start="2023-01-01")],
            },
            "EarningsPerShareDiluted": {"USD": [entry("2023-12-31", 3, A1, start="2023-01-01")]},
        }
    )
    out = _run(raw)
    assert [(f.concept, f.unit) for f in out.facts] == [("revenue", "USD")]
    assert out.report.unit_mismatch == 2


def test_forms_outside_10k_and_10q_are_skipped_and_counted() -> None:
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 1, A1, start="2023-01-01"),
                    entry("2023-12-31", 1, A2, start="2023-01-01", form="10-K/A"),
                    entry("2023-12-31", 1, "0000001234-24-000009", start="2023-01-01", form="8-K"),
                    entry("2023-12-31", 1, "0000001234-24-000010", start="2023-01-01", form="S-1"),
                ]
            }
        }
    )
    out = _run(raw)
    assert sorted(f.form for f in out.facts) == ["10-K", "10-K/A"]
    assert out.report.form_out_of_scope == 2


def test_period_type_and_duration_mismatches_are_skipped_and_counted() -> None:
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 1, A1, start="2023-01-01"),
                    entry("2023-12-31", 2, A1),  # a duration concept without a start
                    entry("2023-12-31", 3, A1, start="2023-12-01"),  # one month
                ]
            },
            "Assets": {
                "USD": [
                    entry("2023-12-31", 4, A1),
                    entry("2023-12-31", 5, A1, start="2023-01-01"),  # an instant with a start
                ]
            },
        }
    )
    out = _run(raw)
    assert sorted((f.concept, f.value) for f in out.facts) == [
        ("revenue", Decimal(1)),
        ("total_assets", Decimal(4)),
    ]
    assert out.report.period_type_mismatch == 2
    assert out.report.unsupported_duration == 1


def test_conflicting_values_in_one_filing_are_dropped_and_counted() -> None:
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 1, A1, start="2023-01-01"),
                    entry("2023-12-31", 2, A1, start="2023-01-01"),
                ]
            },
            "Assets": {"USD": [entry("2023-12-31", 7, A1), entry("2023-12-31", 7, A1)]},
        }
    )
    out = _run(raw)
    # Identical repeats collapse to one fact; disagreeing values are not guessed between.
    assert [(f.concept, f.value) for f in out.facts] == [("total_assets", Decimal(7))]
    assert out.report.conflicting_values == 2


def test_facts_without_a_fiscal_label_are_kept_and_counted() -> None:
    raw = document(
        {
            "Revenues": {"USD": [entry("2023-12-31", 1, A1, start="2023-01-01")]},
            "Assets": {"USD": [entry("2023-08-15", 2, A1)]},  # not a period end of any filing
        }
    )
    out = _run(raw)
    assets = _pick(out.facts, "total_assets", "2023-08-15")
    assert [(f.fiscal_year, f.fiscal_period) for f in assets] == [(None, None)]
    assert out.report.unlabelled == 1


def test_tags_outside_the_table_are_ignored() -> None:
    raw = document(
        {
            "Revenues": {"USD": [entry("2023-12-31", 1, A1, start="2023-01-01")]},
            "AdvertisingExpense": {"USD": [entry("2023-12-31", 9, A1, start="2023-01-01")]},
        }
    )
    out = _run(raw)
    assert [f.concept for f in out.facts] == ["revenue"]
    assert out.report.entries_seen == 1
