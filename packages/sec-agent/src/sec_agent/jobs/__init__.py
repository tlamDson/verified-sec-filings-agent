"""Postgres job queue and the ingest worker that drains it.

Jobs are leased with `FOR UPDATE SKIP LOCKED`, kept alive by heartbeats, and returned to
the queue when a lease expires. Delivery is at least once; handlers make the effect
exactly once by writing under natural keys (CIK, accession number).
"""
