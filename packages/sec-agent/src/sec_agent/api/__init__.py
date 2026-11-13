"""HTTP API of the agent: one turn streamed as server-sent events, feedback, daily limits.

The web app signs a short-lived token for the signed-in user (`identity`); the API counts
the question against the user's day (`store`), runs the turn (`turns`) and streams it
(`sse`, `events`): each tool result as metric cards and citations (`present`, `cards`),
then the checked answer with chart series (`charts`). When no model answers, the figures
the question asks for are looked up without one (`sec_agent.degraded`). Every row the API
keeps carries its cohort, `real` or `simulated`; the two are never added together.
"""
