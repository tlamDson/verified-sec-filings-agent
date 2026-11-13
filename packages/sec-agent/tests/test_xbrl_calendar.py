"""Fiscal year and period of a fact's own period (E1), not of the filing that carried it.

In companyfacts, `fy` and `fp` describe the filing: a 10-K for FY2024 repeats FY2023 and
FY2022 as comparatives, all tagged fy=2024. The calendar maps period end dates to labels.
"""

import datetime as dt
import json

from xbrl_docs import APPLE, NVIDIA, FilingFields, document, entry

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


def test_fiscal_years_off_the_company_offset_are_corrected() -> None:
    # NVIDIA's 10-Ks for the years ended 2013-01-27 and 2014-01-26 say fy 2012 and 2013;
    # from the year ended 2015-01-25 on, fy is the year the fiscal year ends in, which is
    # also NVIDIA's own name for every one of those years ("fiscal 2014").
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("annual", D("2013-01-27")) == FiscalLabel(2013, "FY")
    assert cal.label("annual", D("2014-01-26")) == FiscalLabel(2014, "FY")
    assert cal.label("annual", D("2015-01-25")) == FiscalLabel(2015, "FY")
    assert cal.relabelled == (D("2013-01-27"), D("2014-01-26"))
    # Quarters follow the fiscal year that contains them.
    assert cal.label("quarter", D("2013-10-27")) == FiscalLabel(2014, "Q3")


def test_offset_needs_a_strict_majority() -> None:
    def tenk(end: str, start: str, fy: int, accn: str) -> dict[str, object]:
        return entry(end, 1, accn, start=start, fy=fy, filed=f"{end[:4]}-03-01")

    raw = document(
        {
            "Revenues": {
                "USD": [
                    tenk("2021-12-31", "2021-01-01", 2021, "0000001234-22-000001"),
                    tenk("2022-12-31", "2022-01-01", 2021, "0000001234-23-000001"),
                ]
            }
        }
    )
    cal = _calendar(raw)
    assert cal.relabelled == ()
    assert cal.label("annual", D("2022-12-31")) == FiscalLabel(2021, "FY")


def test_year_ending_in_early_january_belongs_to_the_year_before() -> None:
    def tenk(end: str, start: str, fy: int, accn: str) -> dict[str, object]:
        return entry(end, 1, accn, start=start, fy=fy, filed=f"{end[:4]}-03-01")

    raw = document(
        {
            "Revenues": {
                "USD": [
                    tenk("2020-12-26", "2019-12-29", 2020, "0000001234-21-000001"),
                    tenk("2022-01-01", "2020-12-27", 2021, "0000001234-22-000001"),
                    tenk("2022-12-31", "2022-01-02", 2022, "0000001234-23-000001"),
                ]
            }
        }
    )
    cal = _calendar(raw)
    assert cal.relabelled == ()
    assert cal.label("annual", D("2022-01-01")) == FiscalLabel(2021, "FY")


def test_quarter_of_a_year_not_yet_ended_follows_the_year_before() -> None:
    q1: FilingFields = {"fy": 2099, "fp": "Q1", "form": "10-Q", "filed": "2024-05-01"}  # wrong fy
    tenk = "0000001234-24-000001"
    tenq = "0000001234-24-000002"
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 4, tenk, start="2023-01-01", fy=2023),
                    entry("2024-03-31", 1, tenq, start="2024-01-01", **q1),
                    entry("2023-03-31", 1, tenq, start="2023-01-01", **q1),
                ]
            }
        }
    )
    assert _calendar(raw).label("quarter", D("2024-03-31")) == FiscalLabel(2024, "Q1")


def test_quarter_ending_on_fiscal_year_end_is_q4() -> None:
    cal = FiscalCalendar.from_document(parse_companyfacts(NVIDIA.read_bytes()))
    assert cal.label("quarter", D("2014-01-26")) == FiscalLabel(2014, "Q4")


def test_comparative_with_more_facts_does_not_take_the_own_period() -> None:
    # Apple's FY2009 10-K reports more facts for FY2008 than for FY2009.
    cal = FiscalCalendar.from_document(parse_companyfacts(APPLE.read_bytes()))
    assert cal.label("annual", D("2009-09-26")) == FiscalLabel(2009, "FY")
    assert cal.label("annual", D("2008-09-27")) is None  # no filing kept has it as own period
    assert cal.relabelled == ()


def test_forward_dated_fact_does_not_move_a_filings_own_period() -> None:
    q3: FilingFields = {"fy": 2023, "fp": "Q3", "form": "10-Q", "filed": "2023-11-01"}
    accn = "0000001234-23-000030"
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-09-30", 10, accn, start="2023-07-01", **q3),
                    entry("2022-09-30", 9, accn, start="2022-07-01", **q3),
                ]
            },
            "NetIncomeLoss": {
                "USD": [
                    entry("2023-09-30", 2, accn, start="2023-07-01", **q3),
                    entry("2022-09-30", 1, accn, start="2022-07-01", **q3),
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
