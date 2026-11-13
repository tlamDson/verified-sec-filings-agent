"""`data.sec.gov/submissions` JSON to the filings the text index needs.

The first page holds `filings.recent` (the latest filings, column by column) and a list of
older pages in `filings.files`. A company with many filings (banks file thousands of
prospectuses) can push its 2020 10-Ks off the first page, so older pages whose date range
reaches the report window are read too.
"""

import datetime as dt
import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sec_agent.filings.models import TEXT_FORMS, FilingRef

_LOOSE = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)
_HTML_DOCUMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.html?")


class ReportWindow(BaseModel):
    """Filings whose period of report (reportDate) falls in [start, end], both included."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: dt.date
    end: dt.date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.start > self.end:
            raise ValueError(f"report window starts after it ends: {self.start} > {self.end}")
        return self


# FY2020 to FY2024 under any fiscal calendar: the earliest period is Q1 of a fiscal 2020
# that ends in January 2020 (quarter ending April 2019); the latest is a fiscal 2024 that
# ends in January 2025. This is a superset; exact fiscal years come from XBRL (s-03).
DEFAULT_WINDOW = ReportWindow(start=dt.date(2019, 4, 1), end=dt.date(2025, 1, 31))


class SubmissionsBlock(BaseModel):
    """Column arrays of filings, as in `filings.recent` and in each older page."""

    model_config = _LOOSE

    accession_number: list[str] = Field(alias="accessionNumber")
    filing_date: list[dt.date] = Field(alias="filingDate")
    report_date: list[str] = Field(alias="reportDate")
    form: list[str]
    primary_document: list[str] = Field(alias="primaryDocument")

    @model_validator(mode="after")
    def _same_length(self) -> Self:
        columns = (self.filing_date, self.report_date, self.form, self.primary_document)
        if any(len(c) != len(self.accession_number) for c in columns):
            raise ValueError("submissions columns differ in length")
        return self


class SubmissionsPage(BaseModel):
    model_config = _LOOSE

    name: str
    filing_from: dt.date = Field(alias="filingFrom")
    filing_to: dt.date = Field(alias="filingTo")


class SubmissionsFilings(BaseModel):
    model_config = _LOOSE

    recent: SubmissionsBlock
    files: list[SubmissionsPage] = Field(default_factory=list[SubmissionsPage])


class Submissions(BaseModel):
    model_config = _LOOSE

    filings: SubmissionsFilings


def filings_in_block(cik: str, block: SubmissionsBlock, window: ReportWindow) -> list[FilingRef]:
    """10-K, 10-Q and their amendments with an HTML primary document inside `window`.

    Rows without a report date cannot be placed in a period and are skipped, as are rows
    whose primary document is not HTML (very old text filings).
    """
    filings: list[FilingRef] = []
    rows = zip(
        block.accession_number,
        block.filing_date,
        block.report_date,
        block.form,
        block.primary_document,
        strict=True,
    )
    for accession, filed, reported, form, document in rows:
        if form not in TEXT_FORMS or not reported or not _HTML_DOCUMENT.fullmatch(document):
            continue
        report_date = dt.date.fromisoformat(reported)
        if not window.start <= report_date <= window.end:
            continue
        filings.append(
            FilingRef.model_validate(
                {
                    "cik": cik,
                    "accession": accession,
                    "form": form,
                    "filing_date": filed,
                    "report_date": report_date,
                    "primary_document": document,
                }
            )
        )
    return filings


def older_pages(submissions: Submissions, window: ReportWindow) -> list[str]:
    """Names of older pages that may hold filings in `window`.

    A filing is filed after its period ends, so a page whose last filing date is before
    the window start holds nothing in the window.
    """
    return [page.name for page in submissions.filings.files if page.filing_to >= window.start]
