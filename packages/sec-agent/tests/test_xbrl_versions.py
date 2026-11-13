"""Restated figures (E2): the latest filed version wins, and the original is kept."""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from xbrl_docs import APPLE, NVIDIA, document, entry

from sec_agent.xbrl.companyfacts import parse_companyfacts
from sec_agent.xbrl.normalize import normalize
from sec_agent.xbrl.versions import LatestFact, latest_versions

D = dt.date.fromisoformat


def _latest(source: Path | dict[str, Any]) -> list[LatestFact]:
    body = source.read_bytes() if isinstance(source, Path) else json.dumps(source).encode()
    return latest_versions(normalize(parse_companyfacts(body)).facts)


def _one(items: list[LatestFact], concept: str, end: str, start: str | None) -> LatestFact:
    found = [
        x
        for x in items
        if x.fact.concept == concept
        and x.fact.period_end == D(end)
        and x.fact.period_start == (None if start is None else D(start))
    ]
    assert len(found) == 1
    return found[0]


def test_apple_fy2008_net_income_restated_by_10k_a() -> None:
    item = _one(_latest(APPLE), "net_income", "2008-09-27", "2007-09-30")
    assert item.fact.value == Decimal(6119000000)
    assert (item.fact.form, item.fact.filed) == ("10-K", D("2010-10-27"))
    assert item.original_value == Decimal(4834000000)
    assert (item.original_accession, item.original_filed) == (
        "0001193125-09-214859",
        D("2009-10-27"),
    )
    assert item.versions == 3
    assert item.restated is True


def test_nvidia_fy2024_eps_restated_for_the_stock_split() -> None:
    item = _one(_latest(NVIDIA), "eps_diluted", "2024-01-28", "2023-01-30")
    assert item.fact.value == Decimal("1.19")
    assert item.original_value == Decimal("11.93")
    assert item.restated is True


def test_repeated_comparatives_are_not_a_restatement() -> None:
    item = _one(_latest(NVIDIA), "revenue", "2024-01-28", "2023-01-30")
    assert item.fact.value == Decimal(60922000000)
    assert item.original_value == item.fact.value
    assert item.versions == 3
    assert item.restated is False
    assert (item.fact.fiscal_year, item.fact.fiscal_period) == (2024, "FY")


def test_one_latest_fact_per_concept_unit_and_period() -> None:
    items = _latest(APPLE)
    keys = [x.fact.series_key for x in items]
    assert len(keys) == len(set(keys))


def test_same_filing_date_breaks_ties_by_accession() -> None:
    period = {"start": "2023-01-01", "filed": "2024-03-01"}
    raw = document(
        {
            "Revenues": {
                "USD": [
                    entry("2023-12-31", 1, "0000001234-24-000005", **period),
                    entry("2023-12-31", 2, "0000001234-24-000007", form="10-K/A", **period),
                ]
            }
        }
    )
    item = _one(_latest(raw), "revenue", "2023-12-31", "2023-01-01")
    assert item.fact.value == Decimal(2)
    assert item.original_value == Decimal(1)
