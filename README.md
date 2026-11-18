# Verified SEC Filings Agent

An AI research assistant for public company filings that never makes up a number: every figure in an answer is looked up in the SEC's own data and linked to its source.

[![CI](https://github.com/tlamDson/verified-sec-filings-agent/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/tlamDson/verified-sec-filings-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Live demo: coming soon. Until then, the [results page](https://tlamdson.github.io/verified-sec-filings-agent/) shows the eval results and sample answers with their cited passages (a static page, no model call).

![Architecture: SEC EDGAR filings are ingested into XBRL facts in Postgres and a filing text index; the agent answers with retrieval, figure lookup, a citation check and an advice refusal; a FastAPI API on Hugging Face Spaces serves the Next.js web app; an evaluation harness of golden questions, a judge and a CI gate tests every change.](.github/readme/architecture.svg)

## What it does

- Answers questions about public companies' annual and quarterly reports (10-K, 10-Q), such as revenue, margins, debt or risk factors, and compares companies with each other.
- Takes every number from a lookup in the SEC's structured financial data (XBRL) or from a quoted filing passage, and withholds any number it cannot trace.
- Refuses investment advice and ignores instructions hidden in filing text, while still showing the historical figures with a disclaimer.

## Results at a glance

Measured on a free local model over a seeded sample of S&P 100 companies; the figure, task and passage results are on test companies kept apart from development. Every number below is a row of [`runs.csv`](runs.csv), and a test checks each one against that file. The full tables, with sample sizes and 95% intervals, are in [DEVELOPMENT.md](DEVELOPMENT.md#results).

| What was tested             | Result                                                                                                      | Why it matters                                                                                                             |
| --------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Exact financial figures     | 75.0% of 300 test questions answered with the exact filed value; the same model alone got 15.0%             | A language model on its own misremembers financial numbers; looking them up in the filing data fixes most of those errors. |
| Multi-step research tasks   | 78.0% of 50 scenarios pass every check, against 16.0% for plain search-and-answer                           | It checks the whole job: the right tool, the right figure, a citation, and no claim the sources do not support.            |
| Finding the right passage   | Ranking score (MRR) of 87.2% with the trained reranker, against 76.8% without it, on 89 questions           | The passage that answers the question comes up near the top, so the agent quotes the right text.                           |
| Attacks and advice requests | Blocked 92.0% of 100 attacks and 100.0% of 20 advice requests; wrongly refused 0.0% of 102 normal questions | It cannot be talked into giving investment advice and still answers real questions. The test set is synthetic (simulated). |
| Automatic answer grader     | Agreed with the reference labels on all 38 answers the labellers were sure of (Cohen's kappa 1.00)          | The scores above can be trusted. The reference labels come from LLM raters checked by the owner, not from people.          |
| Eval gate in CI             | Blocked 100.0% of 10 planted regressions                                                                    | A change that makes answers worse cannot be merged by accident.                                                            |

Not measured yet: load, chaos, real users and simulated users have no rows in `runs.csv`, so nothing is claimed about them. Not investment advice.

## What I built

Solo project, from the data pipeline to the web app. The main engineering choices:

- **Numbers come from tools, not the model.** The agent (LangGraph) calls typed tools (`get_fact`, `compute_ratio`, `compare_peers`, `search_filings`) that run SQL over XBRL facts, and a faithfulness checker matches every number in a draft answer, with its unit and period, to a tool result or cited passage before the user sees it.
- **Hybrid retrieval in Postgres.** BM25 (`pg_search`) and pgvector results are fused in SQL, then a small cross-encoder reranker, fine-tuned on labelled question-passage pairs and scored with company-level cross-validation, reorders them on CPU (ONNX) behind a timeout and a circuit breaker.
- **Ingest that respects SEC limits.** One shared token-bucket client for EDGAR, a Postgres job queue with leases (`SKIP LOCKED`), and idempotent upserts keyed by accession number, so a crashed worker's job is picked up again without duplicates.
- **Evaluation first.** Question sets are split by company before any question is written; each system is compared with baselines on the same questions, with bootstrap intervals and paired tests; every measured number is one validated row of `runs.csv`, and a CI gate fails a pull request when a score drops.
- **Zero cost to run.** An OpenAI-compatible LLM router with failover, per-provider quotas and a degraded mode over free and local models, guardrails against prompt injection, OpenTelemetry tracing to Phoenix, and free-plan hosting (Neon, Hugging Face Spaces) set up with Terraform and GitHub Actions.

## Tech stack

| Area              | Tools                                                                       |
| ----------------- | --------------------------------------------------------------------------- |
| Agent and API     | Python, LangGraph, FastAPI (streamed answers), Pydantic, MCP server         |
| Data and search   | Postgres, pgvector, `pg_search` (BM25), ONNX Runtime cross-encoder reranker |
| LLM               | Local Qwen through an OpenAI-compatible router; free providers only         |
| Web app           | Next.js, React, Tailwind CSS, Auth.js                                       |
| Quality           | pytest, pyright (strict), Ruff, Biome, Vitest, eval gate in GitHub Actions  |
| Ops and telemetry | Docker Compose, Terraform, Hugging Face Spaces, OpenTelemetry, Phoenix      |

## Quick start

Requirements: Python with [uv](https://docs.astral.sh/uv/), Node with pnpm. Tests use recorded fixtures and never call SEC, an LLM or the network.

```sh
cp .env.example .env          # put your own contact in SEC_USER_AGENT
uv sync && uv run pytest -q   # Python package, agent and evals
pnpm install && pnpm test     # web app
```

The local database, the API, the web app, simulated users and the full results are in [DEVELOPMENT.md](DEVELOPMENT.md). Design: [docs/design.md](docs/design.md). Rules for contributors and coding agents: [AGENTS.md](AGENTS.md).

## Licence

MIT. See [`LICENSE`](LICENSE).
