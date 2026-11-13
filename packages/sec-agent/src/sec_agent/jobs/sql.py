"""SQL statements of the job queue, one constant per operation."""

# Running jobs whose lease ran out on their last attempt cannot be retried: fail them.
REAP_EXHAUSTED = b"""
UPDATE jobs
SET status = 'failed', last_error = 'lease expired on final attempt (worker lost)',
    lease_token = NULL, lease_expires_at = NULL, finished_at = now(), updated_at = now()
WHERE id IN (
    SELECT id FROM jobs
    WHERE status = 'running' AND lease_expires_at < now() AND attempts >= max_attempts
      AND kind = ANY(%(kinds)s)
    FOR UPDATE SKIP LOCKED
)
"""

# Lease the oldest ready job: queued and due, or running with an expired lease (its worker
# died). SKIP LOCKED passes over rows another claimer holds, so claimers never wait on or
# share a row. A fresh token fences off the previous holder.
CLAIM = b"""
WITH next AS (
    SELECT id FROM jobs
    WHERE kind = ANY(%(kinds)s)
      AND (
            (status = 'queued' AND run_after <= now())
         OR (status = 'running' AND lease_expires_at < now() AND attempts < max_attempts)
      )
    ORDER BY run_after, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE jobs
SET status = 'running', attempts = jobs.attempts + 1, lease_owner = %(owner)s,
    lease_token = gen_random_uuid(),
    lease_expires_at = now() + make_interval(secs => %(lease)s),
    updated_at = now()
FROM next
WHERE jobs.id = next.id
RETURNING jobs.*
"""

ENQUEUE = b"""
INSERT INTO jobs (kind, key, payload, max_attempts)
VALUES (%(kind)s, %(key)s, %(payload)s, %(max_attempts)s)
ON CONFLICT (kind, key) DO NOTHING
"""

# Every report back is fenced by the lease token: a worker whose lease was taken over
# matches no row and learns it from the row count.
HEARTBEAT = b"""
UPDATE jobs
SET lease_expires_at = now() + make_interval(secs => %(lease)s), updated_at = now()
WHERE id = %(id)s AND status = 'running' AND lease_token = %(token)s
"""

COMPLETE = b"""
UPDATE jobs
SET status = 'done', lease_token = NULL, lease_expires_at = NULL, last_error = NULL,
    finished_at = now(), updated_at = now()
WHERE id = %(id)s AND status = 'running' AND lease_token = %(token)s
"""

RETRY = b"""
UPDATE jobs
SET status = 'queued', lease_token = NULL, lease_expires_at = NULL, last_error = %(error)s,
    run_after = now() + make_interval(secs => %(retry_in)s), updated_at = now()
WHERE id = %(id)s AND status = 'running' AND lease_token = %(token)s
"""

FAIL = b"""
UPDATE jobs
SET status = 'failed', lease_token = NULL, lease_expires_at = NULL, last_error = %(error)s,
    finished_at = now(), updated_at = now()
WHERE id = %(id)s AND status = 'running' AND lease_token = %(token)s
"""

COUNTS = b"SELECT status, count(*) AS n FROM jobs GROUP BY status"

GET = b"SELECT * FROM jobs WHERE id = %(id)s"
