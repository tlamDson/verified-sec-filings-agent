"""Checkpoints in Postgres with an optimistic lock, so replicas never overwrite each other.

LangGraph's saver keeps every checkpoint of a conversation and reads the one with the
greatest id as its state. Two replicas running the same conversation would each append
their own chain, and whichever wrote last would silently win. `FencedPostgresSaver`
accepts a checkpoint only when it was computed from the conversation's current head and
its id sorts after that head; otherwise it raises `ConversationConflictError` and writes
nothing. The check and the write are one transaction under a per-conversation advisory
lock.
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import ChannelVersions, Checkpoint, CheckpointMetadata
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import DictRow, dict_row

from sec_agent.agent.errors import ConversationConflictError

_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_HEAD = """
SELECT checkpoint_id, checkpoint_id < %s AS before_new
FROM checkpoints
WHERE thread_id = %s AND checkpoint_ns = %s
ORDER BY checkpoint_id DESC
LIMIT 1
"""


class FencedPostgresSaver(PostgresSaver):
    """One connection per saver; calls from several threads take turns on it."""

    def __init__(self, conn: Connection[DictRow]) -> None:
        super().__init__(conn)
        self._fence_conn = conn
        # Re-entrant, so `put` holds the connection across its check and the parent's write
        # while every other call on this saver waits outside the transaction.
        self.lock = cast(threading.Lock, threading.RLock())

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        configurable = config.get("configurable", {})
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        parent: str | None = configurable.get("checkpoint_id") or None
        with self.lock, self._fence_conn.transaction():
            self._fence_conn.execute(_LOCK, (f"checkpoint:{namespace}:{thread_id}",))
            head = self._fence_conn.execute(
                _HEAD, (checkpoint["id"], thread_id, namespace)
            ).fetchone()
            current: str | None = None if head is None else head["checkpoint_id"]
            if current != parent or (head is not None and not head["before_new"]):
                raise ConversationConflictError(thread_id)
            return super().put(config, checkpoint, metadata, new_versions)


@contextmanager
def postgres_checkpointer(conninfo: str) -> Generator[FencedPostgresSaver]:
    """A saver on its own connection. Call `setup()` once per database to create the tables."""
    with Connection[DictRow].connect(
        conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row
    ) as conn:
        yield FencedPostgresSaver(conn)
