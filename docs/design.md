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
| Companies                       | 50                     | seeded sample of the S&P 100, sectors taking turns (see Golden sets)                 |
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

### Hybrid retrieval (built in s-05)

Code: `sec_agent.retrieval`. A chunk build (`index_version`) becomes searchable once it is embedded into an **embedding space**: that build plus one model and its settings.

```
chunks (index_version) ──► build_index ──► chunk_embeddings (vector) + partial HNSW index per space
                                      └──► chunk_lexical (tsvector, length) ──► lexical_df, lexical_stats
query ──► dense arm (cosine, HNSW or exact) ─┐
      └─► lexical arm (BM25 in SQL) ─────────┴─► RRF in SQL ──► hits with citation spans
snapshot (name, space, SHA-256 of every chunk and vector) ──► pointer "serving" (blue/green)
```

- **Embedding space.** Named `<index_version>.e-<model>-d<dims>-<digest>`, the digest covering every setting that changes vectors: model id, dimensions, normalisation, query and passage prefixes, input limit. A new model or prefix is a new space built beside the old one. Default model: `BAAI/bge-base-en-v1.5` (768 dimensions, 512 input tokens, normalised, its documented query instruction), run locally with `sentence-transformers` on the GPU. It is the optional `embed` extra (`uv sync --all-packages --extra embed`); tests and CI use a deterministic hashing stand-in.
- **Vectors.** One `vector` column without a fixed dimension, so spaces of different models share the table; each space gets a partial HNSW index (`m = 16`, `ef_construction = 64`, cosine) on `embedding::vector(<dims>)` `WHERE space = '<name>'`, as pgvector recommends for mixed dimensions. Each batch is checked before it is written: one vector per text, the space's dimension, finite values, unit length.
- **Build.** `sec-agent index build` embeds only chunks with no vector in the space, in key order, one transaction per batch, so a re-run costs nothing and a crashed run resumes. A re-ingested filing loses its vectors by cascade and is embedded again. Passages longer than the model's input limit are counted in the build report (`truncated`), not hidden: chunk sizes use the model-free token proxy from s-04.
- **Dense arm.** Without filters it walks the space's HNSW index, with `hnsw.ef_search` raised to cover the request. With any filter (company, form, section, report dates) it ranks every matching chunk exactly: an approximate scan followed by a selective filter would silently return fewer results, and one company's chunks are few. Exact ties (the same boilerplate in two filings) rank by chunk key.
- **Lexical arm: BM25 in plain SQL.** Lexemes from `to_tsvector('english', …)`; Okapi BM25 with `k1 = 1.2`, `b = 0.75` and Lucene's non-negative idf, using per-version document frequencies and average length rebuilt by the build. A test checks every score against a Python BM25 over the same lexemes. The query is never parsed as `tsquery` syntax: its lexemes are quoted and joined with OR. `pg_search` is not used: plain SQL runs the same on the local ParadeDB image, the test Postgres and a managed free-tier Postgres.
- **RRF in SQL.** Hybrid takes each arm's top `candidates` (default 50), adds `1 / (60 + rank)` per arm through a full outer join, and orders by that sum, then the best rank either arm gave, then chunk key: the order `rrf.rrf_fuse` defines, and a test holds the SQL equal to it. Modes `dense`, `lexical` and `hybrid` share one query, so the retrieval baselines in R1 differ only in the arm.
- **Pinning and mismatch.** A query names one space; the stored space must equal it and the query embedder must have the same settings, or the search is refused (failure mode "embedding model differs between index and query"). Every hit carries `index_version`, accession, section, `char_start`/`char_end` into the section text, and the filing URL, so a citation points at an exact span.
- **Snapshots for eval.** `sec-agent index snapshot NAME` records a space only when it is complete (every chunk has a vector and a lexical row, statistics match those rows), with chunk and filing counts and a SHA-256 over every chunk key, text hash and vector in key order. `--manifest` writes it as JSON for an eval run to keep beside its results. `verify` recomputes the digest; a name never moves to other content. `activate NAME` verifies, then points `serving` at it: switching the pointer is the blue/green cut-over.
- **Defaults** (configuration, not measurements): batch 64, 10 results, 50 candidates per arm, RRF k = 60. CLI: `sec-agent index init`, `index build [--device cuda]`, `index snapshot NAME [--manifest PATH]`, `index verify NAME`, `index activate NAME`, `index search QUERY [--mode] [--cik] [--form] [--section] [--report-from] [--report-to] [--json]`.

### Golden sets (built in s-06)

Code: `sec_agent.golden`. Every golden set is split by **company**, never by question, so no test question is about a company seen while tuning.

```
sp100.csv (S&P 100, sector, CIK, fiscal year end) ──► seeded sample of 50 ──► 30 train · 10 dev · 10 test
                                                                               │
facts_latest (E2) ──► G-num candidates ──► per-split quota × 5 types ──► g_num.jsonl
hand-written questions (test companies) + TREC runs ──► top-k pool ──► blind labels 0/1/2 ──► qrels
FinanceBench download ──► manifest check (licence, answers, SHA-256 pins) ──► g_public.jsonl
```

- **Universe.** `sp100.csv` has one row per S&P 100 company (Alphabet's two share classes are one CIK): membership and GICS sector from the index's components table (as of 2026-09-21), CIK and current fiscal year end from SEC (`company_tickers.json`, `submissions`) through `EdgarClient`. Companies with no 10-K for part of FY2020–FY2024 (GE Vernova, Sandisk) carry an exclusion reason and are never sampled.
- **Sample.** Only seven GICS sectors have five or more S&P 100 members, so the plan's "5 per sector × 10 sectors" cannot hold. Instead sectors take turns, in a seeded order, each giving its next company in a seeded order, until 50 are taken: sectors stay within one company of each other unless one runs out.
- **Split.** Test, then dev, draw **same-sector pairs**, walking the sectors in seeded order and taking a pair only from a sector that keeps at least one company for train; the rest is train. Pairs let every split ask peer questions inside itself. Until a split holds two companies whose fiscal year does not end in December, the walk prefers sectors that have one, so the fiscal-period trap (E1) can be asked on test. Order comes from SHA-256 of seed and key (no random generator), so adding a company never reorders the others. Committed as `data/golden/company_split.json` (seed 20261113); a test regenerates it from the packaged universe. CLI: `sec-agent golden split`.
- **G-num.** From each company's latest facts in one `index_version`, five question types: `value` (a reported figure), `fiscal_period` (the same, when the period leaves the calendar year its fiscal year names: E1), `yoy_growth` (same fiscal period a year before, in percent), `ratio` (gross, operating and net margin, effective tax rate: two facts of exactly the same period, positive denominator), `peer_comparison` (two same-sector companies of one split, each on its own fiscal year: E3). Questions are fixed templates; answers are computed in `Decimal` and rounded half-even to six places, with every source fact (accession, filing date, original value if restated). Year-to-date sums and unlabelled facts are not asked. Per split, the quota (configuration: 900 train, 300 dev, 300 test, FY2020–FY2024) is shared equally by the five types; within a type, companies (or pairs) take turns in seeded order. A short stratum keeps every candidate and reports the shortfall; quotas never move between types. CLI: `sec-agent golden gnum --index-version V`.
- **G-ret.** Questions are written by hand before reading the filings (gate G-F2), one JSON line each with the ticker of a test company; any other company is refused. The first set (`data/golden/g_ret_questions.jsonl`, q001-q100, 10 per test company, every tenth meant to have no answer in the filings) was drafted by an LLM (Claude) without reading the filings, avoiding each company's own product terms, and reviewed and approved by the owner on 2026-11-13; results on it are reported as "LLM-drafted, owner-reviewed questions", not as hand-written ones. Retrieval runs come in TREC format (`qid Q0 accession/section/ordinal rank score system`). The pool is the union of each system's top 20 per question (TREC pooling: unpooled chunks count as not relevant), in a seeded order per question, with the chunk text from the index. The labelling session shows question and text only, never which system found a chunk or its rank; each grade (0, 1, 2) is appended to the label file at once and tied to the text's SHA-256, so a re-chunked index makes old labels pending again. CLI: `sec-agent golden pool --run R ...`, `golden label`, `golden qrels`.
- **G-public.** FinanceBench's open sample is read from a local download, never committed. `data/golden/g_public_manifest.json` records the licence (CC BY-NC 4.0, from the Hugging Face dataset card; checked 2026-11-13), whether the answers were checked (not yet), and the SHA-256 of both files. The loader refuses the data until both checks are recorded and both files match their pins. Each question gets its company's ticker and split when the company is in the universe; it is `in_scope` only for a split company and a 10-K or 10-Q document (E7). CLI: `sec-agent golden public --questions F --documents D`.

### Eval runner (built in s-07)

Code: `sec_agent.eval`. Statistics are plain Python (no numeric dependency) and seeded.

```
G-num questions ──► b0 | b1 | (b2, s-12) ──► results/numeric/SPLIT/SYSTEM.jsonl (raw output, prompt hash)
                                                  │ parse last JSON reply ─► grade ─► Wilson CI, McNemar
G-ret questions ──► snapshot (verified before and after) ──► random | bm25 | vector | hybrid ──► TREC runs
                                                  │ + qrels ─► recall@5, nDCG@10, MRR@10 ─► bootstrap by company
                                                  ▼
                                      `--record runs.csv` (one row per number)
```

- **N1 grading.** A baseline ends its reply with one JSON object (`number` with value, unit, fiscal year and period or period end; `company`; `not_found`); numbers are read as `Decimal`. Correct means: same unit (E5: a value in millions is a wrong value), the question's fiscal year and period and, when given, the answer's period end (E1), and the value within 0.5% relative error, or within 0.1 percentage points for percent answers (ratios and growth). Peer comparisons need the right ticker. Wrong answers are counted by kind (`unparsed`, `not_found`, `wrong_kind`, `wrong_unit`, `wrong_period`, `wrong_value`, `wrong_company`) for the error analysis of the improvement loop.
- **Baselines.** b0 sends the question and the answer format only. b1 adds the top 5 hybrid passages of the question's companies, fenced as `<passage id="accession/section/ordinal">` and marked as data, not instructions. Both take a chat model as a parameter; the provider router (s-09) supplies it, and s-12 runs them. Answers are appended to a cache (`SYSTEM.cache.jsonl`) as they arrive; a rerun asks only (question, model, prompt hash) triples without a cached answer, so an interrupted night resumes and a changed prompt or passage set asks again. Each run then rewrites the results file (`SYSTEM.jsonl`) with exactly one answer per question for the requested model and prompts, so a rerun of an earlier model or prompt scores that model or prompt, never a leftover answer.
- **N1 statistics.** Systems are scored on the questions every system answered; a results file with two answers to one question, or answers from two models, is refused. Each system's missing count is printed, so a short run shows as a smaller N, not a better score. Accuracy has a Wilson 95% interval; every pair of systems gets an exact two-sided McNemar test on the discordant questions.
- **R1.** `eval retrieval run` pins a snapshot, verifies its digest before and after, and writes one TREC run per baseline plus the snapshot manifest; every baseline searches only the question's company. `random` orders the company's chunks by a seeded hash; `oracle` (scoring only) orders judged chunks by grade. Grade 1 or 2 is relevant, unjudged chunks are not (pooling). nDCG uses linear gain (as trec_eval). Questions with no relevant judged chunk are listed and left out. Intervals and paired differences come from resampling companies (10 test companies, 10,000 resamples, one seed for every system so they see the same resamples).
- **runs.csv.** `--record` appends one row per number: `N1` accuracy with its interval, `N1_mcnemar_p`, `R1_<metric>` with its interval, `R1_<metric>_diff` and `R1_<metric>_p`; cohort `none`, the git SHA, the questions' `index_version`.
- CLI: `sec-agent eval numeric --split test --systems b0,b1`, `sec-agent eval retrieval run --snapshot S`, `sec-agent eval retrieval score --run R ... --baseline bm25 --oracle`.

### Deterministic tools (built in s-08)

Code: `sec_agent.tools`. The only places an answer's numbers and quotes come from. Each tool takes a Pydantic argument model (its JSON schema is what the agent and the MCP server show) and returns a Pydantic result; `tools.catalog` lists the five.

```
FactsContext (facts index_version) ──► get_fact · compute_ratio · compare_peers ──► PostgresFactStore.lookup ──► facts_latest
TextContext (embedding space)      ──► search_filings ──► retrieval.search (hybrid; BM25 alone without an embedder)
                                   └─► diff_risk_factors ──► filing_sections (10-K, 10-K/A Item 1A) + facts (fiscal labels)
```

- **Companies.** Ticker, CIK, name (suffixes such as "Inc." ignored) or a former ticker (`FB` → `META`) resolve to one CIK of the universe (E8); anything else is out of scope (E7), and a name shared by two companies is refused as ambiguous.
- **get_fact.** One canonical concept, in its own unit (E5), for a fiscal year and period of the company's own calendar (E1): FY is the annual period, Q1–Q4 the quarter, `year_to_date` the six or nine months (Q4 year-to-date is the year); a balance at Q4 is the year-end balance and has no year-to-date. The value is the latest filed version, with the original value, filing and version count beside it (E2). A value not reported is the answer `not_reported` (E12); a name outside the canonical concepts is refused, with non-GAAP measures pointed to the text (E4).
- **compute_ratio.** Gross, operating and net margin, effective tax rate, R&D and operating cash flow to revenue (percent), current ratio and liabilities to equity (times), and `yoy_growth` of any concept against the same fiscal period a year before. Both parts must be reported for exactly the same period and the denominator be positive (growth: the prior value not zero), else the result is `not_reported` or `undefined` with the reason. `Decimal`, rounded half-even to six places, the same formulas as the G-num answers.
- **compare_peers.** One concept or ratio for two to ten companies, or a company's GICS sector, read with **one** SQL query. Each company on its own fiscal year (E3), every row with its period end and `same_period_end` saying whether they line up; equal values share a rank; a company without the value is listed unranked.
- **search_filings.** Retrieval over the pinned space with company, form, section and report-date filters; every passage carries its citation key `accession/section/ordinal`, character span in the section text and filing URL. Defaults (configuration): 8 passages, at most 20.
- **diff_risk_factors.** Item 1A of a 10-K against an earlier fiscal year's (default: the latest against the year before). A filing's fiscal year is the XBRL label of the year ending on its report date, else the report date's year (`fiscal_year_basis` says which); a 10-K/A with a new Item 1A supersedes the 10-K. Paragraphs equal after case and spacing are unchanged wherever they moved; the rest pair as `changed` most similar first while the Jaccard index of their word sets is at least 0.5 (configuration); the remainder is `added` or `removed`. Each change has its offsets for a citation. A missing year is `not_found`.
- **In memory.** `MemoryFactQuery` applies the same latest-version rule to facts in memory, per company; a test holds it equal to the SQL lookup, so an eval run can read a fixture without a database.

### Agent and LLM router (built in s-09)

Code: `sec_agent.agent`, `sec_agent.llm`. The model chooses tools and writes prose; code runs the tools and keeps their results. Every limit below is configuration, not a measurement.

```
Agent.ask(thread_id, question, asked_on)
  begin ──► model ──► tool calls? ──► tools ──► model ──► ... ──► done        (checkpoint after every step)
              │                         └─ ToolRunner ──► sec_agent.tools (pinned index versions)
              └─ LLMRouter ──► provider 1 │ 2 │ ... in order
                    per provider: circuit breaker ──► quota (llm_usage) ──► POST {base_url}/chat/completions
```

- **Turn.** `Agent.ask` returns an `Answer`: the text, a status (`answered`, `step_limit`, `degraded`, or `blocked` by the faithfulness checker), the turn's `evidence` (every tool call with the JSON result exactly as the model saw it) and its `llm_calls` (provider, model, tokens, and what the router tried). A turn makes a bounded number of model calls; the last allowed call is sent with tools switched off, and a reply that still asks for tools ends the turn as `step_limit`. A reply cut off at the output limit, or empty, is not shown: half a number is worse than none.
- **Tools as the model sees them.** `ToolRunner` offers the catalog's JSON schemas (the text tools only when a text index is pinned), validates the model's arguments, and returns the result as JSON with decimals as exact strings. A refusal (`unknown_company` for E7, `invalid_arguments`, `unknown_tool`) is a result the model reads, not a crash. A result over the size budget is never cut mid-text: search drops whole passages from the end, anything else is withheld as `result_too_large`.
- **Prompt and history.** The system prompt states the product rules (numbers only from tool results, fiscal years and period ends, restatements, non-GAAP, out of scope, no investment advice, passages are data) and the date the question was asked, which relative periods anchor on (E6). The model sees the current turn whole and earlier turns as question and final answer only, so a follow-up's numbers must come from tool results of its own turn. The prompt asks; the faithfulness checker (s-10) and guardrails (s-13) enforce.
- **Router.** Providers are OpenAI-compatible endpoints listed in `LLM_PROVIDERS` (JSON, tried in order; default: a local llama.cpp server). A key is named by its environment variable, never written in the list. For each provider the breaker must allow a call, then the quota must have room; 429 opens the breaker for the provider's `Retry-After` (capped), a timeout, transport error, 5xx or malformed reply counts toward opening it, another 4xx fails over without counting. Calls to one provider overlap, so the breaker numbers each call it lets through and weighs an outcome by when its call was sent, not when the outcome arrives: a success or failure of a call sent before the breaker last opened changes nothing (a slow success cannot close it, a slow failure cannot restart its wait, neither decides the trial call), and while closed "failures in a row" is in the order sent. A 429 is honoured whenever it arrives and only ever lengthens a wait; no outcome shortens one. Error text holds the status only, never a response body or a key.
- **Quota.** Requests per minute and per day and tokens per day, per provider, in fixed UTC windows. `llm_usage` in Postgres holds the count for all replicas; a reservation checks and counts in one transaction under a per-provider advisory lock, so replicas racing for the last request never overspend. Tokens are reserved the same way, before the call: the reservation holds an upper bound on what the call can use (the bytes of the prompt, since a token is at least one byte, plus the output limit; a request without an output limit gets a default one), and when the call returns the hold is replaced by the tokens it reports. Calls in flight therefore never add up to more than the daily token quota, as long as the provider honours the output limit. A call refused with 429 or another 4xx gives its hold back; one that timed out or returned a broken reply keeps it. A reply's usage replaces the hold only when it is complete (`prompt_tokens` and `completion_tokens` both positive whole numbers; `total_tokens` is charged instead when it is higher than their sum). A usage that is absent or leaves a count out is only a floor: the call is charged its whole bound, or the floor when that is higher. So the count errs toward closing a provider early, never late. Breaker state is per replica.
- **Degraded mode.** When no provider answers, the turn ends `degraded` with a fixed notice and the evidence gathered so far: the deterministic figures are still returned, without model prose.
- **Checkpoints.** LangGraph saves the conversation state (plain JSON values) after every step under its `thread_id`; any replica continues it, and a turn cut short by a crash leaves a conversation the next question continues. `FencedPostgresSaver` adds the optimistic lock: a checkpoint is accepted only if it was computed from the conversation's current head and its id sorts after it, checked and written in one transaction under a per-conversation advisory lock. The replica that lost the race gets `ConversationConflictError` at its next step and saves nothing further. `sec-agent agent init` creates the tables.

### Faithfulness checker (built in s-10)

Code: `sec_agent.faithfulness`. The last step of a turn: the model's draft is shown only as far as every figure, date and citation in it traces to the evidence of that turn. Code does the check; no model is asked. Defaults below are configuration, not measurements.

```
draft ──► sentences (each line; ". " + capital) ──► scan: figures, dates, years, citation keys
evidence ──► sources: tool values (unit, fiscal year, period), ranks, counts, dates, filing ids,
             passage and risk-factor text with the keys that cite it
each mention ──► traced │ wrong_period │ uncited │ wrong_unit │ untraced
sentences ──► pass (shown as written) │ trimmed (failed sentences dropped + note) │ blocked (notice)
```

- **What a figure is.** A number with its scale and unit as written: `$`, `USD` or "dollars"; "per share"; `%`; `x` or "times"; "shares"; an ordinal is a rank; anything else has no unit. Years, forms (10-K), items (Item 1A), quarters (Q3), durations ("12 months"), index names (S&P 100), links and filing ids hold digits but are not figures. Years, and the years of full dates, name the sentence's periods. Number words ("three") are not read.
- **Traced to a tool.** Rounding the tool value to the digits shown must give the figure: the tolerance is half a unit of the last digit at its scale, so "$391.0 billion" and "$391 billion" trace to 391,035,000,000 and "$390 billion" does not. The units must agree (E5: a per-share value shown as a percent is `wrong_unit`). If the sentence names a year or date, the value's fiscal year, period end year or period dates must be one of them (E1: NVIDIA's fiscal 2024 revenue stated for calendar 2023 is `wrong_period`). A count or rank has no period. Without a written sign the magnitude is compared, since "fell 2.5%" says the sign in words. Of several matches the closest wins, so a restated value and the value first reported (E2) each trace to their own field. A sum, difference or ratio the model computed is untraced: there is no tool value for it.
- **Traced to filing text.** A number of a passage counts only when the sentence cites that passage (`[accession/section/ordinal]`); a risk-factor paragraph is cited by its filing's accession. The number is otherwise `uncited`. A passage figure supports the value it states. A bare figure of a passage that states exactly one scale ("in thousands", "in millions", "in billions") also supports that figure at that scale: "12,345" in a table "in millions" supports "$12,345 million" and "$12.3 billion", never "$12,345 billion". A passage that states no scale, or several, gives its bare figures no scale at all, so an answer cannot invent one. Passage figures carry no period, and the checker does not compare them with XBRL (E10 is the prompt's rule, not this check).
- **Citations and dates.** A citation key must be a passage of the turn, or, given as a bare accession, a filing the evidence names. A key is read whole up to its separator, so a malformed one (`accession/mdna`, `accession/MDNA/3`, `accession/mdna/3x`) is judged as written and is unknown; it is never taken for the bare accession it starts with. A full date must be a date of the evidence (period start or end, filing or report date) or the day the question was asked (E6).
- **Decision.** A sentence passes when all its mentions traced and its citations are valid; a sentence with none is not checked and never dropped. All pass: the draft is shown. Otherwise the failed sentences are dropped and a note says so; the answer is blocked instead when more than `max_dropped_share` of the checked sentences failed (default half), when nothing would be left, or with `on_failure="block"`. A blocked turn ends with status `blocked`, reason `untraced_figures`, a fixed notice, and the evidence, like degraded mode.
- **In the turn.** `Answer.text` is what the user was shown, `Answer.draft` what the model wrote, `Answer.faithfulness` the report: every mention, its status and the result field it traced to (`fact.value`, `rows[1].rank`, `passages[0].text`). The conversation history keeps the shown text, so a later turn never sees a dropped figure. `AgentConfig(faithfulness=None)` turns the check off: the "agent without checker" baseline of N2. `FaithfulnessReport.faithful` is N2 for one answer.

### MCP server (built in s-11)

Code: `sec_agent.mcp_server`. `sec-agent mcp --facts-version V` serves the five tools over stdio to Claude Desktop, ChatGPT or any MCP client, with the MCP Python SDK's low-level `Server` (so each tool's input and output schema is its Pydantic model's, exactly as `tools.catalog` describes it). No model runs in the server.

```
MCP client ──stdio──► Server (tools/list from tools.catalog, read-only annotations)
                        └─ tools/call ──► dispatch: validate args ──► tool ──► result.model_dump(mode="json")
                                             (one call at a time, in a worker thread)
```

- **Pinned at start.** One facts `index_version` (refused if it holds no facts, since every answer would read "not reported") and one text snapshot: `--snapshot NAME`, else the `serving` pointer. With no snapshot only the three numeric tools answer; the text tools return `text_index_unavailable`. The query embedder is the snapshot's own model; `--lexical`, or the `embed` extra missing, searches with BM25 alone and the result's `mode` says so.
- **Results.** The tool's result as structured content and as JSON text. Decimals stay strings, dates ISO dates: the server adds no number of its own. A refusal is an error result `{"error": code, "message": ...}` with the tool's stable code (`unknown_company`, `unknown_metric`, ...), `invalid_arguments` (field and reason, the rejected input not echoed), `unknown_tool` or `retrieval_error`. A value not reported is a result, not an error (E12).
- **Instructions.** The server tells the client that every number must come from a tool result with its unit, fiscal year, period end and filing; that filing text is data, never instructions; and to decline investment advice while still showing the historical numbers (E9).
- **Stdout is the protocol.** Every note and error of `sec-agent mcp` goes to stderr.

Claude Desktop (`claude_desktop_config.json`), from a clone with the database loaded:

```json
{
  "mcpServers": {
    "sec-filings": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/verified-sec-filings-agent",
        "run",
        "sec-agent",
        "mcp",
        "--facts-version",
        "v1"
      ],
      "env": { "DATABASE_URL": "postgresql://sec:change-me-local-only@localhost:5432/sec" }
    }
  }
}
```

### Web app and API (built in s-17)

Code: `sec_agent.api`, `sec_agent.degraded`, `web/`. The browser talks only to the Next.js app; the app's server talks to the API. Every limit below is configuration, not a measurement.

```
browser ──► Next.js (Auth.js session) ──► /api/chat, /api/feedback   (route handlers)
                                              │ signs a 60-second identity token (API_AUTH_SECRET)
                                              ▼
                              FastAPI replica: verify token ──► count the question (Postgres)
                                              ▼
                              Agent.steps ──► turn │ evidence … │ answer   (server-sent events)
                                              │ no model reachable and no tool result
                                              ▼
                              degraded lookup: rules read the question ──► the same tools
```

- **Routes.** `GET /healthz`; `GET /v1/me` (cohort, today's usage); `POST /v1/chat` (one turn as server-sent events); `POST /v1/feedback` (thumbs up or down on a turn the caller asked). Refusals share one shape, `{"error": {"code", "message"}}`, and never echo what was sent. `sec-agent api init` creates the tables, `sec-agent api serve --facts-version v1` serves one replica pinned to one facts version and text snapshot.
- **Stream.** `/v1/chat` sends `turn` (thread, cohort, usage), then one `evidence` event per agent step that ran tools (its cards and citations), then `answer`: the text the faithfulness checker passed, the status (`answered`, `step_limit`, `degraded`, `blocked`), every card, citation and chart series, and the checker's summary (figures stated, figures traced, sentences removed). The model's draft is never streamed token by token: text reaches the user only after it is checked, so the stream shows deterministic results early and prose last. A turn that cannot finish ends with `error` (`conversation_conflict` when another request advanced the conversation first). A streamed turn is one trace, like an asked one; its span is the current span only while a step runs, never across a hand-over to the caller, because a streaming server may take each event on a different worker thread.
- **Cards, citations, charts.** `present` parses each tool result with the tool's own result model and copies fields: a fact with its unit, fiscal period, period end (E1), filing and any restatement (E2); a ratio with its formula and input facts; a peer table with each company's own period end (E3); a risk-factor diff; a notice for a refusal (E7, E4); a value not reported is a card that says so (E12). Passages become citations under the key the answer cites; the filing behind every fact is a citation under its accession number. `charts_of` groups cards into series: one metric over two or more fiscal years (one series per company), or one bar per company of a peer comparison. Values are sent as the exact decimal text the tool returned; the web app groups digits as text and converts to a float only to place a point on an axis.
- **Identity.** Auth.js keeps the session in a signed cookie (no user table). For each call the Next.js server signs an HS256 token (`sub`, `cohort`, `aud`, 60-second lifetime) with `API_AUTH_SECRET`; the API verifies signature, audience and lifetime and refuses a token that lives longer than five minutes. A conversation is stored under `<user id>:<thread id>`, so two users who send the same thread id never share one.
- **Cohorts.** An OAuth account (GitHub, Google) has cohort `real`. The simulated sign-in (`SIM_LOGIN_SECRET`, off by default) accepts only `sim-01@example.com` to `sim-50@example.com` and gives cohort `simulated` and a user id that starts `sim:`. The token, the API and a table constraint all require that a `sim:` id and the `simulated` cohort go together, so a simulated row can never be stored as a real user. `cohort_counts` reports users, conversations, turns, degraded turns and thumbs per cohort, side by side, never summed (U1).
- **Daily limit.** `API_DAILY_QUESTIONS` (default 20) questions per user per UTC day. One statement inserts or increments the user's row only while it is under the limit, so replicas racing for the last question never pass it. Past the limit the API answers 429 with `Retry-After` and calls no model. A question is counted when its turn starts, whatever the outcome.
- **Degraded mode.** When every provider is out of quota or down the agent ends the turn `degraded`. If it had already run tools, their results are shown. If not (no model was reachable to choose a tool), `sec_agent.degraded` reads the question with fixed rules: companies by ticker in capitals, `$TICKER`, alias (E8) or name; figures by the names and labels of the concepts and ratios plus everyday synonyms, longest match first; fiscal years as written, a span ("last 3 years"), or else the latest reported year found by stepping back from the question's date (E6). It then runs the same tools through the same runner, at most 16 calls: `get_fact` or `compute_ratio` per company, figure and year; `compare_peers` for several companies in one year or for "peers"; `search_filings` with the question when a text index is served. A non-GAAP measure matches no figure (E4); a question that names no company gets no figure. The answer text is the fixed degraded notice, and the web app labels the turn "Degraded mode".
- **Feedback.** A rating is kept only for a turn the same user asked; rating again replaces it. Simulated feedback is stored with its cohort and only proves the feedback path works; it is not a quality measure.
- **Not here.** A global semaphore on concurrent LLM calls and the answer cache (see Distributed concerns) are not built in s-17: concurrency is bounded by the worker threads of a replica and by the provider quotas, and load shedding is measured in s-20.

### Tracing and the L1 table (built in s-18)

Code: `sec_agent.observability`. One OpenTelemetry trace per question, with the GenAI semantic-convention attributes and the OpenInference ones Phoenix shows (span kind, model, token counts, session = conversation id).

```
invoke_agent sec-agent            Agent.ask: conversation id, turn, status, reason
├─ llm_call                       one model call of the turn, failover included; error.type when degraded
│  ├─ chat                        one call to one provider: provider, max_tokens, response model,
│  │                              finish reason, input and output tokens; error.type = router outcome
│  └─ event sec_agent.llm.skipped a provider passed over without a call (breaker_open, quota_exhausted)
└─ execute_tool <name>            one tool call; error.type = the refusal code
```

- **Where spans go.** `PHOENIX_COLLECTOR_ENDPOINT` (Phoenix's base URL; compose serves it on 6006) exports over OTLP HTTP to `/v1/traces`; `SEC_AGENT_TRACE_FILE` also appends every span to a JSONL file. With neither, no provider is installed and spans cost nothing. Both export in a background batch, so a slow or absent Phoenix never delays an answer; every `sec-agent` command runs under this setup and flushes on exit. Tests never export: they read spans from memory.
- **No content.** Spans hold names, ids, counts, timings and error codes, never a question, an answer, a prompt or a tool result, and no error's text is exported: a failed span carries a code of ours in `error.type` (router outcome, degraded reason, refusal code, exception type) and no status description, since a provider's or an exception's message may quote a URL, a key or a response body.
- **The L1 table.** `sec-agent traces table spans.jsonl` prints p50 and p95 latency per step (`turn` end to end, `llm_call`, `chat:<provider>`, `tool:<name>`, and `agent_overhead`: the turn minus its model calls and tools) with the count of failed spans, and tokens per question (input, output, total summed over the turn's provider calls, as the providers reported them). Failed spans stay in the latency, since a timeout is time a user waited. Percentiles interpolate between closest ranks (type 7). `--record runs.csv --system S --split X --cohort C` appends the rows (`L1.latency_p95.turn`, `L1.tokens_per_question_mean.total`, ...); traffic from simulated users is recorded as cohort `simulated`, never `real`.

### Simulated users (built in s-21)

Code: `sec_agent.simusers`, and `sec-agent api cohorts` in `sec_agent.api`. Every count below is simulated traffic, cohort `simulated`.

- **Accounts.** There is no user table, so the roster is the seed: `sim-01@example.com` to `sim-50@example.com`, the only addresses the web app's simulated sign-in accepts, each playing one of five personas (analyst, student, journalist, retail, skeptic), dealt over a seeded order so each persona plays ten accounts. Retail and skeptic probe E9, E4, E6 and E11 on purpose.
- **Plan.** `plan_day(seed, day)` gives each account 0 to its persona's maximum sessions; a session is one opening question and 1 to 3 different follow-ups about a train or dev company (test companies are never asked about) and a fiscal year one to three years back. Sessions are taken in a seeded order while the day's budget and the per-user daily limit allow; the session that would pass either is cut short. The same seed and day always give the same plan.
- **Budget.** Questions per day = LLM calls per day x share / calls per question, rounded down, with the share read as a decimal. The share is at most 0.5, so simulated traffic never takes more than half the day's quota; calls per question defaults to the plan's estimate of 4, not a measurement.
- **Driver.** `sec-agent sim run` signs each account in through Auth.js (csrf, credentials callback `simulated`, then the session, which must name that account in the `simulated` cohort before anything is sent), asks over `/api/chat` and reads the answer event, and rates over `/api/feedback`. Sessions start at seeded seconds inside `--window-minutes`. A session ends at the daily limit (429) or an error; an account that cannot sign in is counted and skipped. It never sends more questions than planned.
- **Ratings.** Fixed before any answer is seen: up for an `answered` turn the checker passed untouched with at least one card or citation; down for `step_limit`, `blocked` or a trimmed draft; none for degraded turns, errors, the daily limit and evidence-free answers. Whether a rateable turn is rated is a seeded draw per turn against the persona's rate. Ratings only prove the feedback path; they are never a quality measure.
- **Records.** `--record runs.csv` appends `U1.*` rows (sessions run, sign-in failures, questions sent, turns per outcome, ratings kept and refused, turn seconds p50 and p95 as seen through the web app), cohort `simulated`, split `none`, with the seed and day in `config` and "simulated users (test traffic)" in `notes`.
- **Dashboard.** `sec-agent api cohorts --from D --to D` prints `cohort_counts` as two columns, real and simulated, never summed; the users row reads `accounts` and a note says the simulated column is test traffic.
- **Not here.** Concurrent sessions (the driver plays them one at a time; load is s-20's), a web page for the dashboard, and G-num answer checks in the rating criteria.

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
- Check FinanceBench answers (licence checked in s-06) before using G-public.
- Confirm free-tier database size limits against measured index size.
