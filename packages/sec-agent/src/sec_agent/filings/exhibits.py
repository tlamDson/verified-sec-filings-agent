"""The EDGAR filing index page (`<accession>-index.htm`) to a 10-K's Exhibit 13 documents.

A 10-K may answer Items 1A, 7 and 7A by pointing to the annual report to shareholders,
filed as Exhibit 13 (type `EX-13`, or `EX-13.1`, `EX-13.2` when split). The index page
lists every document of the filing in a table with a Type column; the submissions JSON
does not, so this page is read only for a 10-K that incorporates by reference.
"""

import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit

from sec_agent.edgar.urls import archive_url
from sec_agent.filings.html_text import decode_html
from sec_agent.filings.models import FilingRef

_EXHIBIT_13 = re.compile(r"EX-13(?:\.\d{1,2})?", re.IGNORECASE)
_HTML_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.html?")


def filing_index_url(filing: FilingRef) -> str:
    return archive_url(filing.cik, filing.accession, f"{filing.accession}-index.htm")


def annual_report_documents(index_html: bytes | str) -> list[str]:
    """File names of the HTML Exhibit 13 documents, in the index's (sequence) order."""
    text = decode_html(index_html) if isinstance(index_html, bytes) else index_html
    parser = _RowParser()
    parser.feed(text)
    parser.close()
    names: list[str] = []
    for cells, links in parser.rows:
        if not any(_EXHIBIT_13.fullmatch(cell) for cell in cells):
            continue
        for link in links:
            name = _document_name(link)
            if name is not None and name not in names:
                names.append(name)
    return names


def _document_name(href: str) -> str | None:
    parts = urlsplit(href)
    path = parse_qs(parts.query).get("doc", [parts.path])[0]  # "/ix?doc=/Archives/..."
    name = PurePosixPath(path).name
    return name if _HTML_NAME.fullmatch(name) else None


class _RowParser(HTMLParser):
    """Table rows as (cell texts, link targets)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[list[str], list[str]]] = []
        self._cells: list[str] = []
        self._links: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._cells, self._links, self._cell = [], [], None
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            self._cells.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr":
            self.rows.append((self._cells, self._links))
            self._cells, self._links = [], []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)
