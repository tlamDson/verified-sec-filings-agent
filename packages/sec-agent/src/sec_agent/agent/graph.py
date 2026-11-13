"""The turn as a LangGraph state graph, behind one typed function.

    begin ──► model ──► (tool calls?) ──► tools ──► model ──► ... ──► done

The graph checkpoints after every step under the conversation's `thread_id`, and waits
for each write (`durability="sync"`): a replica that lost a race for the conversation
stops at its next step instead of making another model call.
"""
# LangGraph's graph module resolves without type information under strict pyright, so its
# calls are kept in this file and leave it through `TurnRunner`.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false

from collections.abc import Callable
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from sec_agent.agent.nodes import TurnNodes, after_model
from sec_agent.agent.state import AgentState, TurnInput

TurnRunner = Callable[[str, TurnInput, int], AgentState]
"""(thread_id, input, recursion_limit) -> the state when the turn ended."""


def build_turn_runner(nodes: TurnNodes, checkpointer: BaseCheckpointSaver[Any]) -> TurnRunner:
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

    return run
