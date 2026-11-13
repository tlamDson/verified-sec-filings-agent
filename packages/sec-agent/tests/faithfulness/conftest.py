"""The recorded Apple and NVIDIA facts the numeric tools read in the faithfulness tests."""

import pytest
from tools_data import FACTS_VERSION
from xbrl_docs import APPLE, NVIDIA

from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize


@pytest.fixture(scope="session")
def facts_ctx() -> FactsContext:
    facts = [
        fact
        for document in (APPLE, NVIDIA)
        for fact in normalize(parse_companyfacts(document.read_bytes())).facts
    ]
    return FactsContext(
        companies=CompanyDirectory.from_universe(),
        facts=MemoryFactQuery.from_facts(FACTS_VERSION, facts),
        index_version=FACTS_VERSION,
    )
