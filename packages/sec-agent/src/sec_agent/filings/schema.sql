-- Filing text index. Applied by sec_agent.filings.store.apply_schema; every statement is
-- idempotent. Every row carries index_version; one version never overwrites another.

-- One row per filing processed for a version, even when no section was found (a 10-K/A
-- that only amends Part III), so coverage can be counted.
CREATE TABLE IF NOT EXISTS indexed_filings (
    index_version text        NOT NULL,
    accession     text        NOT NULL,
    cik           text        NOT NULL,
    form          text        NOT NULL,
    filing_date   date        NOT NULL,
    report_date   date        NOT NULL,
    source_url    text        NOT NULL,
    section_count integer     NOT NULL CHECK (section_count >= 0),
    chunk_count   integer     NOT NULL CHECK (chunk_count >= 0),
    indexed_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (index_version, accession)
);

CREATE TABLE IF NOT EXISTS filing_sections (
    index_version text    NOT NULL,
    accession     text    NOT NULL,
    section       text    NOT NULL
                  CHECK (section IN ('business', 'risk_factors', 'mdna', 'market_risk')),
    item          text    NOT NULL,
    heading       text    NOT NULL,
    text          text    NOT NULL,
    token_count   integer NOT NULL CHECK (token_count >= 0),
    PRIMARY KEY (index_version, accession, section),
    FOREIGN KEY (index_version, accession)
        REFERENCES indexed_filings (index_version, accession) ON DELETE CASCADE
);

-- Filter columns (cik, form, dates, section) live on the chunk row itself, so the vector
-- and BM25 indexes added later can filter without a join.
CREATE TABLE IF NOT EXISTS chunks (
    index_version text    NOT NULL,
    accession     text    NOT NULL,
    section       text    NOT NULL,
    ordinal       integer NOT NULL CHECK (ordinal >= 0),
    cik           text    NOT NULL,
    form          text    NOT NULL,
    filing_date   date    NOT NULL,
    report_date   date    NOT NULL,
    char_start    integer NOT NULL CHECK (char_start >= 0),
    char_end      integer NOT NULL CHECK (char_end > char_start),
    token_count   integer NOT NULL CHECK (token_count > 0),
    text          text    NOT NULL,
    text_sha256   text    NOT NULL,
    PRIMARY KEY (index_version, accession, section, ordinal),
    FOREIGN KEY (index_version, accession, section)
        REFERENCES filing_sections (index_version, accession, section) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chunks_by_company ON chunks (index_version, cik, report_date);
