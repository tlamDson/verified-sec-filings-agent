"""The research agent: a LangGraph loop where the model picks tools and code runs them.

`service.Agent.ask` runs one turn of a conversation: the model (through `sec_agent.llm`'s
router) chooses among the deterministic tools, `tool_runner` runs them, and the model
writes the answer from their results. Conversation state is checkpointed after every step
(`checkpoint`: Postgres, with an optimistic lock), so any API replica continues it.
When no provider answers, the turn ends degraded with the tool results gathered so far.
"""
