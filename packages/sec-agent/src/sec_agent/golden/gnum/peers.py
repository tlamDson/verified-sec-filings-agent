"""Peer comparison candidates: which of two same-sector companies reported more (E3).

Each company is compared on its own fiscal year of the same number (Apple's fiscal 2024
ended in September 2024, NVIDIA's in January 2024), never converted to calendar years.
Only full-year USD amounts and year-end USD balances are compared, and never a tie. The
order the two names appear in is seeded, so the winner is not always named first.
"""

from collections.abc import Sequence

from sec_agent.golden.gnum import phrasing
from sec_agent.golden.gnum.candidates import GNumCompany, askable, question_id
from sec_agent.golden.gnum.models import CompanyAnswer, NumQuestion, SourceFact
from sec_agent.golden.ranking import seeded_key
from sec_agent.xbrl.concepts import concept
from sec_agent.xbrl.periods import PeriodKind
from sec_agent.xbrl.versions import LatestFact

_KEY = tuple[str, PeriodKind, int]


def _year_ends(company: GNumCompany, years: Sequence[int]) -> dict[_KEY, LatestFact]:
    return {
        (x.fact.concept, x.fact.period_kind, x.fact.fiscal_year or 0): x
        for x in askable(company, years)
        if x.fact.unit == "USD" and x.fact.fiscal_period == "FY"
    }


def peer_questions(
    a: GNumCompany, b: GNumCompany, *, years: Sequence[int], index_version: str, seed: int
) -> list[NumQuestion]:
    if a.company.split != b.company.split:
        raise ValueError("peers must come from one split")
    low, high = sorted((a, b), key=lambda c: c.company.cik)
    low_facts, high_facts = _year_ends(low, years), _year_ends(high, years)
    out: list[NumQuestion] = []
    for key in sorted(low_facts.keys() & high_facts.keys()):
        name, kind, fy = key
        x, y = low_facts[key], high_facts[key]
        if x.fact.value == y.fact.value:
            continue
        qid = question_id("peer_comparison", low.company.cik, high.company.cik, name, kind, fy)
        flip = seeded_key(seed, "peer-order", qid) < seeded_key(seed, "peer-order", qid, "b")
        (first, f1), (second, f2) = ((high, y), (low, x)) if flip else ((low, x), (high, y))
        winner = first if f1.fact.value > f2.fact.value else second
        out.append(
            NumQuestion(
                id=qid,
                split=low.company.split,
                qtype="peer_comparison",
                question=phrasing.peer_question(
                    first.company, second.company, concept(name).label, kind, fy
                ),
                tickers=(first.company.ticker, second.company.ticker),
                ciks=(first.company.cik, second.company.cik),
                concept=name,
                fiscal_year=fy,
                fiscal_period="FY",
                period_kind=kind,
                answer=CompanyAnswer(ticker=winner.company.ticker, cik=winner.company.cik),
                sources=(SourceFact.of(f1), SourceFact.of(f2)),
                index_version=index_version,
            )
        )
    return out
