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

### Web app and API

The web app (Next.js) talks to the API (FastAPI); the browser never reaches the API directly.

```sh
set -a; . ./.env; set +a                                  # DATABASE_URL, API_AUTH_SECRET, LLM_PROVIDERS
uv run sec-agent agent init && uv run sec-agent api init  # tables, once
uv run sec-agent api serve --facts-version v1             # API on 127.0.0.1:8000
cp .env web/.env.local                                    # the web app reads its variables here
pnpm dev                                                  # web app on localhost:3000
```

Sign-in needs one provider: set `AUTH_GITHUB_ID` and `AUTH_GITHUB_SECRET` for real users, or `SIM_LOGIN_SECRET` to enable the simulated test accounts (`sim-01@example.com` to `sim-50@example.com`), which are always labelled simulated and counted apart from real users. When no LLM provider answers, the app shows the figures it can look up without a model and says it is in degraded mode.

### Simulated users

Fifty simulated accounts (`sim-01@example.com` to `sim-50@example.com`, cohort `simulated`) use the deployed app through the same path as people: sign-in, web app, API, agent, tools and LLM router. They are test traffic: every count they produce is labelled "simulated users", kept apart from real users, and never reported as users. Their thumbs up or down only prove the feedback path works; quality is measured by the eval sets.

```sh
uv run sec-agent sim roster                               # the accounts and the persona each plays
uv run sec-agent sim plan --llm-calls-per-day N           # one day's seeded sessions, nothing sent
SIM_LOGIN_SECRET=... uv run sec-agent sim run --base-url https://your-app --llm-calls-per-day N --record runs.csv
uv run sec-agent api cohorts --from YYYY-MM-DD --to YYYY-MM-DD   # real and simulated activity, side by side
```

The driver's daily budget is a share of the production LLM quota (`--share`, at most half, the default), at a planning estimate (not a measurement) of model calls per question (`--calls-per-question`). Run it on a schedule, mostly at night, or point `--base-url` at a staging app on a local model.

Rules for contributors and coding agents: [AGENTS.md](AGENTS.md). Design: [docs/design.md](docs/design.md).
