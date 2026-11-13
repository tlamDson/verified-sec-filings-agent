"""Job kinds the `sec-agent worker` command can run.

Ingest steps register here as they are built (XBRL facts, filing sections). Each kind is
a dotted name such as `xbrl.companyfacts`; each handler must be idempotent.
"""

from sec_agent.edgar.client import EdgarClient
from sec_agent.jobs.worker import Handler
from sec_agent.xbrl import ingest as xbrl_ingest
from sec_agent.xbrl.store import PostgresFactStore


def registered_handlers(database_url: str) -> dict[str, Handler]:
    """Handlers writing to `database_url`. Raises EdgarConfigError without SEC_USER_AGENT."""
    client = EdgarClient.from_env()
    return {
        xbrl_ingest.KIND: xbrl_ingest.make_handler(
            lambda url, refresh: client.get(url, refresh=refresh),
            lambda: PostgresFactStore.connect(database_url),
        ),
    }
