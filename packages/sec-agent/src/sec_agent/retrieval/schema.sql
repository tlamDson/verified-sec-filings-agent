-- Retrieval index over the chunk tables. Applied by sec_agent.retrieval.schema.apply_schema
-- after the chunk schema; every statement is idempotent.
CREATE EXTENSION IF NOT EXISTS vector;

-- One chunk build embedded by one model. `spec` holds every setting that changes vectors;
-- the name is derived from it (sec_agent.retrieval.space), so a new model is a new row.
CREATE TABLE IF NOT EXISTS embedding_spaces (
    name          text        PRIMARY KEY,
    index_version text        NOT NULL,
    model         text        NOT NULL,
    dimensions    integer     NOT NULL CHECK (dimensions BETWEEN 1 AND 2000),
    spec          jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, index_version)
);

-- `vector` without a dimension, so spaces of different models share the table; each space
-- gets its own partial HNSW index on `embedding::vector(<dims>)` (created by build_index).
-- Deleting a chunk (a filing re-ingested) deletes its vectors; the next build re-embeds it.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    space         text    NOT NULL,
    index_version text    NOT NULL,
    accession     text    NOT NULL,
    section       text    NOT NULL,
    ordinal       integer NOT NULL,
    embedding     vector  NOT NULL,
    PRIMARY KEY (space, accession, section, ordinal),
    FOREIGN KEY (space, index_version)
        REFERENCES embedding_spaces (name, index_version) ON DELETE CASCADE,
    FOREIGN KEY (index_version, accession, section, ordinal)
        REFERENCES chunks (index_version, accession, section, ordinal) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_by_chunk
    ON chunk_embeddings (index_version, accession, section, ordinal);

-- BM25 in plain SQL: one tsvector per chunk (english configuration), its length in lexeme
-- occurrences, then per-version document frequencies and averages. Runs on any Postgres.
CREATE TABLE IF NOT EXISTS chunk_lexical (
    index_version text     NOT NULL,
    accession     text     NOT NULL,
    section       text     NOT NULL,
    ordinal       integer  NOT NULL,
    tsv           tsvector NOT NULL,
    doc_len       integer  NOT NULL CHECK (doc_len >= 0),
    PRIMARY KEY (index_version, accession, section, ordinal),
    FOREIGN KEY (index_version, accession, section, ordinal)
        REFERENCES chunks (index_version, accession, section, ordinal) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chunk_lexical_tsv ON chunk_lexical USING gin (tsv);

CREATE TABLE IF NOT EXISTS lexical_stats (
    index_version text             PRIMARY KEY,
    ts_config     text             NOT NULL,
    doc_count     integer          NOT NULL CHECK (doc_count >= 0),
    total_len     bigint           NOT NULL CHECK (total_len >= 0),
    avg_doc_len   double precision NOT NULL,
    built_at      timestamptz      NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lexical_df (
    index_version text    NOT NULL,
    lexeme        text    NOT NULL,
    df            integer NOT NULL CHECK (df > 0),
    PRIMARY KEY (index_version, lexeme)
);

-- A named, verified state of one space: counts and a digest over every chunk and vector.
-- A name never moves to other content; eval runs pin one by name.
CREATE TABLE IF NOT EXISTS retrieval_snapshots (
    name           text        PRIMARY KEY,
    space          text        NOT NULL REFERENCES embedding_spaces (name),
    index_version  text        NOT NULL,
    chunk_count    integer     NOT NULL CHECK (chunk_count >= 0),
    filing_count   integer     NOT NULL CHECK (filing_count >= 0),
    content_sha256 text        NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Blue/green: queries read the snapshot a pointer names; switching is one row update.
CREATE TABLE IF NOT EXISTS retrieval_pointers (
    name        text        PRIMARY KEY,
    snapshot    text        NOT NULL REFERENCES retrieval_snapshots (name),
    switched_at timestamptz NOT NULL DEFAULT now()
);
