"""The EDGAR filing index page: where a 10-K's Exhibit 13 (annual report) documents are."""

from collections.abc import Callable

from sec_agent.filings.exhibits import annual_report_documents, filing_index_url
from sec_agent.filings.models import FilingRef


def test_filing_index_url_is_the_accession_index_page(filing_10k: FilingRef) -> None:
    assert filing_index_url(filing_10k) == (
        "https://www.sec.gov/Archives/edgar/data/9999999999/999999999925000008/"
        "9999999999-25-000008-index.htm"
    )


def test_annual_report_documents_are_the_html_ex_13_rows_in_sequence_order(
    read_fixture: Callable[[str], bytes],
) -> None:
    # EX-13 and EX-13.2 are HTML; the PDF copy, the primary 10-K and other exhibits are not.
    assert annual_report_documents(read_fixture("sim-filing-index.htm")) == [
        "simb-ex13.htm",
        "simb-ex13_2.htm",
    ]


def test_an_index_without_exhibit_13_lists_nothing() -> None:
    page = (
        b"<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>"
        b'<tr><td>1</td><td>10-K</td><td><a href="/Archives/edgar/data/1/2/a.htm">a.htm</a></td>'
        b"<td>10-K</td></tr><tr><td>2</td><td>EX-130</td>"
        b'<td><a href="/Archives/edgar/data/1/2/b.htm">b.htm</a></td><td>EX-130</td></tr></table>'
    )
    assert annual_report_documents(page) == []
