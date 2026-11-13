"""A worker process for the kill test: each job sleeps, then writes one keyed row.

Run as a script with DATABASE_URL set and the owner tag as its argument. Its lease owner is
`host:pid:tag`, like `sec-agent worker --owner-tag`, so the chaos driver can find the
process that holds a job.
"""

import os
import socket
import sys
import time

import psycopg

from sec_agent.jobs.models import Job
from sec_agent.jobs.postgres import PostgresJobQueue
from sec_agent.jobs.worker import Worker, WorkerConfig

KIND = "chaos.slow"
JOB_SECONDS = 1.5


def main() -> None:
    url = os.environ["DATABASE_URL"]

    def handle(job: Job) -> None:
        time.sleep(JOB_SECONDS)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO test_effects (key, runs) VALUES (%s, 1) "
                "ON CONFLICT (key) DO UPDATE SET runs = test_effects.runs + 1",
                (job.key,),
            )

    config = WorkerConfig(
        owner=f"{socket.gethostname()}:{os.getpid()}:{sys.argv[1]}",
        lease_seconds=2.0,
        heartbeat_seconds=0.5,
        poll_seconds=0.2,
    )
    with PostgresJobQueue.connect(url) as queue:
        Worker(queue, {KIND: handle}, config).run()


if __name__ == "__main__":
    main()
