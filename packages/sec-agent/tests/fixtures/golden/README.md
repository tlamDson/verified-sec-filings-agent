# Golden-set fixtures (simulated)

Every file here is **simulated data**, written by hand for tests. Nothing was downloaded,
and no question, label, answer or retrieval result in them is real.

| File                                           | Simulates                                                                   |
| ---------------------------------------------- | --------------------------------------------------------------------------- |
| `g_ret_questions.sim.jsonl`                    | Two G-ret questions about the simulated company `SIMW` (CIK 9999999999)     |
| `bm25.sim.run`, `vector.sim.run`, `hybrid.sim.run` | TREC runs of three retrieval systems over chunks of `filings/sim-10k.htm` |
| `financebench_open_source.sim.jsonl`           | Three records in the FinanceBench open-source format; questions marked SIMULATED |
| `financebench_document_information.sim.jsonl`  | The matching document records, with `example.com` links                     |

The FinanceBench-format files copy only the field names and value types of the real
dataset (checked on 2026-11-13); company names are real so the name-to-ticker mapping can be
tested, but every question, answer and passage is made up.
