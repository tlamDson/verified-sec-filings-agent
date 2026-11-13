"""companyfacts -> facts: one row per canonical concept, unit, period and filing.

Per entry of a tag in the concept table: keep it only from a 10-K, 10-K/A, 10-Q or 10-Q/A,
in the concept's own unit (E5, never converted), with the concept's period type and a
supported duration. Within one filing and period, the concept's highest-priority tag wins;
two different values for that tag are a conflict and are dropped, never guessed between.
Every filing's version is kept (E2 picks among them later). Each fact gets the fiscal
label of its own period from the company's calendar (E1). Every drop is counted.
"""

import datetime as dt
from collections import Counter, defaultdict
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from sec_agent.xbrl.calendar import FORMS_IN_SCOPE, FiscalCalendar
from sec_agent.xbrl.companyfacts import CompanyFacts, RawEntry
from sec_agent.xbrl.concepts import concepts_by_tag, tag_priority
from sec_agent.xbrl.models import Fact, NormalizationReport, VersionKey
from sec_agent.xbrl.periods import DurationClass, classify_duration, period_kind


class Normalized(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: list[Fact]
    report: NormalizationReport


class _Candidate(NamedTuple):
    priority: int
    taxonomy: str
    tag: str
    duration: DurationClass | None
    entry: RawEntry


def normalize(doc: CompanyFacts) -> Normalized:
    calendar = FiscalCalendar.from_document(doc)
    counts: Counter[str] = Counter()
    groups = _candidates(doc, counts)
    facts: list[Fact] = []
    for (concept, unit, start, end, accession), candidates in groups.items():
        best = min(c.priority for c in candidates)
        chosen = [c for c in candidates if c.priority == best]
        counts["lower_priority_tag"] += len(candidates) - len(chosen)
        if len({c.entry.val for c in chosen}) > 1:
            counts["conflicting_values"] += len(chosen)
            continue
        top = chosen[0]
        label = calendar.label(top.duration or "instant", end)
        if label is None:
            counts["unlabelled"] += 1
        facts.append(
            Fact(
                cik=doc.cik,
                concept=concept,
                unit=unit,
                period_kind=period_kind(top.duration),
                period_start=start,
                period_end=end,
                fiscal_year=None if label is None else label.fiscal_year,
                fiscal_period=None if label is None else label.fiscal_period,
                value=top.entry.val,
                taxonomy=top.taxonomy,
                tag=top.tag,
                accession=accession,
                form=top.entry.form,
                filed=top.entry.filed,
                frame=top.entry.frame,
            )
        )
    facts.sort(key=_order)
    report = NormalizationReport.model_validate(
        {**counts, "facts_kept": len(facts), "fiscal_years_relabelled": len(calendar.relabelled)}
    )
    return Normalized(facts=facts, report=report)


def _candidates(doc: CompanyFacts, counts: Counter[str]) -> dict[VersionKey, list[_Candidate]]:
    lookup = concepts_by_tag()
    groups: defaultdict[VersionKey, list[_Candidate]] = defaultdict(list)
    for taxonomy, tag, unit, e in doc.entries():
        concept = lookup.get((taxonomy, tag))
        if concept is None:
            continue
        counts["entries_seen"] += 1
        if e.form not in FORMS_IN_SCOPE:
            counts["form_out_of_scope"] += 1
            continue
        if unit != concept.unit:
            counts["unit_mismatch"] += 1
            continue
        if (e.start is None) != (concept.period_type == "instant"):
            counts["period_type_mismatch"] += 1
            continue
        duration = None if e.start is None else classify_duration(e.start, e.end)
        if e.start is not None and duration is None:
            counts["unsupported_duration"] += 1
            continue
        key: VersionKey = (concept.name, unit, e.start, e.end, e.accn)
        priority = tag_priority(concept, taxonomy, tag)
        groups[key].append(_Candidate(priority, taxonomy, tag, duration, e))
    return groups


def _order(f: Fact) -> tuple[str, str, dt.date, dt.date, dt.date, str]:
    return (f.concept, f.unit, f.period_start or dt.date.min, f.period_end, f.filed, f.accession)
