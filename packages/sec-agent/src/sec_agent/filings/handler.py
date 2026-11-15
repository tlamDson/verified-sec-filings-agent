"""The `filing.sections` job: fetch a filing's primary document, index it, store it.

A 10-K that incorporates items by reference to its annual report also has its filing index
page and each HTML Exhibit 13 fetched (see `incorporation`); a missing index page or exhibit
leaves the 10-K's own text in place.

Idempotent: the store replaces the rows keyed by (index_version, accession), so a second
delivery of the same job changes nothing.
"""

import logging
from collections.abc import Callable

from pydantic import ValidationError

from sec_agent.edgar.client import EdgarClient
from sec_agent.edgar.errors import EdgarNotFoundError
from sec_agent.filings.exhibits import annual_report_documents, filing_index_url
from sec_agent.filings.html_text import html_blocks
from sec_agent.filings.incorporation import incorporated_keys
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import ExhibitDocument, FilingJob, FilingRef
from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.sections import find_sections
from sec_agent.filings.store import ChunkStore, PostgresChunkStore
from sec_agent.jobs.context import HandlerContext
from sec_agent.jobs.errors import PermanentJobError
from sec_agent.jobs.models import Job
from sec_agent.jobs.worker import Handler

log = logging.getLogger(__name__)


def make_filing_handler(
    fetch: Callable[[str], bytes], store: ChunkStore, config: ChunkConfig
) -> Handler:
    """Build the handler; `fetch` is `EdgarClient.get` outside tests."""
    version = index_version(config)

    def handle(job: Job) -> None:
        try:
            payload = FilingJob.model_validate(job.payload)
        except ValidationError as error:
            raise PermanentJobError(f"bad filing.sections payload: {error}") from error
        if payload.index_version != version:
            # The job was enqueued for a build this code cannot reproduce; writing our
            # output under its name would mix two builds into one version.
            raise PermanentJobError(
                f"job is for index version {payload.index_version}; this worker builds {version}"
            )
        filing = payload.filing
        try:
            html = fetch(filing.document_url)
        except EdgarNotFoundError as error:
            raise PermanentJobError(f"HTTP 404 for {filing.document_url}") from error
        indexed = index_filing(html, filing, config, _exhibits(fetch, filing, html))
        store.replace(indexed)
        log.info(
            "indexed %s %s: %d sections, %d chunks",
            filing.form,
            filing.accession,
            len(indexed.sections),
            len(indexed.chunks),
        )

    return handle


def _exhibits(
    fetch: Callable[[str], bytes], filing: FilingRef, html: bytes
) -> list[ExhibitDocument]:
    """The filing's Exhibit 13 documents, fetched only when the 10-K incorporates items."""
    if not incorporated_keys(find_sections(html_blocks(html), filing.form), filing.form):
        return []
    try:
        names = annual_report_documents(fetch(filing_index_url(filing)))
    except EdgarNotFoundError:
        log.warning("no filing index for %s; keeping its own text", filing.accession)
        return []
    folder = filing.document_url.rsplit("/", 1)[0]
    exhibits: list[ExhibitDocument] = []
    for name in names:
        url = f"{folder}/{name}"
        try:
            exhibits.append(ExhibitDocument(url=url, html=fetch(url)))
        except EdgarNotFoundError:
            log.warning("exhibit %s of %s is missing; skipped", name, filing.accession)
    return exhibits


def filing_sections_handler(context: HandlerContext) -> Handler:
    """Handler factory for `sec-agent worker`: EDGAR client from the environment, store on
    the worker's database."""
    client = context.resources.enter_context(EdgarClient.from_env())
    store = context.resources.enter_context(PostgresChunkStore.connect(context.database_url))
    store.apply_schema()
    return make_filing_handler(client.get, store, ChunkConfig())
