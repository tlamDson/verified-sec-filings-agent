"""SQL statements of the facts store, one constant per operation."""

# Upsert on the version key: a re-run (the job ran twice, or SEC corrected a value in its
# companyfacts) updates the row in place and never adds one.
UPSERT_FACT = b"""
INSERT INTO facts (
    index_version, cik, concept, unit, period_kind, period_start, period_end, accession,
    fiscal_year, fiscal_period, value, taxonomy, tag, form, filed, frame
) VALUES (
    %(index_version)s, %(cik)s, %(concept)s, %(unit)s, %(period_kind)s, %(period_start)s,
    %(period_end)s, %(accession)s, %(fiscal_year)s, %(fiscal_period)s, %(value)s,
    %(taxonomy)s, %(tag)s, %(form)s, %(filed)s, %(frame)s
)
ON CONFLICT ON CONSTRAINT facts_version_unique DO UPDATE SET
    period_kind = EXCLUDED.period_kind,
    fiscal_year = EXCLUDED.fiscal_year,
    fiscal_period = EXCLUDED.fiscal_period,
    value = EXCLUDED.value,
    taxonomy = EXCLUDED.taxonomy,
    tag = EXCLUDED.tag,
    form = EXCLUDED.form,
    filed = EXCLUDED.filed,
    frame = EXCLUDED.frame
"""

UPSERT_INGEST = b"""
INSERT INTO xbrl_ingests (index_version, cik, entity_name, facts_written, report)
VALUES (%(index_version)s, %(cik)s, %(entity_name)s, %(facts_written)s, %(report)s)
ON CONFLICT (index_version, cik) DO UPDATE SET
    entity_name = EXCLUDED.entity_name,
    facts_written = EXCLUDED.facts_written,
    report = EXCLUDED.report,
    ingested_at = now()
"""

# Serialises concurrent writes of one company's snapshot (two workers on one job after a
# lost lease): the second waits for the first to commit, then upserts over it.
LOCK_COMPANY = b"SELECT pg_advisory_xact_lock(hashtextextended(%(index_version)s, %(cik)s))"

COUNT = b"SELECT count(*) AS n FROM facts WHERE index_version = %(index_version)s AND cik = %(cik)s"

_FACT_COLUMNS = (
    "cik, concept, unit, period_kind, period_start, period_end, accession, fiscal_year, "
    "fiscal_period, value, taxonomy, tag, form, filed, frame"
)
_COMPANY = "index_version = %(index_version)s AND cik = %(cik)s"
_CONCEPT = "(%(concept)s::text IS NULL OR concept = %(concept)s)"
_ORDER = "ORDER BY concept, unit, period_start NULLS FIRST, period_end, filed, accession"

VERSIONS = f"SELECT {_FACT_COLUMNS} FROM facts WHERE {_COMPANY} AND {_CONCEPT} {_ORDER}".encode()

LATEST = (
    f"SELECT {_FACT_COLUMNS}, original_value, original_accession, original_filed, versions, "
    f"restated FROM facts_latest WHERE {_COMPANY} AND {_CONCEPT} {_ORDER}"
).encode()

GET_INGEST = (
    b"SELECT entity_name, facts_written, report, ingested_at FROM xbrl_ingests "
    b"WHERE index_version = %(index_version)s AND cik = %(cik)s"
)
