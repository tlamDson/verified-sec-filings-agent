"""Parsing the companyfacts JSON document into typed entries."""

import datetime as dt
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError
from xbrl_docs import APPLE, NVIDIA, document, entry

from sec_agent.xbrl.companyfacts import parse_companyfacts


def test_parses_recorded_document() -> None:
    doc = parse_companyfacts(NVIDIA.read_bytes())
    assert doc.cik == 1045810
    assert doc.entity_name == "NVIDIA CORP"
    revenue = doc.facts["us-gaap"]["Revenues"].units["USD"]
    fy2024 = [e for e in revenue if e.end == dt.date(2024, 1, 28) and e.form == "10-K"]
    assert fy2024[0].start == dt.date(2023, 1, 30)
    assert fy2024[0].val == Decimal(60922000000)
    assert fy2024[0].accn == "0001045810-24-000029"
    assert (fy2024[0].fy, fy2024[0].fp, fy2024[0].filed) == (2024, "FY", dt.date(2024, 2, 21))


def test_decimal_values_are_exact() -> None:
    doc = parse_companyfacts(NVIDIA.read_bytes())
    eps = doc.facts["us-gaap"]["EarningsPerShareDiluted"].units["USD/shares"]
    values = {e.val for e in eps if e.end == dt.date(2024, 1, 28)}
    assert values == {Decimal("11.93"), Decimal("1.19")}


def test_instant_entries_have_no_start() -> None:
    doc = parse_companyfacts(APPLE.read_bytes())
    assets = doc.facts["us-gaap"]["Assets"].units["USD"]
    assert all(e.start is None for e in assets)


def test_optional_fields_may_be_missing_or_null() -> None:
    raw = document({"Assets": {"USD": [entry("2023-12-31", 5, "0000001234-24-000001", fy=None)]}})
    raw["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["fp"] = None
    doc = parse_companyfacts(json.dumps(raw).encode())
    only = doc.facts["us-gaap"]["Assets"].units["USD"][0]
    assert (only.fy, only.fp, only.frame) == (None, None, None)


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"cik": 1, "entityName": "x"}', b'{"cik": 1, "facts": {}}'],
)
def test_malformed_documents_are_rejected(body: bytes) -> None:
    with pytest.raises((ValueError, ValidationError)):
        parse_companyfacts(body)
