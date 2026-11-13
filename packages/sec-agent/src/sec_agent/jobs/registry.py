"""Job kinds the `sec-agent worker` command can run.

Ingest steps register a handler factory here as they are built. Each kind is a dotted name
such as `filing.sections` or `xbrl.companyfacts`; each handler must be idempotent.
"""

from sec_agent.filings.handler import filing_sections_handler
from sec_agent.filings.models import FILING_SECTIONS_KIND
from sec_agent.jobs.context import HandlerContext, HandlerFactory
from sec_agent.xbrl import ingest as xbrl_ingest

__all__ = ["HandlerContext", "HandlerFactory", "registered_handlers"]


def registered_handlers() -> dict[str, HandlerFactory]:
    return {
        FILING_SECTIONS_KIND: filing_sections_handler,
        xbrl_ingest.KIND: xbrl_ingest.companyfacts_handler,
    }
