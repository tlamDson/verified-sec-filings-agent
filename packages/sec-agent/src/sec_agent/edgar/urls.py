"""EDGAR URL builders and the allow-list of SEC hosts the client may call."""

import re
from urllib.parse import urlsplit

from sec_agent.edgar.errors import DisallowedHostError

ALLOWED_HOSTS = frozenset({"www.sec.gov", "data.sec.gov"})
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_CIK = re.compile(r"\d{1,10}")
_ACCESSION = re.compile(r"(\d{10})-?(\d{2})-?(\d{6})")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SUBMISSIONS_PAGE = re.compile(r"CIK\d{10}-submissions-\d{3}\.json")


def normalize_cik(cik: int | str) -> str:
    """Return the CIK as 10 zero-padded digits, as data.sec.gov URLs expect."""
    if isinstance(cik, bool):
        raise ValueError(f"CIK must be an int or a digit string, got {cik!r}")
    text = str(cik).strip()
    if not _CIK.fullmatch(text) or int(text) == 0:
        raise ValueError(f"CIK must be 1 to 10 digits and not zero, got {cik!r}")
    return text.zfill(10)


def submissions_url(cik: int | str) -> str:
    return f"https://data.sec.gov/submissions/CIK{normalize_cik(cik)}.json"


def submissions_page_url(name: str) -> str:
    """URL of an older submissions page named in `filings.files` of the first page."""
    if not _SUBMISSIONS_PAGE.fullmatch(name):
        raise ValueError(f"not a submissions page name: {name!r}")
    return f"https://data.sec.gov/submissions/{name}"


def companyfacts_url(cik: int | str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json"


def archive_url(cik: int | str, accession: str, filename: str) -> str:
    """URL of one document inside a filing folder under /Archives/edgar/data."""
    match = _ACCESSION.fullmatch(accession.strip())
    if match is None:
        raise ValueError(f"accession must look like 0000320193-23-000106, got {accession!r}")
    if not _FILENAME.fullmatch(filename) or ".." in filename:
        raise ValueError(f"filename must be a plain file name, got {filename!r}")
    folder = "".join(match.groups())
    return f"https://www.sec.gov/Archives/edgar/data/{int(normalize_cik(cik))}/{folder}/{filename}"


def check_allowed(url: str) -> None:
    """Raise DisallowedHostError unless `url` is https on an SEC EDGAR host, default port."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise DisallowedHostError(f"not a valid URL: {url!r}") from exc
    if (
        parts.scheme != "https"
        or parts.hostname not in ALLOWED_HOSTS
        or parts.username is not None
        or port is not None
    ):
        raise DisallowedHostError(f"EDGAR client only calls https://{{www,data}}.sec.gov: {url!r}")
