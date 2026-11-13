-- Job queue. Applied by sec_agent.jobs.schema.apply_schema; every statement is idempotent.
CREATE TABLE IF NOT EXISTS jobs (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text        NOT NULL,
    key              text        NOT NULL,
    payload          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status           text        NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts         integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts     integer     NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
    run_after        timestamptz NOT NULL DEFAULT now(),
    lease_owner      text,
    lease_token      uuid,
    lease_expires_at timestamptz,
    last_error       text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    CONSTRAINT jobs_kind_key_unique UNIQUE (kind, key),
    CONSTRAINT jobs_running_has_lease CHECK (
        (status = 'running') = (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);

-- Claim scans: ready queued jobs, and running jobs whose lease may have expired.
CREATE INDEX IF NOT EXISTS jobs_queued_ready ON jobs (run_after, id) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS jobs_running_lease ON jobs (lease_expires_at) WHERE status = 'running';
