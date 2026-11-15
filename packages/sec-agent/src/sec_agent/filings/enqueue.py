"""List one company's 10-K and 10-Q filings and enqueue one `filing.sections` job each."""

from collections.abc import Callable

from sec_agent.edgar.urls import normalize_cik, submissions_page_url, submissions_url
from sec_agent.filings.models import FilingJob, FilingRef
from sec_agent.filings.submissions import (
    ReportWindow,
    Submissions,
    SubmissionsBlock,
    filings_in_block,
    older_pages,
)
from sec_agent.jobs.protocol import JobQueue

FetchJson = Callable[[str], object]
"""`EdgarClient.get_json` outside tests."""


def list_filings(fetch_json: FetchJson, cik: int | str, window: ReportWindow) -> list[FilingRef]:
    """Filings in `window`, oldest filing first, each accession once."""
    padded = normalize_cik(cik)
    first = Submissions.model_validate(fetch_json(submissions_url(padded)))
    found = filings_in_block(padded, first.filings.recent, window)
    for name in older_pages(first, window):
        page = SubmissionsBlock.model_validate(fetch_json(submissions_page_url(name)))
        found += filings_in_block(padded, page, window)
    unique = {f.accession: f for f in found}
    return sorted(unique.values(), key=lambda f: (f.filing_date, f.accession))


def enqueue_filings(
    fetch_json: FetchJson,
    queue: JobQueue,
    cik: int | str,
    window: ReportWindow,
    index_version: str,
) -> tuple[int, int]:
    """Return (filings found, jobs newly enqueued); re-running enqueues nothing new."""
    filings = list_filings(fetch_json, cik, window)
    jobs = [FilingJob(index_version=index_version, filing=f).to_new_job() for f in filings]
    return len(filings), queue.enqueue(jobs)
