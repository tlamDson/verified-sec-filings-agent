"""LLM access for the agent: one router over OpenAI-compatible providers.

`router` tries the configured providers in order; each has a quota count (`quota`, shared
through Postgres by `quota_postgres`) and a circuit breaker (`breaker`). `openai_compat`
is the only code that calls a model, over HTTP, at the URL the configuration names.
The model picks tools and writes prose; it is never the source of a number.
"""
