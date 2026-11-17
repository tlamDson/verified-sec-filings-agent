"""The API store keeps working after the server drops its connection (idle timeout, restart)."""

import datetime as dt

from pg_kill import client_backends, terminate

from sec_agent.api.identity import Identity
from sec_agent.api.store_postgres import PostgresApiStore

DAY = dt.date(2026, 11, 17)
SIM_USER = Identity(user_id="sim:reconnect@example.com", cohort="simulated")


def test_a_question_is_counted_after_the_server_dropped_the_connection(api_db: str) -> None:
    before = client_backends(api_db)
    with PostgresApiStore.connect(api_db) as store:
        assert store.charge_question(SIM_USER, DAY, limit=5) == 1
        terminate(api_db, client_backends(api_db) - before)
        assert store.charge_question(SIM_USER, DAY, limit=5) == 2
        assert store.questions_used(SIM_USER.user_id, DAY) == 2
