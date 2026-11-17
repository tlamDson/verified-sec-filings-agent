"""The checkpointer keeps working after the server drops its connection (idle timeout, restart)."""

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import CheckpointMetadata, empty_checkpoint
from pg_kill import client_backends, terminate

from sec_agent.agent.checkpoint import postgres_checkpointer

META: CheckpointMetadata = {"source": "loop", "step": 0, "parents": {}}
THREAD: RunnableConfig = {"configurable": {"thread_id": "t-reconnect", "checkpoint_ns": ""}}


def test_a_conversation_continues_after_the_server_dropped_the_connection(
    checkpoint_db: str,
) -> None:
    first, second = empty_checkpoint(), empty_checkpoint()
    before = client_backends(checkpoint_db)
    with postgres_checkpointer(checkpoint_db) as saver:
        head = saver.put(THREAD, first, META, {})
        terminate(checkpoint_db, client_backends(checkpoint_db) - before)
        saved = saver.get_tuple(THREAD)
        assert saved is not None
        assert saved.checkpoint["id"] == first["id"]
        saver.put(head, second, META, {})
        saved = saver.get_tuple(THREAD)
        assert saved is not None
        assert saved.checkpoint["id"] == second["id"]
