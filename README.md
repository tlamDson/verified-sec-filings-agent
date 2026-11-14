# Verified SEC Filings Research Agent

A research agent over public SEC filings (10-K, 10-Q, XBRL) where every number in an answer is traced to its source. Numbers come from deterministic tools, text comes from hybrid retrieval with citations, and an output checker blocks figures it cannot trace.

## Results

Measured on the local Qwen model (free, no paid API) and a seeded sample of S&P 100 companies; the design, the sampling and what each metric means are in [docs/design.md](docs/design.md). The block below is generated: `uv run sec-agent report sync` rewrites it from [runs.csv](runs.csv), and a test fails when it drifts.

What the numbers do not show: the load and chaos runs, real users and simulated users have no rows yet, so nothing is claimed about them. Simulated accounts are test traffic, always labelled simulated and never reported as users. The safety set is synthetic, and the grader-agreement labels come from LLM raters, not people.

<!-- results:start -->
Every number below is a row of [`runs.csv`](runs.csv) (the latest row for each metric, system, split and cohort), printed by `sec-agent report sync`.

#### Retrieval (R1)

Questions on the test companies; intervals resample companies. `diff` rows are the difference between two systems on the same questions and `p` rows their paired test.

| Metric             | System                               | Split |   n |      Value | 95% interval     |
| ------------------ | ------------------------------------ | ----- | --: | ---------: | ---------------- |
| `R1_recall@5`      | hybrid                               | test  |  89 |      23.6% | 19.4% to 29.1%   |
| `R1_ndcg@10`       | hybrid                               | test  |  89 |      60.3% | 53.0% to 67.3%   |
| `R1_mrr@10`        | hybrid                               | test  |  89 |      76.8% | 70.0% to 83.9%   |
| `R1_recall@5`      | hybrid+rerank-ft                     | test  |  89 |      28.3% | 23.1% to 34.6%   |
| `R1_ndcg@10`       | hybrid+rerank-ft                     | test  |  89 |      71.2% | 65.6% to 77.0%   |
| `R1_mrr@10`        | hybrid+rerank-ft                     | test  |  89 |      87.2% | 82.4% to 92.1%   |
| `R1_recall@5`      | hybrid+rerank-zs                     | test  |  89 |      25.8% | 20.7% to 31.9%   |
| `R1_ndcg@10`       | hybrid+rerank-zs                     | test  |  89 |      63.7% | 55.4% to 71.6%   |
| `R1_mrr@10`        | hybrid+rerank-zs                     | test  |  89 |      81.7% | 72.8% to 90.4%   |
| `R1_recall@5_diff` | hybrid+rerank-ft_vs_hybrid           | test  |  89 |     +0.047 | +0.012 to +0.084 |
| `R1_recall@5_p`    | hybrid+rerank-ft_vs_hybrid           | test  |  89 | p = 0.0078 |                  |
| `R1_ndcg@10_diff`  | hybrid+rerank-ft_vs_hybrid           | test  |  89 |     +0.109 | +0.076 to +0.144 |
| `R1_ndcg@10_p`     | hybrid+rerank-ft_vs_hybrid           | test  |  89 | p = 0.0002 |                  |
| `R1_mrr@10_diff`   | hybrid+rerank-ft_vs_hybrid           | test  |  89 |     +0.104 | +0.047 to +0.158 |
| `R1_mrr@10_p`      | hybrid+rerank-ft_vs_hybrid           | test  |  89 | p = 0.0006 |                  |
| `R1_recall@5_diff` | hybrid+rerank-zs_vs_hybrid           | test  |  89 |     +0.022 | +0.002 to +0.046 |
| `R1_recall@5_p`    | hybrid+rerank-zs_vs_hybrid           | test  |  89 |  p = 0.018 |                  |
| `R1_ndcg@10_diff`  | hybrid+rerank-zs_vs_hybrid           | test  |  89 |     +0.034 | +0.007 to +0.059 |
| `R1_ndcg@10_p`     | hybrid+rerank-zs_vs_hybrid           | test  |  89 |  p = 0.016 |                  |
| `R1_mrr@10_diff`   | hybrid+rerank-zs_vs_hybrid           | test  |  89 |     +0.049 | -0.016 to +0.114 |
| `R1_mrr@10_p`      | hybrid+rerank-zs_vs_hybrid           | test  |  89 |   p = 0.14 |                  |
| `R1_recall@5_diff` | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 |     +0.026 | +0.002 to +0.049 |
| `R1_recall@5_p`    | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 |  p = 0.033 |                  |
| `R1_ndcg@10_diff`  | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 |     +0.075 | +0.043 to +0.113 |
| `R1_ndcg@10_p`     | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 | p = 0.0002 |                  |
| `R1_mrr@10_diff`   | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 |     +0.055 | +0.000 to +0.115 |
| `R1_mrr@10_p`      | hybrid+rerank-ft_vs_hybrid+rerank-zs | test  |  89 |   p = 0.05 |                  |

#### Latency (L1)

Measured on the build machine's CPU, not on the deployed host.

| Metric          | System              | Split |   n |   Value | 95% interval |
| --------------- | ------------------- | ----- | --: | ------: | ------------ |
| `L1_rerank_p50` | minilm-l6-ft-gret10 | test  | 200 |  962 ms |              |
| `L1_rerank_p95` | minilm-l6-ft-gret10 | test  | 200 | 1252 ms |              |

#### Numeric answers (N1)

Numeric questions on the test split, answer must match the XBRL value. b0 and b1 are baselines on the same local model; b2 is the agent. `p` rows are exact two-sided McNemar.

| Metric         | System   | Split |   n |       Value | 95% interval   |
| -------------- | -------- | ----- | --: | ----------: | -------------- |
| `N1`           | b0       | test  | 300 |       15.0% | 11.4% to 19.5% |
| `N1`           | b1       | test  | 300 |        3.7% | 2.1% to 6.4%   |
| `N1`           | b2       | test  | 300 |       75.0% | 69.8% to 79.6% |
| `N1_mcnemar_p` | b1_vs_b0 | test  | 300 |   p = 2e-06 |                |
| `N1_mcnemar_p` | b2_vs_b0 | test  | 300 | p = 1.3e-54 |                |
| `N1_mcnemar_p` | b2_vs_b1 | test  | 300 | p = 7.6e-65 |                |

#### Agent scenarios (A1)

Scenarios with named checks: tool and resolved arguments, traced figure, citation, faithfulness and text.

| Metric         | System       | Split |   n |       Value | 95% interval   |
| -------------- | ------------ | ----- | --: | ----------: | -------------- |
| `A1`           | rag          | test  |  50 |       16.0% | 8.3% to 28.5%  |
| `A1`           | agent        | test  |  50 |       78.0% | 64.8% to 87.2% |
| `A1_mcnemar_p` | agent_vs_rag | test  |  50 | p = 7.9e-09 |                |

#### Safety (S1)

G-red is synthetic: its filing passages are simulated, so these rows say nothing about real attackers.

| Metric                | System  | Split |   n |  Value | 95% interval    |
| --------------------- | ------- | ----- | --: | -----: | --------------- |
| `S1_attack_block`     | none    | none  | 100 |  82.0% | 73.3% to 88.3%  |
| `S1_direct_block`     | none    | none  |  40 |  57.5% | 42.2% to 71.5%  |
| `S1_advice_block`     | none    | none  |  20 | 100.0% | 83.9% to 100.0% |
| `S1_indirect_success` | none    | none  |  40 |   2.5% | 0.4% to 12.9%   |
| `S1_false_refusal`    | none    | none  | 102 |   0.0% | 0.0% to 3.6%    |
| `S1_attack_block`     | guarded | none  | 100 |  92.0% | 85.0% to 95.9%  |
| `S1_direct_block`     | guarded | none  |  40 |  80.0% | 65.2% to 89.5%  |
| `S1_advice_block`     | guarded | none  |  20 | 100.0% | 83.9% to 100.0% |
| `S1_indirect_success` | guarded | none  |  40 |   0.0% | 0.0% to 8.8%    |
| `S1_false_refusal`    | guarded | none  | 102 |   0.0% | 0.0% to 3.6%    |

#### Grader agreement (J1)

Labels come from LLM raters, not human annotators; items they marked unsure are excluded. See `notes` in `runs.csv`.

| Metric     | System | Split |   n |  Value | 95% interval    |
| ---------- | ------ | ----- | --: | -----: | --------------- |
| `J1_kappa` | grader | test  |  38 |   1.00 |                 |
| `J1_tpr`   | grader | test  |  38 | 100.0% | 75.8% to 100.0% |
| `J1_tnr`   | grader | test  |  38 | 100.0% | 87.1% to 100.0% |
| `J1_kappa` | codex  | test  |  38 |   0.87 |                 |
| `J1_tpr`   | codex  | test  |  38 |  83.3% | 55.2% to 95.3%  |
| `J1_tnr`   | codex  | test  |  38 | 100.0% | 87.1% to 100.0% |

#### Not measured yet

No row exists for: LOAD (Load (simulated)), CHAOS (Chaos), U1 (Users). Nothing is claimed for them.
<!-- results:end -->

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
