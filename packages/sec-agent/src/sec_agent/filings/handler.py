"""The `filing.sections` job: fetch a filing's primary document, index it, store it.

Idempotent: the store replaces the rows keyed by (index_version, accession), so a second
delivery of the same job changes nothing.
"""

import logging
from collections.abc import Callable

from pydantic import ValidationError

from sec_agent.edgar.client import EdgarClient
from sec_agent.edgar.errors import EdgarNotFoundError
from sec_agent.filings.index_version import ChunkConfig, index_version
from sec_agent.filings.models import FilingJob
from sec_agent.filings.pipeline import index_filing
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
        indexed = index_filing(html, filing, config)
        store.replace(indexed)
        log.info(
            "indexed %s %s: %d sections, %d chunks",
            filing.form,
            filing.accession,
            len(indexed.sections),
            len(indexed.chunks),
        )

    return handle


def filing_sections_handler(context: HandlerContext) -> Handler:
    """Handler factory for `sec-agent worker`: EDGAR client from the environment, store on
    the worker's database."""
    client = context.resources.enter_context(EdgarClient.from_env())
    store = context.resources.enter_context(PostgresChunkStore.connect(context.database_url))
    store.apply_schema()
    return make_filing_handler(client.get, store, ChunkConfig())
