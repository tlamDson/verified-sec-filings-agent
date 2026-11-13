-- XBRL facts. Applied by sec_agent.xbrl.schema.apply_schema; every statement is idempotent.

-- One row per filed version: a canonical concept, in one unit, for one period, as one
-- filing (accession) reported it, inside one index_version snapshot. Re-running an ingest
-- upserts on this key, so it never adds rows (exactly-once effect under at-least-once jobs).
CREATE TABLE IF NOT EXISTS facts (
    index_version text    NOT NULL,
    cik           bigint  NOT NULL CHECK (cik > 0),
    concept       text    NOT NULL,
    unit          text    NOT NULL,
    period_kind   text    NOT NULL CHECK (period_kind IN ('instant', 'quarter', 'ytd', 'annual')),
    period_start  date,
    period_end    date    NOT NULL,
    accession     text    NOT NULL,
    fiscal_year   integer,
    fiscal_period text    CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    value         numeric NOT NULL,
    taxonomy      text    NOT NULL,
    tag           text    NOT NULL,
    form          text    NOT NULL,
    filed         date    NOT NULL,
    frame         text,
    CONSTRAINT facts_instant_has_no_start CHECK ((period_kind = 'instant') = (period_start IS NULL)),
    CONSTRAINT facts_period_order CHECK (period_start IS NULL OR period_start < period_end),
    CONSTRAINT facts_fiscal_label_whole CHECK ((fiscal_year IS NULL) = (fiscal_period IS NULL)),
    CONSTRAINT facts_version_unique UNIQUE NULLS NOT DISTINCT
        (index_version, cik, concept, unit, period_start, period_end, accession)
);

-- Tool lookups: one company's concept by fiscal year and period.
CREATE INDEX IF NOT EXISTS facts_lookup
    ON facts (index_version, cik, concept, fiscal_year, fiscal_period);

-- One ingest per company and index_version: what was written and what was dropped, why.
CREATE TABLE IF NOT EXISTS xbrl_ingests (
    index_version text        NOT NULL,
    cik           bigint      NOT NULL CHECK (cik > 0),
    entity_name   text        NOT NULL,
    facts_written integer     NOT NULL CHECK (facts_written >= 0),
    report        jsonb       NOT NULL,
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_version, cik)
);

-- Restated figures (E2): per (index_version, cik, concept, unit, period), the latest filed
-- version (greatest filed date, then accession), with the earliest as the original and
-- whether any version's value differs. sec_agent.xbrl.versions applies the same rule.
CREATE OR REPLACE VIEW facts_latest AS
SELECT DISTINCT ON (index_version, cik, concept, unit, period_start, period_end)
    f.*,
    first_value(f.value) OVER series_by_filing     AS original_value,
    first_value(f.accession) OVER series_by_filing AS original_accession,
    first_value(f.filed) OVER series_by_filing     AS original_filed,
    count(*) OVER series                           AS versions,
    min(f.value) OVER series <> max(f.value) OVER series AS restated
FROM facts AS f
WINDOW
    series AS (PARTITION BY index_version, cik, concept, unit, period_start, period_end),
    series_by_filing AS (series ORDER BY filed, accession)
ORDER BY index_version, cik, concept, unit, period_start, period_end, filed DESC, accession DESC;
