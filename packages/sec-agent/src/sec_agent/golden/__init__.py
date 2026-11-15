"""Golden sets for evaluation, all built on one company-level split.

`universe` (the S&P 100 with SEC CIKs) -> `split` (seeded sample of 50, then 30 train,
10 dev, 10 test). Every golden set is split by company, never by question:

- `gnum`: numeric questions generated from XBRL facts, answers computed in code;
- `gret`: qualitative questions written by hand, pooled from retrieval runs, labelled 0/1/2;
- `public`: FinanceBench's open sample, loaded only once its licence and answers are checked.
"""
