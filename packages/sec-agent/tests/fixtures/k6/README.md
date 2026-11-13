# k6 summary fixtures (simulated)

Every file here is **simulated data**, written by hand for tests. k6 did not produce it and
no load test was run. It copies only the shape of k6's `--summary-export` JSON (Rate metrics
with `passes`, `fails` and `value`; Trends with percentiles; Counters with `count`) for the
custom metrics `infra/load/chat.js` emits. The numbers are made up and never reported.

| File               | Simulates                                                       |
| ------------------ | --------------------------------------------------------------- |
| `summary.sim.json` | A run where some turns failed, 3 conversations were interrupted and 1 of them did not resume, some degraded |
