-- What the API keeps. Applied by sec_agent.api.schema.apply_schema; idempotent.
-- Every row carries its cohort. A simulated account is always 'sim:...' and nothing else
-- is, so a simulated row can never be stored, or later counted, as a real user's.

-- Questions asked per user and UTC day: the daily limit.
CREATE TABLE IF NOT EXISTS api_usage (
    user_id   text    NOT NULL,
    cohort    text    NOT NULL CHECK (cohort IN ('real', 'simulated')),
    day       date    NOT NULL,
    questions integer NOT NULL DEFAULT 0 CHECK (questions >= 0),
    PRIMARY KEY (user_id, day),
    CHECK ((cohort = 'simulated') = (user_id LIKE 'sim:%'))
);

-- One row per turn a user asked, written when its answer was sent.
CREATE TABLE IF NOT EXISTS api_turns (
    user_id   text        NOT NULL,
    cohort    text        NOT NULL CHECK (cohort IN ('real', 'simulated')),
    thread_id text        NOT NULL,
    turn      integer     NOT NULL CHECK (turn >= 1),
    asked_at  timestamptz NOT NULL,
    status    text        NOT NULL,
    degraded  boolean     NOT NULL,
    PRIMARY KEY (user_id, thread_id, turn),
    CHECK ((cohort = 'simulated') = (user_id LIKE 'sim:%'))
);

CREATE INDEX IF NOT EXISTS api_turns_asked_at ON api_turns (asked_at);

-- A user's thumbs up or down on a turn they asked; the latest rating wins.
CREATE TABLE IF NOT EXISTS api_feedback (
    user_id   text        NOT NULL,
    cohort    text        NOT NULL CHECK (cohort IN ('real', 'simulated')),
    thread_id text        NOT NULL,
    turn      integer     NOT NULL,
    rating    text        NOT NULL CHECK (rating IN ('up', 'down')),
    rated_at  timestamptz NOT NULL,
    PRIMARY KEY (user_id, thread_id, turn),
    FOREIGN KEY (user_id, thread_id, turn) REFERENCES api_turns ON DELETE CASCADE,
    CHECK ((cohort = 'simulated') = (user_id LIKE 'sim:%'))
);
