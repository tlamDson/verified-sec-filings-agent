"""After an ingest: did any fact land twice, is every company whole, did every job close?

Run after killing a worker mid-ingest. Jobs are delivered at least once, so a killed
worker's job runs again; the facts' unique key and upserts must make that harmless. This
reads the counts that show it, for one `index_version`.
"""

from typing import Any

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, computed_field

from sec_agent.xbrl.ingest import KIND

_JOBS = b"""
SELECT count(*) AS total,
       count(*) FILTER (WHERE status = 'done') AS done,
       count(*) FILTER (WHERE status = 'failed') AS failed,
       count(*) FILTER (WHERE status IN ('queued', 'running')) AS open,
       count(*) FILTER (WHERE status = 'done' AND attempts > 1) AS redone
FROM jobs WHERE kind = %(kind)s AND starts_with(key, %(prefix)s)
"""

# Rows that share the facts' version key. The unique constraint forbids them; this counts
# them anyway, so the check does not rest on the constraint it is meant to test.
_DUPLICATES = b"""
SELECT coalesce(sum(n - 1), 0) AS duplicates, coalesce(sum(n), 0) AS facts FROM (
    SELECT count(*) AS n FROM facts WHERE index_version = %(index_version)s
    GROUP BY cik, concept, unit, period_start, period_end, accession
) AS keys
"""

# A company whose snapshot holds fewer rows than its ingest wrote.
_COMPANIES = b"""
SELECT count(*) AS ingested,
       count(*) FILTER (WHERE coalesce(f.n, 0) < i.facts_written) AS short
FROM xbrl_ingests AS i
LEFT JOIN (
    SELECT cik, count(*) AS n FROM facts WHERE index_version = %(index_version)s GROUP BY cik
) AS f ON f.cik = i.cik
WHERE i.index_version = %(index_version)s
"""


class IngestIntegrity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index_version: str
    jobs_total: int
    jobs_done: int
    jobs_failed: int
    jobs_open: int
    """Queued or running: the ingest has not finished."""
    jobs_redone: int
    """Done jobs that took more than one attempt (a killed worker's job, for one)."""
    duplicate_fact_keys: int
    """Rows beyond the first for a version key; 0 means no fact landed twice."""
    facts: int
    companies_ingested: int
    companies_short: int

    @computed_field
    @property
    def clean(self) -> bool:
        """Something was ingested; nothing left open or failed; nothing twice or short."""
        return (
            self.jobs_total > 0
            and self.jobs_open == 0
            and self.jobs_failed == 0
            and self.duplicate_fact_keys == 0
            and self.companies_short == 0
        )


def check_ingest(conn: psycopg.Connection[Any], index_version: str) -> IngestIntegrity:
    params = {"kind": KIND, "prefix": f"{index_version}:", "index_version": index_version}
    with conn.cursor(row_factory=dict_row) as cur:
        jobs = _one(cur.execute(_JOBS, params).fetchone())
        facts = _one(cur.execute(_DUPLICATES, params).fetchone())
        companies = _one(cur.execute(_COMPANIES, params).fetchone())
    return IngestIntegrity(
        index_version=index_version,
        jobs_total=jobs["total"],
        jobs_done=jobs["done"],
        jobs_failed=jobs["failed"],
        jobs_open=jobs["open"],
        jobs_redone=jobs["redone"],
        duplicate_fact_keys=int(facts["duplicates"]),
        facts=int(facts["facts"]),
        companies_ingested=companies["ingested"],
        companies_short=companies["short"],
    )


def _one(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:  # an aggregate always returns one row
        raise RuntimeError("aggregate query returned no row")
    return row
