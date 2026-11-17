"""The quota store keeps working after the server drops its connection (idle timeout, restart)."""

from llm_fakes import T0
from pg_kill import client_backends, terminate

from sec_agent.llm.quota import QuotaLimits
from sec_agent.llm.quota_postgres import PostgresQuotaStore


def test_a_request_is_reserved_after_the_server_dropped_the_connection(llm_db: str) -> None:
    limits = QuotaLimits(requests_per_day=5)
    before = client_backends(llm_db)
    with PostgresQuotaStore.connect(llm_db) as store:
        assert store.reserve("local", limits, T0)
        terminate(llm_db, client_backends(llm_db) - before)
        assert store.reserve("local", limits, T0)
        assert store.usage("local", T0).day_requests == 2
