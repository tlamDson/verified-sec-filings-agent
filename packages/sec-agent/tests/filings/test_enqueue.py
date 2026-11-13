"""Listing a company's filings from submissions JSON and enqueueing one job per filing."""

from collections.abc import Callable

from sec_agent.edgar.urls import submissions_page_url, submissions_url
from sec_agent.filings.enqueue import enqueue_filings, list_filings
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import FILING_SECTIONS_KIND, FilingJob
from sec_agent.filings.submissions import DEFAULT_WINDOW
from sec_agent.jobs.postgres import PostgresJobQueue

CIK = "9999999999"


def _fetcher(read_json_fixture: Callable[[str], object], log: list[str]) -> Callable[[str], object]:
    pages = {
        submissions_url(CIK): "sim-submissions.json",
        submissions_page_url("CIK9999999999-submissions-001.json"): "sim-submissions-001.json",
    }

    def fetch_json(url: str) -> object:
        log.append(url)
        return read_json_fixture(pages[url])

    return fetch_json


def test_list_filings_reads_older_pages_dedups_and_sorts_by_filing_date(
    read_json_fixture: Callable[[str], object],
) -> None:
    log: list[str] = []
    filings = list_filings(_fetcher(read_json_fixture, log), 9999999999, DEFAULT_WINDOW)
    assert log == [
        submissions_url(CIK),
        submissions_page_url("CIK9999999999-submissions-001.json"),
    ]
    assert [f.accession for f in filings] == [
        "9999999999-19-000001",
        "9999999999-20-000002",
        "9999999999-24-000005",
        "9999999999-25-000008",
        "9999999999-25-000009",
    ]


def test_enqueue_filings_adds_one_job_per_filing_once(
    db_url: str, read_json_fixture: Callable[[str], object]
) -> None:
    version = index_version(ChunkConfig())
    fetch_json = _fetcher(read_json_fixture, [])
    with PostgresJobQueue.connect(db_url) as queue:
        assert enqueue_filings(fetch_json, queue, CIK, DEFAULT_WINDOW, version) == (5, 5)
        assert enqueue_filings(fetch_json, queue, CIK, DEFAULT_WINDOW, version) == (5, 0)
        job = queue.claim("t", [FILING_SECTIONS_KIND], 30.0)
    assert job is not None
    payload = FilingJob.model_validate(job.payload)
    assert payload.index_version == version
    assert payload.filing.accession == "9999999999-19-000001"
    assert job.key == f"{version}/9999999999-19-000001"
