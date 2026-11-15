"""Evidence the faithfulness tests check answers against. Pytest puts this directory on
sys.path (`pythonpath`).

Numeric evidence is produced by running the real tools on the recorded Apple and NVIDIA
companyfacts fixtures, so its figures are what SEC reported. Passages, risk diffs and
restated facts are simulated (made up for a test, named SIM...), never real filing text.
Every answer text in these tests is simulated too: it stands in for what a model writes.
"""

import datetime as dt
import json
from decimal import Decimal

from sec_agent.agent.answer import Evidence
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.retrieval.models import SearchFilters
from sec_agent.tools.companies import CompanyRef
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.get_fact import GetFactResult
from sec_agent.tools.risk_factors import FilingCitation, RiskChange, RiskDiffResult
from sec_agent.tools.search_filings import Passage, SearchResult

ASKED_ON = dt.date(2026, 11, 13)
SIM_ACCESSION = "9999999999-25-000008"
SIM_PREVIOUS_ACCESSION = "9999999999-24-000002"
SIM_COMPANY = CompanyRef(
    ticker="SIMW", name="SIM Widgets Inc.", cik=9999999999, sector="Information Technology"
)


def run_tool(facts: FactsContext, name: str, call_id: str = "c1", **arguments: object) -> Evidence:
    """Run a real numeric tool and keep its result as the agent would."""
    text = json.dumps(arguments)
    output = ToolRunner(facts).run(name, text)
    return Evidence(call_id=call_id, name=name, arguments=text, result=output.content, ok=output.ok)


def passage_citation(ordinal: int, section: str = "mdna") -> str:
    return f"{SIM_ACCESSION}/{section}/{ordinal}"


def search_evidence(*texts: str, call_id: str = "s1") -> Evidence:
    """A simulated search_filings result: one passage per text, ordinals 0, 1, ..."""
    passages = tuple(
        Passage(
            citation=passage_citation(i),
            rank=i + 1,
            score=1.0 / (i + 1),
            company=SIM_COMPANY,
            cik=str(SIM_COMPANY.cik),
            accession=SIM_ACCESSION,
            form="10-K",
            section="mdna",
            ordinal=i,
            filing_date=dt.date(2025, 2, 20),
            report_date=dt.date(2024, 12, 31),
            char_start=0,
            char_end=len(text),
            text=text,
            source_url="https://www.sec.gov/Archives/edgar/data/9999999999/sim-10k.htm",
        )
        for i, text in enumerate(texts)
    )
    result = SearchResult(
        query="SIM query",
        mode="lexical",
        space="sim-space",
        index_version="sim-index",
        filters=SearchFilters(),
        passages=passages,
    )
    return Evidence(
        call_id=call_id,
        name="search_filings",
        arguments='{"query": "SIM query"}',
        result=result.model_dump_json(),
        ok=True,
    )


def _filing(accession: str, year: int) -> FilingCitation:
    return FilingCitation(
        accession=accession,
        form="10-K",
        filing_date=dt.date(year + 1, 2, 20),
        report_date=dt.date(year, 12, 31),
        fiscal_year=year,
        fiscal_year_basis="xbrl",
        source_url="https://www.sec.gov/Archives/edgar/data/9999999999/sim-10k.htm",
    )


def risk_diff_evidence(added_text: str, *, call_id: str = "r1") -> Evidence:
    """A simulated diff_risk_factors result with one added paragraph and two unchanged."""
    result = RiskDiffResult(
        status="compared",
        company=SIM_COMPANY,
        reason=None,
        current=_filing(SIM_ACCESSION, 2024),
        previous=_filing(SIM_PREVIOUS_ACCESSION, 2023),
        added=1,
        removed=0,
        changed=0,
        unchanged=2,
        changes=(
            RiskChange(
                kind="added",
                text=added_text,
                char_start=0,
                char_end=len(added_text),
                previous_text=None,
                previous_char_start=None,
                previous_char_end=None,
                similarity=None,
            ),
        ),
        changes_total=1,
        index_version="sim-index",
    )
    return Evidence(
        call_id=call_id,
        name="diff_risk_factors",
        arguments='{"company": "SIMW"}',
        result=result.model_dump_json(),
        ok=True,
    )


def restated_evidence(*, call_id: str = "f9") -> Evidence:
    """A simulated get_fact result for a value restated by a 10-K/A (E2)."""
    fact = FactValue(
        cik=SIM_COMPANY.cik,
        concept="revenue",
        label="Revenue",
        value=Decimal("1250000000"),
        unit="USD",
        period_kind="annual",
        period_start=dt.date(2024, 1, 1),
        period_end=dt.date(2024, 12, 31),
        fiscal_year=2024,
        fiscal_period="FY",
        accession="9999999999-25-000011",
        form="10-K/A",
        filed=dt.date(2025, 6, 2),
        taxonomy="us-gaap",
        tag="Revenues",
        filing_url="https://www.sec.gov/Archives/edgar/data/9999999999/sim-index.htm",
        restated=True,
        original_value=Decimal("1200000000"),
        original_accession=SIM_ACCESSION,
        original_filed=dt.date(2025, 2, 20),
        versions=2,
    )
    result = GetFactResult(
        status="found",
        company=SIM_COMPANY,
        concept="revenue",
        label="Revenue",
        unit="USD",
        fiscal_year=2024,
        fiscal_period="FY",
        period_kind="annual",
        index_version="sim-index",
        fact=fact,
    )
    return Evidence(
        call_id=call_id,
        name="get_fact",
        arguments='{"company": "SIMW", "concept": "revenue", "fiscal_year": 2024}',
        result=result.model_dump_json(),
        ok=True,
    )
