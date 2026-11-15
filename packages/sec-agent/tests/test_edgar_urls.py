"""EDGAR URLs: CIK and accession formats, and the SEC host allow-list."""

import pytest

from sec_agent.edgar.errors import DisallowedHostError
from sec_agent.edgar.urls import (
    COMPANY_TICKERS_URL,
    archive_url,
    check_allowed,
    companyfacts_url,
    normalize_cik,
    submissions_url,
)


@pytest.mark.parametrize("cik", [320193, "320193", "0000320193", " 320193 "])
def test_normalize_cik_pads_to_ten_digits(cik: int | str) -> None:
    assert normalize_cik(cik) == "0000320193"


@pytest.mark.parametrize("cik", [0, -5, "", "abc", "32O193", 12345678901, True])
def test_normalize_cik_rejects_bad_values(cik: int | str) -> None:
    with pytest.raises(ValueError, match="CIK"):
        normalize_cik(cik)


def test_submissions_url() -> None:
    assert submissions_url(320193) == "https://data.sec.gov/submissions/CIK0000320193.json"


def test_companyfacts_url() -> None:
    assert (
        companyfacts_url("320193")
        == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )


@pytest.mark.parametrize("accession", ["0000320193-23-000106", "000032019323000106"])
def test_archive_url(accession: str) -> None:
    assert (
        archive_url(320193, accession, "aapl-20230930.htm")
        == "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )


@pytest.mark.parametrize("accession", ["0000320193-23-00010", "abc", ""])
def test_archive_url_rejects_bad_accession(accession: str) -> None:
    with pytest.raises(ValueError, match="accession"):
        archive_url(320193, accession, "x.htm")


@pytest.mark.parametrize("filename", ["", "../x.htm", "a/b.htm", "a?b=1"])
def test_archive_url_rejects_bad_filename(filename: str) -> None:
    with pytest.raises(ValueError, match="filename"):
        archive_url(320193, "0000320193-23-000106", filename)


@pytest.mark.parametrize(
    "url",
    [
        COMPANY_TICKERS_URL,
        "https://data.sec.gov/submissions/CIK0000320193.json",
        "https://www.sec.gov/Archives/edgar/data/320193/",
    ],
)
def test_allows_sec_hosts(url: str) -> None:
    check_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://data.sec.gov/submissions/CIK0000320193.json",
        "https://example.com/",
        "https://data.sec.gov.evil.example/x",
        "https://user@evil.example/@data.sec.gov",
        "https://data.sec.gov:8443/x",
        "ftp://www.sec.gov/",
        "not a url",
    ],
)
def test_rejects_other_hosts_and_schemes(url: str) -> None:
    with pytest.raises(DisallowedHostError):
        check_allowed(url)
