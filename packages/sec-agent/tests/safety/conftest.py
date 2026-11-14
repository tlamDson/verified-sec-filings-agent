"""Facts for the S1 harness tests: the recorded Apple and NVIDIA companyfacts fixtures, read
the way `sec-agent eval safety run --companyfacts` reads them."""

import pytest
from xbrl_docs import APPLE, NVIDIA

from sec_agent.eval.safety.facts import companyfacts_context
from sec_agent.tools.context import FactsContext


@pytest.fixture(scope="session")
def facts_ctx() -> FactsContext:
    return companyfacts_context([APPLE, NVIDIA], index_version="x-test")
