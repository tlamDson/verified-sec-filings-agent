# Verified SEC Filings Research Agent

A research agent over public SEC filings (10-K, 10-Q, XBRL) where every number in an answer is traced to its source. Numbers come from deterministic tools, text comes from hybrid retrieval with citations, and an output checker blocks figures it cannot trace.

Status: being built. Results, design and evaluation will appear here as they are measured.

Not investment advice.

## Development

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm, Docker.

```sh
cp .env.example .env        # put your own contact in SEC_USER_AGENT
uv sync && uv run pytest -q
pnpm install && pnpm test
docker compose up -d        # Postgres 17 + pgvector + pg_search, Phoenix on :6006
```

Rules for contributors and coding agents: [AGENTS.md](AGENTS.md). Design: [docs/design.md](docs/design.md).
