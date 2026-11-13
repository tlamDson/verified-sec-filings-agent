"""Fiscal year and period of a fact's own period (E1), not of the filing that carried it.

In companyfacts, `fy` and `fp` describe the filing: a 10-K for FY2024 repeats FY2023 and
FY2022 as comparatives, all tagged fy=2024. The calendar maps period end dates to labels.
"""

import datetime as dt
import json

from xbrl_docs import APPLE, NVIDIA, document, entry

from sec_agent.xbrl.calendar import FiscalCalendar, FiscalLabel
from sec_agent.xbrl.companyfacts import parse_companyfacts

D = dt.date.fromisoformat


def _calendar(raw: dict[str, object]) -> FiscalCalendar:
    return FiscalCalendar.from_document(parse_companyfacts(json.dumps(raw).encode()))


def test_nvidia_fiscal_year_ends_in_january() -> None:
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("annual", D("2024-01-28")) == FiscalLabel(2024, "FY")
    assert cal.label("annual", D("2023-01-29")) == FiscalLabel(2023, "FY")
    assert cal.label("quarter", D("2023-10-29")) == FiscalLabel(2024, "Q3")
    assert cal.label("nine_months", D("2023-10-29")) == FiscalLabel(2024, "Q3")
    assert cal.label("instant", D("2024-01-28")) == FiscalLabel(2024, "FY")


def test_comparatives_get_their_own_fiscal_year() -> None:
    # FY2023 revenue appears in the FY2024 and FY2025 10-Ks (fy 2024, 2025); it is FY2023.
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("annual", D("2023-01-29")) == FiscalLabel(2023, "FY")


def test_apple_53_week_year_and_quarters() -> None:
    cal = FiscalCalendar.from_document(parse_companyfacts(APPLE.read_bytes()))
    assert cal.label("annual", D("2023-09-30")) == FiscalLabel(2023, "FY")
    assert cal.label("quarter", D("2022-12-31")) == FiscalLabel(2023, "Q1")
    assert cal.label("six_months", D("2023-04-01")) == FiscalLabel(2023, "Q2")
    assert cal.label("instant", D("2023-07-01")) == FiscalLabel(2023, "Q3")


def test_duplicate_fiscal_year_label_is_corrected_by_the_company_offset() -> None:
    # NVIDIA's 10-K for the year ended 2014-01-26 says fy 2013, the same label as the year
    # ended 2013-01-27. Every other NVIDIA year is labelled with its end year.
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("annual", D("2013-01-27")) == FiscalLabel(2013, "FY")
    assert cal.label("annual", D("2014-01-26")) == FiscalLabel(2014, "FY")
    assert cal.relabelled == (D("2014-01-26"),)
    # Quarters follow the fiscal year that contains them.
    assert cal.label("quarter", D("2013-10-27")) == FiscalLabel(2014, "Q3")


def test_quarter_ending_on_fiscal_year_end_is_q4() -> None:
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("quarter", D("2014-01-26")) == FiscalLabel(2014, "Q4")


def test_forward_dated_fact_does_not_move_a_filings_own_period() -> None:
    q3 = {"fy": 2023, "fp": "Q3", "form": "10-Q", "filed": "2023-11-01"}
    accn = "0000001234-23-000030"
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-09-30", 10, accn, start="2023-07-01", **q3),
                    entry("2022-09-30", 9, accn, start="2022-07-01", **q3),
                ]
            },
            # A dividend declared after the quarter, for the next quarter: one stray fact.
            "CommonStockDividendsPerShareDeclared": {
                "USD/shares": [entry("2023-12-31", 1, accn, start="2023-10-01", **q3)]
            },
        }
    )
    cal = _calendar(raw)
    assert cal.label("quarter", D("2023-09-30")) == FiscalLabel(2023, "Q3")
    assert cal.label("quarter", D("2023-12-31")) is None


def test_unknown_end_dates_and_mismatched_ytd_have_no_label() -> None:
    cal = FiscalCalendar.from_document(parse_companyfacts(APPLE.read_bytes()))
    assert cal.label("annual", D("2001-09-29")) is None
    assert cal.label("instant", D("2023-08-15")) is None
    # Six months cannot end on a third-quarter end; nine months cannot end on a second.
    assert cal.label("six_months", D("2023-07-01")) is None
    assert cal.label("nine_months", D("2023-04-01")) is None
    # An annual duration must end on a fiscal year end.
    assert cal.label("annual", D("2023-07-01")) is None


def test_filings_outside_10k_and_10q_do_not_define_periods() -> None:
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 10, "0000001234-24-000001", start="2023-01-01", form="8-K"),
                ]
            }
        }
    )
    assert _calendar(raw).label("annual", D("2023-12-31")) is None
