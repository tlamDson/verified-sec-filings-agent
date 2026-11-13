"""`data.sec.gov/submissions` JSON to the 10-K and 10-Q filings the text index needs."""

import datetime as dt
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from sec_agent.edgar.urls import submissions_page_url
from sec_agent.filings.models import FilingRef
from sec_agent.filings.submissions import (
    DEFAULT_WINDOW,
    ReportWindow,
    Submissions,
    SubmissionsBlock,
    filings_in_block,
    older_pages,
)

CIK = "9999999999"


def test_default_window_covers_fiscal_2020_to_2024_on_any_calendar() -> None:
    # Earliest: Q1 of a FY2020 that ends in January 2020. Latest: a FY2024 ending January 2025.
    assert DEFAULT_WINDOW.start == dt.date(2019, 4, 1)
    assert DEFAULT_WINDOW.end == dt.date(2025, 1, 31)


def test_window_must_not_be_reversed() -> None:
    with pytest.raises(ValidationError):
        ReportWindow(start=dt.date(2025, 1, 1), end=dt.date(2024, 1, 1))


def test_recent_block_keeps_text_forms_with_html_documents_inside_the_window(
    read_json_fixture: Callable[[str], object],
) -> None:
    submissions = Submissions.model_validate(read_json_fixture("sim-submissions.json"))
    filings = filings_in_block(CIK, submissions.filings.recent, DEFAULT_WINDOW)
    assert [(f.accession, f.form) for f in filings] == [
        ("9999999999-25-000009", "10-K/A"),
        ("9999999999-25-000008", "10-K"),
        ("9999999999-24-000005", "10-Q"),
        ("9999999999-20-000002", "10-K"),
    ]
    amendment = filings[0]
    assert amendment == FilingRef(
        cik=CIK,
        accession="9999999999-25-000009",
        form="10-K/A",
        filing_date=dt.date(2025, 4, 10),
        report_date=dt.date(2024, 12, 31),
        primary_document="simw-20241231a.htm",
    )
    assert amendment.document_url == (
        "https://www.sec.gov/Archives/edgar/data/9999999999/999999999925000009/simw-20241231a.htm"
    )


def test_only_older_pages_that_reach_into_the_window_are_needed(
    read_json_fixture: Callable[[str], object],
) -> None:
    submissions = Submissions.model_validate(read_json_fixture("sim-submissions.json"))
    assert older_pages(submissions, DEFAULT_WINDOW) == ["CIK9999999999-submissions-001.json"]


def test_older_page_parses_as_a_block(read_json_fixture: Callable[[str], object]) -> None:
    block = SubmissionsBlock.model_validate(read_json_fixture("sim-submissions-001.json"))
    filings = filings_in_block(CIK, block, DEFAULT_WINDOW)
    assert [f.accession for f in filings] == ["9999999999-20-000002", "9999999999-19-000001"]


def test_block_columns_must_have_equal_length() -> None:
    with pytest.raises(ValidationError, match="length"):
        SubmissionsBlock.model_validate(
            {
                "accessionNumber": ["9999999999-25-000001"],
                "filingDate": [],
                "reportDate": [],
                "form": [],
                "primaryDocument": [],
            }
        )


def test_submissions_page_url() -> None:
    assert submissions_page_url("CIK9999999999-submissions-001.json") == (
        "https://data.sec.gov/submissions/CIK9999999999-submissions-001.json"
    )
    with pytest.raises(ValueError, match="submissions page"):
        submissions_page_url("../../files/company_tickers.json")
