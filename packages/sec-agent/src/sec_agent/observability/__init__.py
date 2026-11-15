"""Tracing: one OpenTelemetry trace per question, exported to Phoenix, and the L1 table.

`spans` opens the spans of a turn (agent, model call, provider call, tool) with the
OpenTelemetry GenAI attributes and the OpenInference ones Phoenix reads (`conventions`).
`setup` sends them where the environment says: Phoenix over OTLP HTTP, a JSONL file
(`span_file`), or nowhere. `latency` turns a span file into latency per step and tokens
per question, the rows of L1 in runs.csv; `cli` is `sec-agent traces table`.
No span records a question, an answer or a tool result: only names, counts and timings.
"""
