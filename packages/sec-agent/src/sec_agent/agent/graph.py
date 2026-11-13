"""The turn as a LangGraph state graph, behind one typed function.

    begin ──► model ──► (tool calls?) ──► tools ──► model ──► ... ──► done

The graph checkpoints after every step under the conversation's `thread_id`, and waits
for each write (`durability="sync"`): a replica that lost a race for the conversation
stops at its next step instead of making another model call. `TurnRunner` returns the
state when the turn ended; `TurnStepper` yields the state after every step, so a caller
can show each tool result while the model is still working.
"""
# LangGraph's graph module resolves without type information under strict pyright, so its
# calls are kept in this file and leave it through `TurnRunner`.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false

from collections.abc import Callable, Iterator
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from sec_agent.agent.nodes import TurnNodes, after_model
from sec_agent.agent.state import AgentState, TurnInput

TurnRunner = Callable[[str, TurnInput, int], AgentState]
"""(thread_id, input, recursion_limit) -> the state when the turn ended."""
TurnStepper = Callable[[str, TurnInput, int], Iterator[AgentState]]
"""(thread_id, input, recursion_limit) -> the state after each step of this turn."""


def build_turn_graph(
    nodes: TurnNodes, checkpointer: BaseCheckpointSaver[Any]
) -> tuple[TurnRunner, TurnStepper]:
    graph = StateGraph(AgentState)
    graph.add_node("begin", nodes.begin)
    graph.add_node("model", nodes.call_model)
    graph.add_node("tools", nodes.run_tools)
    graph.add_edge(START, "begin")
    graph.add_edge("begin", "model")
    graph.add_conditional_edges("model", after_model, {"tools": "tools", "done": END})
    graph.add_edge("tools", "model")
    compiled = graph.compile(checkpointer=checkpointer)

    def run(thread_id: str, turn: TurnInput, recursion_limit: int) -> AgentState:
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit,
        }
        state = compiled.invoke(cast(Any, turn), config, durability="sync")
        return cast(AgentState, state)

    def steps(thread_id: str, turn: TurnInput, recursion_limit: int) -> Iterator[AgentState]:
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit,
        }
        stream = compiled.stream(
            cast(Any, turn), config, stream_mode=["updates", "values"], durability="sync"
        )
        started = False  # the first value is the conversation before `begin` reset the turn
        for mode, chunk in stream:
            if mode == "updates":
                started = True
            elif started:
                yield cast(AgentState, chunk)

    return run, steps
