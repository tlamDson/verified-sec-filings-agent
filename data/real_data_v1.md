# Real data, build v1

What one local build put into the compose Postgres on 2026-11-13. Only the small derived
files are committed (the runs, the snapshot manifest and the G-ret pool). The database and
the raw SEC responses (`data/raw/`, git-ignored) are not. These counts describe the build.
They are not eval results, so they have no rows in `runs.csv`.

## Sources

- Companies: the 50 in `data/golden/company_split.json` (30 train, 10 dev, 10 test).
- XBRL: `companyfacts` for every CIK, written as facts snapshot `v1`.
- Text: every 10-K, 10-K/A, 10-Q and 10-Q/A with a period of report from FY2020 to FY2024
  (the default window of `sec-agent filings enqueue`). Fetched through the repository's
  rate-limited EDGAR client, with `SEC_USER_AGENT` taken from the environment.
- Chunks: index version `chunks-p1-t400-8462c38b` (parser 1, 400 tokens).
- Embeddings: `BAAI/bge-base-en-v1.5`, 768 dimensions, on a local GPU. Retrieval snapshot
  `v1`, content sha256 `6951c8e1bb9616f46005ef0a9dabf70b0b704d7461eaf98b7afae026a4a29ed7`,
  activated as `serving`.

## Counts

| What                                                                | Count   |
| ------------------------------------------------------------------- | ------- |
| Ingest jobs (50 companyfacts, 1,142 filings), all done, none failed | 1,192   |
| XBRL facts in `v1` (35 concepts, 50 companies)                      | 226,088 |
| Filings fetched                                                     | 1,142   |
| Filings with at least one section, in snapshot `v1`                 | 1,090   |
| Chunks in snapshot `v1`                                             | 62,753  |
| Chunks cut to the model's 512 input tokens when embedded            | 25      |
| G-ret questions run                                                 | 100     |
| G-ret pool items (top 20 of bm25, vector, hybrid, deduplicated)     | 3,485   |

The filings break down by form as follows:

| Form   | Filings | Companies | With no section found | Chunks |
| ------ | ------- | --------- | --------------------- | ------ |
| 10-K   | 292     | 49        | 6                     | 29,127 |
| 10-K/A | 11      | 3         | 10                    | 85     |
| 10-Q   | 834     | 49        | 32                    | 33,515 |
| 10-Q/A | 5       | 5         | 4                     | 26     |

By company split:

| Split | Companies | Facts   | Filings with chunks | Chunks |
| ----- | --------- | ------- | ------------------- | ------ |
| train | 30        | 132,774 | 643                 | 39,007 |
| dev   | 10        | 50,249  | 231                 | 12,687 |
| test  | 10        | 43,065  | 216                 | 11,059 |

Each question has between 22 and 50 chunks in the pool. 717 items were ranked in the top 20 by
all three systems, 1,081 by two and 1,687 by one. Pool items per test company range from 308
(WFC) to 405 (PANW).

## Known gaps

- ExxonMobil (XOM, train): the universe lists CIK 2115436, which is ExxonMobil Holdings
  Corporation, the holding company formed in 2025. It has no 10-K or 10-Q in the FY2020 to
  FY2024 window, so XOM has no chunks. It has only 140 XBRL facts, all ending in 2024-12-31
  or later. The filings from 2020 to 2024 are probably under the old registrant (CIK 34088, not checked here).
- bm25 returns 91 chunks rather than 100 for q091, because only 91 chunks share a term with it.

## Reproduce

```sh
docker compose up -d postgres
sec-agent jobs init && sec-agent xbrl init && sec-agent filings init && sec-agent index init
sec-agent xbrl enqueue --index-version v1 <50 CIKs>
sec-agent filings enqueue <50 CIKs>
sec-agent worker --drain
sec-agent index build --device cuda          # needs the `embed` extra
sec-agent index snapshot v1 && sec-agent index verify v1 && sec-agent index activate v1
sec-agent eval retrieval run --snapshot v1 --systems bm25,vector,hybrid --out-dir results/retrieval/v1
sec-agent golden pool --index-version chunks-p1-t400-8462c38b \
  --run results/retrieval/v1/bm25.run --run results/retrieval/v1/vector.run \
  --run results/retrieval/v1/hybrid.run
```
