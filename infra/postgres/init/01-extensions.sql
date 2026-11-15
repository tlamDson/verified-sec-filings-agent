-- Runs once, on first start of an empty data volume, in POSTGRES_DB.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;
