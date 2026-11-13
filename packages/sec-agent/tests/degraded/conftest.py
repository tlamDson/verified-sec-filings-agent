"""Fixtures for the degraded-mode tests: the recorded Apple and NVIDIA facts."""

import pytest
from tools_data import FACTS_VERSION
from xbrl_docs import APPLE, NVIDIA

from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize


@pytest.fixture(scope="session")
def directory() -> CompanyDirectory:
    return CompanyDirectory.from_universe()


@pytest.fixture(scope="session")
def facts_ctx(directory: CompanyDirectory) -> FactsContext:
    facts = [
        fact
        for document in (APPLE, NVIDIA)
        for fact in normalize(parse_companyfacts(document.read_bytes())).facts
    ]
    return FactsContext(
        companies=directory,
        facts=MemoryFactQuery.from_facts(FACTS_VERSION, facts),
        index_version=FACTS_VERSION,
    )
