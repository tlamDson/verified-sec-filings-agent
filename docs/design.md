# System design: Verified SEC Filings Research Agent

Version 0 (scaffold). This document is written before most of the system exists. It records the intended design and the reasons for it; later PRs update it as parts are built and measured.

**About numbers in this document.** Measured results appear only in `runs.csv` and are quoted from there. No row exists yet, so this version contains no measured results. Every figure below is a **planning estimate** (marked _est._) or a fixed external limit (marked _limit_), with the arithmetic shown so it can be checked and replaced by a measurement later.

## Problem

An analyst reading a listed company's 10-K and 10-Q filings asks questions such as "How did NVIDIA's gross margin over three years compare with AMD's?" or "Which risk factors are new in this year's 10-K?". A plain LLM chatbot answers fluently but invents numbers or picks the wrong period (fiscal versus calendar year, original versus restated figure), and the reader cannot tell which sentences are right.

The core idea: **numbers never come from the model.** Numbers come from deterministic tools over SEC XBRL data; text comes from hybrid retrieval with citations; an output checker blocks any figure it cannot trace to a tool result or a cited passage.

## Requirements

### Functional

1. Answer numeric questions (value, year-over-year growth, ratios, peer comparison, tricky fiscal periods) from XBRL facts, with period end date and unit shown.
2. Answer qualitative questions from filing text (Items 1, 1A, 7, 7A of 10-K; MD&A and Risk Factors of 10-Q) with citations to the exact passage.
3. Check every number in an answer against tool results and cited passages; drop the sentence or block the answer when a number cannot be traced.
4. Serve the same agent through a web chat (citations panel, charts, feedback), an MCP server, and a CLI for evaluation.
5. Degrade gracefully when every LLM provider is out of quota: return a deterministic "fact card" (XBRL numbers, ratios, chart, cited passages) without LLM prose, and say so.
6. Keep simulated users in their own cohort, end to end, from accounts to dashboards to `runs.csv`.

### Non-functional

| Concern         | Requirement                                                                                                     |
| --------------- | --------------------------------------------------------------------------------------------------------------- |
| Correctness     | No untraced number reaches the user (the faithfulness checker is the last gate).                                |
| Cost            | $0: free tiers and local models only; no per-request billing.                                                   |
| SEC fair access | At most 10 requests per second across all workers (_limit_, SEC policy), with a real contact in the User-Agent. |
| Reproducibility | Every eval number is tied to a git SHA, an `index_version`, a split, and a config in `runs.csv`.                |
| Availability    | API replicas are stateless; any replica can resume any conversation.                                            |
| Observability   | One OpenTelemetry trace per question across API, agent, tools, and LLM calls.                                   |

## Capacity estimates

All values are _est._ from the plan's sampling choices; ingest and eval PRs replace them with measured rows in `runs.csv`.

| Quantity                        | Estimate               | Derivation                                                                           |
| ------------------------------- | ---------------------- | ------------------------------------------------------------------------------------ |
| Companies                       | 50                     | 5 per GICS sector × 10 sectors, seeded sample of the S&P 100                         |
| Filings                         | ~1,000                 | 50 companies × 5 fiscal years × (1 10-K + 3 10-Q), plus amendments                   |
| Text chunks                     | ~40,000                | ~40 section chunks of ~400 tokens per filing                                         |
| Annual XBRL facts               | ~7,500                 | ~30 core US-GAAP concepts × 50 companies × 5 years, plus quarterly facts             |
| Vector storage                  | ~123 MB for d = 768    | 40,000 chunks × d dimensions × 4 bytes; scales linearly with the embedding model's d |
| SEC requests for a full ingest  | a few thousand         | 1 submissions + 1 companyfacts per company, plus index and document pages per filing |
| Minimum full-ingest fetch time  | minutes, not hours     | requests ÷ 10 per second; the raw cache makes re-runs free                           |
| LLM calls per question          | ~4                     | tool selection, tool follow-up, answer, optional repair                              |
| Questions per day in production | provider quota ÷ 4     | bounded by the free provider's daily quota, then degraded mode                       |
| Eval cost with local Qwen       | ~1 minute per question | ~10,000 prompt + ~500 output tokens; the first night measures the real rate          |

These sizes decide several choices below: ~40,000 chunks fit comfortably in pgvector inside the same Postgres as the facts, and SEC filings arrive daily, so batch ingest is enough.

## Architecture

```
                 ┌──────────── Ingest (scheduled batch) ────────────┐
SEC EDGAR ──►  scheduler ──► jobs (Postgres queue, SKIP LOCKED) ──► N ingest workers
 (10 req/s)                                                         │  shared token bucket, 10 req/s
                                                                    ▼
                    raw cache (disk) ──► parse XBRL → facts │ parse HTML → sections → chunks
                                                                    ▼
                                   embed (GPU) ──► Postgres: facts, chunks, pgvector, BM25
                                                    (every row carries index_version)

                 ┌──────────── Query (online) ────────────┐
Web (Next.js) / MCP client ──► API replicas ×2–3 (stateless, behind a load balancer)
                                 │ per-user rate limit + global LLM semaphore
                                 ▼
                        LangGraph agent (checkpoints in Postgres)
                         ├─ get_fact / compute_ratio / compare_peers ──► SQL
                         ├─ search_filings ──► hybrid SQL ──► reranker (breaker, timeout)
                         └─ LLM router ──► provider A │ B │ local (failover, per-provider quota)
                                 ▼
                        numeric faithfulness checker ──► streamed answer (SSE) with citations
                                 │
                          OpenTelemetry ──► Phoenix   │   answer cache (question, index_version, model)

                 ┌──────────── Eval (offline: CI and nightly) ────────────┐
golden sets ──► runner ──► results/*.json ──► CI gate (deterministic part) ──► runs.csv ──► README
```

### Components

| Component             | Responsibility                                                                                            | Built in |
| --------------------- | --------------------------------------------------------------------------------------------------------- | -------- |
| EDGAR client          | Token bucket, User-Agent from `SEC_USER_AGENT`, raw cache, retry with jittered backoff                    | s-01     |
| Job queue and workers | Postgres queue with leases and heartbeats; idempotent upserts keyed by accession number                   | s-02     |
| XBRL parser           | companyfacts → facts; concept normalisation table; all amendment versions kept with filing date           | s-03     |
| Filing parser         | 10-K/10-Q HTML → sections → ~400-token chunks, tagged with `index_version`                                | s-04     |
| Retrieval             | Embeddings in pgvector (HNSW), BM25 via `pg_search` (fallback `tsvector`), RRF fusion in SQL              | s-05     |
| Deterministic tools   | `get_fact`, `compute_ratio`, `compare_peers`, `search_filings`, `diff_risk_factors`                       | s-08     |
| Agent and LLM router  | LangGraph state graph, Postgres checkpoints, OpenAI-compatible router with failover and quota             | s-09     |
| Faithfulness checker  | Extract every number from an answer; match it to a tool result or cited passage, unit and period included | s-10     |
| Web and API           | FastAPI SSE + Next.js chat, citations panel, charts, feedback, Auth.js, quotas, degraded mode             | s-17     |
| Observability         | OpenTelemetry GenAI spans → Phoenix                                                                       | s-18     |

### Data stores

One Postgres 17 instance (ParadeDB image locally: pgvector and `pg_search` bundled) holds facts, chunks, vectors, the BM25 index, the job queue, and agent checkpoints. Locally it runs from `compose.yaml`; in production it is a free-tier managed Postgres. Phoenix stores traces separately.

### Experiment record

`runs.csv` is the single source of reported numbers. Columns (validated by `sec_agent.runs.RunRow`):

| Column                             | Meaning                                                                           |
| ---------------------------------- | --------------------------------------------------------------------------------- |
| `date`, `git_sha`                  | When and at which commit the number was measured                                  |
| `metric`                           | Metric ID from the plan (N1, N2, R1, C1, A1, J1, S1, G1, L1, U1) or a sub-metric  |
| `system`                           | Configuration measured, e.g. `b0`, `b1`, `b2`, `bm25`, `hybrid+rerank`            |
| `split`                            | `train`, `dev`, `test`, or `none`                                                 |
| `cohort`                           | `real`, `simulated`, or `none`; user metrics (U*) must name `real` or `simulated` |
| `n`, `value`, `unit`               | Sample size, the number, and its unit                                             |
| `ci_low`, `ci_high`                | Confidence interval, both or neither; the value must lie inside                   |
| `index_version`, `config`, `notes` | Index snapshot, configuration string, free text                                   |

## Distributed concerns

| Problem                                                                 | Approach                                                                                                                  | Concept                                                             |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Several ingest workers must not duplicate work or exceed SEC's 10 req/s | Postgres queue with `FOR UPDATE SKIP LOCKED`, one shared token bucket, idempotent upserts keyed by accession number       | work queue, at-least-once delivery + idempotency, global rate limit |
| A worker dies mid-job                                                   | Jobs hold a lease renewed by heartbeat; an expired lease returns the job to the queue; keyed writes make re-runs harmless | lease, crash recovery, exactly-once effect                          |
| Several API replicas must continue the same conversation                | Replicas hold no state; LangGraph checkpoints live in Postgres; any replica resumes                                       | stateless service, externalised state                               |
| Two replicas resume one conversation at once                            | Versioned checkpoints with optimistic locking                                                                             | optimistic concurrency                                              |
| Reindexing must not mix into answers in flight                          | Every fact and chunk carries `index_version`; each query pins one version; blue/green reindex, then switch the pointer    | versioned snapshot, blue/green                                      |
| An LLM provider is slow, out of quota, or down                          | Router with per-provider circuit breaker and quota counter, ordered failover, per-step timeouts                           | failover, circuit breaker, bulkhead                                 |
| Too many users at once                                                  | Per-user rate limit, global semaphore on concurrent LLM calls, queue with timeout, answer cache                           | backpressure, load shedding                                         |
| Finding where time goes                                                 | OpenTelemetry trace across API → agent → tool → LLM                                                                       | distributed tracing                                                 |

### Job queue (built in s-02)

Code: `sec_agent.jobs`. One table, `jobs`, unique on `(kind, key)`; enqueueing the same `(kind, key)` again does nothing, so a scheduler can enqueue everything it sees on every run.

```
queued ──claim──► running ──complete──► done
  ▲                 │ │
  └──fail (retry)───┘ └──fail (final, permanent, or lease expired on last attempt)──► failed
  ▲                 │
  └─lease expired───┘   (the next claim takes the job over; attempts + 1)
```

- **Claim** is one statement: select the oldest job that is queued and due, or running with an expired lease, `FOR UPDATE SKIP LOCKED`, and lease it. Claimers never wait on each other and never get the same row.
- **Lease and fencing.** A claim writes a new random `lease_token` and an expiry. Heartbeat, complete, and fail all match on the token, so a worker whose lease was taken over gets "lease lost" and its late report changes nothing.
- **Heartbeat** runs in a background thread while the handler runs. A failed heartbeat (dropped connection) is retried at the next interval; only a lost lease stops it.
- **Retry** uses exponential backoff with full jitter, capped. A `PermanentJobError` fails the job at once. A job whose lease expires on its last attempt is failed with that reason instead of being retried.
- **Delivery is at least once.** A job can run twice (the worker dies after writing but before reporting), so every handler writes under natural keys (CIK, accession number) with upserts. That makes the effect exactly once.
- **Defaults** (configuration, not measurements): 60 s lease, 20 s heartbeat, 5 attempts, backoff from 5 s capped at 600 s. CLI: `sec-agent jobs init`, `sec-agent jobs stats`, `sec-agent worker [--drain]`.

### XBRL facts (built in s-03)

Code: `sec_agent.xbrl`. One job per company and snapshot, kind `xbrl.companyfacts`, key `<index_version>:<CIK>` (CLI: `sec-agent xbrl init`, `sec-agent xbrl enqueue --index-version v1 CIK...`). The handler fetches `companyfacts` through `EdgarClient`, normalises it in memory, and upserts in one transaction.

```
companyfacts JSON ──► entries (exact decimals) ──► concept table ──► fiscal calendar ──► facts (every version)
                                                   tag → concept      own period → label        │
                                                   unit, period type  (E1)                      ▼
                                                                                       facts_latest view (E2)
```

- **Concept table** (`concepts.py`): about 30 canonical concepts (revenue, gross profit, operating income, net income, EPS, cash, assets, liabilities, equity, cash flows...). Each lists its US-GAAP tags in priority order; within one filing and period the first tag that reports a value wins. A tag is listed only when it means the same thing: lines that include more (noncontrolling interest, current portion of debt, restricted cash) or less (goods-only or services-only revenue and cost, nonoperating-only interest, pretax income before equity-method income) are left out. A narrower line worth keeping is its own concept, never a fallback for the wider one: `dividends_paid_common` (common stock only) beside `dividends_paid` (all dividends), `marketable_securities_current` beside `short_term_investments`. Each concept declares its unit (E5) and period type; entries in another unit or of the other period type are dropped, never converted.
- **Fiscal labels (E1).** companyfacts' `fy`/`fp` describe the filing, not the value: a 10-K repeats prior years under its own `fy`. The calendar learns each 10-K/10-Q's own period (the latest end date carrying more than half as many facts as the busiest one) and labels each fact by its own end date. A company's offset between `fy` and the year its fiscal year ends in is treated as a constant: years that break a strict-majority offset are relabelled (NVIDIA's early 10-Ks say `fy` one year low). Quarters take the fiscal year that contains them; a quarter ending on a fiscal year end is Q4; six- and nine-month durations are stored as `ytd`. A fact whose end date is no known period end keeps its dates and has no label.
- **Versions (E2).** Every filing's value is a row, keyed by `(index_version, cik, concept, unit, period_start, period_end, accession)`. The view `facts_latest` returns, per period, the latest filed version (greatest filed date, then accession), the original value, the number of versions, and `restated` when any value differs, including precision changes (thousands, then millions). `versions.latest_versions` applies the same rule in Python; a test holds them equal.
- **Counted, not hidden.** Each ingest writes a report row (`xbrl_ingests`): entries seen, facts kept, and how many were dropped for form (only 10-K, 10-K/A, 10-Q, 10-Q/A), unit, period type, unsupported duration, conflicting values within one filing, or a lower-priority tag, plus unlabelled facts and relabelled years.
- **Idempotent.** The upsert on the version key, under a per-company advisory lock, makes a job that runs twice write each row once. A missing company (404) or a malformed document fails the job permanently; SEC unavailability is retried by the queue.

### Filing text index (built in s-04)

Code: `sec_agent.filings`. One `filing.sections` job per filing and index version.

```
submissions JSON ──► 10-K, 10-K/A, 10-Q, 10-Q/A in the report window ──► jobs (key: index_version/accession)
primary HTML (EdgarClient) ──► text blocks ──► sections ──► chunks ──► indexed_filings, filing_sections, chunks
```

- **Text blocks.** One block per paragraph, line, or table row (cells joined by a space). Dropped: `script`, `style`, `head`, the inline-XBRL `ix:header`, anything styled `display:none`, page numbers, and "Table of Contents" back-links.
- **Sections.** 10-K: Item 1 (`business`), 1A (`risk_factors`), 7 (`mdna`), 7A (`market_risk`). 10-Q: Part I Item 2 (`mdna`), Part II Item 1A (`risk_factors`). Amendments use their base form's items. A heading is a short block "Item _n_" plus a title that matches the item and is the whole rest of the block; "Item 7 of this report…" and "Item 1A: Risk Factors in our 2023 Form 10-K." are references, not headings. A section ends at the next item heading, "PART", or "SIGNATURES". The table of contents repeats every heading, so the candidate with the longest body wins.
- **Chunks.** Paragraphs are packed greedily up to `max_tokens`; a longer paragraph is cut at sentence ends, a longer sentence at token boundaries. Chunks do not overlap. Each chunk stores `char_start`/`char_end` into its section text, so a citation points at an exact span, and carries the filter columns (CIK, form, filing and report dates, section) on its own row. Tokens are a model-free proxy (one per word run or punctuation mark) until s-05 picks the embedding model.
- **`index_version`** is `chunks-p<parser>-t<max_tokens>-<digest>`, the digest covering the parser version and the whole chunk configuration. Same code and configuration give the same name; any change gives a new one, whose jobs and rows are built beside the old ones (blue/green). A worker refuses a job enqueued for a version it does not build. A test pins the parser's output on a fixture, so changing it without bumping the parser version fails CI.
- **Idempotent writes.** A job deletes and re-inserts its filing's rows for its version in one transaction under an advisory lock on `(index_version, accession)`, so a second delivery, or two workers after a lease takeover, leave one copy. A filing with no section found (a 10-K/A that only amends Part III) still gets an `indexed_filings` row, so coverage can be counted.
- **Defaults** (configuration, not measurements): 400 tokens per chunk; report window 2019-04-01 to 2025-01-31, a superset of FY2020–FY2024 under any fiscal calendar (exact fiscal years come from XBRL). CLI: `sec-agent filings init`, `sec-agent filings enqueue CIK… [--report-from] [--report-to]`, then `sec-agent worker`.
- **Known gap.** Filings that put MD&A outside the item structure (an "Item 7" line that only points to an annual-report section elsewhere in the document) yield only that pointer text for the item.

## Failure modes

| Failure                                         | Effect                              | Mitigation                                                                                                  |
| ----------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| SEC returns 429 or is unavailable               | Ingest stops or the IP is blocked   | Token bucket, jittered backoff, raw cache, idempotent re-runs                                               |
| Companies tag XBRL differently, or wrongly      | Numeric answers wrong at the source | Tested concept normalisation table; questions that cannot be normalised are excluded and counted separately |
| Restated figures (10-K/A)                       | Two "right answers" for one period  | Keep every version with its filing date; default rule in E2                                                 |
| LLM invents a number or the wrong period        | The most serious error              | Numbers only from tools; faithfulness checker (N2); CI gate                                                 |
| Prompt injection inside filing text             | Agent follows foreign instructions  | Source text marked as data, canary tokens, read-only tools, S1 test set                                     |
| Reranker slow or down                           | Latency rises                       | Timeout, breaker, fall back to hybrid order                                                                 |
| Embedding model differs between index and query | Retrieval silently wrong            | Store model name and `index_version` with the index; refuse queries on mismatch                             |
| Cold start with zero minimum replicas           | First question slow                 | Reported separately in L1; warm-up health check                                                             |
| Very long filings                               | Context overflow or token cost      | Only reranked chunks enter the prompt; token budget per step                                                |

## Edge-case rules

These decide what counts as the correct answer, so eval and product follow the same rule.

| #   | Case                                   | Example                                   | Rule                                                                                                                                  |
| --- | -------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | Fiscal year differs from calendar year | NVIDIA FY2024 ends January 2024           | Always use the fiscal year and show the period end date; for a calendar-year question, ask or state the assumption                    |
| E2  | Restated figures                       | A 10-K/A corrects prior-year revenue      | Use the latest filed figure; note the original when it differs                                                                        |
| E3  | Peers with different fiscal calendars  | Apple (September) and Microsoft (June)    | Compare each company's own fiscal year with a period-end column; no conversion to calendar years                                      |
| E4  | Non-GAAP measures                      | "Adjusted EBITDA" is not in XBRL          | Answer only if the company reports it in text, with a citation and the label "non-GAAP, as reported by the company"; never compute it |
| E5  | Units and scale                        | Thousands versus units; USD versus shares | Take units from XBRL; the checker rejects unit mismatches                                                                             |
| E6  | Relative time                          | "last quarter", "this year"               | Anchor on the question date and state the concrete period used                                                                        |
| E7  | Company outside the 50 in scope        | A small-cap company                       | Say it is out of scope; no ingest at question time                                                                                    |
| E8  | Renames and mergers                    | FB → META; Activision into Microsoft      | Look up by CIK, with an alias table of names and tickers                                                                              |
| E9  | Forecasts or investment advice         | "Should I buy NVDA?"                      | Decline to advise; still give historical figures with a disclaimer                                                                    |
| E10 | Text and XBRL disagree                 | An MD&A table rounds differently          | XBRL wins for numbers; mention the gap when it exceeds a threshold                                                                    |
| E11 | Segment versus consolidated figures    | Data Center segment revenue               | Prefer consolidated; segment figures only when asked explicitly, with a citation                                                      |
| E12 | No answer exists                       | The figure is not disclosed               | Answer "not in the filings"; this counts as a correct answer                                                                          |

## Non-goals

Every component must be justified by a metric or a requirement. Deliberately left out:

- **Kafka or streaming.** Filings arrive slowly, by day; batch ingest is enough.
- **A separate vector database.** pgvector in the same Postgres as the facts handles ~40,000 chunks (_est._).
- **Redis or BullMQ.** The Postgres queue does the job with one component fewer.
- **Microservices beyond API, worker, and reranker.**
- **Fine-tuning the LLM.** Only a small reranker is fine-tuned, and kept only if it beats the baseline.
- **Multi-region or Kubernetes in the core.** k3d + Helm is an optional last step.

## Open items

- Measure local Qwen throughput on the first eval night and replace the eval-cost estimate.
- Choose the production LLM provider by measuring free quotas.
- Check FinanceBench licence and answers before using G-public.
- Confirm free-tier database size limits against measured index size.
