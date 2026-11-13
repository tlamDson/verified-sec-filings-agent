-- LLM usage per provider. Applied by sec_agent.llm.schema.apply_schema; idempotent.
-- One row per provider and window: 'minute' rows count requests, 'day' rows count
-- requests and tokens. window_start is the UTC start of the window.
CREATE TABLE IF NOT EXISTS llm_usage (
    provider     text        NOT NULL,
    window_kind  text        NOT NULL CHECK (window_kind IN ('minute', 'day')),
    window_start timestamptz NOT NULL,
    requests     bigint      NOT NULL DEFAULT 0 CHECK (requests >= 0),
    tokens       bigint      NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    PRIMARY KEY (provider, window_kind, window_start)
);
