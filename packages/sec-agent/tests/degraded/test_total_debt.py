"""'Total debt' end to end: question -> deterministic tools -> the cards the web app shows.

No XBRL concept is total debt, so the answer is its three balance-sheet lines, each on its
own card, and never the non-current term debt alone. The three debt entries are synthetic
(made-up values added to the recorded Apple document, filed with its fiscal 2025 10-K);
every other fact is what SEC reported.
"""

import copy
import datetime as dt
import json
from decimal import Decimal
from typing import Any

import pytest
from api_kit import RecordingTools
from faithfulness_kit import ASKED_ON
from tools_data import FACTS_VERSION
from xbrl_docs import APPLE, entry

from sec_agent.api.cards import FactCard
from sec_agent.api.present import present
from sec_agent.degraded.lookup import deterministic_evidence
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize

QUESTION = "What was Apple's total debt at the end of fiscal 2025?"
_ACCESSION = "0000320193-25-000079"
SYNTHETIC_DEBT = {
    "LongTermDebtNoncurrent": 70_000_000_000,
    "LongTermDebtCurrent": 10_000_000_000,
    "CommercialPaper": 2_000_000_000,
}
LINES = (
    ("long_term_debt_noncurrent", "Long-term debt, noncurrent"),
    ("long_term_debt_current", "Long-term debt, current"),
    ("commercial_paper", "Commercial paper"),
)


def _facts(directory: CompanyDirectory, tags: dict[str, int]) -> FactsContext:
    doc: dict[str, Any] = copy.deepcopy(json.loads(APPLE.read_bytes()))
    for tag, value in tags.items():
        doc["facts"]["us-gaap"][tag] = {
            "label": tag,
            "units": {"USD": [entry("2025-09-27", value, _ACCESSION, fy=2025, filed="2025-10-31")]},
        }
    facts = normalize(parse_companyfacts(json.dumps(doc).encode())).facts
    return FactsContext(
        companies=directory,
        facts=MemoryFactQuery.from_facts(FACTS_VERSION, facts),
        index_version=FACTS_VERSION,
    )


def _cards(facts: FactsContext, question: str = QUESTION) -> list[FactCard]:
    evidence = deterministic_evidence(
        question, tools=RecordingTools(facts), companies=facts.companies, asked_on=ASKED_ON
    )
    cards = present(evidence).cards
    assert all(isinstance(card, FactCard) for card in cards)
    return [card for card in cards if isinstance(card, FactCard)]


@pytest.mark.parametrize("question", [QUESTION, "Apple total borrowings fiscal 2025"])
def test_total_debt_is_answered_with_its_three_lines(
    question: str, directory: CompanyDirectory
) -> None:
    cards = _cards(_facts(directory, SYNTHETIC_DEBT), question)
    assert [(c.concept, c.label, c.status, c.value) for c in cards] == [
        (concept, label, "found", Decimal(SYNTHETIC_DEBT[tag]))
        for (concept, label), tag in zip(LINES, SYNTHETIC_DEBT, strict=True)
    ]
    for card in cards:
        assert (card.company.ticker, card.fiscal_year, card.fiscal_period) == ("AAPL", 2025, "FY")
        assert card.period_end == dt.date(2025, 9, 27)
        assert card.source is not None
        assert card.source.accession == _ACCESSION


def test_a_missing_debt_line_is_shown_as_not_reported_not_dropped(
    directory: CompanyDirectory,
) -> None:
    """A snapshot with only the non-current line (ingested before the two other concepts
    existed) still answers with all three lines, so that one never stands for the total."""
    only_noncurrent = {"LongTermDebtNoncurrent": SYNTHETIC_DEBT["LongTermDebtNoncurrent"]}
    cards = _cards(_facts(directory, only_noncurrent))
    assert [(c.concept, c.status, c.value) for c in cards] == [
        ("long_term_debt_noncurrent", "found", Decimal(70_000_000_000)),
        ("long_term_debt_current", "not_reported", None),
        ("commercial_paper", "not_reported", None),
    ]
