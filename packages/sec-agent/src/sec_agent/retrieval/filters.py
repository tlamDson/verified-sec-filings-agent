"""SearchFilters as a SQL condition on the chunk row `c`, with named parameters."""

from typing import Any

from psycopg import sql

from sec_agent.retrieval.models import SearchFilters


def filter_condition(filters: SearchFilters) -> sql.Composable:
    """`AND ...` for each filter that is set; empty when none is."""
    parts: list[sql.Composable] = []
    if filters.ciks:
        parts.append(sql.SQL(" AND c.cik = ANY(%(ciks)s)"))
    if filters.forms:
        parts.append(sql.SQL(" AND c.form = ANY(%(forms)s)"))
    if filters.sections:
        parts.append(sql.SQL(" AND c.section = ANY(%(sections)s)"))
    if filters.report_from is not None:
        parts.append(sql.SQL(" AND c.report_date >= %(report_from)s"))
    if filters.report_to is not None:
        parts.append(sql.SQL(" AND c.report_date <= %(report_to)s"))
    return sql.Composed(parts)


def filter_params(filters: SearchFilters) -> dict[str, Any]:
    return {
        "ciks": list(filters.ciks),
        "forms": list(filters.forms),
        "sections": list(filters.sections),
        "report_from": filters.report_from,
        "report_to": filters.report_to,
    }
