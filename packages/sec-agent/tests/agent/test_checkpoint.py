"""Checkpoints in Postgres: any replica continues a conversation, and none overwrites another.

Each "replica" is its own connection to the one test database. The model is simulated.
"""

import threading

import pytest
from agent_kit import ASKED_ON, agent_of
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.checkpoint import FencedPostgresSaver, postgres_checkpointer
from sec_agent.agent.errors import ConversationConflictError
from sec_agent.llm.messages import ChatRequest, Message, user
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
ANSWER = "SIMULATED answer that quotes the tool result."
META: CheckpointMetadata = {"source": "loop", "step": 0, "parents": {}}


def _thread(thread_id: str) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


def _head(saver: FencedPostgresSaver, thread_id: str) -> str:
    saved = saver.get_tuple(_thread(thread_id))
    assert saved is not None
    return saved.checkpoint["id"]


def test_a_conversation_started_on_one_replica_continues_on_another(
    facts_ctx: FactsContext, replica_a: FencedPostgresSaver, replica_b: FencedPostgresSaver
) -> None:
    model_a = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    first = agent_of(facts_ctx, model_a, checkpointer=replica_a).ask(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    assert (first.status, first.turn) == ("answered", 1)

    model_b = ScriptedProvider("a", [says("SIM second answer")])
    follow_up = agent_of(facts_ctx, model_b, checkpointer=replica_b).ask(
        "t-1", "And net income?", asked_on=ASKED_ON
    )
    assert (follow_up.status, follow_up.turn) == ("answered", 2)
    assert model_b.requests[0].messages[1:] == [
        user(QUESTION),
        says(ANSWER),
        user("And net income?"),
    ]


def test_a_turn_cut_short_by_a_crash_leaves_a_conversation_another_replica_continues(
    facts_ctx: FactsContext, replica_a: FencedPostgresSaver, replica_b: FencedPostgresSaver
) -> None:
    """The tool result was saved before the crash; the next question starts a new turn."""
    crashing = ScriptedProvider("a", [calls(REVENUE), RuntimeError("replica died")])
    with pytest.raises(RuntimeError, match="replica died"):
        agent_of(facts_ctx, crashing, checkpointer=replica_a).ask(
            "t-1", QUESTION, asked_on=ASKED_ON
        )

    model_b = ScriptedProvider("a", [says(ANSWER)])
    answer = agent_of(facts_ctx, model_b, checkpointer=replica_b).ask(
        "t-1", "Again?", asked_on=ASKED_ON
    )
    assert (answer.status, answer.turn) == ("answered", 2)
    assert answer.evidence == (), "evidence of the cut turn is not this turn's"
    assert model_b.requests[0].messages[1:] == [user(QUESTION), user("Again?")]


def test_a_replica_that_lost_the_race_fails_and_the_winner_s_turn_is_kept_whole(
    facts_ctx: FactsContext, replica_a: FencedPostgresSaver, replica_b: FencedPostgresSaver
) -> None:
    """While replica A waits for its model, replica B answers the same conversation."""
    model_b = ScriptedProvider("b", [says("SIM from b")])
    agent_b = agent_of(facts_ctx, model_b, checkpointer=replica_b)

    def slow_model(request: ChatRequest) -> Message:
        agent_b.ask("t-1", "Question on b", asked_on=ASKED_ON)
        return says("SIM from a")

    agent_a = agent_of(facts_ctx, ScriptedProvider("a", [slow_model]), checkpointer=replica_a)
    with pytest.raises(ConversationConflictError, match="t-1"):
        agent_a.ask("t-1", "Question on a", asked_on=ASKED_ON)

    model_b.then(says("SIM third answer"))
    third = agent_b.ask("t-1", "Next", asked_on=ASKED_ON)
    assert third.turn == 3
    assert model_b.requests[-1].messages[1:] == [
        user("Question on a"),
        user("Question on b"),
        says("SIM from b"),
        user("Next"),
    ], "the answer replica A computed from a stale state was never saved"


def test_a_checkpoint_written_from_a_stale_head_is_refused(
    replica_a: FencedPostgresSaver, replica_b: FencedPostgresSaver
) -> None:
    first, second, third = empty_checkpoint(), empty_checkpoint(), empty_checkpoint()
    head = replica_a.put(_thread("t-1"), first, META, {})

    with pytest.raises(ConversationConflictError):
        replica_b.put(_thread("t-1"), second, META, {})  # B still thinks the thread is new
    assert _head(replica_b, "t-1") == first["id"]

    head_b = replica_b.put(head, second, META, {})
    with pytest.raises(ConversationConflictError):
        replica_a.put(head, third, META, {})  # A's head is one behind now
    replica_a.put(head_b, third, META, {})
    assert _head(replica_a, "t-1") == third["id"]


def test_a_checkpoint_that_would_sort_before_the_head_is_refused(
    replica_a: FencedPostgresSaver,
) -> None:
    """Ids are time-ordered and the newest is the state: a replica with a slow clock must
    not write a checkpoint no reader would ever see."""
    older, newer = empty_checkpoint(), empty_checkpoint()
    head = replica_a.put(_thread("t-1"), newer, META, {})
    with pytest.raises(ConversationConflictError):
        replica_a.put(head, older, META, {})
    assert _head(replica_a, "t-1") == newer["id"]


def test_conversations_do_not_fence_each_other(
    replica_a: FencedPostgresSaver, replica_b: FencedPostgresSaver
) -> None:
    replica_a.put(_thread("t-1"), empty_checkpoint(), META, {})
    other = empty_checkpoint()
    replica_b.put(_thread("t-2"), other, META, {})
    assert _head(replica_a, "t-2") == other["id"]


def test_of_many_replicas_starting_one_conversation_exactly_one_wins(checkpoint_db: str) -> None:
    barrier = threading.Barrier(8)
    outcomes: list[str] = []
    written: list[Checkpoint] = []

    def replica() -> None:
        checkpoint = empty_checkpoint()
        with postgres_checkpointer(checkpoint_db) as saver:
            barrier.wait()
            try:
                saver.put(_thread("t-1"), checkpoint, META, {})
            except ConversationConflictError:
                outcomes.append("conflict")
            else:
                outcomes.append("saved")
                written.append(checkpoint)

    threads = [threading.Thread(target=replica) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["conflict"] * 7 + ["saved"]
    with postgres_checkpointer(checkpoint_db) as saver:
        assert _head(saver, "t-1") == written[0]["id"]
        assert len(list(saver.list(_thread("t-1")))) == 1
