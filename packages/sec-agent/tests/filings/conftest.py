"""Fixtures for the filing text index: simulated filings and a clean chunk schema."""

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

import psycopg
import pytest

from sec_agent.filings.models import FilingRef
from sec_agent.filings.store import apply_schema

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "filings"
SIM_CIK = "9999999999"


@pytest.fixture
def read_fixture() -> Callable[[str], bytes]:
    return lambda name: (FIXTURES / name).read_bytes()


@pytest.fixture
def read_json_fixture() -> Callable[[str], object]:
    return lambda name: json.loads((FIXTURES / name).read_text("utf-8"))


@pytest.fixture
def filing_10k() -> FilingRef:
    return FilingRef(
        cik=SIM_CIK,
        accession="9999999999-25-000008",
        form="10-K",
        filing_date=dt.date(2025, 2, 20),
        report_date=dt.date(2024, 12, 31),
        primary_document="simw-20241231.htm",
    )


@pytest.fixture
def filing_10q() -> FilingRef:
    return FilingRef(
        cik=SIM_CIK,
        accession="9999999999-24-000005",
        form="10-Q",
        filing_date=dt.date(2024, 8, 1),
        report_date=dt.date(2024, 6, 30),
        primary_document="simw-20240630.htm",
    )


@pytest.fixture
def chunk_db(db_url: str) -> str:
    """The test database with the jobs and chunk schemas applied and every table empty."""
    with psycopg.connect(db_url, autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE indexed_filings CASCADE")
    return db_url
