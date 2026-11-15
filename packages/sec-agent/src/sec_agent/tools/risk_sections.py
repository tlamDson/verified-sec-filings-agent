"""Item 1A Risk Factors sections of a company's 10-K and 10-K/A filings, labelled by fiscal year.

The fiscal year of a 10-K comes from the XBRL facts when they hold a fiscal year that ends
on the filing's report date (`sec_agent.xbrl.calendar`, E1); the caller falls back to the
report date only when they do not.
"""

import datetime as dt
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from sec_agent.edgar.urls import normalize_cik
from sec_agent.filings.models import FilingForm

_ANNUAL_RISK_SECTIONS = b"""
SELECT fi.accession, fi.form, fi.filing_date, fi.report_date,
       coalesce(s.source_url, fi.source_url) AS source_url, s.text,
       (SELECT max(f.fiscal_year) FROM facts f
        WHERE f.index_version = %(facts_version)s AND f.cik = %(cik)s
          AND f.fiscal_period = 'FY' AND f.period_end = fi.report_date) AS xbrl_fiscal_year
FROM indexed_filings fi
JOIN filing_sections s ON s.index_version = fi.index_version AND s.accession = fi.accession
WHERE fi.index_version = %(text_version)s AND fi.cik = %(cik_text)s
  AND fi.form IN ('10-K', '10-K/A') AND s.section = 'risk_factors'
ORDER BY fi.report_date, fi.filing_date, fi.accession COLLATE "C"
"""


class RiskSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accession: str
    form: FilingForm
    filing_date: dt.date
    report_date: dt.date
    source_url: str
    text: str
    xbrl_fiscal_year: int | None


class RiskSectionSource(Protocol):
    def annual_risk_sections(
        self, *, cik: int, text_version: str, facts_version: str
    ) -> list[RiskSection]:
        """Every 10-K and 10-K/A risk factor section, by report date, then filing date."""
        ...


class PostgresRiskSections:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def annual_risk_sections(
        self, *, cik: int, text_version: str, facts_version: str
    ) -> list[RiskSection]:
        params = {
            "cik": cik,
            "cik_text": normalize_cik(cik),
            "text_version": text_version,
            "facts_version": facts_version,
        }
        with self._conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(_ANNUAL_RISK_SECTIONS, params).fetchall()
        return [RiskSection.model_validate(r) for r in rows]
