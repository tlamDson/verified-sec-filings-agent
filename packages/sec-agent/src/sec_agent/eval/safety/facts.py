"""The facts S1 runs on: recorded companyfacts documents, read into memory.

S1 measures guardrails, not retrieval, so a fixed offline facts source is enough and
makes the run repeatable without a database.
"""

from collections.abc import Iterable
from pathlib import Path

from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize


def companyfacts_context(paths: Iterable[Path], *, index_version: str) -> FactsContext:
    facts = [
        fact for path in paths for fact in normalize(parse_companyfacts(path.read_bytes())).facts
    ]
    return FactsContext(
        companies=CompanyDirectory.from_universe(),
        facts=MemoryFactQuery.from_facts(index_version, facts),
        index_version=index_version,
    )
