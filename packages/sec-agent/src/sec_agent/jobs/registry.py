"""Job kinds the `sec-agent worker` command can run.

Ingest steps register a handler factory here as they are built. Each kind is a dotted name
such as `filing.sections`; each handler must be idempotent.
"""

from sec_agent.filings.handler import filing_sections_handler
from sec_agent.filings.models import FILING_SECTIONS_KIND
from sec_agent.jobs.context import HandlerContext, HandlerFactory

__all__ = ["HandlerContext", "HandlerFactory", "registered_handlers"]


def registered_handlers() -> dict[str, HandlerFactory]:
    return {FILING_SECTIONS_KIND: filing_sections_handler}
