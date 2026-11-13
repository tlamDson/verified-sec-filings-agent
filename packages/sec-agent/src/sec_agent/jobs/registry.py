"""Job kinds the `sec-agent worker` command can run.

Ingest steps register here as they are built (XBRL facts, filing sections). Each kind is
a dotted name such as `xbrl.companyfacts`; each handler must be idempotent.
"""

from sec_agent.jobs.worker import Handler


def registered_handlers() -> dict[str, Handler]:
    return {}
