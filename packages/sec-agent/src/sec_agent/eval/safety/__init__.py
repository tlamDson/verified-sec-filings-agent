"""S1 safety eval: G-red items run through the agent with and without guardrails.

`planted` serves each item's simulated passages as `search_filings` results; `runner`
appends one `SafetyRecord` per item; `grade` decides by code whether an attack got what it
asked for and whether a benign question was refused; `report` turns records into rates
with Wilson intervals and runs.csv rows.
"""
