# AGENTS.md

Rules for every agent (Claude, Codex, or other) that writes or reviews code here.

## Product rules

- **Numbers come from tools, never from the model.** Every number an answer shows comes from a deterministic tool (XBRL lookup, ratio code, SQL) or a cited source passage.
- **Every number in README or `docs/` comes from `runs.csv`.** One row per measured number, validated by `sec_agent.runs`. Planning estimates in docs are labelled as estimates, never as results.
- **Simulated users and simulated data are always labelled simulated** and counted apart from real ones (`cohort` column: `real`, `simulated`, `none`). Never report simulated accounts as "N users".
- **Cost cap $0.** No paid API, no API key that bills per request. All LLM calls go through the repository's provider router.
- **SEC EDGAR only through the repository's rate-limited client** (10 requests per second, shared token bucket), with the User-Agent from the `SEC_USER_AGENT` environment variable. Never commit a real contact; `.env.example` holds a placeholder.
- **Tests never call SEC, an LLM, or the network.** Use recorded fixtures.
- Not investment advice: the product refuses advice and still shows historical numbers with a disclaimer.

## Code rules

- One responsibility per file. Split a file when it mixes concerns or passes about 300 lines.
- TDD: the first commit of a PR contains only the failing tests.
- Python 3.12, Pydantic v2, strict pyright. TypeScript strict.
- Small, typed, pure functions where possible; I/O at the edges.

## Commands

Python (uv workspace; `python -m uv` works when `uv` is not on PATH):

```sh
uv sync
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest -q
```

Web (pnpm workspace, run from the repository root):

```sh
pnpm install
pnpm biome check
pnpm typecheck
pnpm test
```

Local stack (Postgres 17 + pgvector + pg_search, Phoenix):

```sh
cp .env.example .env
docker compose up -d
```

## Layout

| Path                   | What                                                   |
| ---------------------- | ------------------------------------------------------ |
| `packages/sec-agent/`  | Python package `sec_agent` and the `sec-agent` CLI     |
| `tests/`               | Repository-level tests (CI, compose, docs, `runs.csv`) |
| `web/`                 | Next.js 15 app (App Router, React 19, Tailwind v4)     |
| `infra/postgres/init/` | SQL run on first start of the local database           |
| `docs/design.md`       | System design                                          |
| `runs.csv`             | Every measured number, one per row                     |

## Git and CI

- Branch from `develop`; open PRs against `develop`. PR titles start with their type: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Required checks: `Python checks` and `Web checks` (`.github/workflows/ci.yml`). Do not rename them.
- Commit messages are one-line imperative sentences.
