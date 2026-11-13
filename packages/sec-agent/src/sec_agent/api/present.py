"""present: a turn's evidence as cards and citations, in the order the tools ran.

Each tool result is parsed with the tool's own result model and copied field by field,
so every figure shown is a figure a tool returned. A refusal becomes a notice. Evidence
that cannot be read (a tool this code does not know, a result that is not its model) is
left out rather than guessed at.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from sec_agent.agent.answer import Evidence
from sec_agent.api.cards import (
    Card,
    Citation,
    CompanyTag,
    EvidenceView,
    FactCard,
    FilingSource,
    NoticeCard,
    PeerRow,
    PeersCard,
    RatioCard,
    RatioInput,
    RiskChange,
    RiskDiffCard,
    RiskFiling,
)
from sec_agent.tools.companies import CompanyRef
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.get_fact import GetFactResult
from sec_agent.tools.peers import PeerComparison
from sec_agent.tools.ratios import RatioResult
from sec_agent.tools.risk_factors import FilingCitation, RiskDiffResult
from sec_agent.tools.search_filings import SearchResult

_View = tuple[list[Card], list[Citation]]


def present(evidence: Sequence[Evidence]) -> EvidenceView:
    cards: list[Card] = []
    citations: dict[str, Citation] = {}
    for item in evidence:
        new_cards, new_citations = _present_one(item)
        cards.extend(new_cards)
        for citation in new_citations:
            citations.setdefault(citation.key, citation)
    return EvidenceView(cards=tuple(cards), citations=tuple(citations.values()))


def _present_one(item: Evidence) -> _View:
    if not item.ok:
        notice = _notice(item)
        return ([] if notice is None else [notice]), []
    reader = _READERS.get(item.name)
    if reader is None:
        return [], []
    model, view = reader
    try:
        result = model.model_validate_json(item.result)
    except ValidationError:
        return [], []
    return view(item.call_id, result)


def _notice(item: Evidence) -> NoticeCard | None:
    try:
        error: Any = json.loads(item.result)["error"]
        code, message = error["code"], error["message"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(code, str) or not isinstance(message, str):
        return None
    return NoticeCard(call_id=item.call_id, tool=item.name, code=code, message=message)


def _fact(call_id: str, result: GetFactResult) -> _View:
    fact = result.fact
    card = FactCard(
        call_id=call_id,
        company=_tag(result.company),
        concept=result.concept,
        label=result.label,
        unit=result.unit,
        fiscal_year=result.fiscal_year,
        fiscal_period=result.fiscal_period,
        status=result.status,
        value=None if fact is None else fact.value,
        period_start=None if fact is None else fact.period_start,
        period_end=None if fact is None else fact.period_end,
        source=None if fact is None else _source(fact),
        restated=fact is not None and fact.restated,
        original_value=None if fact is None else fact.original_value,
        original_filed=None if fact is None else fact.original_filed,
    )
    return [card], [] if fact is None else [_filing(fact, result.company)]


def _ratio(call_id: str, result: RatioResult) -> _View:
    card = RatioCard(
        call_id=call_id,
        company=_tag(result.company),
        ratio=result.ratio,
        label=result.label,
        formula=result.formula,
        unit=result.unit,
        fiscal_year=result.fiscal_year,
        fiscal_period=result.fiscal_period,
        status=result.status,
        value=result.value,
        reason=result.reason,
        period_start=result.period_start,
        period_end=result.period_end,
        inputs=tuple(_input(fact) for fact in result.inputs),
    )
    return [card], [_filing(fact, result.company) for fact in result.inputs]


def _peers(call_id: str, result: PeerComparison) -> _View:
    card = PeersCard(
        call_id=call_id,
        metric=result.metric,
        label=result.label,
        unit=result.unit,
        fiscal_year=result.fiscal_year,
        fiscal_period=result.fiscal_period,
        same_period_end=result.same_period_end,
        note=result.note,
        rows=tuple(
            PeerRow(
                rank=row.rank,
                company=_tag(row.company),
                status=row.status,
                value=row.value,
                period_end=row.period_end,
                reason=row.reason,
            )
            for row in result.rows
        ),
    )
    filings = [_filing(fact, row.company) for row in result.rows for fact in row.inputs]
    return [card], filings


def _passages(call_id: str, result: SearchResult) -> _View:
    return [], [
        Citation(
            key=p.citation,
            kind="passage",
            company=None if p.company is None else _tag(p.company),
            form=p.form,
            section=p.section,
            filing_date=p.filing_date,
            report_date=p.report_date,
            text=p.text,
            url=p.source_url,
        )
        for p in result.passages
    ]


def _risk_diff(call_id: str, result: RiskDiffResult) -> _View:
    filings = [f for f in (result.current, result.previous) if f is not None]
    card = RiskDiffCard(
        call_id=call_id,
        company=_tag(result.company),
        status=result.status,
        reason=result.reason,
        current=None if result.current is None else _risk_filing(result.current),
        previous=None if result.previous is None else _risk_filing(result.previous),
        added=result.added,
        removed=result.removed,
        changed=result.changed,
        unchanged=result.unchanged,
        changes=tuple(
            RiskChange(kind=c.kind, text=c.text, previous_text=c.previous_text)
            for c in result.changes
        ),
        changes_total=result.changes_total,
    )
    company = _tag(result.company)
    return [card], [
        Citation(
            key=f.accession,
            kind="filing",
            company=company,
            form=f.form,
            section="risk_factors",
            filing_date=f.filing_date,
            report_date=f.report_date,
            text=None,
            url=f.source_url,
        )
        for f in filings
    ]


def _tag(company: CompanyRef) -> CompanyTag:
    return CompanyTag(ticker=company.ticker, name=company.name)


def _source(fact: FactValue) -> FilingSource:
    return FilingSource(
        accession=fact.accession, form=fact.form, filed=fact.filed, url=fact.filing_url
    )


def _input(fact: FactValue) -> RatioInput:
    return RatioInput(
        concept=fact.concept,
        label=fact.label,
        value=fact.value,
        unit=fact.unit,
        fiscal_year=fact.fiscal_year,
        period_end=fact.period_end,
        source=_source(fact),
    )


def _filing(fact: FactValue, company: CompanyRef) -> Citation:
    return Citation(
        key=fact.accession,
        kind="filing",
        company=_tag(company),
        form=fact.form,
        section=None,
        filing_date=fact.filed,
        report_date=None,
        text=None,
        url=fact.filing_url,
    )


def _risk_filing(filing: FilingCitation) -> RiskFiling:
    return RiskFiling(
        accession=filing.accession,
        form=filing.form,
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        fiscal_year=filing.fiscal_year,
        url=filing.source_url,
    )


def _reader[M: BaseModel](
    model: type[M], view: Callable[[str, M], _View]
) -> tuple[type[BaseModel], Callable[[str, Any], _View]]:
    return model, view


_READERS: dict[str, tuple[type[BaseModel], Callable[[str, Any], _View]]] = {
    "get_fact": _reader(GetFactResult, _fact),
    "compute_ratio": _reader(RatioResult, _ratio),
    "compare_peers": _reader(PeerComparison, _peers),
    "search_filings": _reader(SearchResult, _passages),
    "diff_risk_factors": _reader(RiskDiffResult, _risk_diff),
}
