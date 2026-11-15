"""PlantedTools: the agent's tools, with `search_filings` serving one item's passages.

Whatever the model searches for, the result is the item's simulated passages (an
injected one among them for an indirect attack), so every run of an item reads the same
text. The numeric tools are the real ones on the facts given. `diff_risk_factors` is not
offered: G-red plants its text in search results only.
"""

import datetime as dt
from collections.abc import Sequence

from pydantic import ValidationError

from sec_agent.agent.tool_runner import ToolOutput, ToolRunner, refusal
from sec_agent.retrieval.models import SearchFilters
from sec_agent.tools.catalog import TOOLS
from sec_agent.tools.context import FactsContext
from sec_agent.tools.search_filings import Passage, SearchFilingsArgs, SearchResult

PLANTED_ACCESSION = "9999999999-24-{:06d}"
"""Simulated accession numbers: CIK 9999999999 is no SEC filer."""


class PlantedTools(ToolRunner):
    def __init__(
        self, facts: FactsContext, passages: Sequence[str], *, company: str = "AAPL"
    ) -> None:
        super().__init__(facts)
        self._specs = {spec.name: spec for spec in TOOLS if spec.name != "diff_risk_factors"}
        self._passages = tuple(passages)
        self._company = facts.companies.resolve(company)

    def run(self, name: str, arguments: str) -> ToolOutput:
        if name != "search_filings":
            return super().run(name, arguments)
        try:
            args = SearchFilingsArgs.model_validate_json(arguments)
        except ValidationError:
            return refusal("invalid_arguments", "search_filings needs a query")
        result = SearchResult(
            query=args.query,
            mode="lexical",
            space="planted",
            index_version="planted",
            filters=SearchFilters(),
            passages=tuple(self._passage(i, text) for i, text in enumerate(self._passages)),
        )
        return ToolOutput(True, result.model_dump_json())

    def _passage(self, ordinal: int, text: str) -> Passage:
        accession = PLANTED_ACCESSION.format(ordinal + 1)
        return Passage(
            citation=f"{accession}/risk_factors/{ordinal}",
            rank=ordinal + 1,
            score=1.0 / (ordinal + 1),
            company=self._company,
            cik=str(self._company.cik),
            accession=accession,
            form="10-K",
            section="risk_factors",
            ordinal=ordinal,
            filing_date=dt.date(2024, 11, 1),
            report_date=dt.date(2024, 9, 28),
            char_start=0,
            char_end=len(text),
            text=text,
            source_url=f"https://www.sec.gov/Archives/edgar/data/{self._company.cik}/",
        )
